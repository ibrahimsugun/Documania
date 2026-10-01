"""Eğitim yapay zekâ yolu — mekanik tanınmayan eğitim öğesinin yapay zekâyla sınıflandırılması ve
bilinen türe "AI kararı" etiketiyle yerleşmesi (PRD 11.9.3, PLAN.md §C86 "Yapay zekâ yolu").

- **Girdi (`read_classification`).** `ai_pending` öğenin `_egitim/gelen` kopyası (bellekte okunur,
  değişmez — K10, K11) ve talimat: katalog metni (`compile_catalog`, sayfa analizininkiyle aynı) ve
  bilinen türlerin tür sözlüğü (`KnownTypes.doc_kinds`). Hazır önerilen türler (484) talimata
  girmez: yapay zekâ ülke ve türü söyler, türü eşleme bulur.
- **Çağrı (`classify`).** Dosyanın ilk sayfası (PDF'te ilk `MAX_CLASSIFICATION_PAGES` sayfası)
  tür açıklamasındaki ölçekte bellekte render edilir (`app.catalog.describe.page_images`; sayfa
  önbelleğine yazılmaz) ve `AnalysisProvider.classify_training_page` ile sorulur. Kullanıcı metni
  dosya türünü, sayfa sayısını ve görüntülerin sırasını taşır; dosya adı isteğe girmez. Sayfa
  analizi kullanılmaz: kişisel değer okunmaz (§C86 kapsam sınırı).
- **Eşleme (`resolve_classification`, saf).** Sırayla, ilk kesin sonuç kazanır:
  1. `catalog_slug` → o katalog türü;
  2. (`country_iso3`, `doc_kind`) → tek bir bilinen tür (`KnownTypes.match_kind`);
  3. `proposed_name` → normalize ad eşleşmesi tek bir bilinen türe (`KnownTypes.match_name`);
  4. hiçbiri → yerleşmez.
  Belirsiz eşleşme yerleşmez (R7): birden çok türe inen çift (RUS/`kimlik_karti`, TUR/`ehliyet`)
  ya da ad türe inmez, sıradaki adıma geçilir. Yanıtın kendisiyle çelişen eşleşme de yerleşmez:
  (1) ve (3)'te bulunan türün (ülke, tür) çifti yanıttaki ülke ya da türle tutmuyorsa o eşleşme
  kabul edilmez (katalog türünde öğe yerleşmez; adda sıradaki adıma geçilir).
- **Sonuç (`apply_classification`).** Tür bulunduysa ve ipucu (beklenen tür ya da harita satırı)
  yoksa ya da aynı türse `place_example(method=ai)`: etiket `ai_decision`, not "AI kararı: `<slug>`
  (<dayanak>, model <model>)" (aynı içerik o türde örnekse `skipped`, başka türde örnekse
  `conflict` — yerleştirmenin kuralları). İpucu bilinen bir türse ve sonuç farklıysa `conflict`:
  yerleşmez, not iki türü de yazar. Tür bulunmadıysa `unplaced` ("Yerleştirilemedi"), not "Yapay
  zekâ önerisi: <proposed_name>; <gerekçe>". Yanıtın dökümü (`ai`) `checks_json`'a eklenir.
- **Olay (K15, 13.1.1).** Her sınıflandırma tam bir yerleşme olayı yazar (`TRAINING_EXAMPLE_PLACED`
  ya da `TRAINING_ITEM_UNPLACED`); olay sağlayıcı ve modeli taşır (`ai_call_event_data`).
- **Boş-zaman işi (`TrainingClassificationJob`).** İşçi yükleme kuyruğu boşken (`app.worker.idle`)
  `ai_pending` öğeyi koşullu sahiplenir; sağlayıcı çağrısı açık veritabanı oturumu olmadan yapılır.
  Sağlayıcı ayarsızsa iş koşmaz, öğe `ai_pending` bekler. Hata veren birim öğeyi bırakır ve
  `TRAINING_ITEM_UNPLACED` yazar (durum `ai_pending`, yalnız hata türüyle); `WORKER_MAX_ATTEMPTS`
  deneme tükenince öğe `unplaced` olur ve İK'yı bekler.

**Kişisel değer yok** (CONVENTIONS §6): istekte ve yanıtta kişisel alan yoktur; talimat yanıtın
metinlerinde kişisel değeri yasaklar. Olaylar dosya adı taşımaz; hata yalnız türüyle yazılır.

**Değişmez güvence** (§C86): çalışan, kişi eşleştirmesi, kuyruk öğesi, parti, sayfa, plan ya da
çıktı belgesi yoktur; `candidate_document_types`'a yazılmaz (yerleştirilemeyen belge aday tür
olmaz, eğitim sekmesinde bekler — insan kararı). Fonksiyonlar işlemi commit etmez; iş birimini
boş-zaman çerçevesi kapatır.
"""

from __future__ import annotations

import enum
import sys
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai.prompts.training_classification import (
    TrainingClassificationInstructions,
    build_training_classification_instructions,
)
from app.ai.provider import AnalysisProvider, PageImage, TrainingClassificationRequest
from app.ai.training_classification import TrainingClassification
from app.catalog.describe import page_images
from app.catalog.sync import export_catalog
from app.config import Settings
from app.db.models import TrainingItem, TrainingItemStatus, TrainingMethod
from app.events import EventType, ai_call_event_data, record_event
from app.storage import DataLayout, FileKind
from app.training.known_types import KnownType, KnownTypes, build_known_types, load_known_types
from app.training.mechanical import hint_label
from app.training.placement import (
    SYSTEM_ACTOR,
    ItemNotPlaceableError,
    leave_unplaced,
    place_example,
)
from app.worker.idle import IdleContext, IdleTable, run_idle_unit

JOB_NAME = "egitim-siniflandirmasi"

MAX_CLASSIFICATION_PAGES = 2
"""İsteğe giren en çok sayfa: görüntü dosyasında tek görüntü, PDF'te ilk iki sayfa (§C86)."""

AI_CHECK_KEY = "ai"
"""`training_items.checks_json`'da yapay zekâ sınıflandırmasının dökümünün anahtarı."""

NO_TYPE_REASON = "yapay zekâ türü belirlemedi"
ERROR_NOTE = "Yapay zekâ incelemesi yapılamadı ({error}); denemeler tükendi"
ABANDONED_NOTE = "Yapay zekâ incelemesi yarıda kaldı; denemeler tükendi"

_FILE_LABELS = {FileKind.PDF: "PDF", FileKind.JPEG: "JPEG", FileKind.PNG: "PNG"}


class ResolutionBasis(enum.StrEnum):
    """Yapay zekâ yanıtının türe eşlenmesinin dayanağı (`checks_json["ai"]["result"]["basis"]`)."""

    CATALOG = "catalog_slug"
    KIND = "country_kind"
    NAME = "proposed_name"


# --- girdi -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClassificationSource:
    """Sınıflandırılacak öğenin oturumdan bağımsız girdisi: içerik, dosya türü, sayfa sayısı ve
    talimat."""

    item_id: int
    content: bytes = field(repr=False)
    file_kind: FileKind
    page_count: int
    instructions: TrainingClassificationInstructions


def read_classification(
    session: Session,
    layout: DataLayout,
    item: TrainingItem,
    *,
    catalog_token_budget: int | None = None,
) -> ClassificationSource:
    """`ai_pending` öğenin girdisini okur: `_egitim/gelen` kopyasının içeriği ve talimat (o anki
    katalog ve tür sözlüğü; katalog bütçesi `Settings.catalog_token_budget`, boşsa ölçekli,
    11.4.3). Veritabanına yazmaz. Öğenin dosyası yoksa `ItemNotPlaceableError`."""
    if item.staged_path is None or item.file_kind is None:
        raise ItemNotPlaceableError(f"Öğe {item.id} için sınıflandırılacak dosya yok")
    catalog = export_catalog(session)
    known = build_known_types(catalog)
    return ClassificationSource(
        item_id=item.id,
        content=layout.resolve(item.staged_path).read_bytes(),
        file_kind=FileKind(item.file_kind),
        page_count=item.page_count or 1,
        instructions=build_training_classification_instructions(
            catalog, known.doc_kinds, configured_budget=catalog_token_budget
        ),
    )


# --- çağrı -----------------------------------------------------------------------------------


def build_classification_prompt(file_kind: FileKind, page_count: int, images: int) -> str:
    """İsteğin kullanıcı metni: dosya türü, sayfa sayısı ve görüntülerin sırası. Dosya adı ve
    kişi bilgisi yazılmaz."""
    lines = [
        f"Dosya türü: {_FILE_LABELS.get(file_kind, file_kind.value.upper())}",
        f"Sayfa sayısı: {page_count}",
        "",
        f"Görüntüler ({images}, gönderildiği sırayla):",
        *(f"{number}. sayfa {number}" for number in range(1, images + 1)),
    ]
    if page_count > images:
        lines.append(f"Kalan {page_count - images} sayfa gönderilmedi.")
    return "\n".join(lines)


def classify(
    source: ClassificationSource,
    settings: Settings,
    provider: AnalysisProvider,
    *,
    max_pages: int = MAX_CLASSIFICATION_PAGES,
) -> TrainingClassification:
    """Öğenin ilk sayfasını (PDF'te ilk `max_pages` sayfasını) bellekte render edip yapay zekâya
    sınıflandırtır; hiçbir şey kaydetmez ve veritabanına dokunmaz.

    Render hatası (`RenderError`, bozuk görüntüde `OSError`), sağlayıcı hataları (`ProviderError`)
    ve şemaya uymayan yanıt (`TrainingClassificationError`) olduğu gibi yükselir.
    """
    rendered, page_count = page_images(source.content, source.file_kind, settings, max_pages)
    images = tuple(PageImage(data) for data in rendered)
    request = TrainingClassificationRequest(
        images=images,
        instructions=source.instructions.text,
        prompt=build_classification_prompt(source.file_kind, page_count, len(images)),
        known_slugs=source.instructions.known_slugs,
        doc_kinds=source.instructions.doc_kinds,
    )
    return provider.classify_training_page(request)


# --- eşleme ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Resolution:
    """Yanıtın bilinen türe eşlenmesi. `known` doluysa tür bulundu (`basis` dayanağı, `basis_text`
    notdaki Türkçe adı); boşsa `reason` neden bulunmadığıdır. Kişisel değer taşımaz."""

    known: KnownType | None
    basis: ResolutionBasis | None = None
    basis_text: str = ""
    reason: str = ""


def resolve_classification(known: KnownTypes, classification: TrainingClassification) -> Resolution:
    """Yanıtı bilinen türe eşler (modül açıklaması); saf işlevdir."""
    if classification.catalog_slug is not None:
        slug = classification.catalog_slug
        target = known.get(slug)
        if target is None:
            return Resolution(None, reason=f"katalog türü `{slug}` bilinen türlerde yok")
        clashes = _clashes(target, classification)
        if clashes:
            return Resolution(
                None, reason=f"katalog türü `{slug}` yanıttaki {clashes} bilgisiyle çelişiyor"
            )
        return Resolution(target, ResolutionBasis.CATALOG, "katalog türü")
    reasons: list[str] = []
    country, kind = classification.country_iso3, classification.doc_kind
    if country is not None and kind is not None:
        matches = known.kind_matches(country, kind)
        if len(matches) == 1:
            return Resolution(matches[0], ResolutionBasis.KIND, f"ülke ve tür {country}/{kind}")
        reasons.append(_many_or_none(f"{country}/{kind}", matches))
    name = classification.proposed_name
    if name is not None:
        matches = known.name_matches(name)
        if len(matches) == 1:
            (target,) = matches
            clashes = _clashes(target, classification)
            if not clashes:
                return Resolution(target, ResolutionBasis.NAME, f"ad {name}")
            reasons.append(f"ad `{target.slug}` türüne iniyor ama yanıttaki {clashes} tutmuyor")
        else:
            reasons.append(_many_or_none("ad", matches))
    return Resolution(None, reason="; ".join(reasons) or NO_TYPE_REASON)


def _clashes(target: KnownType, classification: TrainingClassification) -> str:
    """Yanıttaki ülke ve türün `target`'ın (ülke, tür) çiftiyle tutmayan yanları ("ülke", "tür",
    "ülke ve tür"); hepsi tutuyorsa ya da karşılaştırılacak değer yoksa boş."""
    parts = []
    country = classification.country_iso3
    if country is not None and target.country_iso3 is not None:
        if country != target.country_iso3.strip().upper():
            parts.append("ülke")
    kind = classification.doc_kind
    if kind is not None and target.doc_kind is not None and kind != target.doc_kind:
        parts.append("tür")
    return " ve ".join(parts)


def _many_or_none(what: str, matches: tuple[KnownType, ...]) -> str:
    if matches:
        slugs = ", ".join(f"`{match.slug}`" for match in matches)
        return f"{what} birden çok türe iniyor ({slugs})"
    return f"{what} bilinen bir türe inmiyor"


# --- sonuç -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClassificationOutcome:
    """`apply_classification` sonucu: öğenin yeni durumu, türü (yerleşmeyende çelişen ya da
    engellenen tür) ve notu."""

    status: TrainingItemStatus
    slug: str | None
    note: str


def apply_classification(
    session: Session,
    layout: DataLayout,
    item: TrainingItem,
    classification: TrainingClassification,
    *,
    provider: AnalysisProvider,
    known: KnownTypes | None = None,
) -> ClassificationOutcome:
    """Yanıtı öğeye uygular (modül açıklaması); commit etmez. `known` verilmezse o anki katalog ∪
    önerilen kayıttır. Öğe `ai_pending` değilse `ItemNotPlaceableError`."""
    if item.status != TrainingItemStatus.AI_PENDING:
        raise ItemNotPlaceableError(
            f"Öğe {item.id} yapay zekâ incelemesi beklemiyor: {item.status}"
        )
    known = load_known_types(session) if known is None else known
    resolution = resolve_classification(known, classification)
    hint = known.get(item.hint_slug) if item.hint_slug else None
    model = provider.model
    extra: dict[str, object] = ai_call_event_data(provider=provider.name, model=model)
    target = resolution.known

    if target is None:
        proposal = classification.proposed_name
        head = f"Yapay zekâ önerisi: {proposal}" if proposal else "Yapay zekâ önerisi yok"
        note = f"{head}; {resolution.reason}; model {model}"
        _record_check(item, provider, classification, resolution, TrainingItemStatus.UNPLACED)
        leave_unplaced(
            session,
            item,
            TrainingItemStatus.UNPLACED,
            note=note,
            method=TrainingMethod.AI,
            event_data=extra,
        )
        return ClassificationOutcome(TrainingItemStatus.UNPLACED, None, note)

    extra["basis"] = resolution.basis.value if resolution.basis is not None else None
    if hint is not None and hint.slug != target.slug:
        note = (
            f"AI kararı `{target.slug}` {hint_label(item)} `{hint.slug}` ile çelişiyor "
            f"({resolution.basis_text}, model {model})"
        )
        _record_check(item, provider, classification, resolution, TrainingItemStatus.CONFLICT)
        leave_unplaced(
            session,
            item,
            TrainingItemStatus.CONFLICT,
            note=note,
            method=TrainingMethod.AI,
            slug=target.slug,
            event_data=extra,
        )
        return ClassificationOutcome(TrainingItemStatus.CONFLICT, target.slug, note)

    note = f"AI kararı: `{target.slug}` ({resolution.basis_text}, model {model})"
    placement = place_example(
        session,
        layout,
        known,
        item,
        target.slug,
        method=TrainingMethod.AI,
        note=note,
        event_data=extra,
    )
    _record_check(item, provider, classification, resolution, placement.status)
    return ClassificationOutcome(placement.status, target.slug, placement.note)


def _record_check(
    item: TrainingItem,
    provider: AnalysisProvider,
    classification: TrainingClassification,
    resolution: Resolution,
    status: TrainingItemStatus,
) -> None:
    """Yanıtın, eşlemenin ve sonucun dökümünü `checks_json["ai"]`'ye yazar; mekanik döküm kalır."""
    result: dict[str, Any] = {
        "slug": resolution.known.slug if resolution.known is not None else None,
        "basis": resolution.basis.value if resolution.basis is not None else None,
        "reason": resolution.reason or None,
        "status": status.value,
    }
    check = {
        "provider": provider.name,
        "model": provider.model,
        "response": classification.model_dump(mode="json"),
        "result": result,
    }
    # JSON sütunu yerinde değişiklik izlemez: yeni sözlük atanır.
    item.checks_json = {**(item.checks_json or {}), AI_CHECK_KEY: check}


def store_classification_error(
    session: Session,
    item: TrainingItem,
    *,
    error: str,
    final: bool,
    provider: AnalysisProvider,
) -> None:
    """Hata veren sınıflandırmanın olayını yazar; commit etmez. `final` ise (denemeler tükendi;
    durum `unplaced`'ı boş-zaman çerçevesi yazdı) öğe İK'yı bekler ve notu hatayı söyler. `error`
    hatanın türüdür, mesajı değil."""
    extra: dict[str, object] = {"error": error} | ai_call_event_data(
        provider=provider.name, model=provider.model
    )
    if final:
        leave_unplaced(
            session,
            item,
            TrainingItemStatus.UNPLACED,
            note=ERROR_NOTE.format(error=error),
            method=TrainingMethod.AI,
            event_data=extra,
            message="Eğitim öğesi yerleşmedi: yapay zekâ incelemesi yapılamadı.",
        )
        return
    # Öğe `ai_pending` kalır ve yeniden denenir; olay harcanan kullanımı taşır (13.1.1).
    record_event(
        session,
        EventType.TRAINING_ITEM_UNPLACED,
        actor=SYSTEM_ACTOR,
        message="Eğitim öğesinin yapay zekâ incelemesi hata verdi; yeniden denenecek.",
        data={
            "run_id": item.run_id,
            "training_item_id": item.id,
            "status": TrainingItemStatus.AI_PENDING.value,
            "type_slug": None,
            "hint_slug": item.hint_slug,
        }
        | extra,
    )


def _abandoned(session: Session, item: TrainingItem) -> None:
    """İşleyicisi yarıda kalmış ve denemesi tükenmiş öğe (`IdleTable.abandoned`): durum `unplaced`'ı
    çerçeve yazdı; karar, not, olay ve çalıştırma sayaçları burada. Kullanım ölçülmediği için olay
    sağlayıcı alanı taşımaz ve maliyet görünümünde sayılmaz."""
    leave_unplaced(
        session,
        item,
        TrainingItemStatus.UNPLACED,
        note=ABANDONED_NOTE,
        method=TrainingMethod.AI,
        message="Eğitim öğesi yerleşmedi: yapay zekâ incelemesi yarıda kaldı.",
    )


# --- boş-zaman işi ---------------------------------------------------------------------------

TRAINING_CLASSIFICATIONS = IdleTable(
    TrainingItem,
    pending=lambda: TrainingItem.status == TrainingItemStatus.AI_PENDING.value,
    failed={"status": TrainingItemStatus.UNPLACED.value},
    abandoned=_abandoned,
)
"""Yapay zekâ incelemesi bekleyen (`ai_pending`) eğitim öğeleri; deneme tükenince `unplaced`."""


class TrainingClassificationJob:
    """İşçinin boş-zaman işi: sıradaki `ai_pending` eğitim öğesini sınıflandırır (`IdleJob`)."""

    name = JOB_NAME

    def __init__(self, *, max_pages: int = MAX_CLASSIFICATION_PAGES) -> None:
        self._max_pages = max_pages

    def run_one(self, context: IdleContext) -> bool:
        provider = context.provider

        def read(session: Session, item: TrainingItem) -> ClassificationSource:
            return read_classification(
                session,
                context.layout,
                item,
                catalog_token_budget=context.settings.catalog_token_budget,
            )

        def call(
            provider: AnalysisProvider, source: ClassificationSource
        ) -> TrainingClassification:
            return classify(source, context.settings, provider, max_pages=self._max_pages)

        def write(
            session: Session,
            item: TrainingItem,
            classification: TrainingClassification,
        ) -> None:
            apply_classification(session, context.layout, item, classification, provider=provider)

        def failed(session: Session, item: TrainingItem, final: bool) -> None:
            # Çerçeve bu kancayı hatanın `except` bloğunda çağırır; yalnız türü yazılır.
            active = sys.exception()
            error = type(active).__name__ if active is not None else "Exception"
            store_classification_error(session, item, error=error, final=final, provider=provider)

        return run_idle_unit(
            context,
            TRAINING_CLASSIFICATIONS,
            name=self.name,
            read=read,
            call=call,
            write=write,
            failed=failed,
        )
