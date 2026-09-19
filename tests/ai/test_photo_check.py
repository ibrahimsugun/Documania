"""11.7.1 — fotoğraf kontrolü sözleşmesi, isteği, sağlayıcının ortak `check_photo` adımı, kayıtlı
yanıt sağlayıcısı, talimat metni ve analiz talimatının taşıdığı kurallar.

Yapay zekâ canlı çağrılmaz: sağlayıcılar ağsız test sınıfları ya da kayıtlı yanıttır.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.ai import (
    AnalysisProvider,
    PageAnalysisInstructions,
    PageAnalysisRequest,
    PageImage,
    PhotoCheck,
    PhotoCheckError,
    PhotoCheckRequest,
    PhotoRuleResult,
    ProviderConnectionError,
    ProviderError,
    ProviderServerError,
    build_page_analysis_instructions,
    validate_photo_check,
)
from app.ai.prompts import load_photo_check_instructions
from app.ai.provider import MAX_ANALYSIS_ATTEMPTS, RETRY_BACKOFF_SECONDS
from app.ai.recording_provider import RecordingProvider
from app.catalog import load_seed_catalog, validate_catalog
from tests.ai.payloads import (
    PHOTO_RULES,
    analysis_payload,
    page_request,
    photo_check_payload,
    photo_check_request,
)
from tests.fixtures.gen import make_half_filled_image_bytes

CATALOG = load_seed_catalog()


class CheckingProvider(AnalysisProvider):
    """Ağsız test sağlayıcısı: fotoğraf kontrolü isteklerine sırayla verilen yanıtı/hatayı döner."""

    name = "denetleyen"

    def __init__(self, *responses: object) -> None:
        super().__init__(model="denetleyen-model")
        self._responses = list(responses)
        self.checks: list[PhotoCheckRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        self.checks.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AnalysisOnlyProvider(AnalysisProvider):
    """Fotoğraf kontrolünü uygulamayan sağlayıcı (varsayılan davranış)."""

    name = "yalniz-analiz"

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        return analysis_payload()


# --- Sözleşme ------------------------------------------------------------------------------------


def test_payload_is_accepted_from_object_json_text_and_model() -> None:
    payload = photo_check_payload(single_person="fail", no_sunglasses="unsure")

    from_object = validate_photo_check(payload, rules=PHOTO_RULES)
    from_text = validate_photo_check(json.dumps(payload), rules=PHOTO_RULES)

    assert from_object == from_text == validate_photo_check(from_object, rules=PHOTO_RULES)
    assert [(v.rule, v.result, v.note) for v in from_object.rules] == [
        ("face_visible", PhotoRuleResult.PASS, None),
        ("single_person", PhotoRuleResult.FAIL, "Kısa gerekçe."),
        ("no_sunglasses", PhotoRuleResult.UNSURE, "Kısa gerekçe."),
    ]
    assert from_object.verdict("single_person") == from_object.rules[1]
    assert from_object.verdict("min_resolution") is None


def test_rules_may_come_in_any_order_and_notes_are_stripped() -> None:
    payload = photo_check_payload()
    payload["rules"].reverse()
    payload["rules"][0]["note"] = "  Gözler görünüyor.  "

    check = validate_photo_check(payload, rules=PHOTO_RULES)

    assert [verdict.rule for verdict in check.rules] == list(reversed(PHOTO_RULES))
    assert check.rules[0].note == "Gözler görünüyor."


def _with(payload: dict[str, Any], index: int, **changes: Any) -> dict[str, Any]:
    payload["rules"][index].update(changes)
    return payload


@pytest.mark.parametrize(
    ("payload", "location"),
    [
        pytest.param(_with(photo_check_payload(), 0, result="evet"), "rules.0.result", id="sonuc"),
        pytest.param(_with(photo_check_payload(), 0, result=True), "rules.0.result", id="bool"),
        pytest.param(_with(photo_check_payload(), 1, note="x" * 201), "rules.1.note", id="uzun"),
        pytest.param(_with(photo_check_payload(), 1, note="   "), "rules.1.note", id="bos-not"),
        pytest.param(_with(photo_check_payload(), 2, rule="Yüz"), "rules.2.rule", id="kimlik"),
        pytest.param(_with(photo_check_payload(), 0, extra=1), "rules.0.extra", id="fazla-alan"),
        pytest.param(
            {"rules": [{"rule": "face_visible", "result": "pass"}]}, "rules.0.note", id="not-yok"
        ),
        pytest.param({"rules": []}, "rules", id="bos-liste"),
        pytest.param({"rules": "hepsi"}, "rules", id="liste-degil"),
        pytest.param({**photo_check_payload(), "notes": None}, "notes", id="ust-fazla"),
        pytest.param("{bozuk", "yanıt", id="json-degil"),
    ],
)
def test_non_conforming_payload_is_rejected(payload: object, location: str) -> None:
    with pytest.raises(PhotoCheckError) as caught:
        validate_photo_check(payload, rules=PHOTO_RULES)

    assert any(problem.startswith(location) for problem in caught.value.problems)


def test_each_rule_is_answered_once() -> None:
    payload = photo_check_payload()
    payload["rules"].append(dict(payload["rules"][0]))

    with pytest.raises(PhotoCheckError) as caught:
        validate_photo_check(payload, rules=PHOTO_RULES)

    assert caught.value.problems == ["yanıt: rules: her kural bir kez yazılır"]


def test_answer_must_cover_exactly_the_asked_rules() -> None:
    payload = photo_check_payload()
    payload["rules"] = [
        *payload["rules"][1:],
        {"rule": "ornekova_kurali", "result": "pass", "note": None},
    ]

    with pytest.raises(PhotoCheckError) as caught:
        validate_photo_check(payload, rules=PHOTO_RULES)

    assert caught.value.problems == [
        "rules: sorulan kural yanıtta yok: face_visible",
        "rules: sorulmayan 1 kural yanıtlandı",
    ]
    # Yanıttan gelen kimlik mesaja konmaz (CONVENTIONS §6).
    assert "ornekova" not in str(caught.value)


def test_stored_check_is_read_back_without_asked_rules() -> None:
    check = validate_photo_check(photo_check_payload(), rules=PHOTO_RULES)

    assert PhotoCheck.model_validate(check.model_dump(mode="json")) == check


# --- İstek ---------------------------------------------------------------------------------------


def test_request_copies_rules_into_a_tuple() -> None:
    image = PageImage(make_half_filled_image_bytes())
    request = PhotoCheckRequest(image=image, instructions="T", prompt="P", rules=["a", "b"])

    assert request.rules == ("a", "b")


@pytest.mark.parametrize(
    ("changes", "error", "message"),
    [
        ({"rules": ()}, ValueError, "en az bir"),
        ({"rules": ("a", "a")}, ValueError, "tekrarsız"),
        ({"rules": "face_visible"}, TypeError, "koleksiyonu"),
        ({"image": b"ham"}, TypeError, "PageImage"),
        ({"instructions": "  "}, ValueError, "instructions"),
        ({"prompt": ""}, ValueError, "prompt"),
    ],
)
def test_request_is_validated(
    changes: dict[str, Any], error: type[Exception], message: str
) -> None:
    values: dict[str, Any] = {
        "image": PageImage(make_half_filled_image_bytes()),
        "instructions": "Talimat",
        "prompt": "Kurallar",
        "rules": PHOTO_RULES,
    }
    values.update(changes)

    with pytest.raises(error, match=message):
        PhotoCheckRequest(**values)


# --- Ortak adım: `check_photo` -----------------------------------------------------------------


def test_check_photo_validates_the_answer_against_the_asked_rules() -> None:
    provider = CheckingProvider(photo_check_payload(face_visible="fail"))
    request = photo_check_request()

    check = provider.check_photo(request)

    assert check.verdict("face_visible") is not None
    assert provider.checks == [request]


def test_check_photo_rejects_an_answer_to_other_rules() -> None:
    provider = CheckingProvider(photo_check_payload())

    with pytest.raises(PhotoCheckError):
        provider.check_photo(photo_check_request(rules=("face_visible",)))


def test_check_photo_retries_server_errors_like_analysis(no_sleep: list[float]) -> None:
    provider = CheckingProvider(ProviderServerError("5xx", status_code=503), photo_check_payload())

    provider.check_photo(photo_check_request())

    assert len(provider.checks) == 2
    assert no_sleep == [RETRY_BACKOFF_SECONDS]


def test_check_photo_gives_up_after_max_attempts(no_sleep: list[float]) -> None:
    errors = [ProviderServerError("5xx", status_code=500) for _ in range(MAX_ANALYSIS_ATTEMPTS)]
    provider = CheckingProvider(*errors)

    with pytest.raises(ProviderServerError):
        provider.check_photo(photo_check_request())

    assert len(provider.checks) == MAX_ANALYSIS_ATTEMPTS


def test_connection_error_is_not_retried(no_sleep: list[float]) -> None:
    provider = CheckingProvider(ProviderConnectionError("yok"))

    with pytest.raises(ProviderConnectionError):
        provider.check_photo(photo_check_request())

    assert no_sleep == []


def test_provider_without_photo_check_refuses() -> None:
    with pytest.raises(ProviderError, match="fotoğraf kontrolü yapmıyor"):
        AnalysisOnlyProvider(model="m").check_photo(photo_check_request())


# --- Kayıtlı yanıt sağlayıcısı -------------------------------------------------------------------


def test_recording_provider_serves_photo_checks_from_the_same_queue(tmp_path: Path) -> None:
    analysis = tmp_path / "0.json"
    analysis.write_text(json.dumps(analysis_payload()), encoding="utf-8")
    check = tmp_path / "1.json"
    check.write_text(json.dumps(photo_check_payload(single_person="fail")), encoding="utf-8")
    provider = RecordingProvider.from_directory(tmp_path)
    request = photo_check_request()

    provider.analyze_page(page_request())
    result = provider.check_photo(request)

    verdict = result.verdict("single_person")
    assert verdict is not None and verdict.result is PhotoRuleResult.FAIL
    assert provider.photo_check_requests == [request]
    assert len(provider.requests) == 1


# --- Talimat ve analiz talimatındaki kurallar --------------------------------------------------


def test_instructions_are_packaged_and_ask_for_every_listed_rule() -> None:
    text = load_photo_check_instructions()

    assert text.startswith("# Profil fotoğrafı kontrolü talimatı")
    assert "her kural için tam bir satır" in text
    assert "`pass`, `fail` veya `unsure`" in text


def _catalog(slug: str, **changes: Any) -> Any:
    entries = [entry.model_dump(mode="json") for entry in CATALOG]
    for entry in entries:
        if entry["slug"] == slug:
            entry.update(changes)
    return validate_catalog(entries)


def test_analysis_instructions_carry_the_open_rules_of_photo_types() -> None:
    instructions = build_page_analysis_instructions(CATALOG)

    assert list(instructions.photo_rules) == ["profile_picture"]
    assert [rule.id for rule in instructions.photo_rules["profile_picture"]] == [
        "face_visible",
        "single_person",
        "neutral_expression",
        "plain_background",
        "min_resolution",
        "no_sunglasses",
    ]
    # Kurallar sayfa analizi talimatına girmez; ayrı istekte sorulur.
    assert "face_visible" not in instructions.text


ALL_CLOSED = {
    rule: {"enabled": False}
    for rule in (
        "face_visible",
        "single_person",
        "neutral_expression",
        "plain_background",
        "min_resolution",
        "no_sunglasses",
    )
}


@pytest.mark.parametrize(
    ("catalog", "checked"),
    [
        pytest.param(_catalog("profile_picture", active=False), [], id="pasif-tur"),
        pytest.param(
            _catalog("profile_picture", analyze=False, required_fields=[]),
            [],
            id="analiz-edilmeyen",
        ),
        pytest.param(_catalog("profile_picture", photo_rules=ALL_CLOSED), [], id="hepsi-kapali"),
        pytest.param(
            _catalog("russian_passport", photo_rules={"face_visible": {"enabled": True}}),
            ["profile_picture"],
            id="fotograf-turu-degil",
        ),
    ],
)
def test_only_active_analyzed_photo_types_with_open_rules_are_checked(
    catalog: Any, checked: list[str]
) -> None:
    instructions = build_page_analysis_instructions(catalog)

    assert list(instructions.photo_rules) == checked


def test_instructions_built_by_hand_ask_no_photo_rules() -> None:
    assert dict(PageAnalysisInstructions(text="T", known_slugs=frozenset()).photo_rules) == {}
