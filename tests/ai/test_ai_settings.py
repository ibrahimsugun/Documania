"""03.8.1 — çalışma zamanı yapay zekâ ayarı (`ai_settings`, PLAN.md §D124 b).

Satır yokken `.env` aynen geçerlidir; satır varsa sağlayıcı/model/efor bütün sağlayıcı kuran yerlere
geçer, tek sağlayıcı etkindir, anahtarı tanımsız sağlayıcı etkinleştirilemez ve işçi bir sonraki
işte yeni ayarı yeniden başlatmasız kullanır.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.runtime import (
    AiChoice,
    AiSettingsError,
    active_settings,
    current_choice,
    save_ai_settings,
)
from app.config import Settings, load_settings
from app.db.models import AiSettings, Base
from app.db.session import create_db_engine, create_session_factory
from app.storage import prepare_data_dir
from app.web import ai_runtime
from app.web.routers import catalog, output_templates, training, upload_page, uploads
from app.worker.runner import Worker

ANTHROPIC_KEY = "sk-ant-gizli-anahtar"


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'ai.db').as_posix()}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "sqlite://",
        "ai_provider": "anthropic",
        "anthropic_api_key": ANTHROPIC_KEY,
        "anthropic_model": "claude-opus-5",
        "openai_api_key": "sk-openai-gizli",
    }
    values.update(overrides)
    return load_settings(_env_file=None, **values)


def _choice(**overrides: Any) -> AiChoice:
    values: dict[str, Any] = {
        "provider": "openai",
        "anthropic_model": "claude-opus-5-5",
        "anthropic_effort": "xhigh",
        "openai_model": "gpt-6-luna",
        "openai_effort": None,
    }
    values.update(overrides)
    return AiChoice(**values)


def test_without_a_row_the_env_settings_are_used_unchanged(
    session_factory: sessionmaker[Session],
) -> None:
    settings = _settings()
    with session_factory() as session:
        assert active_settings(settings, session) is settings


def test_a_saved_row_overrides_provider_model_and_effort(
    session_factory: sessionmaker[Session],
) -> None:
    settings = _settings()
    with session_factory() as session:
        changes = save_ai_settings(session, settings, _choice(), actor="zvz")
        session.commit()

    with session_factory() as session:
        active = active_settings(settings, session)
        row = session.get_one(AiSettings, 1)
        assert session.scalar(select(func.count()).select_from(AiSettings)) == 1
    assert (active.ai_provider, active.anthropic_model, active.anthropic_effort) == (
        "openai",
        "claude-opus-5-5",
        "xhigh",
    )
    assert active.anthropic_api_key == settings.anthropic_api_key  # anahtar .env'de kalır
    assert row.updated_by == "zvz"
    assert changes["provider"] == {"from": "anthropic", "to": "openai"}
    assert "openai_model" not in changes  # değişmeyen alan yazılmaz
    assert ANTHROPIC_KEY not in str(changes)


def test_saving_the_same_choice_changes_nothing(session_factory: sessionmaker[Session]) -> None:
    settings = _settings()
    with session_factory() as session:
        save_ai_settings(session, settings, _choice(), actor="zvz")
        session.commit()
        assert save_ai_settings(session, settings, _choice(), actor="baska") == {}
        assert session.get_one(AiSettings, 1).updated_by == "zvz"


def test_a_provider_without_a_key_cannot_be_activated(
    session_factory: sessionmaker[Session],
) -> None:
    settings = _settings(openai_api_key=None)
    with session_factory() as session:
        with pytest.raises(AiSettingsError, match="openai") as raised:
            save_ai_settings(session, settings, _choice(), actor="zvz")
        assert ANTHROPIC_KEY not in str(raised.value)
        assert current_choice(session, settings).provider == "anthropic"


@pytest.mark.parametrize(
    "choice",
    [
        _choice(provider="ikisi"),
        _choice(openai_effort="high"),  # GPT-6 Luna işlevi yalnız `none` ile çağırır
        _choice(anthropic_effort="none"),
        _choice(anthropic_model=""),
    ],
    ids=["unknown-provider", "luna-high", "anthropic-none", "empty-model"],
)
def test_invalid_choices_are_rejected(
    session_factory: sessionmaker[Session], choice: AiChoice
) -> None:
    with session_factory() as session, pytest.raises(AiSettingsError):
        save_ai_settings(session, _settings(), choice, actor="zvz")


def test_only_one_row_and_one_provider_can_exist(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            AiSettings(
                id=2,
                provider="anthropic",
                anthropic_model="m",
                openai_model="m",
                updated_by="zvz",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_the_worker_uses_the_new_setting_for_its_next_job_without_restart(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    built: list[Settings] = []

    def factory(settings: Settings) -> Any:
        built.append(settings)
        return object()

    settings = _settings()
    worker = Worker(
        session_factory,
        prepare_data_dir(tmp_path / "data"),
        settings=settings,
        provider=None,  # type: ignore[arg-type]
        provider_factory=factory,
    )

    first = worker.current_provider()
    assert worker.current_provider() is first  # ayar değişmedi: aynı sağlayıcı
    with session_factory() as session:
        save_ai_settings(session, settings, _choice(), actor="zvz")
        session.commit()
    second = worker.current_provider()

    assert second is not first
    assert [s.ai_provider for s in built] == ["anthropic", "openai"]
    assert built[-1].anthropic_effort == "xhigh"


def test_every_provider_entry_point_reads_the_active_setting(
    session_factory: sessionmaker[Session],
) -> None:
    settings = _settings()
    with session_factory() as session:
        save_ai_settings(session, settings, _choice(), actor="zvz")
        session.commit()
        assert ai_runtime.active_ai_settings(settings, session).ai_provider == "openai"

    # Panelin sağlayıcı bağımlılıkları etkin ayarı alır; bot `.env`'i doğrudan kullanmaz.
    for dependency in (
        catalog.get_description_provider,
        output_templates.provider_available,
        training.get_training_provider_problem,
        upload_page.get_reanalysis_provider,
        uploads.get_analysis_provider,
    ):
        annotation = inspect.signature(dependency).parameters["settings"].annotation
        assert annotation == "ActiveAiSettings", dependency.__name__
    root = Path(__file__).resolve().parents[2] / "app" / "telegram"
    for name in ("handlers.py", "intent.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "self._provider_factory(self._settings)" not in source
        assert "active_settings_from(self._settings, self._session_factory)" in source
