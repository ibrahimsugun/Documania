"""Arşive taşıma — etkin çıktı belgesini `Hazir/`'dan `Archive/<yyyy-mm>/`'e taşır (PRD 08.4.1;
K11, K16, R11) — ve arşivden geri alma (PRD 10.5.10; PLAN.md §C90-e, §D61).

Belge silinmez: kaynak `write_unique` ile hedefe yayınlanır (aynı adı zaten dolu bulursa K8'deki
gibi `-2`, `-3`… eki alır), yayın bittikten sonra kaynak silinir — bu gerçek bir **taşıma**dır
(K11), kopya bırakılmaz; belge çalışanın `Hazir/` klasöründen çıkar (§20.6 ikinci onay metni).
`documents.status` `archived`'e, `path` yeni göreli yola güncellenir; satır, kökeni
(`source_refs_json`, `plan_id`) ve sıra numarası değişmeden kalır (K18'deki gibi silinmez,
yeniden adlandırılmaz).

Yalnız `active` durumundaki belge arşivlenir: zaten arşivlenmiş ya da eski sürüm (`superseded`,
K18) belge `DocumentNotArchivableError`.

Arşivlenen belge paket kalemi karşılamaz: sahibinin belge paketleri aynı işlemde yenilenir
(14.2.2; `app.groups.refresh_employee_packages`, tamamlanmış paket açığa döner). Belgenin durumu ve
yolu değiştiği için sahibinin `profil.md`'si son adım olarak yeniden üretilir (09.1.1;
`app.profiles.write_profile`, yalnız veritabanından, K17). Oturum commit edilmediği için
çağıran commit'ten önce işlemi geri alırsa `profil.md` bir sonraki yeniden üretime kadar bayat
kalır (PLAN.md §D31); dosya taşıması zaten geri alınmaz.

**Arşivden geri alma** (`unarchive_document`) yalnız `archived` belgeyi `Archive/<yyyy-mm>/`'den
sahibinin `Hazir/`'ına taşır. Ad K8 adıdır: sahibin **bugünkü** adı ve türün `file_label`'ı
(`document_stem`) ile belgenin sıra eki; o ek `Hazir/`'da doluysa (arada aynı türden yeni belge
geldiyse) ilk boş ek seçilir ve `documents.sequence_no` güncellenir (`write_sequenced`). Sahip,
birleştirmede (10.5.9) kalan kayıttır: `employee_id` zaten ona bağlanmıştır, belge onun
klasörüne döner. Birleşmiş kayda geri alma yapılmaz. İçerik bayt bayt aynı kalır (K11); dosya önce
hedefe yayınlanır, satır ve olay yazılır, en son arşivdeki ad kaldırılır — bir adım düşerse
yayınlanan kopya kaldırılır, arşivdeki dosya yerinde kalır, oturumu geri almak çağıranındır.
Köken (`source_refs_json`, `plan_id`) değişmez. Boş kalan `Archive/<yyyy-mm>/` dizini silinmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeStatus,
    Event,
    KnownDocumentType,
    utcnow,
)
from app.events import EventType, record_event
from app.storage.atomic import iter_file_chunks, sha256_file, write_sequenced, write_unique
from app.storage.layout import DataLayout
from app.storage.naming import document_stem, normalize_extension


class DocumentNotFoundError(LookupError):
    """08.4.1: arşivlenecek belge kaydı yok."""


class DocumentNotArchivableError(ValueError):
    """08.4.1: belge `active` değil — zaten arşivlenmiş ya da eski sürüm (K18); hiçbir şey
    taşınmadı."""


class DocumentNotRestorableError(ValueError):
    """10.5.10: belge arşivden geri alınamaz — arşivde değil (etkin ya da eski sürüm, K18), sahibi
    birleştirilmiş ya da dosyası arşivde yok; hiçbir şey taşınmadı."""


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
    sürüm) `DocumentNotArchivableError` — hiçbir şey taşınmaz. Başarıdan sonra belgenin sahibinin
    belge paketleri yenilenir (14.2.2) ve `profil.md`'si yeniden üretilir (09.1.1). Oturum commit
    edilmez. Aynı belgeyi eşzamanlı arşivleyen ikinci işlem satırın kilidinde bekler ve belgeyi
    arşivlenmiş görür.
    """
    # `app.profiles` ve `app.groups` `app.storage`'ı içe aktarır; üst düzeyde içe aktarmak paket
    # başlatmada döngü kurar.
    from app.groups import refresh_employee_packages
    from app.profiles import write_profile

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
    # 14.2.2: arşivdeki belge kalem karşılamaz; paket açığa dönebilir.
    refresh_employee_packages(session, document.employee_id, actor=actor)
    # 09.1.1: profil belgenin yeni durumunu ve dosya adını gösterir; son adım.
    write_profile(session, layout, session.get_one(Employee, document.employee_id))
    return ArchivedDocument(document, event)


@dataclass(frozen=True, slots=True)
class UnarchivedDocument:
    """`unarchive_document` sonucu: geri alınan belge satırı, arşivdeki eski göreli yolu ve sıra
    eki, `UNARCHIVED` olayı."""

    document: Document
    previous_path: str
    previous_sequence_no: int
    event: Event


def unarchive_document(
    session: Session,
    layout: DataLayout,
    document_id: int,
    *,
    actor: str,
) -> UnarchivedDocument:
    """Arşivdeki belgeyi sahibinin `Hazir/`'ına K8 adıyla taşır ve etkin yapar (10.5.10; K8, K11,
    K16, §D61).

    `actor` iki aşamalı onayı tamamlamış kullanıcının adıdır; boşsa `ValueError`. Belge kaydı
    yoksa `DocumentNotFoundError`; arşivde değilse, sahibi birleştirilmişse ya da dosyası arşivde
    yoksa (adı uzantısız, yolu veri dizininin dışında) `DocumentNotRestorableError` — hiçbir şey
    taşınmaz. Başarıdan sonra
    sahibinin belge paketleri yenilenir (14.2.2) ve `profil.md`'si yeniden üretilir (09.1.1).
    Oturum commit edilmez.
    """
    # `app.profiles` ve `app.groups` `app.storage`'ı içe aktarır (bkz. `archive_document`).
    from app.groups import refresh_employee_packages
    from app.profiles import write_profile

    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    document = session.get(Document, document_id, with_for_update=True, populate_existing=True)
    if document is None:
        raise DocumentNotFoundError(f"Belge bulunamadı: {document_id}")
    if document.status != DocumentStatus.ARCHIVED.value:
        raise DocumentNotRestorableError(
            f"Belge {document.id} arşivden geri alınamaz: durum {document.status!r} "
            "(yalnız arşivdeki belge geri alınır)"
        )
    owner = session.get_one(Employee, document.employee_id)
    if owner.status == EmployeeStatus.MERGED.value:
        raise DocumentNotRestorableError(
            f"Belge {document.id} geri alınamaz: {owner.id} başka bir kayıtla birleştirildi "
            "(10.5.9)"
        )
    document_type = session.get_one(KnownDocumentType, document.type_slug)
    source = _archived_file(layout, document)
    try:
        extension = normalize_extension(source.suffix)
    except ValueError:
        raise DocumentNotRestorableError(
            f"Belge {document.id} geri alınamaz: dosya adının uzantısı okunamadı"
        ) from None

    previous_path, previous_sequence_no = document.path, document.sequence_no
    layout.ensure_employee_tree(owner.folder_name)
    stored = write_sequenced(
        layout.ready_dir(owner.folder_name),
        document_stem(owner.given_names, owner.surname, document_type.file_label),
        extension,
        iter_file_chunks(source),
        expected_sha256=sha256_file(source),
        preferred_sequence_no=max(previous_sequence_no, 1),
    )
    try:
        document.path = layout.relative(stored.path)
        document.status = DocumentStatus.ACTIVE.value
        document.sequence_no = stored.sequence_no
        session.flush()
        event = record_event(
            session,
            EventType.UNARCHIVED,
            document_id=document.id,
            employee_id=owner.id,
            actor=actor,
            data={
                "document_id": document.id,
                "from": previous_path,
                "to": document.path,
                "previous_sequence_no": previous_sequence_no,
                "sequence_no": stored.sequence_no,
            },
        )
        # 14.2.2: geri dönen etkin belge paket kalemini yeniden karşılayabilir.
        refresh_employee_packages(session, owner.id, actor=actor)
        source.unlink()
    except BaseException:
        # Arşivdeki dosya yerinde; yayınlanan kopya kaldırılır, oturumu geri almak çağıranındır.
        stored.path.unlink(missing_ok=True)
        raise
    # 09.1.1: profil belgenin yeni durumunu ve dosya adını gösterir; son adım.
    write_profile(session, layout, owner)
    return UnarchivedDocument(document, previous_path, previous_sequence_no, event)


def _archived_file(layout: DataLayout, document: Document) -> Path:
    try:
        path = layout.resolve(document.path)
    except ValueError:
        raise DocumentNotRestorableError(
            f"Belge {document.id} geri alınamaz: kayıtlı yolu veri dizininin dışında"
        ) from None
    if not path.is_file():
        raise DocumentNotRestorableError(
            f"Belge {document.id} geri alınamaz: dosyası arşivde bulunamadı"
        )
    return path
