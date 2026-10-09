"""Uygulayıcı — planın seçtiği fiziksel işlemler (PRD 07.x, §20.5).

Bu modül planlayıcının (`app/pipeline/plan.py`) `operation` alanına yazdığı kararı yürütür;
işlemi yeniden seçmez ya da izinlerini yeniden denetlemez (06.2.1–06.4.1 planlayıcının işidir).
Tek istisna K3'tür: `merge` Direkt Belge türünde çalışmaz (07.3.1) — plan dondurulduktan sonra
tür Direkt Belge yapılmış olsa bile belge başka kaynaklardan kurulmaz.
Ortak kural (K11): hiçbir işlem içeriği üretmez, kırpmaz ya da değiştirmez.

İşlemler: `passthrough` (07.1.1), `extract` (07.2.1), `merge` (07.3.1), `wrap_image` (07.4.1),
`extract_image` (07.5.1), `render_image` (07.6.1). `execute_<işlem>` işlevleri yalnız işlemin
çekirdeğidir: verilen hedefe yazar, veritabanına ve olay logına dokunmaz.

**Ortak çıktı yazma (07.7.1, 07.7.2; §20.5).** `execute_ready_item` planın tek `hazir` öğesini
uygular. Çekirdeği `execute_item`'dır: kaynak ve köken plan öğesinden, sahip, tür, işlem ve hedef
ad karardan (`ItemDecision`) gelir — `hazir` öğede karar planın kendisidir, kuyruk öğesinde
insanın atamasıdır (08.2.1, `app.pipeline.route.assign_queue_item`). Adımlar ikisinde de aynıdır:

1. Öğenin çalışanı, belge türü ve kaynak dosyaları veritabanından bulunur; dosya planın partisinin
   olmalıdır (`PlanItemReferenceError`). Inbox'taki her kaynağın SHA-256'sı yüklemede kaydedilenle
   aynı olmalıdır (K10, `SourceIntegrityError`). İkisi de hiçbir şey yazılmadan reddeder.
2. İşlem plandaki `operation`'dır, yeniden seçilmez; `merge`'ün Direkt Belge bekçisi türün güncel
   `direct` bayrağıdır. Çıktı çalışanın `Hazir/` klasörüne planın `target_name`'iyle **atomik**
   yazılır (00.4.4): gövde doluysa K8 sıra eki diskte seçilir (`-2`, `-3`; `write_sequenced`),
   `extract_image` uzantıyı gerçek biçimden alır (§20.5). İşlem hatası olduğu gibi yükselir; hiçbir
   çıktı, kopya, satır ya da olay kalmaz — kuyruğa çevirmek çağıranındır (08.1, 09.2). Şifreli
   kaynağın sayfalarını kopyalayamayan `extract`/`merge`'ün hatası `EncryptedSourceError`'dır:
   `execute_plan` bu öğeyi Unreadable'a yönlendirir, öbür hatalar uygulamayı durdurur (08.1.3).
3. Çıktı yayınlandıktan sonra (belge çözüldü, K10) her kaynak dosya `sources` sırasıyla çalışanın
   `Alinan/` klasörüne kopyalanır; aynı SHA-256 orada varsa tekrar kopyalanmaz (`copy_to_received`).
   Aynı çalışana yazan uygulamalar (idempotenlik denetimi, çıktı, kopya) PostgreSQL'de çalışan
   başına işlem ömürlü advisory kilitle sıraya girer; SQLite işlemi `BEGIN IMMEDIATE` ile yazma
   kilidini zaten tutar.
4. `documents` satırı (`active`) yazılır: çalışan, tür, veri köküne göreli yol, gerçek biçim, sıra
   numarası, plan kimliği ve köken — `source_refs_json` öğenin `sources`'udur (`file_id` ve 0
   tabanlı `pages`; bütün dosyada `[]`), sırası korunur (K15, R13).
5. İşlemin §8.3 olayı (`PAGE_EXTRACTED`, `PAGES_MERGED`, `IMAGE_WRAPPED`, `IMAGE_EXTRACTED`,
   `IMAGE_RENDERED`; `passthrough`'un türü yok) ve `OUTPUT_SAVED` yazılır. İkisi de partinin,
   ilk kaynağın dosyası ve ilk sayfasıyla, `document_id` ve `employee_id` sütunlarıyla; veri köken
   bilgisidir — `item_id`, `plan_id`, `sources`; `OUTPUT_SAVED` ayrıca tür, işlem, biçim, sıra
   numarası, çıktının SHA-256'sı ve kaynak başına Alinan sonucu (`file_id`, `copied`). Mesaj yok;
   yol ve ad kişi adı taşıdığı için olaya girmez (CONVENTIONS §6).

Oturum commit edilmez. Dosya sistemi işleme bağlı değildir: işlem geri alınırsa yayınlanan çıktı ve
kopya diskte kalır.

**İdempotenlik (07.8.1, S18).** Aynı plan ikinci kez uygulanınca ikinci dosya üretilmez:

- Öğe, planın kimliği ve kaynaklarıyla tanınır: `documents.plan_id` planın, `source_refs_json`
  öğenin `sources`'u olan satır o öğenin çıktısıdır (`executed_document`). Plan bir sayfayı en
  fazla bir öğeye bağladığı için (`PlanDocument`) bu eşleşme tekildir; satırın durumu ve sahibi
  sonradan değişmiş olabilir (eski sürüm, arşiv, başka çalışana taşıma — K16, K18), yine o öğenin
  çıktısıdır. Böyle satır varsa öğe yeniden uygulanmaz: kaynak okunmaz, işlem yürümez, diske ve
  `documents`'a hiçbir şey yazılmaz; `OUTPUT_SKIPPED` o satırla loglanır ve satır döner. İK'nın
  kalıcı sildiği çıktı (`deleted`, 10.5.12) da böyle atlanır — silinen belge yeniden üretilmez —
  ve olayın verisi `reason: deleted` taşır (`SKIPPED_DELETED`).
- Uygulama geri alınmışsa (işlem commit edilmeden öldü ya da geri alındı) çıktı diskte kalmış,
  satırı yoktur. Yeniden uygulamada işlem yürür; aynı gövdeyle ve aynı SHA-256'yla `Hazir/`'da
  duran ve hiçbir `documents` satırının göstermediği dosya varsa yeni dosya yazılmaz, o dosya
  çıktı olarak kaydedilir (`find_sequenced`) — Alinan tekilliği gibi doğruluk kaynağı disktir.
  Bu yüzden işlemlerin çıktısı aynı girdiden aynı baytlardır; `wrap_image` tarih ve rastgele
  kimlik taşımasın diye img2pdf'in kendi yazıcısıyla ve tarihsiz sarılır. Başka bir satırın
  gösterdiği dosya — başka öğenin ya da eski sürümün çıktısı, içeriği aynı olsa da — benimsenmez;
  o durumda K8 eki yine diskte seçilir.
- Denetim ile yayın aynı çalışan kilidinin altındadır (madde 3): aynı öğeyi eşzamanlı uygulayan
  ikinci işlem ilki commit edilince onun satırını görür.
"""

from __future__ import annotations

import zlib
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentStatus, Employee, KnownDocumentType, Plan, UploadFile
from app.events import EventType, record_event
from app.pipeline.plan import Operation, PlanItem, Route
from app.storage import (
    ContentMismatchError,
    DataLayout,
    StoredFile,
    copy_file,
    copy_to_received,
    find_sequenced,
    iter_file_chunks,
    sha256_bytes,
    sha256_file,
    split_document_filename,
    write_sequenced,
)

from .execute_errors import (
    EXECUTION_ERRORS,
    DirectDocumentMergeError,
    EncryptedSourceError,
    ExtractEncryptedSourceError,
    ExtractImageIntegrityError,
    ExtractImageSourceError,
    ExtractIntegrityError,
    ExtractSourceError,
    MergeEncryptedSourceError,
    MergeIntegrityError,
    MergeSourceError,
    PassthroughIntegrityError,
    PdfProtection,
    PlanItemReferenceError,
    RenderImageSourceError,
    SourceIntegrityError,
    WrapImageSourceError,
)
from .execute_image_utils import (
    _IMAGE_WRAP_ERRORS,
    _wrap_image_to_pdf,
)
from .execute_images import (
    _EXTRACTED_IMAGE_KINDS,
    _PIXMAP_MODES,
    _extract_embedded_image,
    _extract_image_output,
    _png_matches_pixels,
    _render_image_output,
    _wrap_image_output,
    execute_extract_image,
    execute_render_image,
    execute_wrap_image,
)
from .execute_pdf import (
    _copy_pages,
    _extract_output,
    _file_kind,
    _merge_output,
    _merge_source_pdf,
    _open_pdf,
    _page_selection,
    _PdfPages,
    _read_pdf,
    _verify_pages,
    execute_extract,
    execute_merge,
)
from .execute_types import (
    ExecutedItem,
    ItemDecision,
    MergeSource,
    _ItemSource,
    _ReadyOutput,
)


def execute_passthrough(source: Path, destination: Path) -> StoredFile:
    """Kaynak dosyayı hedefe bayt bayt kopyalar (07.1.1, §20.5).

    Yeniden yazma, yeniden kaydetme ya da kütüphaneden geçirme yoktur: `copy_file` kaynağı
    olduğu gibi okuyup atomik olarak yayınlar (K10, K11). Doğrulama: yayınlanan dosyanın
    SHA-256'sı kaynağınkine **eşit** olmalıdır; değilse `PassthroughIntegrityError`.
    """
    expected_sha256 = sha256_file(source)
    return _verified_passthrough(copy_file(source, destination), expected_sha256)


def _verified_passthrough(stored: StoredFile, expected_sha256: str) -> StoredFile:
    if stored.sha256 != expected_sha256:
        raise PassthroughIntegrityError(
            f"passthrough bütünlük hatası: kaynak {expected_sha256}, çıktı {stored.sha256}"
        )
    return stored


_OPERATION_EVENTS: dict[Operation, EventType] = {
    Operation.EXTRACT: EventType.PAGE_EXTRACTED,
    Operation.MERGE: EventType.PAGES_MERGED,
    Operation.WRAP_IMAGE: EventType.IMAGE_WRAPPED,
    Operation.EXTRACT_IMAGE: EventType.IMAGE_EXTRACTED,
    Operation.RENDER_IMAGE: EventType.IMAGE_RENDERED,
}

_EMPLOYEE_LOCK_NAMESPACE = "belgeee.employees.outputs"
# `OUTPUT_SKIPPED` verisinin `reason`'ı: öğenin çıktısı kalıcı silinmiş (10.5.12, PLAN.md §D110 c).
SKIPPED_DELETED = "deleted"


def execute_ready_item(
    session: Session,
    layout: DataLayout,
    plan: Plan,
    item: PlanItem,
    *,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
) -> ExecutedItem:
    """Planın `hazir` öğesini uygular: çıktıyı `Hazir/`'a atomik yazar, kökenini kaydeder ve
    kaynakları `Alinan/`'a kopyalar (07.7.1, 07.7.2; §20.5). Sözleşmesi modül açıklamasındadır.

    İdempotenttir (07.8.1): öğe bu planla daha önce uygulanmışsa (`executed_document`) kaynak
    okunmaz, hiçbir şey yazılmaz; `OUTPUT_SKIPPED` loglanır ve o uygulamanın satırı döner
    (`ExecutedItem.applied` yanlış). Geri alınmış bir uygulamadan diskte kalan aynı çıktı ikinci
    kez yazılmaz, kaydedilir.

    `item` `plan`'ın doğrulanmış (`read_plan`) öğesidir. `render_image_dpi` ve
    `render_image_jpeg_quality` `render_image` işleminin yapılandırma değerleridir
    (`Settings.render_image_dpi`, `Settings.render_image_jpeg_quality`).

    `hazir` olmayan ya da türsüz öğe, tek kaynaklı işlemde (`merge` dışındakiler) birden çok kaynak
    ve `extract_image`/`render_image`'da tek olmayan sayfa `ValueError`. Bunlarda, kayıt ve kaynak
    hatalarında ve işlem hatalarında (`passthrough`'un bütünlük hatası dahil, yayından önce
    denetlenir) hiçbir şey yazılmaz. Oturum commit edilmez.
    """
    operation, target_name = item.operation, item.target_name
    employee_id, document_type_slug = item.employee.employee_id, item.document_type_slug
    if (
        item.route is not Route.READY
        or document_type_slug is None
        or operation is None
        or target_name is None
        or employee_id is None
    ):
        raise ValueError("Yalnız çalışanı, türü, işlemi ve hedefi olan hazir öğe uygulanır")
    return execute_item(
        session,
        layout,
        plan,
        item,
        ItemDecision(employee_id, document_type_slug, operation, target_name),
        render_image_dpi=render_image_dpi,
        render_image_jpeg_quality=render_image_jpeg_quality,
    )


def execute_item(
    session: Session,
    layout: DataLayout,
    plan: Plan,
    item: PlanItem,
    decision: ItemDecision,
    *,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
) -> ExecutedItem:
    """`plan`'ın öğesini `decision`'la uygular — `execute_ready_item`'ın çekirdeği (07.7, 07.8).

    Kaynaklar (`item.sources`) ve köken (`item_id`, `plan.id`) plandan, sahip, tür, işlem ve hedef
    ad `decision`'dan gelir; öğenin rotasına bakılmaz — kararın doğruluğu çağıranındır
    (`execute_ready_item` planın `hazir` öğesi, 08.2.1 insanın ataması). Sözleşme, idempotenlik ve
    hatalar `execute_ready_item`'la aynıdır. Oturum commit edilmez.
    """
    operation, target_name = decision.operation, decision.target_name
    employee = session.get(Employee, decision.employee_id)
    if employee is None:
        raise PlanItemReferenceError(f"{item.item_id} öğesinin çalışanı kayıtlı değil")
    document_type = session.get(KnownDocumentType, decision.document_type_slug)
    if document_type is None:
        raise PlanItemReferenceError(f"{item.item_id} öğesinin belge türü katalogda yok")

    _lock_employee_outputs(session, employee.id)
    source_refs = _source_refs(item)
    first = item.sources[0]
    origin = {
        "upload_id": plan.upload_id,
        "file_id": first.file_id,
        "page_index": first.pages[0] if first.pages else None,
    }
    provenance = {"item_id": item.item_id, "plan_id": plan.id, "sources": source_refs}
    existing = executed_document(session, plan, item)
    if existing is not None:
        # 10.5.12 (K9, §D110 c): İK'nın kalıcı sildiği çıktı yeniden üretilmez; gerekçesi `deleted`.
        deleted = existing.status == DocumentStatus.DELETED.value
        record_event(
            session,
            EventType.OUTPUT_SKIPPED,
            **origin,
            document_id=existing.id,
            employee_id=existing.employee_id,
            data={**provenance, "reason": SKIPPED_DELETED} if deleted else provenance,
        )
        return ExecutedItem(existing, None, ())

    sources = _item_sources(session, layout, plan, item)
    ready = _ready_output(
        operation,
        target_name,
        sources,
        direct=document_type.direct,
        render_image_dpi=render_image_dpi,
        render_image_jpeg_quality=render_image_jpeg_quality,
    )
    output = _publish_ready_output(
        session, layout, ready, directory=layout.ready_dir(employee.folder_name)
    )
    received = tuple(
        copy_to_received(layout, employee.folder_name, source.path, sha256=source.sha256)
        for source in sources
    )

    output_format = output.path.suffix.removeprefix(".")
    document = Document(
        employee_id=employee.id,
        type_slug=document_type.slug,
        path=layout.relative(output.path),
        format=output_format,
        sequence_no=output.sequence_no,
        plan_id=plan.id,
        source_refs_json=source_refs,
        status=DocumentStatus.ACTIVE.value,
    )
    session.add(document)
    session.flush()

    operation_event = _OPERATION_EVENTS.get(operation)
    if operation_event is not None:
        record_event(
            session,
            operation_event,
            **origin,
            document_id=document.id,
            employee_id=employee.id,
            data=provenance,
        )
    record_event(
        session,
        EventType.OUTPUT_SAVED,
        **origin,
        document_id=document.id,
        employee_id=employee.id,
        data={
            **provenance,
            "document_type_slug": document_type.slug,
            "operation": operation.value,
            "format": output_format,
            "sequence_no": output.sequence_no,
            "sha256": output.sha256,
            "received": [
                {"file_id": source.file_id, "copied": received_copy.copied}
                for source, received_copy in zip(item.sources, received, strict=True)
            ],
        },
    )
    return ExecutedItem(document, output, received)


def executed_document(session: Session, plan: Plan, item: PlanItem) -> Document | None:
    """Öğenin bu planla önceki uygulamasının çıktı satırı; uygulanmamışsa `None` (07.8.1).

    Satır planın kimliği (`documents.plan_id`) ve öğenin kaynaklarıyla (`source_refs_json`) bulunur;
    plan bir sayfayı en fazla bir öğeye bağladığı için eşleşme tekildir. Satırın durumuna ve
    sahibine bakılmaz: eski sürüm, arşivlenmiş ya da başka çalışana taşınmış çıktı da öğenin
    uygulandığını gösterir. `item` `plan`'ın öğesidir.
    """
    source_refs = _source_refs(item)
    documents = session.scalars(
        select(Document).where(Document.plan_id == plan.id).order_by(Document.id)
    )
    return next(
        (document for document in documents if document.source_refs_json == source_refs), None
    )


def _source_refs(item: PlanItem) -> list[dict[str, object]]:
    # K15 köken: öğenin `sources`'u olduğu gibi — `file_id`, 0 tabanlı `pages`, plan sırası.
    return [source.model_dump(mode="json") for source in item.sources]


def _item_sources(
    session: Session, layout: DataLayout, plan: Plan, item: PlanItem
) -> list[_ItemSource]:
    files: list[UploadFile] = []
    for position, source in enumerate(item.sources):
        upload_file = session.get(UploadFile, source.file_id)
        if upload_file is None or upload_file.upload_id != plan.upload_id:
            raise PlanItemReferenceError(
                f"{item.item_id} öğesinin sources[{position}] dosyası planın partisinde yok"
            )
        files.append(upload_file)
    sources: list[_ItemSource] = []
    for position, (source, upload_file) in enumerate(zip(item.sources, files, strict=True)):
        path = layout.resolve(upload_file.stored_path)
        if sha256_file(path) != upload_file.sha256:
            raise SourceIntegrityError(
                f"{item.item_id} öğesinin sources[{position}] kaynağı yüklemede kaydedilen "
                "SHA-256'yı taşımıyor (K10)"
            )
        sources.append(_ItemSource(path, source.pages, upload_file.sha256))
    return sources


def _lock_employee_outputs(session: Session, employee_id: str) -> None:
    # İdempotenlik denetimi (07.8.1) ile çıktının yayını ve `copy_to_received`'ın hash taraması ile
    # yayını arasına aynı çalışana yazan başka işlem girmesin; aynı öğeyi eşzamanlı uygulayan ikinci
    # işlem ilkinin satırını görür. SQLite işlemi `BEGIN IMMEDIATE` ile yazma kilidini zaten baştan
    # tutar.
    if session.get_bind().dialect.name == "postgresql":
        key = zlib.crc32(f"{_EMPLOYEE_LOCK_NAMESPACE}.{employee_id}".encode())
        session.execute(select(func.pg_advisory_xact_lock(key)))


def _ready_output(
    operation: Operation,
    target_name: str,
    sources: Sequence[_ItemSource],
    *,
    direct: bool,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
) -> _ReadyOutput:
    """İşlemi yürütür ve çıktısını planın adıyla yayına hazırlar; diske yazmaz."""
    stem, extension = split_document_filename(target_name)
    if operation is Operation.MERGE:
        merged = _merge_output(
            [MergeSource(source.path, source.pages) for source in sources], direct=direct
        )
        return _in_memory(stem, extension, merged)
    if len(sources) != 1:
        raise ValueError(f"{operation.value} tek kaynak ister: {len(sources)} kaynak")
    (source,) = sources
    if operation is Operation.PASSTHROUGH:
        # Kaynak belleğe alınmaz, akışla kopyalanır; içeriği yüklemede kaydedilen ve az önce
        # doğrulanan hash'tir.
        return _ReadyOutput(
            stem,
            extension,
            iter_file_chunks(source.path),
            sha256=source.sha256,
            size=source.path.stat().st_size,
            expected_sha256=source.sha256,
        )
    if operation is Operation.EXTRACT:
        return _in_memory(stem, extension, _extract_output(source.path, source.pages))
    if operation is Operation.WRAP_IMAGE:
        return _in_memory(stem, extension, _wrap_image_output(source.path))
    if len(source.pages) != 1:
        raise ValueError(f"{operation.value} tek sayfa ister: {len(source.pages)} sayfa")
    (page,) = source.pages
    if operation is Operation.EXTRACT_IMAGE:
        image, kind = _extract_image_output(source.path, page)
        return _in_memory(stem, kind.value, image)
    rendered = _render_image_output(
        source.path, page, dpi=render_image_dpi, jpeg_quality=render_image_jpeg_quality
    )
    return _in_memory(stem, extension, rendered)


def _in_memory(stem: str, extension: str, content: bytes) -> _ReadyOutput:
    return _ReadyOutput(stem, extension, content, sha256=sha256_bytes(content), size=len(content))


def _publish_ready_output(
    session: Session, layout: DataLayout, output: _ReadyOutput, *, directory: Path
) -> StoredFile:
    """Çıktıyı `directory`'ye planın adıyla ve K8 sıra ekiyle atomik yayınlar.

    Aynı içerik bu gövdeyle diskte duruyor ve hiçbir `documents` satırı onu göstermiyorsa — geri
    alınmış bir uygulamanın çıktısı — yeni dosya yazılmaz, o dosya döner (07.8.1).
    """
    for candidate in find_sequenced(
        directory, output.stem, output.extension, sha256=output.sha256, size=output.size
    ):
        if not _is_recorded(session, layout, candidate.path):
            return candidate
    try:
        return write_sequenced(
            directory,
            output.stem,
            output.extension,
            output.content,
            expected_sha256=output.expected_sha256,
        )
    except ContentMismatchError as exc:
        # Beklenen hash'i yalnız `passthrough` verir.
        raise PassthroughIntegrityError(f"passthrough bütünlük hatası: {exc}") from exc


def _is_recorded(session: Session, layout: DataLayout, path: Path) -> bool:
    recorded = select(Document.id).where(Document.path == layout.relative(path)).limit(1)
    return session.scalar(recorded) is not None


__all__ = [
    "DirectDocumentMergeError",
    "EXECUTION_ERRORS",
    "EncryptedSourceError",
    "ExecutedItem",
    "ExtractEncryptedSourceError",
    "ExtractImageIntegrityError",
    "ExtractImageSourceError",
    "ExtractIntegrityError",
    "ExtractSourceError",
    "ItemDecision",
    "MergeEncryptedSourceError",
    "MergeIntegrityError",
    "MergeSource",
    "MergeSourceError",
    "PassthroughIntegrityError",
    "PdfProtection",
    "PlanItemReferenceError",
    "RenderImageSourceError",
    "SKIPPED_DELETED",
    "SourceIntegrityError",
    "WrapImageSourceError",
    "_EMPLOYEE_LOCK_NAMESPACE",
    "_EXTRACTED_IMAGE_KINDS",
    "_IMAGE_WRAP_ERRORS",
    "_ItemSource",
    "_OPERATION_EVENTS",
    "_PIXMAP_MODES",
    "_PdfPages",
    "_ReadyOutput",
    "_copy_pages",
    "_extract_embedded_image",
    "_extract_image_output",
    "_extract_output",
    "_file_kind",
    "_in_memory",
    "_is_recorded",
    "_item_sources",
    "_lock_employee_outputs",
    "_merge_output",
    "_merge_source_pdf",
    "_open_pdf",
    "_page_selection",
    "_png_matches_pixels",
    "_publish_ready_output",
    "_read_pdf",
    "_ready_output",
    "_render_image_output",
    "_source_refs",
    "_verified_passthrough",
    "_verify_pages",
    "_wrap_image_output",
    "_wrap_image_to_pdf",
    "execute_extract",
    "execute_extract_image",
    "execute_item",
    "execute_merge",
    "execute_passthrough",
    "execute_ready_item",
    "execute_render_image",
    "execute_wrap_image",
    "executed_document",
]
