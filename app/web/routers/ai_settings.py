"""Yapay zekâ ayarları sayfası (PRD 10.1.10; PLAN.md §D124 a, c, e, f).

Root, analizlerin hangi sağlayıcıyla (Anthropic ya da OpenAI), hangi modelle ve hangi eforla
yapılacağını seçer. Ayarın kendisi ve kuralları `app.ai.runtime`'dadır (tm 188): tek satırlık
`ai_settings`, aynı anda tek etkin sağlayıcı, anahtarı `.env`'de tanımsız sağlayıcı
etkinleştirilemez, efor modelin kümesinden (`app.ai.model_list`). Satır yokken sayfa `.env`
değerlerini gösterir ve "henüz kaydedilmedi" der; ilk kayıt satırı açar.

- `GET /ai-settings` sağlayıcı başına bir kart: anahtar durumu (yalnız tanımlı/tanımsız — anahtarın
  hiçbir parçası sayfaya gelmez), etkin/pasif (tek radyo grubu), model ve efor seçimi. Efor
  listesi kayıtlı modelinkidir; JavaScript yoktur: model değişince küme kaydetten sonra yenilenir,
  modele uymayan efor 422'dir.
- `/ai-settings/<her şey>` (`GET`, `POST`) herkese — root dahil — bilinmeyen yolla aynı 404.
- `POST /ai-settings` tek adımda kaydeder (geri alınabilir, §D61): bilinmeyen sağlayıcı/model/efor
  ve anahtarsız sağlayıcıyı etkinleştirme 422, sayfa hatayla yeniden çizilir; başarıda
  `AI_SETTINGS_CHANGED` {alan: {from, to}} root'un adıyla ve bildirim (10.11.1). Değişiklik yoksa
  olay yazılmaz. Listede olmayan model yalnız o sağlayıcının kayıtlı (`.env`'den gelen) modeliyse
  kabul edilir.

Yalnız root açar (10.1.9 kalıbı): `require_root` yönlendiricinin bütün yollarındadır ve yazma
kapısından önce çalışır (`app.main`), İK ve Kullanıcı için adres — `POST` dahil — bilinmeyen yolla
aynı 404'tür; bağlantı yalnız root'un gezinmesindedir (`base.html`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.model_list import allowed_efforts, find_model, models_for
from app.ai.runtime import (
    AiChoice,
    AiSettingsError,
    current_choice,
    key_defined,
    load_ai_settings,
    save_ai_settings,
)
from app.config import Settings, get_settings
from app.db.models import AiProviderName
from app.db.session import get_session
from app.events import EventType, record_event
from app.i18n import N_, Translatable
from app.web.auth import PanelUser, require_panel_user, require_root
from app.web.feedback import AI_SETTINGS_SAVED, AI_SETTINGS_UNCHANGED, flash
from app.web.templating import render_page

router = APIRouter(tags=["ai-settings"], dependencies=[Depends(require_root)])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
# Form sınırı yalnız aşırı girdiye karşıdır; model sütunu 100 karakterdir (`app.ai.runtime`).
FormValue = Annotated[str, Form(max_length=200)]

AI_SETTINGS_PATH = "/ai-settings"
ACTIVE_KEY = "ai_settings"
PROVIDER_LABELS = {
    AiProviderName.ANTHROPIC.value: "Anthropic",
    AiProviderName.OPENAI.value: "OpenAI",
}

UNKNOWN_PROVIDER = N_("Bilinmeyen sağlayıcı.")
KEY_MISSING = N_(
    "{provider} sağlayıcısının API anahtarı sunucunun .env dosyasında tanımlı değil; "
    "etkinleştirilemez."
)
UNKNOWN_MODEL = N_("{provider} için seçilen model listede yok.")
UNKNOWN_EFFORT = N_(
    "Seçilen efor {provider} modelinde kullanılamaz. Modeli değiştirdiyseniz önce modeli "
    "kaydedin, sonra eforu seçin."
)
NOT_SAVED = N_("Ayar kaydedilemedi.")


@dataclass(frozen=True, slots=True)
class ModelOption:
    model_id: str
    label: str


@dataclass(frozen=True, slots=True)
class ProviderCard:
    """Bir sağlayıcının kartı: değerler gösterime hazırdır; anahtar değeri taşımaz."""

    name: str
    label: str
    key_defined: bool
    active: bool
    models: tuple[ModelOption, ...]
    model: str
    model_listed: bool
    efforts: tuple[str, ...]
    effort: str | None
    default_effort: str | None


@dataclass(frozen=True, slots=True)
class AiSettingsPage:
    cards: tuple[ProviderCard, ...]
    saved: bool  # `ai_settings` satırı var mı (yoksa `.env` gösterilir)


def _default_effort(provider: str, model_id: str) -> str | None:
    """ "Varsayılan" seçeneğinde gerçekte kullanılan efor: modelin varsayılanı; listede olmayan
    modelde bilinmez."""
    model = find_model(provider, model_id)
    if model is None:
        return None
    return model.default_effort


def build_page(session: Session, settings: Settings) -> AiSettingsPage:
    choice = current_choice(session, settings)
    cards = []
    for provider, model_id, effort in (
        (AiProviderName.ANTHROPIC.value, choice.anthropic_model, choice.anthropic_effort),
        (AiProviderName.OPENAI.value, choice.openai_model, choice.openai_effort),
    ):
        cards.append(
            ProviderCard(
                name=provider,
                label=PROVIDER_LABELS[provider],
                key_defined=key_defined(settings, provider),
                active=choice.provider == provider,
                models=tuple(
                    ModelOption(model.model_id, model.label) for model in models_for(provider)
                ),
                model=model_id,
                model_listed=find_model(provider, model_id) is not None,
                efforts=allowed_efforts(provider, model_id),
                effort=effort,
                default_effort=_default_effort(provider, model_id),
            )
        )
    return AiSettingsPage(cards=tuple(cards), saved=load_ai_settings(session) is not None)


def _page(
    request: Request,
    user: PanelUser,
    session: Session,
    settings: Settings,
    *,
    status_code: int = status.HTTP_200_OK,
    error: str | Translatable | None = None,
) -> HTMLResponse:
    page = build_page(session, settings)
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`).
    session.rollback()
    return render_page(
        request,
        "ai_settings.html",
        user=user,
        active=ACTIVE_KEY,
        page=page,
        error=error,
        status_code=status_code,
    )


def _form_choice(
    session: Session,
    settings: Settings,
    provider: str,
    models: dict[str, str],
    efforts: dict[str, str],
) -> AiChoice | Translatable | str:
    """Formdaki seçim; geçersizse kullanıcıya gösterilecek (çevrilebilir) hata metni."""
    if provider not in PROVIDER_LABELS:
        return UNKNOWN_PROVIDER
    if not key_defined(settings, provider):
        return Translatable(KEY_MISSING, provider=PROVIDER_LABELS[provider])
    saved = current_choice(session, settings)
    saved_models = {
        AiProviderName.ANTHROPIC.value: saved.anthropic_model,
        AiProviderName.OPENAI.value: saved.openai_model,
    }
    for name, label in PROVIDER_LABELS.items():
        model_id = models[name]
        # Listede olmayan model yalnız kayıtlı olansa korunur (§D124 d); başka değer 422.
        if find_model(name, model_id) is None and model_id != saved_models[name]:
            return Translatable(UNKNOWN_MODEL, provider=label)
        effort = efforts[name]
        if effort and effort not in allowed_efforts(name, model_id):
            return Translatable(UNKNOWN_EFFORT, provider=label)
    return AiChoice(
        provider=provider,
        anthropic_model=models[AiProviderName.ANTHROPIC.value],
        anthropic_effort=efforts[AiProviderName.ANTHROPIC.value] or None,
        openai_model=models[AiProviderName.OPENAI.value],
        openai_effort=efforts[AiProviderName.OPENAI.value] or None,
    )


@router.get(AI_SETTINGS_PATH, response_class=HTMLResponse)
def ai_settings_page(
    request: Request, user: CurrentUser, session: DbSession, settings: CurrentSettings
) -> HTMLResponse:
    return _page(request, user, session, settings)


@router.post(AI_SETTINGS_PATH, response_class=HTMLResponse)
def save_ai_settings_endpoint(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    settings: CurrentSettings,
    provider: FormValue = "",
    anthropic_model: FormValue = "",
    anthropic_effort: FormValue = "",
    openai_model: FormValue = "",
    openai_effort: FormValue = "",
) -> Response:
    choice = _form_choice(
        session,
        settings,
        provider.strip(),
        {
            AiProviderName.ANTHROPIC.value: anthropic_model.strip(),
            AiProviderName.OPENAI.value: openai_model.strip(),
        },
        {
            AiProviderName.ANTHROPIC.value: anthropic_effort.strip(),
            AiProviderName.OPENAI.value: openai_effort.strip(),
        },
    )
    unprocessable = status.HTTP_422_UNPROCESSABLE_CONTENT
    if not isinstance(choice, AiChoice):
        session.rollback()
        return _page(request, user, session, settings, status_code=unprocessable, error=choice)
    first_save = load_ai_settings(session) is None
    try:
        changes = save_ai_settings(session, settings, choice, actor=user.username)
    except AiSettingsError:
        # Kurallar yukarıda denetlendi; yine de servis reddederse metni (çevrilmemiş) gösterilmez.
        session.rollback()
        return _page(request, user, session, settings, status_code=unprocessable, error=NOT_SAVED)
    if changes:
        record_event(session, EventType.AI_SETTINGS_CHANGED, actor=user.username, data=changes)
    session.commit()
    response = RedirectResponse(AI_SETTINGS_PATH, status.HTTP_303_SEE_OTHER)
    # İlk kayıt değer değiştirmese de satırı açar: ayar artık `.env`'den değil buradan gelir.
    flash(response, AI_SETTINGS_SAVED if changes or first_save else AI_SETTINGS_UNCHANGED)
    return response


@router.api_route(f"{AI_SETTINGS_PATH}/{{rest:path}}", methods=["GET", "POST"])
def ai_settings_subpath(rest: str) -> None:
    """Alt yol yoktur: her biri (sondaki eğik çizgi dahil) bilinmeyen yolla aynı 404'tür. Bu yol
    olmasa Starlette `/ai-settings/`'i 307 ile `/ai-settings`'e yönlendirir ve İK'ya adresin
    varlığını ele verirdi; root kapısı yine önce çalışır."""
    raise StarletteHTTPException(status.HTTP_404_NOT_FOUND)
