"""Belgeyi başka çalışana taşıma — etkin çıktıyı bir çalışanın `Hazir/`'ından ötekinin `Hazir/`'ına
K8 adıyla taşır (PRD 10.8.2; K8, K10, K11, K16).

İzinli fiziksel işlemler yalnız **yeniden adlandırma** ve **taşıma**dır (K11): içerik bayt bayt
aynı kalır. Yeni ad yeni sahibin ad-soyadı ve türün `file_label`'ıyla K8 adıdır; o gövde yeni
sahibin `Hazir/`'ında doluysa sıra eki diskte seçilir (`-2`, `-3`; `write_sequenced`). Yayın
bittikten sonra eski dosya silinir — kopya bırakılmaz, belge eski sahibin klasöründen çıkar.

`documents` satırı aynı kalır (kimliği, kökeni `plan_id` + `source_refs_json`, türü, biçimi,
durumu); yalnız `employee_id`, `path` ve `sequence_no` güncellenir. Belgenin kaynak dosyaları
(Inbox orijinalleri) yeni sahibin `Alinan/` klasörüne kopyalanır (K10; aynı SHA-256 oradaysa
kopyalanmaz). Eski sahibin `Alinan/` kopyası silinmez (K16: silme yok) — aynı dosya o çalışanın
başka belgelerinin de kaynağı olabilir. `MANUAL_MOVE` kullanıcı adıyla loglanır; iki çalışan da
kimlikleriyle olaya girer, yol ve ad kişi adı taşıdığı için olaya girmez (CONVENTIONS §6).

Yalnız `active` belge taşınır: eski sürüm (K18: yeniden adlandırılmaz) ve arşivlenmiş belge
`DocumentNotMovableError`. Bütün denetimler diske dokunmadan önce yapılır. Çalışan profilleri
(`profil.md`) burada değil çağıranca yeniden üretilir (`app.profiles.write_profile`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Document, DocumentStatus, Employee, Event, KnownDocumentType, UploadFile
from app.events import EventType, record_event
from app.storage.archive import DocumentNotFoundError
from app.storage.atomic import iter_file_chunks, sha256_file, write_sequenced
from app.storage.layout import DataLayout
from app.storage.naming import document_stem, normalize_extension
from app.storage.received import ReceivedCopy, copy_to_received


class MoveTargetNotFoundError(LookupError):
    """10.8.2: belgenin taşınacağı çalışan kayıtlı değil."""


class DocumentNotMovableError(ValueError):
    """10.8.2: belge taşınamaz — etkin değil, zaten o çalışanın, dosyası ya da kaynağı yerinde
    değil; hiçbir şey taşınmadı."""


@dataclass(frozen=True, slots=True)
class MovedDocument:
    """`move_document` sonucu: taşınan belge satırı, eski ve yeni sahibi, Alinan kopyaları ve
    `MANUAL_MOVE` olayı."""

    document: Document
    previous_owner: Employee
    new_owner: Employee
    received: tuple[ReceivedCopy, ...]
    event: Event


@dataclass(frozen=True, slots=True)
class _Source:
    upload_file: UploadFile
    path: Path
    pages: list[int]


def move_document(
    session: Session,
    layout: DataLayout,
    document_id: int,
    employee_id: str,
    *,
    actor: str,
) -> MovedDocument:
    """Etkin belgeyi `employee_id` çalışanına taşır (10.8.2; K8, K11, K16).

    `actor` iki aşamalı onayı (K16, §20.6.1) tamamlamış kullanıcının adıdır; boşsa `ValueError`.
    Belge kaydı yoksa `DocumentNotFoundError`, çalışan yoksa `MoveTargetNotFoundError`; belge etkin
    değilse, zaten o çalışanınsa ya da dosyası veya kaynak orijinali yerinde değilse
    `DocumentNotMovableError` — hiçbir şey taşınmaz. Oturum commit edilmez. Aynı belgeyi eşzamanlı
    taşıyan ikinci işlem satırın kilidinde bekler ve belgeyi yeni sahibinde görür.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    document = session.get(Document, document_id, with_for_update=True, populate_existing=True)
    if document is None:
        raise DocumentNotFoundError(f"Belge bulunamadı: {document_id}")
    new_owner = session.get(Employee, employee_id)
    if new_owner is None:
        raise MoveTargetNotFoundError(f"Çalışan bulunamadı: {employee_id}")
    if document.status != DocumentStatus.ACTIVE.value:
        raise DocumentNotMovableError(
            f"Belge {document.id} taşınamaz: durum {document.status!r} "
            "(yalnız etkin belge başka çalışana taşınır)"
        )
    if document.employee_id == new_owner.id:
        raise DocumentNotMovableError(f"Belge {document.id} zaten {new_owner.id} çalışanının")
    previous_owner = session.get_one(Employee, document.employee_id)
    document_type = session.get_one(KnownDocumentType, document.type_slug)

    current = _current_file(layout, document)
    sources = _sources(session, layout, document)
    extension = _extension(document)

    layout.ensure_employee_tree(new_owner.folder_name)
    sha256 = sha256_file(current)
    stored = write_sequenced(
        layout.ready_dir(new_owner.folder_name),
        document_stem(new_owner.given_names, new_owner.surname, document_type.file_label),
        extension,
        iter_file_chunks(current),
        expected_sha256=sha256,
    )
    received = tuple(
        copy_to_received(
            layout, new_owner.folder_name, source.path, sha256=source.upload_file.sha256
        )
        for source in sources
    )
    current.unlink()

    document.employee_id = new_owner.id
    document.path = layout.relative(stored.path)
    document.sequence_no = stored.sequence_no
    session.flush()

    first = sources[0] if sources else None
    event = record_event(
        session,
        EventType.MANUAL_MOVE,
        upload_id=first.upload_file.upload_id if first is not None else None,
        file_id=first.upload_file.id if first is not None else None,
        page_index=first.pages[0] if first is not None and first.pages else None,
        document_id=document.id,
        employee_id=new_owner.id,
        actor=actor,
        data={
            "document_id": document.id,
            "from_employee_id": previous_owner.id,
            "to_employee_id": new_owner.id,
            "document_type_slug": document.type_slug,
            "sequence_no": stored.sequence_no,
            "sha256": sha256,
            "received": [
                {"file_id": source.upload_file.id, "copied": copy.copied}
                for source, copy in zip(sources, received, strict=True)
            ],
        },
    )
    return MovedDocument(document, previous_owner, new_owner, received, event)


def _current_file(layout: DataLayout, document: Document) -> Path:
    try:
        path = layout.resolve(document.path)
    except ValueError:
        raise DocumentNotMovableError(
            f"Belge {document.id} taşınamaz: kayıtlı yolu veri dizininin dışında"
        ) from None
    if not path.is_file():
        raise DocumentNotMovableError(f"Belge {document.id} taşınamaz: dosyası bulunamadı")
    return path


def _extension(document: Document) -> str:
    try:
        return normalize_extension(PurePosixPath(document.path).suffix)
    except ValueError:
        raise DocumentNotMovableError(
            f"Belge {document.id} taşınamaz: dosya adının uzantısı okunamadı"
        ) from None


def _reference(ref: Any) -> tuple[int, list[int]] | None:
    if not isinstance(ref, dict):
        return None
    file_id, pages = ref.get("file_id"), ref.get("pages", [])
    if isinstance(file_id, bool) or not isinstance(file_id, int):
        return None
    if not isinstance(pages, list) or not all(
        isinstance(page, int) and not isinstance(page, bool) for page in pages
    ):
        return None
    return file_id, pages


def _sources(session: Session, layout: DataLayout, document: Document) -> list[_Source]:
    """Belgenin köken kaydındaki kaynak dosyalar (tekrarsız, kayıt sırasıyla). Kayıt bozuksa ya da
    kaynak orijinal yüklemede kaydedilen SHA-256'yı taşımıyorsa (K10) `DocumentNotMovableError`:
    yeni sahibin `Alinan/`'ına doğrulanmamış dosya kopyalanmaz."""
    refs = document.source_refs_json
    if not isinstance(refs, list):
        raise DocumentNotMovableError(f"Belge {document.id} taşınamaz: köken kaydı bozuk")
    sources: list[_Source] = []
    seen: set[int] = set()
    for ref in refs:
        parsed = _reference(ref)
        if parsed is None:
            raise DocumentNotMovableError(f"Belge {document.id} taşınamaz: köken kaydı bozuk")
        file_id, pages = parsed
        if file_id in seen:
            continue
        seen.add(file_id)
        upload_file = session.get(UploadFile, file_id)
        if upload_file is None:
            raise DocumentNotMovableError(
                f"Belge {document.id} taşınamaz: kaynak dosya kaydı {file_id} yok"
            )
        try:
            path = layout.resolve(upload_file.stored_path)
        except ValueError:
            path = None
        if path is None or not path.is_file() or sha256_file(path) != upload_file.sha256:
            raise DocumentNotMovableError(
                f"Belge {document.id} taşınamaz: kaynak dosya {file_id} yüklemede kaydedilen "
                "SHA-256'yı taşımıyor (K10)"
            )
        sources.append(_Source(upload_file, path, pages))
    return sources
