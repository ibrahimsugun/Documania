"""Hazır şablon incelemesi — PRD 15.1.2 (PLAN.md §D123 c).

Yüklenen şablonun bütün sayfa görüntüleri (15.1.1'de üretilen önizlemeler; 02.1.1 render ayarı)
işçide yapay zekâya gönderilir, yanıt §8.7 şemasıyla doğrulanır (`TemplateFieldMap`) ve **alan
haritası sürümü** olarak dondurulur (K9/R10): üretim bu haritayı uygular, yapay zekâya tekrar
sorulmaz. Şablon `draft` kalır; haritayı İK onaylar (15.1.3).

- **İstek (`request_examination`).** Yükleme ve "yeniden incele" şablonu kuyruğa koyar
  (`examine_requested_at`, deneme sayacı sıfır, eski hata silinir). Sağlayıcı ayarlı değilse
  kuyruğa girmez: `examine_error` `provider_unavailable` olur, olay yazılır, sebep listede görünür.
  Arşivdeki şablon incelenmez (`TemplateArchivedError`).
- **Kullanıcı metni (`build_map_prompt`).** Şablonun adı, sayfa sayısı ve görüntülerin hangi sayfa
  olduğu. Talimat sabittir (`app.ai.prompts.template_map`).
- **İnceleme (`examine`).** Veritabanına dokunmaz. Sayfa görüntüsü eksikse sağlayıcı çağrılmaz
  (`no_pages`); şemaya uymayan yanıt yeniden sorulmaz (`invalid_response`). Sağlayıcı hatası
  (`ProviderError`) yükselir: boş-zaman çerçevesi yeniden dener, `WORKER_MAX_ATTEMPTS` deneme
  tükenince `provider_error`.
- **Sürüm (`store_examination`).** Harita `output_template_maps`'e bir sonraki sürüm olarak yazılır:
  JSON §8.7'nin bütün hâli (`template_id`, `version`, `pages`, `fields`, `notes`), `model`,
  `map_hash` = kanonik JSON'un (anahtarlar sıralı, boşluksuz ayırıcı, UTF-8) SHA-256'sı. Eski sürüm
  silinmez, şablonun durumu değişmez. Harita belgeden okunan değer taşımaz: alan başına yalnız
  basılı etiket (`label_text`) saklanır, şablon boş kalıptır.
- **Olay `TEMPLATE_EXAMINED`** (`actor` system): `template_id`, `model`, `field_count`, `error`
  (başarıda `null`), başarıda `version`; sağlayıcı adı `ai_call_event_data` ile. Kişisel değer ve
  hata mesajı taşımaz — sağlayıcı hatasında yalnız türü (`error_type`).

Hiçbir fonksiyon commit etmez. Şablon dosyası ve görüntüleri okunur, değiştirilmez (K10, K11).
"""

from __future__ import annotations

import enum
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.ai.prompts.template_map import load_template_map_instructions
from app.ai.provider import AnalysisProvider, PageImage, TemplateMapRequest
from app.ai.schemas import TemplateFieldMap, TemplateFieldMapError
from app.db.models import OutputTemplate, OutputTemplateMap, OutputTemplateStatus, utcnow
from app.events import EventType, ai_call_event_data, record_event
from app.storage import DataLayout
from app.storage.atomic import sha256_bytes
from app.worker.idle import IdleContext, IdleTable, run_idle_unit

JOB_NAME = "sablon-incelemesi"


class ExamineError(enum.StrEnum):
    """`output_templates.examine_error` kodu: incelemenin neden harita üretmediği."""

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    """Yapay zekâ sağlayıcısı ayarlı değil; şablon kuyruğa girmedi."""
    INVALID_RESPONSE = "invalid_response"
    """Yanıt §8.7 şemasına uymadı."""
    PROVIDER_ERROR = "provider_error"
    """Sağlayıcı çağrısı denemeler boyunca tamamlanamadı."""
    NO_PAGES = "no_pages"
    """Şablonun sayfa görüntüsü bulunamadı."""


class TemplateArchivedError(ValueError):
    """Arşivdeki şablon incelenmez."""


@dataclass(frozen=True, slots=True)
class TemplateSource:
    """İncelemenin oturumdan bağımsız girdisi."""

    template_id: int
    name: str
    page_count: int


@dataclass(frozen=True, slots=True)
class Examination:
    """İncelemenin sonucu: harita ya da hata kodu (biri dolu)."""

    field_map: TemplateFieldMap | None = None
    error: ExamineError | None = None


# --- istek -------------------------------------------------------------------------------------


def is_examining(template: OutputTemplate) -> bool:
    """İnceleme işçide bekliyor ya da sürüyor."""
    return template.examine_requested_at is not None


def request_examination(
    session: Session, template: OutputTemplate, *, provider_available: bool
) -> bool:
    """Şablonu incelemeye koyar; kuyruğa girdiyse `True`. Sağlayıcı ayarlı değilse sebebi yazar ve
    `TEMPLATE_EXAMINED`'ı hatayla kaydeder (`False`). Arşivdeki şablonda `TemplateArchivedError`."""
    if template.status == OutputTemplateStatus.ARCHIVED.value:
        raise TemplateArchivedError(template.id)
    template.idle_claimed_by = None
    template.idle_claim_expires_at = None
    template.idle_attempts = 0
    if not provider_available:
        template.examine_requested_at = None
        template.examine_error = ExamineError.PROVIDER_UNAVAILABLE.value
        session.flush()
        _record(session, template, model=None, error=ExamineError.PROVIDER_UNAVAILABLE)
        return False
    template.examine_requested_at = utcnow()
    template.examine_error = None
    session.flush()
    return True


# --- inceleme ----------------------------------------------------------------------------------


def read_source(session: Session, template: OutputTemplate) -> TemplateSource:
    return TemplateSource(template.id, template.name, template.page_count)


def build_map_prompt(source: TemplateSource) -> str:
    """Şablona özgü kullanıcı metni: ad, sayfa sayısı ve görüntülerin sırası."""
    lines = [
        f"Şablon adı: {source.name}",
        f"Sayfa sayısı: {source.page_count}",
        "Görüntüler sayfa sırasıyladır:",
    ]
    lines += [
        f"- {index + 1}. görüntü: sayfa {index} (`page: {index}`)"
        for index in range(source.page_count)
    ]
    return "\n".join(lines)


def _page_images(layout: DataLayout, source: TemplateSource) -> tuple[PageImage, ...] | None:
    images: list[PageImage] = []
    for index in range(source.page_count):
        path = layout.template_page_image_path(source.template_id, index)
        try:
            images.append(PageImage(path.read_bytes()))
        except (OSError, ValueError):
            return None
    return tuple(images)


def examine(source: TemplateSource, layout: DataLayout, provider: AnalysisProvider) -> Examination:
    """Şablonu inceletir (modül açıklaması); hiçbir şey kaydetmez. `ProviderError` yükselir."""
    images = _page_images(layout, source)
    if not images:
        return Examination(error=ExamineError.NO_PAGES)
    request = TemplateMapRequest(
        images=images,
        instructions=load_template_map_instructions(),
        prompt=build_map_prompt(source),
        page_count=source.page_count,
    )
    try:
        return Examination(field_map=provider.examine_template(request))
    except TemplateFieldMapError:
        # Yanıt yeniden sorulmaz; ayrıntı (yanıttaki değerler) saklanmaz.
        return Examination(error=ExamineError.INVALID_RESPONSE)


# --- sürüm -------------------------------------------------------------------------------------


def canonical_map_json(data: Mapping[str, Any]) -> bytes:
    """`map_hash`'in girdisi: anahtarları sıralı, ayırıcıları boşluksuz, UTF-8 JSON."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def map_hash(data: Mapping[str, Any]) -> str:
    """Saklanan haritanın kanonik JSON'unun SHA-256'sı (K9/R10 dondurma)."""
    return sha256_bytes(canonical_map_json(data))


def store_map(
    session: Session,
    template: OutputTemplate,
    field_map: TemplateFieldMap,
    *,
    model: str | None,
) -> OutputTemplateMap:
    """Haritayı şablonun bir sonraki sürümü olarak yazar; eski sürümlere dokunmaz."""
    latest = session.scalar(
        select(func.max(OutputTemplateMap.version)).where(
            OutputTemplateMap.template_id == template.id
        )
    )
    version = (latest or 0) + 1
    data = {
        "template_id": template.id,
        "version": version,
        "pages": template.page_count,
        **field_map.model_dump(mode="json"),
    }
    row = OutputTemplateMap(
        template_id=template.id,
        version=version,
        json=data,
        model=model,
        map_hash=map_hash(data),
    )
    session.add(row)
    session.flush()
    session.refresh(template, ["maps"])
    return row


def store_examination(
    session: Session,
    template: OutputTemplate,
    examination: Examination,
    *,
    provider: AnalysisProvider,
) -> OutputTemplateMap | None:
    """Sonucu yazar (harita sürümü ya da hata kodu), kuyruktan çıkarır ve olayı kaydeder."""
    template.examine_requested_at = None
    if examination.field_map is None:
        error = examination.error or ExamineError.INVALID_RESPONSE
        template.examine_error = error.value
        _record(
            session,
            template,
            model=provider.model,
            provider=provider.name,
            effort=provider.effort,
            error=error,
        )
        return None
    template.examine_error = None
    row = store_map(session, template, examination.field_map, model=provider.model)
    _record(
        session,
        template,
        model=provider.model,
        provider=provider.name,
        effort=provider.effort,
        field_count=examination.field_map.fillable_count,
        version=row.version,
    )
    return row


def store_error(
    session: Session,
    template: OutputTemplate,
    *,
    error_type: str,
    final: bool,
    provider: AnalysisProvider,
) -> None:
    """Hata veren denemenin olayını yazar; `final` ise (denemeler tükendi) sebebi de. Kuyruktan
    çıkarma boş-zaman çerçevesinin işidir (`TEMPLATE_EXAMINATIONS.failed`)."""
    if final:
        template.examine_error = ExamineError.PROVIDER_ERROR.value
    _record(
        session,
        template,
        model=provider.model,
        provider=provider.name,
        effort=provider.effort,
        error=ExamineError.PROVIDER_ERROR,
        error_type=error_type,
        final=final,
    )


def _record(
    session: Session,
    template: OutputTemplate,
    *,
    model: str | None,
    provider: str | None = None,
    effort: str | None = None,
    field_count: int = 0,
    error: ExamineError | None = None,
    version: int | None = None,
    error_type: str | None = None,
    final: bool | None = None,
) -> None:
    data: dict[str, object] = {
        "template_id": template.id,
        "model": model,
        "field_count": field_count,
        "error": None if error is None else error.value,
    }
    if provider is not None:
        data |= ai_call_event_data(provider=provider, model=model or "", effort=effort)
    if version is not None:
        data["version"] = version
    if error_type is not None:
        data["error_type"] = error_type
    if final is not None:
        data["final"] = final
    record_event(session, EventType.TEMPLATE_EXAMINED, data=data)


# --- boş-zaman işi -----------------------------------------------------------------------------

TEMPLATE_EXAMINATIONS = IdleTable(
    OutputTemplate,
    pending=lambda: and_(
        OutputTemplate.examine_requested_at.is_not(None),
        OutputTemplate.status != OutputTemplateStatus.ARCHIVED.value,
    ),
    failed={
        "examine_requested_at": None,
        "examine_error": ExamineError.PROVIDER_ERROR.value,
    },
)
"""İncelemesi istenmiş, arşivde olmayan şablonlar; deneme tükenince `provider_error`."""


class TemplateExaminationJob:
    """İşçinin boş-zaman işi: sıradaki incelemesi istenmiş şablonu inceler (`IdleJob`)."""

    name = JOB_NAME

    def run_one(self, context: IdleContext) -> bool:
        provider = context.provider

        def call(provider: AnalysisProvider, source: TemplateSource) -> Examination:
            return examine(source, context.layout, provider)

        def write(session: Session, template: OutputTemplate, examination: Examination) -> None:
            store_examination(session, template, examination, provider=provider)

        def failed(session: Session, template: OutputTemplate, final: bool) -> None:
            # Çerçeve bu kancayı hatanın `except` bloğunda çağırır; yalnız türü yazılır.
            active = sys.exception()
            error_type = type(active).__name__ if active is not None else "Exception"
            store_error(session, template, error_type=error_type, final=final, provider=provider)

        return run_idle_unit(
            context,
            TEMPLATE_EXAMINATIONS,
            name=self.name,
            read=read_source,
            call=call,
            write=write,
            failed=failed,
        )
