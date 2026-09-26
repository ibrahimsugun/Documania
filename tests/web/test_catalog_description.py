"""11.3.1 — Belge Türleri ekranında örneklerden yapılandırılmış tür açıklaması üretilir ve
düzenlenebilir: üretilen metin formun "Analizci için açıklama" alanına yazılır, kaydedilmez; İK
düzenleyip kaydeder ve kaydedilen metin bir sonraki analizin talimatına girer.

Veri sentetiktir (`tests/fixtures/gen.py`); yapay zekâ canlı çağrılmaz (kayıtlı yanıt ya da ağsız
test sağlayıcısı). Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import (
    AnalysisProvider,
    PageAnalysisRequest,
    ProviderConfigError,
    ProviderServerError,
    TypeDescriptionRequest,
    validate_type_description,
)
from app.ai.anthropic_provider import AnthropicProvider
from app.ai.prompts import build_page_analysis_instructions
from app.ai.recording_provider import RecordingProvider
from app.catalog import export_catalog, load_record
from app.catalog.describe import MAX_DESCRIPTION_PAGES, format_description
from app.config import Settings
from app.db.models import (
    Document,
    Event,
    ExampleFileRecord,
    ExampleLabel,
    KnownDocumentType,
    Upload,
    UploadFile,
)
from app.storage import DataLayout, sha256_file
from app.web.routers.catalog import get_description_provider
from tests.ai.payloads import description_payload
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes

SLUG = "sample_card"
EDIT_URL = f"/document-types/{SLUG}"
DESCRIBE_URL = f"/document-types/{SLUG}/description"
ROOT = Path(__file__).resolve().parents[2]
RECORDING = ROOT / "tests" / "fixtures" / "ai" / "type_descriptions" / "passport"
RECORDED_TEXT = format_description(
    validate_type_description((RECORDING / "0.json").read_text("utf-8"))
)


class DescribingProvider(AnalysisProvider):
    """Ağsız test sağlayıcısı: tür açıklaması isteğini saklar, verilen yanıtı/hatayı döner."""

    name = "aciklayan"

    def __init__(self, response: object) -> None:
        super().__init__(model="aciklayan-model")
        self.response = response
        self.descriptions: list[TypeDescriptionRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        self.descriptions.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _form(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "slug": SLUG,
        "name": "Sample Card",
        "file_label": "Sample Card",
        "country": "RS",
        "expected_file_types": ["pdf", "jpeg"],
        "pages_min": "1",
        "pages_max": "2",
        "sides": "single",
        "analyze": "on",
        "required_fields": "surname, document_number",
        "allowed_conversions": ["merge"],
        "output_format": "pdf",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


@pytest.fixture(autouse=True)
def sample_type(client: TestClient) -> None:
    response = client.post("/document-types", data=_form(), follow_redirects=False)
    assert response.status_code == 303, response.text


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    calls: list[float] = []
    monkeypatch.setattr("app.ai.provider.time.sleep", calls.append)
    return calls


@pytest.fixture
def recorded(app: FastAPI) -> RecordingProvider:
    provider = RecordingProvider.from_directory(RECORDING)
    app.dependency_overrides[get_description_provider] = lambda: provider
    return provider


def _use(app: FastAPI, response: object) -> DescribingProvider:
    provider = DescribingProvider(response)
    app.dependency_overrides[get_description_provider] = lambda: provider
    return provider


def _upload_examples(client: TestClient, *files: tuple[str, bytes]) -> None:
    response = client.post(
        f"{EDIT_URL}/examples",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )
    assert response.status_code == 200, response.text


def _field_value(page: str, name: str) -> str:
    match = re.search(rf'name="{name}" value="([^"]*)"', page)
    assert match, f"{name} alanı yok"
    return html.unescape(match.group(1))


def _saved_description(session_factory: sessionmaker[Session]) -> object:
    with session_factory() as session:
        return load_record(session, SLUG)["prompt_description"]


def _row_counts(session_factory: sessionmaker[Session]) -> dict[str, int]:
    with session_factory() as session:
        return {
            model.__name__: session.scalar(select(func.count()).select_from(model)) or 0
            for model in (Upload, UploadFile, Document, Event, KnownDocumentType)
        }


def _files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --- düğme ---------------------------------------------------------------------------------------


def test_edit_page_offers_generation_only_when_the_type_has_examples(client: TestClient) -> None:
    button = f'formaction="{DESCRIBE_URL}"'

    assert button not in client.get(EDIT_URL).text
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))

    page = client.get(EDIT_URL).text
    assert button in page
    assert "Örneklerden açıklama üret" in page
    # "Kaydet" formun ilk düğmesidir: Enter tuşu açıklama üretmez, kaydeder.
    assert page.index(">Kaydet</button>") < page.index(button)
    assert button not in client.get("/document-types/new").text


def test_types_that_are_not_analyzed_offer_no_generation(client: TestClient) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    response = client.post(
        EDIT_URL, data=_form(analyze=None, required_fields=""), follow_redirects=False
    )
    assert response.status_code == 303, response.text

    assert f'formaction="{DESCRIBE_URL}"' not in client.get(EDIT_URL).text


# --- üretim ve düzenleme -------------------------------------------------------------------------


def test_generated_description_fills_the_field_and_is_not_saved(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    recorded: RecordingProvider,
) -> None:
    _upload_examples(
        client, ("sablon.pdf", make_pdf_bytes(2)), ("foto.png", make_half_filled_image_bytes("PNG"))
    )
    rows, files = _row_counts(session_factory), _files(layout.root)

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 200, response.text
    page = response.text
    assert _field_value(page, "prompt_description") == RECORDED_TEXT
    assert "Henüz kaydedilmedi" in page
    assert 'id="description"' in page
    # Yapılandırılmış hâli ayrıca gösterilir.
    assert "<dt>Başlıklar</dt>" in page and "ПАСПОРТ / PASSPORT" in page
    assert "<code>given_names</code> — soyadı satırının altında" in page
    assert "2 satır, sayfanın altında, eş aralıklı yazıyla" in page
    assert "Kiril, Latin" in page
    assert (
        "<code>foto.png</code> (s. 1), <code>sablon.pdf</code> (s. 1), "
        "<code>sablon.pdf</code> (s. 2)." in page
    )
    (request,) = recorded.description_requests
    assert len(request.images) == 3
    # Hiçbir şey kaydedilmez: tür, satırlar ve veri dizini aynı.
    assert _saved_description(session_factory) is None
    assert _row_counts(session_factory) == rows
    assert _files(layout.root) == files


def test_the_generated_text_can_be_edited_and_saved_for_the_next_analysis(
    client: TestClient, session_factory: sessionmaker[Session], recorded: RecordingProvider
) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    generated = _field_value(client.post(DESCRIBE_URL, data=_form()).text, "prompt_description")
    edited = generated.replace("Tek sayfalık pasaport", "Tek sayfalık örnek kart")

    response = client.post(EDIT_URL, data=_form(prompt_description=edited), follow_redirects=False)

    assert response.status_code == 303, response.text
    assert _saved_description(session_factory) == edited
    assert _field_value(client.get(EDIT_URL).text, "prompt_description") == edited
    with session_factory() as session:
        instructions = build_page_analysis_instructions(export_catalog(session)).text
    assert edited in instructions


def test_unsaved_form_values_are_kept_and_used_for_the_request(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    provider = _use(app, description_payload())

    response = client.post(
        DESCRIBE_URL,
        data=_form(
            name="Sample Card v2",
            country="",
            required_fields="surname, expiry_date",
            acceptance_criteria=["Kenarlar görünür"],
            prompt_description="eski metin",
        ),
    )

    assert response.status_code == 200, response.text
    page = response.text
    assert _field_value(page, "name") == "Sample Card v2"
    assert 'value="Kenarlar görünür"' in page
    assert _field_value(page, "prompt_description") != "eski metin"
    (request,) = provider.descriptions
    assert "Belge türü: Sample Card v2 (`sample_card`)" in request.prompt
    assert "Ülke: belirtilmemiş" in request.prompt
    assert "Zorunlu alanlar: surname, expiry_date" in request.prompt
    assert "sablon" not in request.prompt
    with session_factory() as session:
        assert load_record(session, SLUG)["name"] == "Sample Card"


def test_slug_comes_from_the_address_not_the_form(app: FastAPI, client: TestClient) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    provider = _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form(slug="baska_tur"))

    assert response.status_code == 200, response.text
    assert "(`sample_card`)" in provider.descriptions[0].prompt


# --- üretilemeyen durumlar: hiçbir şey kaydedilmez ------------------------------------------------


def test_invalid_form_is_rejected_before_any_request(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    provider = _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form(sides="front_back", prompt_description="x"))

    assert response.status_code == 422
    assert "Açıklama üretilmedi: önce alanların altındaki uyarıları düzeltin." in response.text
    assert _field_value(response.text, "prompt_description") == "x"
    assert provider.descriptions == []
    assert _saved_description(session_factory) is None


def test_type_without_examples_is_not_described(app: FastAPI, client: TestClient) -> None:
    provider = _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 422
    assert "bu türün açılabilen örneği yok" in response.text
    assert provider.descriptions == []


def test_unreadable_examples_are_named_in_the_error(
    app: FastAPI, client: TestClient, layout: DataLayout
) -> None:
    directory = layout.type_examples_dir(SLUG)
    directory.mkdir(parents=True)
    (directory / "bozuk.pdf").write_bytes(b"%PDF-1.4 bozuk")
    provider = _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 422
    assert "&#39;bozuk.pdf&#39; dosyası açılamadı; bozuk olabilir." in response.text
    assert provider.descriptions == []


def test_skipped_examples_are_reported_next_to_a_generated_description(
    app: FastAPI, client: TestClient, layout: DataLayout
) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    (layout.type_examples_dir(SLUG) / "zz-bozuk.png").write_bytes(b"\x89PNG\r\n\x1a\nbozuk")
    _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 200
    assert "Açılamayan örnekler atlandı" in response.text
    assert "zz-bozuk.png" in response.text


def test_page_limit_is_reported(app: FastAPI, client: TestClient) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(MAX_DESCRIPTION_PAGES + 1)))
    provider = _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 200
    assert len(provider.descriptions[0].images) == MAX_DESCRIPTION_PAGES
    assert f"Sınır ({MAX_DESCRIPTION_PAGES} sayfa) yüzünden 1 sayfa gönderilmedi." in response.text


def _label(session_factory: sessionmaker[Session], name: str, label: ExampleLabel) -> None:
    """Örneğe eğitim modunun kaydını ve etiketini verir (11.9)."""
    with session_factory() as session:
        session.add(
            ExampleFileRecord(
                type_slug=SLUG,
                name=name,
                sha256="0" * 63 + str(len(name) % 10),
                method="ai",
                label=label.value,
            )
        )
        session.commit()


def test_unverified_ai_decision_examples_are_left_out_and_counted(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """11.9.4: doğrulanmamış "AI kararı" örneği açıklama üretimine girmez; dışlanan sayı sonuçta
    yazar. Doğrulanmış örnek girer."""
    _upload_examples(
        client, ("sablon.pdf", make_pdf_bytes(1)), ("foto.png", make_half_filled_image_bytes("PNG"))
    )
    _label(session_factory, "foto.png", ExampleLabel.AI_DECISION)
    _label(session_factory, "sablon.pdf", ExampleLabel.VERIFIED)
    provider = _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 200, response.text
    assert len(provider.descriptions[0].images) == 1
    assert "<code>sablon.pdf</code> (s. 1)." in response.text
    assert "<code>foto.png</code>" not in response.text
    assert '1 "AI kararı" örneği İK doğrulamadığı için açıklama üretimine girmedi.' in (
        response.text
    )


def test_only_unverified_ai_decisions_leave_nothing_to_describe(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload_examples(client, ("foto.png", make_half_filled_image_bytes("PNG")))
    _label(session_factory, "foto.png", ExampleLabel.AI_DECISION)
    provider = _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 422
    assert "İK doğrulamadığı için açıklama üretimine girmedi" in response.text
    assert provider.descriptions == []


def test_not_analyzed_type_in_the_form_is_refused(app: FastAPI, client: TestClient) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    provider = _use(app, description_payload())

    response = client.post(DESCRIBE_URL, data=_form(analyze=None, required_fields=""))

    assert response.status_code == 422
    assert "analiz edilmeyen türün açıklaması analizde kullanılmaz" in response.text
    assert provider.descriptions == []


def test_provider_that_cannot_be_set_up_gives_503(app: FastAPI, client: TestClient) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    app.dependency_overrides[get_description_provider] = lambda: ProviderConfigError(
        "ANTHROPIC_API_KEY tanımlı olmalı."
    )

    response = client.post(DESCRIBE_URL, data=_form(prompt_description="eski"))

    assert response.status_code == 503
    assert "yapay zekâ sağlayıcısı kurulamadı. ANTHROPIC_API_KEY tanımlı olmalı." in response.text
    assert _field_value(response.text, "prompt_description") == "eski"


def test_provider_failure_gives_502(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], no_sleep: list[float]
) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    _use(app, ProviderServerError("Anthropic isteği başarısız: HTTP 529", status_code=529))

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 502
    assert "yanıt vermedi (Anthropic isteği başarısız: HTTP 529)" in response.text
    assert _saved_description(session_factory) is None


def test_non_conforming_response_gives_502(app: FastAPI, client: TestClient) -> None:
    _upload_examples(client, ("sablon.pdf", make_pdf_bytes(1)))
    _use(app, description_payload(layout=None))

    response = client.post(DESCRIBE_URL, data=_form())

    assert response.status_code == 502
    assert "tür açıklaması şemasına uymadı" in response.text


def test_unknown_type_is_404(app: FastAPI, client: TestClient) -> None:
    provider = _use(app, description_payload())

    response = client.post("/document-types/olmayan_tur/description", data=_form())

    assert response.status_code == 404
    assert provider.descriptions == []


# --- sağlayıcı bağımlılığı -----------------------------------------------------------------------


def test_description_provider_is_the_configured_one() -> None:
    configured = Settings(_env_file=None, database_url="sqlite://", anthropic_api_key="test-key")

    assert isinstance(get_description_provider(configured), AnthropicProvider)


def test_description_provider_error_is_returned_not_raised() -> None:
    unknown = Settings(_env_file=None, database_url="sqlite://", ai_provider="bilinmeyen")

    assert isinstance(get_description_provider(unknown), ProviderConfigError)
