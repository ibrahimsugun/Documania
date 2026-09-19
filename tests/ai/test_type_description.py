"""11.3.1 — tür açıklaması sözleşmesi, sağlayıcının ortak `describe_type` adımı, kayıtlı yanıt
sağlayıcısı ve talimat metni.

Yapay zekâ canlı çağrılmaz: sağlayıcılar ağsız test sınıfları ya da kayıtlı yanıttır.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.ai import (
    AnalysisProvider,
    PageAnalysisRequest,
    PageImage,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderServerError,
    Script,
    TypeDescription,
    TypeDescriptionError,
    TypeDescriptionRequest,
    validate_type_description,
)
from app.ai.prompts import load_type_description_instructions
from app.ai.provider import MAX_ANALYSIS_ATTEMPTS, RETRY_BACKOFF_SECONDS
from app.ai.recording_provider import RecordingExhaustedError, RecordingProvider
from app.ai.type_description import MAX_FIELD_LOCATIONS, MAX_HEADINGS
from tests.ai.payloads import (
    SYNTHETIC_DOCUMENT_NUMBER,
    SYNTHETIC_SURNAME,
    analysis_payload,
    description_payload,
    description_request,
    page_request,
)
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTIONS = ROOT / "tests" / "fixtures" / "ai" / "type_descriptions"


class DescribingProvider(AnalysisProvider):
    """Ağsız test sağlayıcısı: tür açıklaması isteklerine sırayla verilen yanıtı/hatayı döner."""

    name = "aciklayan"

    def __init__(self, *responses: object) -> None:
        super().__init__(model="aciklayan-model")
        self._responses = list(responses)
        self.descriptions: list[TypeDescriptionRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        self.descriptions.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AnalysisOnlyProvider(AnalysisProvider):
    """Tür açıklamasını uygulamayan sağlayıcı (varsayılan davranış)."""

    name = "yalniz-analiz"

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        return analysis_payload()


# --- Sözleşme ------------------------------------------------------------------------------------


def test_payload_is_accepted_from_object_and_json_text() -> None:
    payload = description_payload()

    from_object = validate_type_description(payload)
    from_text = validate_type_description(json.dumps(payload, ensure_ascii=False))

    assert from_object == from_text
    assert from_object.layout.startswith("Pasaport kimlik sayfası")
    assert from_object.headings == ("ПАСПОРТ", "PASSPORT")
    assert from_object.languages == ("ru", "en")
    assert from_object.scripts == (Script.CYRILLIC, Script.LATIN)
    assert [item.field for item in from_object.field_locations] == ["surname", "document_number"]
    assert from_object.mrz is not None
    assert (from_object.mrz.line_count, from_object.mrz.location) == (2, "sayfanın altında")
    assert from_object.side_differences is None


def test_empty_lists_and_nulls_are_a_valid_description() -> None:
    description = validate_type_description(
        description_payload(headings=[], languages=[], scripts=[], field_locations=[], mrz=None)
    )

    assert description.headings == description.languages == description.scripts == ()
    assert description.field_locations == ()
    assert description.mrz is None


def test_text_is_stripped() -> None:
    description = validate_type_description(
        description_payload(layout="  Kart, yatay  ", side_differences=" Arkada MRZ ")
    )

    assert description.layout == "Kart, yatay"
    assert description.side_differences == "Arkada MRZ"


def test_the_accepted_photo_definition_is_optional_short_text() -> None:
    # 11.8.1: fotoğraf türünde şirketin kabul ettiği fotoğrafın tanımı; öteki türlerde `null`.
    described = validate_type_description(
        description_payload(accepted_photo="  Omuzdan yukarı, düz açık arka plan  ")
    )

    assert described.accepted_photo == "Omuzdan yukarı, düz açık arka plan"
    assert validate_type_description(description_payload()).accepted_photo is None


def test_a_validated_model_is_revalidated() -> None:
    description = validate_type_description(description_payload())

    assert validate_type_description(description) == description


@pytest.mark.parametrize(
    ("change", "location"),
    [
        ({"layout": None}, "layout"),
        ({"layout": "   "}, "layout"),
        ({"layout": "x" * 201}, "layout"),
        ({"headings": ["A", "B", "C", "D", "E"]}, "headings"),
        ({"headings": ["PASSPORT", "passport"]}, "headings"),
        ({"headings": ["x" * 61]}, "headings.0"),
        ({"languages": ["xx"]}, "languages.0"),
        ({"languages": ["RU"]}, "languages.0"),
        ({"languages": ["ru", "ru"]}, "languages"),
        ({"scripts": ["greek"]}, "scripts.0"),
        ({"scripts": ["latin", "latin"]}, "scripts"),
        ({"field_locations": [{"field": "Surname", "location": "üstte"}]}, "field_locations.0"),
        ({"field_locations": [{"field": "surname"}]}, "field_locations.0.location"),
        (
            {"field_locations": [{"field": "surname", "location": "üstte", "value": "X"}]},
            "field_locations.0.value",
        ),
        (
            {
                "field_locations": [
                    {"field": "surname", "location": "üstte"},
                    {"field": "surname", "location": "altta"},
                ]
            },
            "yanıt",
        ),
        (
            {
                "field_locations": [
                    {"field": f"field_{index}", "location": "üstte"}
                    for index in range(MAX_FIELD_LOCATIONS + 1)
                ]
            },
            "field_locations",
        ),
        ({"mrz": {"line_count": 1, "location": "altta"}}, "mrz.line_count"),
        ({"mrz": {"line_count": 4, "location": "altta"}}, "mrz.line_count"),
        ({"mrz": {"line_count": "2", "location": "altta"}}, "mrz.line_count"),
        ({"mrz": {"line_count": True, "location": "altta"}}, "mrz.line_count"),
        ({"mrz": {"line_count": 2}}, "mrz.location"),
        ({"side_differences": ""}, "side_differences"),
        ({"accepted_photo": " "}, "accepted_photo"),
        ({"accepted_photo": "x" * 201}, "accepted_photo"),
        ({"accepted_photo": ["Sade arka plan"]}, "accepted_photo"),
        ({"notes": "fazladan"}, "notes"),
    ],
    ids=[
        "duzen-yok",
        "duzen-bos",
        "duzen-uzun",
        "cok-baslik",
        "tekrar-baslik",
        "uzun-baslik",
        "dil-bilinmeyen",
        "dil-buyuk-harf",
        "dil-tekrar",
        "alfabe-bilinmeyen",
        "alfabe-tekrar",
        "alan-adi-bicimi",
        "alan-yeri-yok",
        "alan-fazladan-anahtar",
        "alan-tekrar",
        "cok-alan",
        "mrz-bir-satir",
        "mrz-dort-satir",
        "mrz-metin",
        "mrz-bool",
        "mrz-yeri-yok",
        "yuz-farki-bos",
        "kabul-fotografi-bos",
        "kabul-fotografi-uzun",
        "kabul-fotografi-liste",
        "tanimsiz-anahtar",
    ],
)
def test_non_conforming_payload_is_rejected_with_location(
    change: dict[str, Any], location: str
) -> None:
    with pytest.raises(TypeDescriptionError) as caught:
        validate_type_description(description_payload(**change))

    assert any(problem.startswith(location) for problem in caught.value.problems), (
        caught.value.problems
    )


@pytest.mark.parametrize(
    "key",
    [
        "layout",
        "headings",
        "languages",
        "scripts",
        "field_locations",
        "mrz",
        "side_differences",
        "accepted_photo",
    ],
)
def test_every_key_is_required(key: str) -> None:
    payload = description_payload()
    del payload[key]

    with pytest.raises(TypeDescriptionError) as caught:
        validate_type_description(payload)

    assert any(problem.startswith(key) for problem in caught.value.problems)


@pytest.mark.parametrize("text", ['{"layout": "Kart"', "açıklama", "[]"], ids=str)
def test_text_that_is_not_a_json_object_is_rejected(text: str) -> None:
    with pytest.raises(TypeDescriptionError):
        validate_type_description(text)


def test_rejection_does_not_echo_values_from_the_response() -> None:
    # Örnekteki kişisel değer yanıta sızmışsa hata mesajına taşınmaz (CONVENTIONS §6).
    payload = description_payload(
        headings=[SYNTHETIC_SURNAME, SYNTHETIC_SURNAME.lower()],
        languages=[SYNTHETIC_DOCUMENT_NUMBER],
    )

    with pytest.raises(TypeDescriptionError) as caught:
        validate_type_description(payload)

    assert SYNTHETIC_SURNAME not in str(caught.value)
    assert SYNTHETIC_DOCUMENT_NUMBER not in str(caught.value)


def test_json_schema_requires_every_key_and_forbids_others() -> None:
    schema = TypeDescription.model_json_schema()

    assert set(schema["required"]) == set(schema["properties"]) == set(TypeDescription.model_fields)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["headings"]["maxItems"] == MAX_HEADINGS


# --- İstek --------------------------------------------------------------------------------------


def test_request_keeps_images_in_order_and_hides_text_from_repr() -> None:
    first = PageImage(make_half_filled_image_bytes("JPEG"))
    second = PageImage(make_half_filled_image_bytes("PNG"))

    request = TypeDescriptionRequest(
        images=[first, second],  # type: ignore[arg-type]
        instructions="GIZLI TALIMAT",
        prompt=SYNTHETIC_SURNAME,
    )

    assert request.images == (first, second)
    assert "GIZLI TALIMAT" not in repr(request)
    assert SYNTHETIC_SURNAME not in repr(request)


@pytest.mark.parametrize(
    ("changes", "error", "message"),
    [
        ({"images": ()}, ValueError, "en az bir"),
        ({"images": (make_half_filled_image_bytes("JPEG"),)}, TypeError, "PageImage"),
        ({"instructions": "  "}, ValueError, "instructions"),
        ({"prompt": ""}, ValueError, "prompt"),
    ],
    ids=["goruntu-yok", "ham-bayt", "talimat-bos", "metin-bos"],
)
def test_request_rejects_invalid_values(
    changes: dict[str, Any], error: type[Exception], message: str
) -> None:
    values: dict[str, Any] = {
        "images": (PageImage(make_half_filled_image_bytes("JPEG")),),
        "instructions": "Talimat",
        "prompt": "Metin",
    }
    values.update(changes)

    with pytest.raises(error, match=message):
        TypeDescriptionRequest(**values)


def test_page_image_still_rejects_pdf_bytes() -> None:
    with pytest.raises(ValueError, match="JPEG veya PNG"):
        PageImage(make_pdf_bytes())


# --- Ortak adım: describe_type -----------------------------------------------------------------


def test_describe_type_returns_validated_description() -> None:
    provider = DescribingProvider(description_payload())
    request = description_request(images=2)

    description = provider.describe_type(request)

    assert isinstance(description, TypeDescription)
    assert description == validate_type_description(description_payload())
    assert provider.descriptions == [request]


def test_describe_type_rejects_non_conforming_response_without_retry(
    no_sleep: list[float],
) -> None:
    provider = DescribingProvider(description_payload(layout=None), description_payload())

    with pytest.raises(TypeDescriptionError):
        provider.describe_type(description_request())

    assert len(provider.descriptions) == 1
    assert no_sleep == []


@pytest.mark.parametrize(
    "error",
    [
        ProviderRateLimitError("429", status_code=429),
        ProviderServerError("529", status_code=529),
    ],
    ids=["hiz-siniri", "sunucu"],
)
def test_describe_type_retries_rate_limit_and_server_errors(
    error: ProviderError, no_sleep: list[float]
) -> None:
    provider = DescribingProvider(error, error, description_payload())

    description = provider.describe_type(description_request())

    assert description.layout
    assert len(provider.descriptions) == 3
    assert no_sleep == [RETRY_BACKOFF_SECONDS, RETRY_BACKOFF_SECONDS * 2]


def test_describe_type_gives_up_after_max_attempts(no_sleep: list[float]) -> None:
    error = ProviderServerError("503", status_code=503)
    provider = DescribingProvider(*([error] * MAX_ANALYSIS_ATTEMPTS))

    with pytest.raises(ProviderServerError):
        provider.describe_type(description_request())

    assert len(provider.descriptions) == MAX_ANALYSIS_ATTEMPTS


def test_describe_type_does_not_retry_permanent_errors(no_sleep: list[float]) -> None:
    provider = DescribingProvider(ProviderConnectionError("yok"), description_payload())

    with pytest.raises(ProviderConnectionError):
        provider.describe_type(description_request())

    assert len(provider.descriptions) == 1
    assert no_sleep == []


def test_provider_without_description_support_raises_provider_error() -> None:
    provider = AnalysisOnlyProvider(model="m")

    with pytest.raises(ProviderError, match="tür açıklaması üretmiyor"):
        provider.describe_type(description_request())
    # Sayfa analizi etkilenmez.
    assert provider.analyze_page(page_request()).page_index == 0


# --- Kayıtlı yanıt sağlayıcısı -------------------------------------------------------------------


def test_recording_provider_serves_a_recorded_description() -> None:
    directory = DESCRIPTIONS / "passport"
    provider = RecordingProvider.from_directory(directory)
    request = description_request(images=2)

    description = provider.describe_type(request)

    recorded = json.loads((directory / "0.json").read_text("utf-8"))
    assert description == validate_type_description(recorded)
    assert provider.description_requests == [request]
    assert provider.requests == []


def test_recording_provider_shares_one_sequence_between_request_kinds(tmp_path: Path) -> None:
    (tmp_path / "0.json").write_text(json.dumps(analysis_payload()), encoding="utf-8")
    (tmp_path / "1.json").write_text(json.dumps(description_payload()), encoding="utf-8")
    provider = RecordingProvider.from_directory(tmp_path)

    analysis = provider.analyze_page(page_request())
    description = provider.describe_type(description_request())

    assert analysis.page_index == 0
    assert description.mrz is not None
    assert len(provider.requests) == len(provider.description_requests) == 1
    with pytest.raises(RecordingExhaustedError, match="2 kayıt yüklendi, 3. istek"):
        provider.describe_type(description_request())


# --- Talimat -------------------------------------------------------------------------------------


def test_instructions_name_every_response_key_and_the_privacy_rule() -> None:
    text = load_type_description_instructions()

    for key in (*TypeDescription.model_fields, "line_count", "location", "field"):
        assert f"`{key}`" in text, key
    assert "Türü anlat, kişiyi değil" in text
    assert "değerini yazma" in text
    assert "Türkçe" in text
    # Talimat sabittir: doldurulacak yuva yok.
    assert re.search(r"\{\{\s*\w+\s*\}\}", text) is None
