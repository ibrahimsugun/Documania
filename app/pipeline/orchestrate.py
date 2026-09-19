"""Parti orkestrasyonu ve durum makinesi, yarım kalan partiyi sürdürme, planı yeniden çalıştırma
ve partiyi yeniden analiz — PRD 09.2.1, 09.2.2, 09.2.3, 13.3.1, 06.6.1, 06.6.2 (K9, K10, K15, K18,
S18).

**Durum makinesi (09.2.1).** Parti `received → rendering → analyzing → planning → executing →
done | partial` yolunu izler; bitmemiş her durumdan `failed`'a geçilir, son durumlardan (`done`,
`partial`, `failed`) çıkış yoktur (`UPLOAD_TRANSITIONS`). Her geçiş `uploads.status`'a yazılır ve
hemen commit edilir: durum her an başka bir oturumdan sorgulanabilir (`GET /api/uploads/{id}`,
01.6.1) ve adımın veritabanı işi (sayfalar, analizler, plan) geçişle birlikte kalıcı olur. §8.3'ün
kapalı listesinde durum geçişi için olay türü yoktur (PLAN.md §D21): geçişin izi sütunun kendisi,
adımların olayları (`PAGE_RENDERED`, `PAGE_ANALYZED`, `PLAN_CREATED`, `OUTPUT_SAVED`, `QUEUED_*`…)
ve hatada `PIPELINE_FAILED`'ın `stage`'idir.

**Uçtan uca işleme (09.2.2).** `process_upload` `received` partiyi tek çağrıda baştan sona işler;
başka durumdaki parti işlenmez (`UploadTransitionError`, iz bırakmaz — ikinci bir işleyici partinin
satır kilidinde bekler ve partiyi işlenmiş görür):

1. `rendering` — tekrar olmayan her dosya içerik imzasıyla (01.2.1) ayrılır: PDF'in sayfa
   görüntüsü (02.1), metin katmanı (02.2), boş sayfa (02.4) ve gömülü tek görüntü (02.5)
   işaretleri; JPEG/PNG'nin analiz kopyası (02.3). Word/Excel (K2) ve tanınmayan içerik render
   edilmez; tekrar dosyası (01.4.1) atlanır. Render'ın reddettiği dosya (bozuk ya da parolalı PDF —
   `RenderError`; çözülemeyen görüntü) partiyi durdurmaz: yazdığı her şey geri alınır, dosya
   sayfasız kalır ve plan onu "işlenemeyen dosya" olarak Unresolved'a gönderir (R7, D14).
2. `analyzing` — sayfalar güncel katalogla (`export_catalog`) analiz edilir (03.7); sağlayıcının
   ön eleme modeli varsa kolay sayfalar onda kalır (13.2.1).
3. `planning` — aynı katalogla plan üretilir ve dondurulur (06.1, K9); planın modeli
   sağlayıcının ana modelidir (sayfanın analizini hangi modelin verdiği `PAGE_ANALYZED`'dadır).
4. `executing` — plan `execute_plan` ile uygulanır (`Settings.render_image_*`).
5. Sonuç: en az bir sayfanın analizi başarısızsa `partial` (03.7.2), değilse `done`. Kuyruğa giden
   öğe hata değildir. Analiz kısmi başarıda `partial`'ı erkenden yazar; son durum olduğu için o
   değer bir sonraki geçişin altında kalır ve yürütmeden sonra yeniden yazılır.

**Hata dayanıklılığı (09.2.3).** Adım beklenmeyen bir hatayla durursa o adımın veritabanı işi geri
alınır, parti `failed` olur ve `PIPELINE_FAILED` yazılır; önceki adımların commit edilmiş işi kalır
(yürütmede durmuş partinin planı yeniden çalıştırılabilir). Inbox'a hiçbir adım yazmaz (K10):
dosyalar olduğu gibi kalır. Olay verisi `stage` (partinin durduğu durum), `error` (hata türünün
tam adı) ve `traceback` (değer taşımayan `dosya:satır işlev` çerçeveleri). Mesaj yalnız uygulamanın
kendi hatalarında hata metnidir — bu metinler kişisel değer taşımaz (C12, C13); dış kütüphanenin
metni (SQL parametresi, kişi adı taşıyan dosya yolu) yazılmaz (CONVENTIONS §6). Hata yeniden
fırlatılmaz, sonuç `ProcessedUpload`'dadır. Dosya sistemi işleme bağlı değildir: geri alınan
yürütmenin diske yazdığı çıktı kalır ve yeniden uygulamada benimsenir (07.8.1).

**Yarım kalan partiyi sürdürme (13.3.1).** Süreç bir adımın ortasında durursa (yeniden başlatma,
çökme) o adımın işlemi hiç commit edilmez; parti son commit edilen durumda kalır ve önceki adımların
işi kalıcıdır. `resume_upload` partiyi o durumdan sürdürür: `received` baştan işlenir, `rendering`
render'dan, `analyzing` analizden (analiz tek işlem olduğu için bütün sayfalar yeniden analiz
edilir), `planning` planlamadan devam eder. `executing`'deki partinin planı geçişle commit
edilmiştir: plan yeniden üretilmez, yapay zekâ çağrılmaz, commit edilmiş plan olduğu gibi uygulanır
(K9; yarım kalan uygulamanın diske yazdığı çıktı benimsenir, 07.8.1). Sonuç analizi başarısız sayfa
varsa `partial`'dır. Son durumdaki parti sürdürülmez (`UploadTransitionError`). Sürdürmenin ayrı
olayı yoktur (§8.3 listesi kapalı); izi işçi kuyruğunun iş kaydındadır (`app.worker`).

**Geçiş kancası (13.3.1).** `checkpoint` verilirse `process_upload`/`resume_upload`'ın commit ettiği
her işlemde (geçişler ve `failed` kaydı) commit'ten hemen önce partinin yazılmakta olan durumuyla
çağrılır. Aynı işleme kendi yazısını ekleyebilir (işçinin kirası, işin bitişi) ve
`ProcessingWithdrawn` fırlatarak partiyi geri çekebilir: işlem geri alınır, parti `failed`
yapılmaz, son commit edilen durumunda kalır ve hata çağırana yükselir.

**Uygulayıcı.** `PlanExecutor` planı uygulayan adımdır. Sözleşmesi: doğrulanmış planı ve kaydını
alır, yapay zekâ çağırmaz, planı değiştirmez, plan öğesi başına idempotenttir (07.8.1) ve oturumu
commit etmez. Uygulama bitince `plans.executed_at` son uygulamanın zamanı olur. `execute_plan`
(`plan_executor(settings)`) öğeleri plan sırasıyla yürütür: `hazir` → `execute_ready_item` (07.7,
07.8), `unknown`/`unreadable`/`unresolved` → `route_queue_item` (08.1), `skip` → yalnız
`OUTPUT_SKIPPED` (belgesiz; mesaj öğenin gerekçesi, veri `route: skip`). Öğeyi yürütemeyen hata
(`PLAN_EXECUTION_ERRORS`) belge tahmin ettirmez, uygulamayı durdurur. Sonra partinin çıktısı olan
her çalışanın `profil.md`'si yeniden üretilir (09.1.1) — yeniden analizde eski sürüm işaretlenen
çıktının sahibi dahil.

**Güncel plan.** Partinin güncel planı en yüksek sürümlü `plans` kaydıdır; eski sürümler
değiştirilmez ve silinmez.

**Yeniden çalıştırma (06.6.1).** Güncel plan `read_plan` ile okunur ve olduğu gibi uygulayıcıya
verilir (K9). Yapay zekâ çağrılmaz: bu yol sağlayıcı almaz; sayfa analizine, gruplamaya ve çalışan
eşleştirmeye dokunmaz. Plan yeniden üretilmez ve yeni sürüm açılmaz — planlamanın yan etkileri
(çalışan açma, profil önerisi, kimlik birikimi, aday tür görülmesi) tekrar yürümez. Uygulayıcı
ilk uygulamadaki `plans` kaydını (aynı kimlik, aynı `plan_hash`) aldığı için plan öğesi başına
idempotent uygulayıcı (07.8.1) ikinci kopya üretmez; yeniden planlama aynı içerikte bile yeni
sürüm ve yeni hash doğurur ve öğeleri uygulanmamış görünür, bu yüzden yeniden çalıştırmanın
yerini tutmaz. Dondurulduktan sonra değişmiş ya da sözleşmeye uymayan plan yürütülmez
(`PlanIntegrityError`); planı olmayan parti yeniden çalıştırılmaz (`NoPlanError`).

**Yeniden analiz (06.6.2).** Planı olan partinin sayfaları sağlayıcıya yeniden gönderilir (03.7;
ucuz model ön elemesi yapılmaz, her sayfa ana modele gider — 13.2.1), yeni analizlerden bir
sonraki plan sürümü üretilir (06.1, K18), önceki sürümlerin etkin çıktıları
(`documents.status = active`) "eski sürüm" (`superseded`) işaretlenir ve yeni plan uygulanır.
Eski çıktı silinmez, taşınmaz, yeniden adlandırılmaz: satırı ve dosyası yerinde kalır, temizlik
İK'nın arşive taşımasıdır. Başka partinin ve plana bağlı olmayan çıktıya dokunulmaz. Planı
olmayan partiyi baştan işlemek `process_upload`'ın işidir; yeniden analiz sağlayıcıyı çağırmadan
reddeder. Eski sürümün kuyruk kaydı `queue_items.plan_id` ile ayrılır (güncel plana ait değil).

**Olay.** `PLAN_RERUN` doğrulamadan sonra, uygulayıcıdan önce yazılır: veri `plan_id`, `version`,
`plan_hash`. `PLAN_REANALYZED` yeni plan (`PLAN_CREATED`) ve eski sürüm işaretlemesinden sonra,
uygulayıcıdan önce yazılır: veri yeni ve önceki planın kimliği ile sürümü, `plan_hash`, `model`,
sayfa sonuç sayıları ve eski sürüm işaretlenen çıktıların kimlikleri. Mesaj yok, kişisel değer
yok. Uygulayıcının olayları partinin bağlamında yazılır.

Yeniden çalıştırma ve yeniden analiz parti durumuna dokunmaz (yalnız analiz kısmi başarıda
`partial` yazar, 03.7.2) ve oturumu commit etmez — işlem sınırı çağıranındır; hata olursa hiçbir iz
kalmaz. `process_upload` ise işlem sınırını kendisi çizer: her geçişte commit eder.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from functools import partial
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, Protocol

from PIL import UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts import build_page_analysis_instructions
from app.ai.provider import AnalysisProvider
from app.catalog import Catalog, export_catalog
from app.config import Settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Page,
    Plan,
    Upload,
    UploadFile,
    UploadStatus,
    utcnow,
)
from app.events import EventType, event_context, record_event
from app.pipeline.analyze import PageAnalysisStatus, UploadAnalysisResult, analyze_upload
from app.pipeline.execute import EXECUTION_ERRORS, execute_ready_item
from app.pipeline.plan import PlanDocument, PlanItem, Route, create_plan, read_plan
from app.pipeline.render import (
    RenderError,
    extract_upload_file_text,
    mark_upload_file_blank_pages,
    mark_upload_file_single_image_pages,
    render_image_file,
    render_upload_file,
)
from app.pipeline.route import QueueItemReferenceError, QueueSourceIntegrityError, route_queue_item
from app.profiles import write_profile
from app.storage import DataLayout, FileKind, UnsupportedFileTypeError, detect_file_kind

# 09.2.1: bitmemiş her durumdan `failed`'a geçilir; `done`, `partial` ve `failed` son durumdur.
UPLOAD_TRANSITIONS: Mapping[UploadStatus, frozenset[UploadStatus]] = MappingProxyType(
    {
        UploadStatus.RECEIVED: frozenset({UploadStatus.RENDERING, UploadStatus.FAILED}),
        UploadStatus.RENDERING: frozenset({UploadStatus.ANALYZING, UploadStatus.FAILED}),
        UploadStatus.ANALYZING: frozenset({UploadStatus.PLANNING, UploadStatus.FAILED}),
        UploadStatus.PLANNING: frozenset({UploadStatus.EXECUTING, UploadStatus.FAILED}),
        UploadStatus.EXECUTING: frozenset(
            {UploadStatus.DONE, UploadStatus.PARTIAL, UploadStatus.FAILED}
        ),
        UploadStatus.DONE: frozenset(),
        UploadStatus.PARTIAL: frozenset(),
        UploadStatus.FAILED: frozenset(),
    }
)

# Plan öğesini yürütemeyen hatalar: kayıt, kaynak bütünlüğü (K10) ve işlem. Hiçbir şey
# yazılmamıştır; belge tahmin edilmez, uygulama durur (`process_upload`'da parti `failed`).
PLAN_EXECUTION_ERRORS: tuple[type[Exception], ...] = (
    *EXECUTION_ERRORS,
    QueueItemReferenceError,
    QueueSourceIntegrityError,
)

# Render adımının dosyayı reddetmesi: dosya sayfasız kalır, parti sürer (R7, D14).
_RENDER_REFUSALS = (RenderError, UnidentifiedImageError)
_IMAGE_KINDS = frozenset({FileKind.JPEG, FileKind.PNG})
# `PIPELINE_FAILED.data.traceback`'te tutulan en içteki çerçeve sayısı.
_TRACEBACK_FRAMES = 20


class PlanExecutor(Protocol):
    """Doğrulanmış planı uygulayan adım; sözleşmesi modül açıklamasında."""

    def __call__(
        self, session: Session, layout: DataLayout, plan: Plan, document: PlanDocument
    ) -> None: ...


Checkpoint = Callable[[Session, UploadStatus], None]
"""Geçiş kancası (13.3.1): commit edilecek her işlemde, commit'ten önce, partinin yazılmakta olan
durumuyla çağrılır; sözleşmesi modül açıklamasında."""


class ProcessingWithdrawn(RuntimeError):
    """13.3.1: geçiş kancası partiyi geri çekti (ör. iş başka bir işleyiciye geçti). Parti `failed`
    yapılmaz; son commit edilen durumunda kalır."""


class NoPlanError(LookupError):
    """Partinin planı yok: yeniden çalıştırılacak ya da yeniden analiz edilecek sürüm bulunmadı."""


class UploadTransitionError(ValueError):
    """09.2.1: parti bulunduğu durumdan istenen duruma geçemez — ör. işlenmiş parti yeniden
    işlenmez."""


@dataclass(frozen=True, slots=True)
class ProcessedUpload:
    """`process_upload` sonucu.

    `status` partinin son durumudur (`done`, `partial` ya da `failed`). `plan` partinin commit
    edilmiş planıdır; parti plan dondurulmadan durduysa `None`. `failed_stage` yalnız `failed`
    sonucunda dolar: partinin durduğu adımın durumu.
    """

    status: UploadStatus
    plan: Plan | None
    failed_stage: UploadStatus | None = None


@dataclass(frozen=True, slots=True)
class PlanRun:
    """Yeniden çalıştırmanın sonucu: uygulanan kayıt ve doğrulanmış planı."""

    plan: Plan
    document: PlanDocument


@dataclass(frozen=True, slots=True)
class Reanalysis:
    """Yeniden analizin sonucu.

    `plan` açılan yeni sürümdür, `previous_plan` yeniden analizden önceki güncel plan.
    `superseded_document_ids` bu yeniden analizde "eski sürüm" işaretlenen çıktılardır.
    """

    plan: Plan
    document: PlanDocument
    previous_plan: Plan
    superseded_document_ids: tuple[int, ...]
    analysis: UploadAnalysisResult


# --- durum makinesi ve uçtan uca işleme (09.2) --------------------------------------------------


def check_transition(current: UploadStatus, target: UploadStatus) -> None:
    """`current` durumundaki parti `target`'a geçemiyorsa `UploadTransitionError` (09.2.1)."""
    if target not in UPLOAD_TRANSITIONS[current]:
        raise UploadTransitionError(
            f"Parti '{current.value}' durumundan '{target.value}' durumuna geçemez (09.2.1)."
        )


def process_upload(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    *,
    settings: Settings,
    provider: AnalysisProvider,
    checkpoint: Checkpoint | None = None,
) -> ProcessedUpload:
    """`received` partiyi tek çağrıda render eder, analiz eder, planlar ve uygular (09.2.2).

    Kurallar modül açıklamasındadır. Parti `received` değilse — başka bir işleyici almış ya da
    işlenmiş — hiçbir şey yazılmadan `UploadTransitionError`. Adımlardan biri beklenmeyen bir
    hatayla durursa parti `failed` olur ve `PIPELINE_FAILED` yazılır (09.2.3); hata yeniden
    fırlatılmaz. Her geçiş commit edilir; `checkpoint` her commit'ten önce çağrılır (13.3.1).
    """
    stage = _begin(session, upload, checkpoint)
    return _process_stages(
        session, layout, upload, stage, settings=settings, provider=provider, checkpoint=checkpoint
    )


def resume_upload(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    *,
    settings: Settings,
    provider: AnalysisProvider,
    checkpoint: Checkpoint | None = None,
) -> ProcessedUpload:
    """Bitmemiş partiyi durduğu aşamadan sonuna kadar işler (13.3.1).

    `received` parti `process_upload` gibi baştan işlenir; ara durumdaki parti modül açıklamasındaki
    kurallarla sürdürülür (`executing`'de yapay zekâ çağrılmaz, commit edilmiş plan uygulanır). Son
    durumdaki parti için hiçbir şey yazılmadan `UploadTransitionError`. Hata dayanıklılığı ve
    `checkpoint` `process_upload`'dakiyle aynıdır.
    """
    session.refresh(upload, with_for_update=True)
    stage = UploadStatus(upload.status)
    if not UPLOAD_TRANSITIONS[stage]:
        session.rollback()
        raise UploadTransitionError(
            f"Parti '{stage.value}' durumunda; son durumdaki parti sürdürülmez (13.3.1)."
        )
    if stage is UploadStatus.RECEIVED:
        stage = _advance(session, upload, stage, UploadStatus.RENDERING, checkpoint)
    return _process_stages(
        session, layout, upload, stage, settings=settings, provider=provider, checkpoint=checkpoint
    )


def fail_upload(session: Session, upload: Upload, exc: Exception) -> UploadStatus:
    """Bitmemiş partiyi `failed` yapar ve `PIPELINE_FAILED` yazar (09.2.3); commit etmez.

    Olay verisi `process_upload`'ın hata kaydıyla aynıdır (modül açıklaması); `stage` partinin şu
    anki durumudur ve döndürülür. Son durumdaki parti için `UploadTransitionError`.
    """
    stage = UploadStatus(upload.status)
    _mark_failed(session, upload, stage, exc)
    return stage


def _process_stages(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    stage: UploadStatus,
    *,
    settings: Settings,
    provider: AnalysisProvider,
    checkpoint: Checkpoint | None,
) -> ProcessedUpload:
    # `stage` partinin commit edilmiş durumudur: o aşamanın işi yapılır, sonrakiler sırayla gelir.
    plan: Plan | None = None
    catalog: Catalog | None = None
    with event_context(upload_id=upload.id):
        try:
            if stage is UploadStatus.RENDERING:
                _render_upload(session, layout, settings, upload)
                stage = _advance(session, upload, stage, UploadStatus.ANALYZING, checkpoint)

            if stage is UploadStatus.ANALYZING:
                catalog = export_catalog(session)
                analyze_upload(
                    session,
                    layout,
                    upload,
                    provider=provider,
                    instructions=build_page_analysis_instructions(catalog),
                )
                stage = _advance(session, upload, stage, UploadStatus.PLANNING, checkpoint)

            if stage is UploadStatus.PLANNING:
                if catalog is None:
                    catalog = export_catalog(session)
                plan = create_plan(session, layout, upload, catalog=catalog, model=provider.model)
                stage = _advance(session, upload, stage, UploadStatus.EXECUTING, checkpoint)
            else:
                # K9: `executing`'deki partinin planı geçişle commit edilmiştir; yeniden üretilmez.
                plan = _require_current_plan(session, upload)

            _execute(session, layout, plan, read_plan(plan), executor=plan_executor(settings))
            outcome = (
                UploadStatus.PARTIAL if _has_failed_page(session, upload) else UploadStatus.DONE
            )
            stage = _advance(session, upload, stage, outcome, checkpoint)
        except ProcessingWithdrawn:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            _record_failure(session, upload, stage, exc, checkpoint)
            # Plan yalnız `executing`'e geçişle commit edilmiştir; öncesinde geri alındı.
            committed = plan if stage is UploadStatus.EXECUTING else None
            return ProcessedUpload(UploadStatus.FAILED, committed, failed_stage=stage)
    return ProcessedUpload(stage, plan)


def execute_plan(
    session: Session,
    layout: DataLayout,
    plan: Plan,
    document: PlanDocument,
    *,
    render_image_dpi: int,
    render_image_jpeg_quality: int,
) -> None:
    """Planın öğelerini plan sırasıyla yürütür ve partinin çalışan profillerini yeniden üretir.

    `PlanExecutor` sözleşmesine uyar (modül açıklaması); `render_image_*` `render_image` işleminin
    yapılandırma değerleridir. Öğeyi yürütemeyen hata (`PLAN_EXECUTION_ERRORS`) olduğu gibi
    yükselir. Oturum commit edilmez.
    """
    for item in document.items:
        if item.route is Route.READY:
            execute_ready_item(
                session,
                layout,
                plan,
                item,
                render_image_dpi=render_image_dpi,
                render_image_jpeg_quality=render_image_jpeg_quality,
            )
        elif item.route is Route.SKIP:
            _record_skip(session, plan, item)
        else:
            route_queue_item(session, layout, plan, item)
    _write_profiles(session, layout, plan.upload_id)


def plan_executor(settings: Settings) -> PlanExecutor:
    """Uygulamanın `PlanExecutor`'ı: `execute_plan`, `render_image` ayarları `settings`'ten."""
    return partial(
        execute_plan,
        render_image_dpi=settings.render_image_dpi,
        render_image_jpeg_quality=settings.render_image_jpeg_quality,
    )


def _begin(session: Session, upload: Upload, checkpoint: Checkpoint | None) -> UploadStatus:
    # Satır kilidi (PostgreSQL `FOR UPDATE`; SQLite `BEGIN IMMEDIATE`): aynı partiyi alan ikinci
    # işleyici bekler, sonra partiyi `received` dışında görür.
    session.refresh(upload, with_for_update=True)
    try:
        check_transition(UploadStatus(upload.status), UploadStatus.RENDERING)
    except UploadTransitionError:
        session.rollback()
        raise
    return _advance(session, upload, UploadStatus.RECEIVED, UploadStatus.RENDERING, checkpoint)


def _advance(
    session: Session,
    upload: Upload,
    current: UploadStatus,
    target: UploadStatus,
    checkpoint: Checkpoint | None,
) -> UploadStatus:
    check_transition(current, target)
    upload.status = target.value
    _commit(session, target, checkpoint)
    return target


def _commit(session: Session, status: UploadStatus, checkpoint: Checkpoint | None) -> None:
    if checkpoint is not None:
        try:
            checkpoint(session, status)
        except ProcessingWithdrawn:
            session.rollback()
            raise
    session.commit()


def _has_failed_page(session: Session, upload: Upload) -> bool:
    # 03.7.2: analizi başarısız bir sayfa partiyi `partial` yapar. Sayfaların durumundan okunur:
    # sürdürülen partinin analizi bu çağrıda değil, önceki bir işlemde yapılmış olabilir.
    failed = (
        select(Page.id)
        .join(UploadFile, Page.file_id == UploadFile.id)
        .where(
            UploadFile.upload_id == upload.id,
            Page.analysis_status == PageAnalysisStatus.FAILED.value,
        )
        .limit(1)
    )
    return session.scalar(failed) is not None


def _render_upload(
    session: Session, layout: DataLayout, settings: Settings, upload: Upload
) -> None:
    for upload_file in upload.files:
        if upload_file.is_duplicate_of is not None:
            continue  # 01.4.1: tekrar dosyası analiz edilmez, plan onu `skip` eder.
        kind = _content_kind(layout, upload_file)
        if kind is not FileKind.PDF and kind not in _IMAGE_KINDS:
            continue  # K2: Word/Excel render edilmez; tanınmayan içerik de sayfasız kalır.
        try:
            with session.begin_nested():
                if kind is FileKind.PDF:
                    render_upload_file(session, layout, settings, upload_file)
                    extract_upload_file_text(session, layout, upload_file)
                    mark_upload_file_blank_pages(session, layout, upload_file)
                    mark_upload_file_single_image_pages(session, layout, upload_file)
                else:
                    render_image_file(session, layout, settings, upload_file)
        except _RENDER_REFUSALS:
            continue


def _content_kind(layout: DataLayout, upload_file: UploadFile) -> FileKind | None:
    content = layout.resolve(upload_file.stored_path).read_bytes()
    try:
        return detect_file_kind(content)
    except UnsupportedFileTypeError:
        return None


def _record_failure(
    session: Session,
    upload: Upload,
    stage: UploadStatus,
    exc: Exception,
    checkpoint: Checkpoint | None,
) -> None:
    _mark_failed(session, upload, stage, exc)
    _commit(session, UploadStatus.FAILED, checkpoint)


def _mark_failed(session: Session, upload: Upload, stage: UploadStatus, exc: Exception) -> None:
    check_transition(stage, UploadStatus.FAILED)
    upload.status = UploadStatus.FAILED.value
    kind = type(exc)
    frames = traceback.extract_tb(exc.__traceback__)[-_TRACEBACK_FRAMES:]
    record_event(
        session,
        EventType.PIPELINE_FAILED,
        upload_id=upload.id,
        # Uygulamanın kendi hata metni kişisel değer taşımaz (C12, C13); dış hatanınki taşıyabilir.
        message=(str(exc) or None) if kind.__module__.partition(".")[0] == "app" else None,
        data={
            "stage": stage.value,
            "error": f"{kind.__module__}.{kind.__qualname__}",
            "traceback": [
                f"{PurePath(frame.filename).name}:{frame.lineno} {frame.name}" for frame in frames
            ],
        },
    )


def _record_skip(session: Session, plan: Plan, item: PlanItem) -> None:
    # `skip` öğe (boş sayfa S8, tekrar yükleme S2) çıktı ve kuyruk kaydı üretmez; yalnız izi kalır.
    first = item.sources[0]
    data: dict[str, Any] = {
        "item_id": item.item_id,
        "plan_id": plan.id,
        "route": item.route.value,
        "sources": [source.model_dump(mode="json") for source in item.sources],
    }
    record_event(
        session,
        EventType.OUTPUT_SKIPPED,
        upload_id=plan.upload_id,
        file_id=first.file_id,
        page_index=first.pages[0] if first.pages else None,
        message=item.route_reason,
        data=data,
    )


def _write_profiles(session: Session, layout: DataLayout, upload_id: str) -> None:
    # 09.1.1: partinin herhangi bir plan sürümünden çıktısı olan her çalışanın profili güncellenir.
    owners = (
        select(Document.employee_id)
        .join(Plan, Document.plan_id == Plan.id)
        .where(Plan.upload_id == upload_id)
    )
    employees = session.scalars(
        select(Employee).where(Employee.id.in_(owners)).order_by(Employee.id)
    )
    for employee in employees:
        write_profile(session, layout, employee)


# --- yeniden çalıştırma ve yeniden analiz (06.6) -----------------------------------------------


def current_plan(session: Session, upload: Upload) -> Plan | None:
    """Partinin en yüksek sürümlü planı; plan yoksa `None`."""
    session.flush()
    return session.scalars(
        select(Plan).where(Plan.upload_id == upload.id).order_by(Plan.version.desc()).limit(1)
    ).first()


def rerun_plan(
    session: Session, layout: DataLayout, upload: Upload, *, executor: PlanExecutor
) -> PlanRun:
    """Partinin güncel planını yapay zekâya ve planlamaya sormadan yeniden uygular (06.6.1).

    Plan yoksa `NoPlanError`, saklanan plan doğrulanmazsa `PlanIntegrityError`; iki durumda da
    olay yazılmaz ve uygulayıcı çağrılmaz. Oturum commit edilmez.
    """
    plan = _require_current_plan(session, upload)
    document = read_plan(plan)
    with event_context(upload_id=upload.id):
        record_event(
            session,
            EventType.PLAN_RERUN,
            data={"plan_id": plan.id, "version": plan.version, "plan_hash": plan.plan_hash},
        )
        _execute(session, layout, plan, document, executor=executor)
    return PlanRun(plan, document)


def reanalyze_upload(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    *,
    provider: AnalysisProvider,
    catalog: Catalog,
    executor: PlanExecutor,
    reference_date: date | None = None,
) -> Reanalysis:
    """Planı olan partiyi yeniden analiz eder, yeni plan sürümünü açar ve uygular (06.6.2).

    `catalog` hem analiz talimatının hem planın kataloğudur (`export_catalog(session)`); plan
    modeli `provider.model`'dır. `reference_date` `create_plan`'e aynen geçer. Plan yoksa
    sağlayıcı çağrılmadan `NoPlanError`. Oturum commit edilmez.
    """
    previous = _require_current_plan(session, upload)
    # İK'nın şüphelendiği parti ucuz model ön elemesinden geçmez, ana modele gider (13.2.1).
    analysis = analyze_upload(
        session,
        layout,
        upload,
        provider=provider,
        instructions=build_page_analysis_instructions(catalog),
        prescreen=False,
    )
    plan = create_plan(
        session,
        layout,
        upload,
        catalog=catalog,
        model=provider.model,
        reference_date=reference_date,
    )
    document = read_plan(plan)
    superseded = _supersede_older_outputs(session, plan)
    with event_context(upload_id=upload.id):
        record_event(
            session,
            EventType.PLAN_REANALYZED,
            data={
                "plan_id": plan.id,
                "version": plan.version,
                "plan_hash": plan.plan_hash,
                "model": plan.model,
                "previous_plan_id": previous.id,
                "previous_version": previous.version,
                "pages": {
                    "analyzed": len(analysis.analyzed),
                    "failed": len(analysis.failed),
                    "skipped": len(analysis.skipped),
                },
                "superseded_document_ids": list(superseded),
            },
        )
        _execute(session, layout, plan, document, executor=executor)
    return Reanalysis(plan, document, previous, superseded, analysis)


def _require_current_plan(session: Session, upload: Upload) -> Plan:
    plan = current_plan(session, upload)
    if plan is None:
        raise NoPlanError(f"Partinin planı yok (parti {upload.id}); önce parti işlenmeli.")
    return plan


def _execute(
    session: Session,
    layout: DataLayout,
    plan: Plan,
    document: PlanDocument,
    *,
    executor: PlanExecutor,
) -> None:
    executor(session, layout, plan, document)
    plan.executed_at = utcnow()
    session.flush()


def _supersede_older_outputs(session: Session, plan: Plan) -> tuple[int, ...]:
    # K18: partinin önceki sürümlerinin etkin çıktıları yerinde kalır, yalnız durumu değişir.
    older = select(Plan.id).where(Plan.upload_id == plan.upload_id, Plan.version < plan.version)
    documents = session.scalars(
        select(Document)
        .where(Document.plan_id.in_(older), Document.status == DocumentStatus.ACTIVE.value)
        .order_by(Document.id)
    ).all()
    for output in documents:
        output.status = DocumentStatus.SUPERSEDED.value
    session.flush()
    return tuple(output.id for output in documents)
