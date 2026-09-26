"""13.2.1 — ucuz model ön elemesi: kolay sayfa ucuz modelde kalır, gerisi ana modele gider.

Kolay sayfa ölçütü (`prescreen_escalation`) yanıtın kendi içeriğinden deterministik olarak
okunur — ayrı güven skoru yoktur (K1). Sayfalar ve yanıtlar `tests/fixtures/gen.py`'nin sentetik
belgeleridir; sağlayıcılar ağ çağrısı yapmaz (sıralı kayıtlı yanıt). Test matrisinin (uçtan uca
senaryolar) ön elemeyle aynı sonucu verdiği `test_prescreen_matrix.py`'dedir.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.ai import (
    AnalysisProvider,
    PageAnalysis,
    PageAnalysisRequest,
    PhotoCheckRequest,
    ProviderConnectionError,
    ProviderError,
    build_page_analysis_instructions,
    validate_page_analysis,
)
from app.ai.prompts import PageAnalysisInstructions
from app.ai.usage import report_usage
from app.catalog import Catalog, load_seed_catalog
from app.db.models import Upload
from app.events import (
    PRESCREEN_DATA_KEY,
    USAGE_BY_MODEL_DATA_KEY,
    USAGE_DATA_KEY,
    EventType,
)
from app.pipeline.analyze import (
    Escalation,
    PageAnalysisStatus,
    analyze_upload,
    prescreen_escalation,
)
from app.storage import DataLayout
from tests.fixtures.gen import (
    EMPLOYMENT_CONTRACT,
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    PERSON_SIDOROV,
    SyntheticPage,
    driving_license_pages,
    employment_contract_entry,
    employment_contract_page,
    make_document_pdf_bytes,
    make_portrait_image_bytes,
    passport_page,
    photo_check_response,
    profile_picture_page,
    residence_card_pages,
    unknown_document_page,
    work_permit_page,
)
from tests.pipeline.test_photo_check import _events, _upload

CATALOG = load_seed_catalog()
INSTRUCTIONS = build_page_analysis_instructions(CATALOG)
MAIN, CHEAP = "ana-model", "ucuz-model"
PASSPORT_NUMBER = "00 0000001"
LICENSE_NUMBER = "000123456"


def _passport(**overrides: Any) -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA,
        document_number=PASSPORT_NUMBER,
        expiry_date=date(2030, 1, 1),
        **overrides,
    )


def _license() -> tuple[SyntheticPage, SyntheticPage]:
    return driving_license_pages(
        PERSON_SIDOROV, document_number=LICENSE_NUMBER, expiry_date=date(2031, 6, 30)
    )


def _analysis(page: SyntheticPage, page_index: int = 0, **top: Any) -> PageAnalysis:
    data = page.analysis(page_index)
    data.update(top)
    return validate_page_analysis(data, known_slugs=INSTRUCTIONS.known_slugs)


def _with_person(page: SyntheticPage, **person: Any) -> PageAnalysis:
    data = page.analysis()
    data["person"].update(person)
    return validate_page_analysis(data, known_slugs=INSTRUCTIONS.known_slugs)


# --- Kolay sayfa ölçütü -------------------------------------------------------------------------


def test_passport_page_with_a_valid_mrz_agreeing_with_the_visible_text_is_easy() -> None:
    assert prescreen_escalation(_analysis(_passport()), INSTRUCTIONS) is None


def test_photo_page_without_required_fields_or_identity_is_easy() -> None:
    assert prescreen_escalation(_analysis(profile_picture_page()), INSTRUCTIONS) is None


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        # Ön yüz her zorunlu alanı okur ama numarayı doğrulayacak MRZ yok (K6, K7).
        (_license()[0], Escalation.UNVERIFIED_NUMBER),
        (
            work_permit_page(
                PERSON_SIDOROV, document_number="WP-0000042", expiry_date=date(2027, 3, 31)
            ),
            Escalation.UNVERIFIED_NUMBER,
        ),
        # Arka yüzde zorunlu alan yok: K1 sayfanın kendisinde sağlanmıyor.
        (_license()[1], Escalation.REQUIRED_FIELDS),
        (
            residence_card_pages(
                PERSON_SIDOROV, document_number="AB1234567", expiry_date=date(2029, 12, 31)
            )[0],
            Escalation.REQUIRED_FIELDS,
        ),
        (_passport(blurred=("date_of_birth",)), Escalation.REQUIRED_FIELDS),
        (
            unknown_document_page(
                PERSON_SIDOROV, candidate_type_name="Peruvian Diploma", title="DIPLOMA"
            ),
            Escalation.TYPE_UNDETERMINED,
        ),
        (_passport(notes="Sağ alt köşede parlama var."), Escalation.NOTES),
    ],
    ids=[
        "ehliyet-on",
        "calisma-izni",
        "ehliyet-arka",
        "oturum-on",
        "bulanik-alan",
        "katalog-disi",
        "not",
    ],
)
def test_page_that_is_not_easy_names_why(page: SyntheticPage, expected: Escalation) -> None:
    assert prescreen_escalation(_analysis(page), INSTRUCTIONS) is expected


def test_blank_and_unreadable_answers_are_not_easy() -> None:
    passport = _passport()

    assert prescreen_escalation(_analysis(passport, is_blank=True), INSTRUCTIONS) is (
        Escalation.BLANK
    )
    assert prescreen_escalation(_analysis(passport, is_readable=False), INSTRUCTIONS) is (
        Escalation.UNREADABLE
    )


def test_type_without_known_required_fields_is_not_easy() -> None:
    without = PageAnalysisInstructions(text="T", known_slugs=INSTRUCTIONS.known_slugs)

    assert prescreen_escalation(_analysis(_passport()), without) is Escalation.REQUIRED_FIELDS
    assert prescreen_escalation(_analysis(profile_picture_page()), without) is (
        Escalation.REQUIRED_FIELDS
    )


def test_mrz_whose_check_digit_fails_is_not_easy() -> None:
    first, second = _passport().mrz_lines
    # Belge numarasının bir hanesi yanlış okunmuş: kendi kontrol hanesi tutmaz.
    misread = ("1" if second[0] != "1" else "2") + second[1:]

    analysis = _with_person(_passport(), mrz_lines=[first, misread])

    assert prescreen_escalation(analysis, INSTRUCTIONS) is Escalation.MRZ


def test_mrz_whose_composite_check_digit_fails_is_not_easy() -> None:
    first, second = _passport().mrz_lines
    # Alanların kendi haneleri tutar, yalnız bileşik hane tutmaz: MRZ bütün olarak şüphelidir ve
    # belge numarası temiz sayılmaz (§20.1.7, §20.2.3).
    composite = "1" if second[-1] != "1" else "2"

    analysis = _with_person(_passport(), mrz_lines=[first, second[:-1] + composite])

    assert prescreen_escalation(analysis, INSTRUCTIONS) is Escalation.MRZ


def test_mrz_contradicting_the_visible_number_is_not_easy() -> None:
    # MRZ geçerli ama görünen numara başka: ikisinden biri yanlış okunmuş (05.3.3).
    analysis = _with_person(_passport(), document_number="00 0000009")

    assert prescreen_escalation(analysis, INSTRUCTIONS) is Escalation.MRZ


@pytest.mark.parametrize(
    "mrz_lines",
    [["P<RUSORNEKOVA<<TEST", "0000000010RUS"], ["P<RUS" + "É" * 39, "0" * 44]],
    ids=["bicimsiz", "gecersiz-karakter"],
)
def test_mrz_that_cannot_be_used_is_not_easy(mrz_lines: list[str]) -> None:
    analysis = _with_person(_passport(), mrz_lines=mrz_lines)

    assert prescreen_escalation(analysis, INSTRUCTIONS) is Escalation.MRZ


def test_mrz_with_an_unusable_field_is_not_easy() -> None:
    first, second = _passport().mrz_lines
    # İsim bileşik haneye girmez: haneler tutar ama isim alanında rakam var, alan okunamadı
    # sayılır (§20.1.7).
    assert "ORNEKOVA" in first

    analysis = _with_person(_passport(), mrz_lines=[first.replace("ORNEKOVA", "ORNEK0VA"), second])

    assert prescreen_escalation(analysis, INSTRUCTIONS) is Escalation.MRZ


def test_number_read_only_as_a_required_field_is_unverified_without_mrz() -> None:
    data = _license()[0].analysis()
    data["person"]["document_number"] = None

    analysis = validate_page_analysis(data, known_slugs=INSTRUCTIONS.known_slugs)

    assert prescreen_escalation(analysis, INSTRUCTIONS) is Escalation.UNVERIFIED_NUMBER


# S19'un numarasız türü kataloğa eklenmiş talimat (zorunlu alanları ad, soyad, doğum tarihi).
WITH_CONTRACT = build_page_analysis_instructions(Catalog((*CATALOG, employment_contract_entry())))


def _contract(instructions: PageAnalysisInstructions = WITH_CONTRACT) -> PageAnalysis:
    data = employment_contract_page(PERSON_PRUEBA).analysis()
    return validate_page_analysis(data, known_slugs=instructions.known_slugs)


def test_mrz_less_page_of_a_type_requiring_the_birth_date_is_not_easy() -> None:
    # §20.2.4 koşul 4 (§C84): doğum tarihi satır 6b'de yeni çalışan açar; MRZ'siz sayfada ucuz
    # modelin doğrulanmamış okuması buna dayanak olmaz. Sayfa her zorunlu alanı okur, not yok,
    # numara yok — yine de ana modele gider.
    analysis = _contract()

    assert analysis.person.mrz_lines is None and analysis.person.document_number is None
    assert prescreen_escalation(analysis, WITH_CONTRACT) is Escalation.UNVERIFIED_DATE_OF_BIRTH
    assert Escalation.UNVERIFIED_DATE_OF_BIRTH.value == "unverified_date_of_birth"


def test_the_same_page_is_easy_when_its_type_does_not_require_the_birth_date() -> None:
    # Kural türün zorunlu alanlarına bakar, türün adına ya da sayfada doğum tarihi yazmasına değil
    # (başkasının doğum tarihini taşıyan tür satır 6b'yi kullanmaz).
    instructions = PageAnalysisInstructions(
        text="T",
        known_slugs=WITH_CONTRACT.known_slugs,
        required_fields={EMPLOYMENT_CONTRACT: ("surname", "given_names")},
    )

    analysis = _contract(instructions)

    assert analysis.person.date_of_birth is not None
    assert prescreen_escalation(analysis, instructions) is None


def test_birth_date_verified_by_the_mrz_keeps_the_passport_page_easy() -> None:
    # Pasaport doğum tarihini zorunlu tutar; tarih kontrol haneleri tutan MRZ'den gelir.
    assert "date_of_birth" in INSTRUCTIONS.required_fields["russian_passport"]
    assert prescreen_escalation(_analysis(_passport()), INSTRUCTIONS) is None


def test_unverified_number_is_named_before_the_unverified_birth_date() -> None:
    # Ehliyetin ön yüzü numarayı da doğum tarihini de MRZ'siz okur: gerekçe numaranınkidir.
    assert "date_of_birth" in INSTRUCTIONS.required_fields["serbian_driving_license"]
    assert prescreen_escalation(_analysis(_license()[0]), INSTRUCTIONS) is (
        Escalation.UNVERIFIED_NUMBER
    )


def test_page_of_a_type_without_numbers_and_all_fields_legible_is_easy() -> None:
    instructions = PageAnalysisInstructions(
        text="T",
        known_slugs=INSTRUCTIONS.known_slugs,
        required_fields={"work_permit": ("surname", "given_names")},
    )
    data = work_permit_page(
        PERSON_SIDOROV, document_number="WP-0000042", expiry_date=date(2027, 3, 31)
    ).analysis()
    data["person"]["document_number"] = None
    data["fields"] = {name: data["fields"][name] for name in ("surname", "given_names")}

    analysis = validate_page_analysis(data, known_slugs=INSTRUCTIONS.known_slugs)

    assert prescreen_escalation(analysis, instructions) is None


# --- Analiz akışı: ucuz model → gerekirse ana model -------------------------------------------


class Model(AnalysisProvider):
    """Sıralı yanıt veren test modeli. Öğe `(kullanım, yanıt)` çiftiyse kullanımı bildirir; hata
    örneği fırlatılır. `cheap` verilirse ön eleme modeli odur (`_with_model` onu döner)."""

    name = "test"

    def __init__(self, model: str, *script: object, cheap: Model | None = None) -> None:
        super().__init__(model=model, prescreen_model=None if cheap is None else cheap.model)
        self._script = list(script)
        self._cheap = cheap
        self.requests: list[PageAnalysisRequest] = []
        self.photo_requests: list[PhotoCheckRequest] = []

    def _with_model(self, model: str) -> AnalysisProvider:
        assert self._cheap is not None and model == self._cheap.model
        return self._cheap

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        self.requests.append(request)
        return self._serve()

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        self.photo_requests.append(request)
        return self._serve()

    def _serve(self) -> object:
        assert self._script, f"{self.model} beklenmeyen bir istek aldı"
        item = self._script.pop(0)
        usage, response = item if isinstance(item, tuple) else (None, item)
        if usage is not None:
            report_usage(*usage)
        if isinstance(response, Exception):
            raise response
        return response


def _pdf(session: Session, layout: DataLayout, *pages: SyntheticPage) -> Upload:
    return _upload(session, layout, ("belgeler.pdf", make_document_pdf_bytes(pages)))


def _analyze(
    session: Session, layout: DataLayout, upload: Upload, provider: Model, **options: Any
) -> Any:
    return analyze_upload(
        session, layout, upload, provider=provider, instructions=INSTRUCTIONS, **options
    )


def _analyzed(session: Session) -> list[dict[str, Any]]:
    return [event.data_json for event in _events(session, EventType.PAGE_ANALYZED)]


def test_easy_page_stays_with_the_cheap_model_and_the_main_model_is_not_asked(
    session: Session, layout: DataLayout
) -> None:
    passport = _passport()
    upload = _pdf(session, layout, passport)
    cheap = Model(CHEAP, passport.analysis())
    main = Model(MAIN, cheap=cheap)

    result = _analyze(session, layout, upload, main)

    assert [outcome.status for outcome in result.outcomes] == [PageAnalysisStatus.DONE]
    assert len(cheap.requests) == 1 and main.requests == []
    assert result.outcomes[0].analysis == _analysis(passport)
    assert upload.files[0].pages[0].analysis_json == _analysis(passport).model_dump(mode="json")
    (data,) = _analyzed(session)
    assert data["model"] == CHEAP
    assert data["provider"] == "test"
    assert data[PRESCREEN_DATA_KEY] == {"model": CHEAP, "accepted": True}


def test_page_that_is_not_easy_is_asked_again_to_the_main_model_whose_answer_replaces_it(
    session: Session, layout: DataLayout
) -> None:
    front, _ = _license()
    upload = _pdf(session, layout, front)
    main_reading = front.analysis()
    main_reading["language"] = "en"  # ana modelin yanıtı ayırt edilebilsin
    cheap = Model(CHEAP, front.analysis())
    main = Model(MAIN, main_reading, cheap=cheap)

    result = _analyze(session, layout, upload, main)

    # Aynı istek (görüntü, talimat, metin) ana modele gider; ucuz yanıt yazılmaz.
    assert main.requests == cheap.requests and main.requests[0] is cheap.requests[0]
    assert result.outcomes[0].analysis is not None
    assert result.outcomes[0].analysis.language == "en"
    assert upload.files[0].pages[0].analysis_json["language"] == "en"
    (data,) = _analyzed(session)
    assert data["model"] == MAIN
    assert data[PRESCREEN_DATA_KEY] == {
        "model": CHEAP,
        "accepted": False,
        "escalation": "unverified_document_number",
    }


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        (ProviderConnectionError("ulaşılamadı"), "ProviderConnectionError"),
        ({"page_index": 0}, "PageAnalysisError"),
    ],
    ids=["saglayici-hatasi", "semaya-uymayan"],
)
def test_cheap_model_failure_never_fails_the_page_it_goes_to_the_main_model(
    session: Session, layout: DataLayout, answer: object, error: str
) -> None:
    passport = _passport()
    upload = _pdf(session, layout, passport)
    cheap = Model(CHEAP, answer)
    main = Model(MAIN, passport.analysis(), cheap=cheap)

    result = _analyze(session, layout, upload, main)

    assert not result.is_partial
    assert len(main.requests) == 1
    (data,) = _analyzed(session)
    assert data["model"] == MAIN
    assert data[PRESCREEN_DATA_KEY] == {
        "model": CHEAP,
        "accepted": False,
        "escalation": "failed",
        "error": error,
    }
    assert _events(session, EventType.PAGE_ANALYSIS_FAILED) == []


def test_main_model_failure_after_escalation_fails_the_page_and_records_the_prescreen(
    session: Session, layout: DataLayout
) -> None:
    front, _ = _license()
    upload = _pdf(session, layout, front)
    cheap = Model(CHEAP, ((900, 150), front.analysis()))
    main = Model(MAIN, ProviderError("istek reddedildi", status_code=400), cheap=cheap)

    result = _analyze(session, layout, upload, main)

    assert result.is_partial
    (failed,) = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert failed.data_json["model"] == MAIN
    assert (failed.data_json["error"], failed.data_json["status_code"]) == ("ProviderError", 400)
    assert failed.data_json[PRESCREEN_DATA_KEY]["escalation"] == "unverified_document_number"
    # Ucuz model yanıt verdi, ana model vermedi: harcama yalnız ucuz modelindir.
    assert failed.data_json[USAGE_DATA_KEY] == {"input_tokens": 900, "output_tokens": 150}
    assert failed.data_json[USAGE_BY_MODEL_DATA_KEY] == {
        CHEAP: {"input_tokens": 900, "output_tokens": 150}
    }


def test_tokens_of_both_models_are_split_by_model_and_add_up_to_the_page_total(
    session: Session, layout: DataLayout
) -> None:
    passport, (front, _) = _passport(), _license()
    upload = _pdf(session, layout, passport, front)
    cheap = Model(CHEAP, ((500, 100), passport.analysis(0)), ((400, 90), front.analysis(1)))
    main = Model(MAIN, ((3000, 700), front.analysis(1)), cheap=cheap)

    _analyze(session, layout, upload, main)

    first, second = _analyzed(session)
    assert first[USAGE_DATA_KEY] == {"input_tokens": 500, "output_tokens": 100}
    assert first[USAGE_BY_MODEL_DATA_KEY] == {CHEAP: {"input_tokens": 500, "output_tokens": 100}}
    assert second[USAGE_DATA_KEY] == {"input_tokens": 3400, "output_tokens": 790}
    assert second[USAGE_BY_MODEL_DATA_KEY] == {
        CHEAP: {"input_tokens": 400, "output_tokens": 90},
        MAIN: {"input_tokens": 3000, "output_tokens": 700},
    }


def test_cached_input_is_split_by_model_with_the_rest_of_the_tokens(
    session: Session, layout: DataLayout
) -> None:
    # C77: önbellekten okunan girdi de modellere dağıtılır (ana modelin payı = toplam − ucuz).
    passport, (front, _) = _passport(), _license()
    upload = _pdf(session, layout, passport, front)
    cheap = Model(
        CHEAP, ((500, 100, 400), passport.analysis(0)), ((400, 90, 256), front.analysis(1))
    )
    main = Model(MAIN, ((3000, 700, 2048), front.analysis(1)), cheap=cheap)

    _analyze(session, layout, upload, main)

    _, second = _analyzed(session)
    assert second[USAGE_DATA_KEY] == {
        "input_tokens": 3400,
        "output_tokens": 790,
        "cached_input_tokens": 2304,
    }
    assert second[USAGE_BY_MODEL_DATA_KEY] == {
        CHEAP: {"input_tokens": 400, "output_tokens": 90, "cached_input_tokens": 256},
        MAIN: {"input_tokens": 3000, "output_tokens": 700, "cached_input_tokens": 2048},
    }


def test_models_that_report_no_usage_leave_the_usage_fields_out(
    session: Session, layout: DataLayout
) -> None:
    passport = _passport()
    upload = _pdf(session, layout, passport)
    main = Model(MAIN, cheap=Model(CHEAP, passport.analysis()))

    _analyze(session, layout, upload, main)

    (data,) = _analyzed(session)
    assert USAGE_DATA_KEY not in data and USAGE_BY_MODEL_DATA_KEY not in data
    assert data[PRESCREEN_DATA_KEY]["accepted"] is True


def test_photo_page_accepted_by_the_cheap_model_is_still_checked_by_the_main_model(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    cheap = Model(CHEAP, ((300, 50), profile_picture_page().analysis()))
    main = Model(MAIN, ((800, 120), photo_check_response()), cheap=cheap)

    result = _analyze(session, layout, upload, main)

    assert main.requests == [] and len(main.photo_requests) == 1
    assert result.outcomes[0].photo_check is not None
    (data,) = _analyzed(session)
    assert data["model"] == CHEAP
    assert data[PRESCREEN_DATA_KEY] == {"model": CHEAP, "accepted": True}
    assert set(data["photo_check"]) >= {"face_visible"}
    assert data[USAGE_BY_MODEL_DATA_KEY] == {
        CHEAP: {"input_tokens": 300, "output_tokens": 50},
        MAIN: {"input_tokens": 800, "output_tokens": 120},
    }


def test_photo_check_failure_after_a_cheap_analysis_fails_the_page(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    cheap = Model(CHEAP, profile_picture_page().analysis())
    main = Model(MAIN, ProviderConnectionError("ulaşılamadı"), cheap=cheap)

    result = _analyze(session, layout, upload, main)

    assert result.is_partial
    (failed,) = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert failed.data_json["step"] == "photo_check"
    assert failed.data_json["model"] == CHEAP
    assert failed.data_json[PRESCREEN_DATA_KEY] == {"model": CHEAP, "accepted": True}


def test_without_prescreen_every_page_goes_to_the_main_model(
    session: Session, layout: DataLayout
) -> None:
    passport = _passport()
    upload = _pdf(session, layout, passport)
    cheap = Model(CHEAP)
    main = Model(MAIN, passport.analysis(), cheap=cheap)

    _analyze(session, layout, upload, main, prescreen=False)

    assert cheap.requests == [] and len(main.requests) == 1
    (data,) = _analyzed(session)
    assert data["model"] == MAIN
    assert PRESCREEN_DATA_KEY not in data and USAGE_BY_MODEL_DATA_KEY not in data


def test_provider_without_a_prescreen_model_writes_no_prescreen_fields(
    session: Session, layout: DataLayout
) -> None:
    passport = _passport()
    upload = _pdf(session, layout, passport)

    _analyze(session, layout, upload, Model(MAIN, ((10, 2), passport.analysis())))

    (data,) = _analyzed(session)
    assert data["model"] == MAIN
    assert data[USAGE_DATA_KEY] == {"input_tokens": 10, "output_tokens": 2}
    assert PRESCREEN_DATA_KEY not in data and USAGE_BY_MODEL_DATA_KEY not in data


def test_next_page_summary_comes_from_the_accepted_analysis_whichever_model_gave_it(
    session: Session, layout: DataLayout
) -> None:
    front, back = _license()
    passport = _passport()
    upload = _pdf(session, layout, passport, front, back)
    cheap = Model(CHEAP, passport.analysis(0), front.analysis(1), back.analysis(2))
    main = Model(MAIN, front.analysis(1), back.analysis(2), cheap=cheap)

    result = _analyze(session, layout, upload, main)

    assert [outcome.status for outcome in result.outcomes] == [PageAnalysisStatus.DONE] * 3
    # İkinci sayfanın isteği birincinin (ucuz modelde kalan) analizinin özetini taşır; üçüncü
    # sayfanınki ikincinin (ana modelin) özetini. İki model aynı isteği görür.
    assert "Belge türü: `russian_passport`" in cheap.requests[1].prompt
    assert "Belge türü: `serbian_driving_license`" in cheap.requests[2].prompt
    assert main.requests == cheap.requests[1:]
    models = [data["model"] for data in _analyzed(session)]
    assert models == [CHEAP, MAIN, MAIN]
