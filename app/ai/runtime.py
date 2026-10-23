"""Yapay zekâ çalışma zamanı ayarı — PRD 03.8.1, 03.8.2; PLAN.md §D124 (b).

Bütün yapay zekâ çağrılarının sağlayıcısı, modeli ve eforu tek bir girişten gelir: `active_settings`
`.env` ayarının (`Settings`) üzerine veritabanındaki tek satırlık `ai_settings`'i (varsa) yazar;
satır yoksa `.env` olduğu gibi döner ve bugünkü kurulum değişmeden çalışır. Sağlayıcıyı kuran her
yer (panel bağımlılıkları `app.web.ai_runtime`, Telegram işleyicileri, işçi) sağlayıcıyı bu ayarla
`create_provider`'dan kurar; satır her çağrıda (işçide her iş başında) yeniden okunur, bu yüzden
ayar değişikliği yeniden başlatma istemez. Kurulmuş sağlayıcı kendi ayarıyla kalır: süren çağrı
(işçide süren iş) başladığı ayarla biter.

`save_ai_settings` satırı yazar (commit etmez): aynı anda tek sağlayıcı etkindir (satırda tek
`provider` sütunu), anahtarı `.env`'de tanımsız sağlayıcı etkinleştirilemez, efor seçilen modelde
geçerli olmalıdır (`app.ai.model_list`). API anahtarı ne satıra ne dönen değişikliğe girer; hata
metinleri anahtarın hiçbir parçasını taşımaz.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.model_list import check_effort
from app.ai.provider import AnalysisProvider, create_provider
from app.config import Settings
from app.db.models import AiProviderName, AiSettings, utcnow

SINGLE_ROW_ID = 1
MAX_MODEL_LENGTH = 100  # `ai_settings.*_model` sütun uzunluğu


class AiSettingsError(ValueError):
    """Kaydedilemeyen ayar; mesaj kullanıcıya gösterilebilir (anahtar taşımaz)."""


@dataclass(frozen=True, slots=True)
class AiChoice:
    """Etkin sağlayıcı ve her sağlayıcının modeli ile eforu (`None` = sağlayıcı varsayılanı)."""

    provider: str
    anthropic_model: str
    anthropic_effort: str | None
    openai_model: str
    openai_effort: str | None


def load_ai_settings(session: Session) -> AiSettings | None:
    """Ayar satırı; yoksa `None`. Satır her çağrıda veritabanından tazelenir (başka süreç
    değiştirmiş olabilir)."""
    return session.scalars(
        select(AiSettings)
        .where(AiSettings.id == SINGLE_ROW_ID)
        .execution_options(populate_existing=True)
    ).one_or_none()


def env_choice(settings: Settings) -> AiChoice:
    """`.env`'in seçimi (satır yokken geçerli olan)."""
    return AiChoice(
        provider=settings.ai_provider,
        anthropic_model=settings.anthropic_model,
        anthropic_effort=settings.anthropic_effort,
        openai_model=settings.openai_model,
        openai_effort=settings.openai_effort,
    )


def current_choice(session: Session, settings: Settings) -> AiChoice:
    """Geçerli seçim: satır varsa satırınki, yoksa `.env`'inki."""
    row = load_ai_settings(session)
    return env_choice(settings) if row is None else _row_choice(row)


def _row_choice(row: AiSettings) -> AiChoice:
    return AiChoice(
        provider=row.provider,
        anthropic_model=row.anthropic_model,
        anthropic_effort=row.anthropic_effort,
        openai_model=row.openai_model,
        openai_effort=row.openai_effort,
    )


def apply_choice(settings: Settings, choice: AiChoice) -> Settings:
    """`settings`'in seçimi `choice` ile ezilmiş kopyası (anahtarlar ve öteki ayarlar aynen)."""
    return settings.model_copy(
        update={
            "ai_provider": choice.provider,
            "anthropic_model": choice.anthropic_model,
            "anthropic_effort": choice.anthropic_effort,
            "openai_model": choice.openai_model,
            "openai_effort": choice.openai_effort,
        }
    )


def active_settings(settings: Settings, session: Session) -> Settings:
    """Etkin yapay zekâ ayarı (modül açıklaması): satır yoksa `settings`'in kendisi."""
    row = load_ai_settings(session)
    return settings if row is None else apply_choice(settings, _row_choice(row))


def active_settings_from(settings: Settings, session_factory: sessionmaker[Session]) -> Settings:
    """`active_settings`'in kendi kısa oturumuyla okunanı (bot, işçi)."""
    with session_factory() as session:
        return active_settings(settings, session)


def create_active_provider(settings: Settings, session: Session) -> AnalysisProvider:
    """Etkin ayarla sağlayıcı; kurulamazsa `ProviderConfigError` (`create_provider`)."""
    return create_provider(active_settings(settings, session))


def key_defined(settings: Settings, provider: str) -> bool:
    """Sağlayıcının API anahtarı `.env`'de tanımlı mı (yalnız var/yok; değer okunmaz dışarı)."""
    keys: dict[str, SecretStr | None] = {
        AiProviderName.ANTHROPIC.value: settings.anthropic_api_key,
        AiProviderName.OPENAI.value: settings.openai_api_key,
    }
    key = keys.get(provider)
    return key is not None and bool(key.get_secret_value().strip())


def save_ai_settings(
    session: Session, settings: Settings, choice: AiChoice, *, actor: str
) -> dict[str, dict[str, object]]:
    """Satırı `choice`'la yazar (yoksa açar); commit etmez. Dönen sözlük değişen alanların önceki
    ve sonraki hâlidir (`{"provider": {"from": ..., "to": ...}}`); değişiklik yoksa boştur ve satıra
    yazılmaz. Geçersiz seçimde `AiSettingsError`."""
    _validate(settings, choice)
    before = current_choice(session, settings)
    changes = {
        name: {"from": old, "to": new}
        for (name, old), new in zip(asdict(before).items(), asdict(choice).values(), strict=True)
        if old != new
    }
    row = load_ai_settings(session)
    if row is not None and not changes:
        return {}
    if row is None:
        row = AiSettings(id=SINGLE_ROW_ID)
        session.add(row)
    row.provider = choice.provider
    row.anthropic_model = choice.anthropic_model
    row.anthropic_effort = choice.anthropic_effort
    row.openai_model = choice.openai_model
    row.openai_effort = choice.openai_effort
    row.updated_by = actor
    row.updated_at = utcnow()
    session.flush()
    return changes


def _validate(settings: Settings, choice: AiChoice) -> None:
    providers = {member.value for member in AiProviderName}
    if choice.provider not in providers:
        raise AiSettingsError(f"Bilinmeyen sağlayıcı '{choice.provider}'.")
    if not key_defined(settings, choice.provider):
        raise AiSettingsError(
            f"'{choice.provider}' sağlayıcısının API anahtarı .env'de tanımlı değil; "
            "etkinleştirilemez."
        )
    for provider, model, effort in (
        (AiProviderName.ANTHROPIC.value, choice.anthropic_model, choice.anthropic_effort),
        (AiProviderName.OPENAI.value, choice.openai_model, choice.openai_effort),
    ):
        if not model.strip() or len(model) > MAX_MODEL_LENGTH:
            raise AiSettingsError(f"'{provider}' modeli boş ya da çok uzun.")
        try:
            check_effort(provider, model, effort)
        except ValueError as exc:
            raise AiSettingsError(str(exc)) from None
