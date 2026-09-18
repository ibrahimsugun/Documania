"""Arşive taşıma — etkin çıktı belgesini `Hazir/`'dan `Archive/<yyyy-mm>/`'e taşır (PRD 08.4.1;
K11, K16, R11).

Belge silinmez: kaynak `write_unique` ile hedefe yayınlanır (aynı adı zaten dolu bulursa K8'deki
gibi `-2`, `-3`… eki alır), yayın bittikten sonra kaynak silinir — bu gerçek bir **taşıma**dır
(K11), kopya bırakılmaz; belge çalışanın `Hazir/` klasöründen çıkar (§20.6 ikinci onay metni).
`documents.status` `archived`'e, `path` yeni göreli yola güncellenir; satır, kökeni
(`source_refs_json`, `plan_id`) ve sıra numarası değişmeden kalır (K18'deki gibi silinmez,
yeniden adlandırılmaz).

Yalnız `active` durumundaki belge arşivlenir: zaten arşivlenmiş ya da eski sürüm (`superseded`,
K18) belge `DocumentNotArchivableError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.db.models import Document, DocumentStatus, Event, utcnow
from app.events import EventType, record_event
from app.storage.atomic import iter_file_chunks, sha256_file, write_unique
from app.storage.layout import DataLayout


class DocumentNotFoundError(LookupError):
    """08.4.1: arşivlenecek belge kaydı yok."""


class DocumentNotArchivableError(ValueError):
    """08.4.1: belge `active` değil — zaten arşivlenmiş ya da eski sürüm (K18); hiçbir şey
    taşınmadı."""


@dataclass(frozen=True, slots=True)
class ArchivedDocument:
    """`archive_document` sonucu: arşivlenen belge satırı ve `ARCHIVED` olayı."""

    document: Document
    event: Event


def archive_document(
    session: Session,
    layout: DataLayout,
    document_id: int,
    *,
    actor: str,
    today: date | None = None,
) -> ArchivedDocument:
    """Etkin belgeyi `Archive/<yyyy-mm>/`'e taşır ve durumunu günceller (08.4.1; K11, K16).

    `actor` iki aşamalı onayı (K16, §20.6.1) tamamlamış kullanıcının adıdır; boşsa `ValueError`.
    `today` ay dizinini seçer, varsayılanı taşımanın yapıldığı gündür (UTC).

    Belge kaydı yoksa `DocumentNotFoundError`; `active` değilse (zaten arşivlenmiş ya da eski
    sürüm) `DocumentNotArchivableError` — hiçbir şey taşınmaz. Oturum commit edilmez. Aynı belgeyi
    eşzamanlı arşivleyen ikinci işlem satırın kilidinde bekler ve belgeyi arşivlenmiş görür.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    document = session.get(Document, document_id, with_for_update=True, populate_existing=True)
    if document is None:
        raise DocumentNotFoundError(f"Belge bulunamadı: {document_id}")
    if document.status != DocumentStatus.ACTIVE.value:
        raise DocumentNotArchivableError(
            f"Belge {document.id} arşivlenemez: durum {document.status!r} "
            "(yalnız etkin belge arşivlenir)"
        )

    source = layout.resolve(document.path)
    sha256 = sha256_file(source)
    directory = layout.archive_dir(today or utcnow().date())
    stored = write_unique(directory, source.name, iter_file_chunks(source), expected_sha256=sha256)
    source.unlink()

    document.path = layout.relative(stored.path)
    document.status = DocumentStatus.ARCHIVED.value
    session.flush()

    event = record_event(
        session,
        EventType.ARCHIVED,
        document_id=document.id,
        employee_id=document.employee_id,
        actor=actor,
        data={"document_id": document.id, "path": document.path},
    )
    return ArchivedDocument(document, event)
