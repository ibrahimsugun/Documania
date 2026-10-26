"""10.1.10 — yapay zekâ ayarları sayfası yalnız root (PLAN.md §D124 a, c, e, f).

Root sağlayıcı başına kartı görür (anahtar yalnız tanımlı/tanımsız), tek adımda kaydeder; İK ve
Kullanıcı için adres ve `POST` bilinmeyen yolla aynı 404'tür, bağlantı hiçbir sayfalarında yoktur.
Kaydet tek etkin sağlayıcıyı, anahtarsız sağlayıcıyı, bilinmeyen model ve eforu sunucuda denetler;
`AI_SETTINGS_CHANGED` olayı değişen alanların `from`/`to` hâlini taşır, anahtarı taşımaz. Sahte
anahtarlar hiçbir yanıtta, olayda ya da satırda geçmez. Kaydedilen ayar bir sonraki yapay zekâ
çağrısının sağlayıcısını kurar (tm 188 servisi). Ağ yok; canlı yapay zekâ çağrısı yok.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.runtime import create_active_provider
from app.config import Settings, get_settings, load_settings
from app.db.models import AiSettings, Event, UserRole
from app.events import EventType
from app.web.auth import PanelUser, get_current_user
from app.web.feedback import AI_SETTINGS_SAVED, AI_SETTINGS_UNCHANGED
from tests.web import test_translation_sweep as sweep
from tests.web.conftest import SIGNED_IN
from tests.web.flash import flashed, toasts

world = sweep.world

ANTHROPIC_KEY = "sk-ant-sahte-anahtar-1189"
OPENAI_KEY = "sk-openai-sahte-anahtar-2289"
HR = SIGNED_IN
READER = PanelUser(SIGNED_IN.id, SIGNED_IN.username, UserRole.USER.value)
ROOT = PanelUser(SIGNED_IN.id, "Zvz", UserRole.ROOT.value)
PATH = "/ai-settings"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "sqlite://",
        "ai_provider": "anthropic",
        "anthropic_api_key": ANTHROPIC_KEY,
        "anthropic_model": "claude-opus-5",
        "openai_api_key": OPENAI_KEY,
        "openai_model": "gpt-6.1-sol",
    }
    values.update(overrides)
    return load_settings(_env_file=None, **values)


def _use(app: FastAPI, user: PanelUser, settings: Settings | None = None) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    resolved = settings or _settings()
    app.dependency_overrides[get_settings] = lambda: resolved


def _form(**overrides: str) -> dict[str, str]:
    values = {
        "provider": "openai",
        "anthropic_model": "claude-opus-5-5",
        "anthropic_effort": "xhigh",
        "openai_model": "gpt-6.1-sol",
        "openai_effort": "",
    }
    values.update(overrides)
    return values


def _events(session_factory: sessionmaker[Session]) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(select(Event).where(Event.type == EventType.AI_SETTINGS_CHANGED.value))
        )


def _row(session_factory: sessionmaker[Session]) -> AiSettings | None:
    with session_factory() as session:
        return session.get(AiSettings, 1)


def _no_key(*texts: str) -> None:
    for text in texts:
        for key in (ANTHROPIC_KEY, OPENAI_KEY):
            assert key not in text
            assert key[-8:] not in text


# --- gizlilik (10.1.9 kalıbı) -------------------------------------------------------------------


@pytest.mark.parametrize("user", [HR, READER], ids=["hr", "user"])
def test_hr_and_user_get_the_unknown_path_404_on_every_method(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], user: PanelUser
) -> None:
    unknown_get = client.get("/olmayan-bir-yol")
    unknown_post = client.post("/olmayan-bir-yol", data=_form())
    _use(app, user)

    for path in (PATH, f"{PATH}?x=1", f"{PATH}/", f"{PATH}/alt-yol"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 404, path
        assert response.json() == unknown_get.json(), path
    response = client.post(PATH, data=_form())
    assert (response.status_code, response.json()) == (404, unknown_post.json())
    # Bilinmeyen yol gibi bildirim çerezi de yok.
    assert flashed(response) is None and flashed(unknown_post) is None
    assert _row(session_factory) is None and _events(session_factory) == []


@pytest.mark.parametrize("user", [HR, READER], ids=["hr", "user"])
def test_no_page_hr_or_user_sees_mentions_the_ai_settings(
    app: FastAPI, client: TestClient, world: dict[str, object], user: PanelUser
) -> None:
    _use(app, user)
    seen = 0
    for addresses in sweep.PAGES.values():
        for template, _expected in addresses:
            response = client.get(template.format(**world), follow_redirects=False)
            if response.status_code >= 300 and response.status_code < 400:
                continue
            assert PATH not in response.text, template
            assert "Yapay zekâ ayarları" not in response.text, template
            seen += 1
    assert seen > 40


def test_root_sees_the_link_in_its_navigation(app: FastAPI, client: TestClient) -> None:
    _use(app, ROOT)
    nav = client.get("/employees").text.split('<form class="session"', 1)[0]
    assert 'class="tool-link" href="/ai-settings">Yapay zekâ ayarları</a>' in nav

    page = client.get(PATH).text
    assert (
        '<a class="tool-link active" href="/ai-settings" aria-current="page">'
        "Yapay zekâ ayarları</a>"
    ) in page


# --- sayfa --------------------------------------------------------------------------------------


def test_without_a_row_the_page_shows_the_env_values_and_a_not_saved_note(
    app: FastAPI, client: TestClient
) -> None:
    _use(app, ROOT, _settings(openai_api_key=None))
    response = client.get(PATH)

    assert response.status_code == 200
    html = response.text
    assert "Ayar henüz kaydedilmedi" in html
    anthropic, openai = html.split('<section class="ai-provider"')[1:3]
    assert "Tanımlı" in anthropic and "Etkin</span>" in anthropic
    assert 'value="anthropic" form="ai-settings-form" checked>' in anthropic
    assert '<option value="claude-opus-5" translate="no" selected>' in anthropic
    assert "Tanımsız" in openai and "Pasif</span>" in openai
    assert 'value="openai" form="ai-settings-form" disabled>' in openai
    # Efor: "varsayılan" + modelin kümesi; Sol'da `low`–`max` (`none` yok).
    assert '<option value="" selected>Varsayılan (high)</option>' in anthropic
    assert re.findall(r'<option value="(\w+)" translate="no"', openai.split("effort")[-1]) == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    _no_key(html)


def test_an_unlisted_model_from_env_is_kept_selected_with_a_warning(
    app: FastAPI, client: TestClient
) -> None:
    _use(app, ROOT, _settings(anthropic_model="claude-ozel-model"))
    html = client.get(PATH).text

    assert '<option value="claude-ozel-model" translate="no" selected>' in html
    assert "Bu model listede yok" in html


# --- kaydet -------------------------------------------------------------------------------------


def test_saving_writes_one_active_provider_an_event_and_a_notice(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _use(app, ROOT)
    response = client.post(PATH, data=_form(), follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == PATH
    assert flashed(response) == (AI_SETTINGS_SAVED, {})
    row = _row(session_factory)
    assert row is not None
    assert (row.provider, row.anthropic_model, row.anthropic_effort) == (
        "openai",
        "claude-opus-5-5",
        "xhigh",
    )
    assert row.updated_by == "Zvz"
    (event,) = _events(session_factory)
    assert event.actor == "Zvz"
    assert event.document_id is None and event.employee_id is None
    assert event.data_json == {
        "provider": {"from": "anthropic", "to": "openai"},
        "anthropic_model": {"from": "claude-opus-5", "to": "claude-opus-5-5"},
        "anthropic_effort": {"from": None, "to": "xhigh"},
    }
    page = client.get(PATH).text
    assert "Ayar henüz kaydedilmedi" not in page
    openai = page.split('<section class="ai-provider"')[2]
    assert 'value="openai" form="ai-settings-form" checked>' in openai
    # Tek etkin: Anthropic kartı pasif.
    assert "Pasif</span>" in page.split('<section class="ai-provider"')[1]
    _no_key(page, response.text, str(event.data_json))


def test_saving_the_same_choice_again_writes_no_event(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _use(app, ROOT)
    client.post(PATH, data=_form())
    again = client.post(PATH, data=_form(), follow_redirects=False)

    assert flashed(again) == (AI_SETTINGS_UNCHANGED, {})
    assert len(_events(session_factory)) == 1


def test_switching_back_is_one_step_too(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _use(app, ROOT)
    client.post(PATH, data=_form())
    client.post(PATH, data=_form(provider="anthropic"))

    row = _row(session_factory)
    assert row is not None and row.provider == "anthropic"
    assert _events(session_factory)[-1].data_json == {
        "provider": {"from": "openai", "to": "anthropic"}
    }


@pytest.mark.parametrize(
    ("form", "message"),
    [
        (_form(provider="gemini"), "Bilinmeyen sağlayıcı."),
        (_form(provider=""), "Bilinmeyen sağlayıcı."),
        (_form(anthropic_model="claude-yok"), "Anthropic için seçilen model listede yok."),
        (_form(openai_model="gpt-yok"), "OpenAI için seçilen model listede yok."),
        (_form(anthropic_effort="extreme"), "Seçilen efor Anthropic modelinde kullanılamaz."),
        # Sol `none` eforunu 400 ile reddeder (§D127).
        (_form(openai_effort="none"), "Seçilen efor OpenAI modelinde kullanılamaz."),
    ],
    ids=[
        "provider",
        "empty-provider",
        "anthropic-model",
        "openai-model",
        "effort",
        "sol-none-effort",
    ],
)
def test_unknown_values_are_refused_with_422_and_nothing_changes(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    form: dict[str, str],
    message: str,
) -> None:
    _use(app, ROOT)
    response = client.post(PATH, data=form)

    assert response.status_code == 422
    assert message in response.text
    assert toasts(response.text)  # 10.11.1: başarısız kayıt da bildirim taşır
    assert _row(session_factory) is None and _events(session_factory) == []
    _no_key(response.text)


def test_a_provider_without_a_key_cannot_be_enabled(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _use(app, ROOT, _settings(openai_api_key=None))
    response = client.post(PATH, data=_form(provider="openai"))

    assert response.status_code == 422
    assert "OpenAI sağlayıcısının API anahtarı" in response.text
    assert _row(session_factory) is None and _events(session_factory) == []


def test_the_unlisted_saved_model_is_kept_but_another_unlisted_one_is_refused(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _use(app, ROOT, _settings(anthropic_model="claude-ozel-model"))

    kept = client.post(PATH, data=_form(provider="anthropic", anthropic_model="claude-ozel-model"))
    other = client.post(PATH, data=_form(anthropic_model="claude-baska-model"))

    assert kept.status_code == 200 and other.status_code == 422
    row = _row(session_factory)
    assert row is not None and row.anthropic_model == "claude-ozel-model"


def test_the_saved_setting_builds_the_next_ai_call(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    settings = _settings()
    _use(app, ROOT, settings)
    with session_factory() as session:
        assert isinstance(create_active_provider(settings, session), AnthropicProvider)

    client.post(PATH, data=_form())

    with session_factory() as session:
        provider = create_active_provider(settings, session)
    assert isinstance(provider, OpenAIProvider)
    client.post(PATH, data=_form(provider="anthropic", anthropic_effort="low"))
    with session_factory() as session:
        provider = create_active_provider(settings, session)
    assert isinstance(provider, AnthropicProvider)
    assert (provider.model, provider.effort) == ("claude-opus-5-5", "low")
