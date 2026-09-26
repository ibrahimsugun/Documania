"""05.6.2 — kayıtlı çalışanla eşleşmeyen kişide temiz numara yoksa Latin ad-soyad ve okunaklı,
tekil, çelişkisiz, makul doğum tarihiyle yeni çalışan açılır (§20.2.2 satır 6b, §20.2.4; R9, K7,
D11).
R8 korunur: yalnız adla eşleşme yeni çalışan açmaz.

Birim testleri `resolve_unmatched`, `can_create_employee`, `create_employee` ve
`propose_pending_profile`'ı elle kurulan `PersonKey` ve geçici SQLite'taki sentetik çalışanlarla
sınar; entegrasyon testi kayıtlı yanıtla analiz edilmiş sentetik pasaportun (numarası bulanık)
anahtarını kullanır. Uçtan uca S19 `tests/test_scenario_s19.py`'dedir, ön elemenin
`unverified_date_of_birth`'ü `tests/pipeline/test_prescreen.py`'dedir. Gerçek kişi/belge yok, ağ
çağrısı yok.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.catalog import CatalogEntry
from app.db.models import QueueKind
from app.events import EventType, event_context
from app.matching.match import (
    MAX_AGE,
    MIN_AGE,
    NAME_ONLY_REASON,
    PENDING_PROFILE_LATIN_REASON,
    PENDING_PROFILE_REASON,
    CreationBasis,
    EmployeeAction,
    EmployeeCreationRefusedError,
    EmployeeMatch,
    MatchRule,
    PendingProfileRefusedError,
    PersonKey,
    UnmatchedResolution,
    UnmatchedRule,
    can_create_employee,
    create_employee,
    dob_plausible,
    match_employee,
    propose_pending_profile,
    resolve_unmatched,
)
from app.storage import DataLayout
from tests.fixtures.gen import employment_contract_entry
from tests.matching.test_pending_profile_and_aliases import (
    BORN,
    CYRILLIC,
    NAME,
    NUMBER,
    PASSPORT,
    PASSPORT_WITHOUT_DOB,
    PHOTO,
    TODAY,
    UPLOAD_ID,
    _assert_no_personal_values,
    _counts,
    _employee,
    _events,
    _folders,
    _key,
    _number,
    _recorded_key,
)

NO_MATCH = EmployeeMatch(MatchRule.NO_MATCH)
# S19'un numarasız türü: zorunlu alanları ad, soyad, doğum tarihi.
CONTRACT = employment_contract_entry()
CONTRACT_WITHOUT_DOB = employment_contract_entry(required_fields=("surname", "given_names"))
NAME_DOB = UnmatchedResolution(UnmatchedRule.CREATE, basis=CreationBasis.NAME_DOB)
FOLDER = "Test_Ornekova_E0001"


def _resolve(key: PersonKey, entry: CatalogEntry) -> UnmatchedResolution:
    return resolve_unmatched(key, NO_MATCH, entry=entry, today=TODAY)


def _years_before(years: int, *, days: int = 0) -> date:
    # `TODAY`'den tam `years` yıl önce, `days` gün sonra.
    return date(TODAY.year - years, TODAY.month, TODAY.day + days)


# --- §20.2.4: satır 6b kararı ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "entry"),
    [
        (_key(numbers=()), CONTRACT),
        (_key(numbers=(), original=None), CONTRACT),
        (_key(numbers=()), PASSPORT),
        (_key(numbers=_number(legible=False)), PASSPORT),
        (_key(numbers=_number("AB12")), PASSPORT),
        (_key(mrz_allows=False), PASSPORT),
    ],
    ids=[
        "numberless-type",
        "numberless-type-latin-document",
        "passport-without-number",
        "passport-illegible-number",
        "passport-four-characters",
        "passport-mrz-check-digits-fail",
    ],
)
def test_name_and_birth_date_without_a_clean_number_open_an_employee(
    key: PersonKey, entry: CatalogEntry
) -> None:
    # Satır 6b: eşleşme yok, temiz numara yok, doğum tarihi türün zorunlu alanı, okunaklı, tek,
    # makul; ad-soyad Latin ve klasör adı veriyor → `create`, Hazir, dayanak `name_dob`.
    resolution = _resolve(key, entry)

    assert resolution == NAME_DOB
    assert (resolution.action, resolution.queue, resolution.reason) == (
        EmployeeAction.CREATE,
        None,
        None,
    )
    assert resolution.proposed_profile is None
    assert can_create_employee(key, NO_MATCH, entry=entry, today=TODAY)


def test_clean_number_comes_first_and_is_row_6() -> None:
    # Doğum tarihi de uysa temiz numara varsa dayanak numaradır (satır 6 önce gelir).
    resolution = _resolve(_key(), PASSPORT)

    assert resolution == UnmatchedResolution(
        UnmatchedRule.CREATE, basis=CreationBasis.DOCUMENT_NUMBER
    )


@pytest.mark.parametrize(
    ("key", "entry"),
    [
        (_key(numbers=()), CONTRACT_WITHOUT_DOB),
        (_key(numbers=_number(legible=False)), PASSPORT_WITHOUT_DOB),
        (_key(numbers=()), PHOTO),
        (_key(numbers=(), born=None), CONTRACT),
        (_key(numbers=(), dob_legible=False), CONTRACT),
        (_key(numbers=(), conflicts=("date_of_birth",)), CONTRACT),
        (_key(numbers=(), born=date(2027, 1, 1)), CONTRACT),
        (_key(numbers=(), born=TODAY), CONTRACT),
        (_key(numbers=(), born=date(2015, 6, 1)), CONTRACT),
        (_key(numbers=(), born=date(1930, 6, 1)), CONTRACT),
    ],
    ids=[
        "type-does-not-require-birth-date",
        "passport-variant-without-birth-date",
        "type-without-required-fields",
        "birth-date-not-read",
        "birth-date-not-legible",
        "birth-date-conflicts-across-pages",
        "birth-date-in-the-future",
        "birth-date-today",
        "too-young",
        "too-old",
    ],
)
def test_birth_date_failing_section_20_2_4_leaves_a_pending_profile(
    key: PersonKey, entry: CatalogEntry
) -> None:
    # Satır 7: ad-soyad var ama satır 6 ve 6b uymuyor; tahmin edilmez, profil onaya önerilir.
    resolution = _resolve(key, entry)

    assert resolution.rule is UnmatchedRule.PENDING_PROFILE
    assert (resolution.action, resolution.queue) == (EmployeeAction.PENDING, QueueKind.UNRESOLVED)
    assert resolution.reason == PENDING_PROFILE_REASON
    assert resolution.basis is None
    assert resolution.proposed_profile is not None
    assert not can_create_employee(key, NO_MATCH, entry=entry, today=TODAY)


@pytest.mark.parametrize(
    ("born", "rule"),
    [
        (_years_before(MIN_AGE), UnmatchedRule.CREATE),
        (_years_before(MIN_AGE, days=1), UnmatchedRule.PENDING_PROFILE),
        (_years_before(MAX_AGE + 1, days=1), UnmatchedRule.CREATE),
        (_years_before(MAX_AGE + 1), UnmatchedRule.PENDING_PROFILE),
    ],
    ids=["turns-16-today", "turns-16-tomorrow", "still-90", "turns-91-today"],
)
def test_plausible_age_is_measured_on_the_reference_day(born: date, rule: UnmatchedRule) -> None:
    # `dob_plausible` (§20.1.6): 16–90 tamamlanmış yıl, iki uç dahil; referans gün `today`dir.
    assert (MIN_AGE, MAX_AGE) == (16, 90)
    assert dob_plausible(born, today=TODAY) is (rule is UnmatchedRule.CREATE)

    assert _resolve(_key(numbers=(), born=born), CONTRACT).rule is rule


def test_reference_day_decides_the_same_birth_date_differently() -> None:
    key = _key(numbers=(), born=_years_before(MIN_AGE, days=1))

    assert _resolve(key, CONTRACT).rule is UnmatchedRule.PENDING_PROFILE
    later = date(TODAY.year, TODAY.month, TODAY.day + 1)
    assert resolve_unmatched(key, NO_MATCH, entry=CONTRACT, today=later) == NAME_DOB


@pytest.mark.parametrize(
    "key",
    [
        _key(numbers=(), given_names="محمد", surname="علي", original=None),
        _key(numbers=(), given_names="Тест", surname="Орнекова"),
    ],
    ids=["arabic", "cyrillic-without-latin-spelling"],
)
def test_name_without_latin_spelling_stays_a_pending_profile(key: PersonKey) -> None:
    # §20.2.4 koşul 2 (05.2.2): Latin yazım yoksa doğum tarihi uysa da satır 7.
    resolution = _resolve(key, CONTRACT)

    assert (resolution.rule, resolution.latin_missing) == (UnmatchedRule.PENDING_PROFILE, True)
    assert resolution.reason == PENDING_PROFILE_LATIN_REASON
    assert not can_create_employee(key, NO_MATCH, entry=CONTRACT, today=TODAY)


@pytest.mark.parametrize(
    "key",
    [
        _key(numbers=(), given_names=None, surname=None, original=None),
        _key(numbers=(), given_names=None, surname=None, original=None, born=None),
    ],
    ids=["birth-date-only", "nothing"],
)
def test_birth_date_without_a_name_is_row_8(key: PersonKey) -> None:
    # Klasör adı ad-soyaddan kurulur: yalnız doğum tarihinden çalışan açılmaz.
    resolution = _resolve(key, CONTRACT)

    assert resolution.rule is UnmatchedRule.NO_PERSON
    assert not can_create_employee(key, NO_MATCH, entry=CONTRACT, today=TODAY)


# --- satır 6b: çalışan ve klasör -----------------------------------------------------------------


def test_name_and_birth_date_open_the_employee_without_any_document_number(
    session: Session, layout: DataLayout
) -> None:
    # Numara okunmuş ama temiz değil (okunaksız): hiçbir yere yazılmaz (D11); çalışan, isim
    # yazımları, klasör ve dayanağı `name_dob` olan olay.
    key = _key(numbers=_number(legible=False))

    employee = create_employee(session, layout, key, entry=PASSPORT, today=TODAY, page_index=1)

    assert (employee.id, employee.folder_name, employee.status) == ("E0001", FOLDER, "active")
    assert (
        employee.given_names,
        employee.surname,
        employee.other_names,
        employee.original_script_name,
        employee.date_of_birth,
        employee.nationality,
    ) == ("TEST", "ORNEKOVA", "IVANOVNA", CYRILLIC, BORN, "RUS")
    assert {(alias.raw_name, alias.normalized_name) for alias in employee.aliases} == {
        ("TEST ORNEKOVA", NAME),
        (CYRILLIC, NAME),
    }
    assert employee.identifiers == []
    assert _counts(session) == (1, 2, 0)
    assert _folders(layout) == [FOLDER]
    assert layout.received_dir(FOLDER).is_dir() and layout.ready_dir(FOLDER).is_dir()

    (event,) = _events(session)
    assert (event.type, event.employee_id, event.page_index, event.actor) == (
        EventType.EMPLOYEE_CREATED,
        "E0001",
        1,
        "system",
    )
    assert event.data_json == {
        "action": "create",
        "basis": "name_dob",
        "document_type_slug": "russian_passport",
    }
    _assert_no_personal_values(json.dumps([event.data_json, event.message], ensure_ascii=False))


def test_numberless_type_opens_the_employee(session: Session, layout: DataLayout) -> None:
    employee = create_employee(session, layout, _key(numbers=()), entry=CONTRACT, today=TODAY)

    assert (employee.id, employee.identifiers) == ("E0001", [])
    (event,) = _events(session)
    assert event.data_json == {
        "action": "create",
        "basis": "name_dob",
        "document_type_slug": "employment_contract",
    }


def test_employee_opened_by_name_and_birth_date_is_found_by_the_next_document(
    session: Session, layout: DataLayout
) -> None:
    # Sonraki belge satır 3'le eşleşir; ikinci çalışan açılmaz.
    key = _key(numbers=())
    create_employee(session, layout, key, entry=CONTRACT, today=TODAY)

    assert match_employee(session, key) == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))
    with pytest.raises(EmployeeCreationRefusedError, match="eşleştirme hükmü name_dob"):
        create_employee(session, layout, key, entry=CONTRACT, today=TODAY)
    assert _counts(session) == (1, 2, 0)
    assert _folders(layout) == [FOLDER]


@pytest.mark.parametrize(
    ("born", "rule"),
    [(BORN, MatchRule.NAME_DOB), (date(1980, 1, 1), MatchRule.NAME_ONLY)],
    ids=["same-birth-date-registered", "name-only-r8"],
)
def test_verdict_is_re_evaluated_in_the_database(
    session: Session, layout: DataLayout, born: date, rule: MatchRule
) -> None:
    # Çağıranın elindeki hükme güvenilmez: araya aynı isimli çalışan girdiyse satır 3 ya da 5
    # (R8: yalnız adla eşleşme Unresolved'dır, yeni çalışan açılmaz).
    _employee(session, "E0001", born=born, aliases=("ORNEKOVA TEST",))
    key = _key(numbers=())
    before = _counts(session)

    with pytest.raises(EmployeeCreationRefusedError) as refused:
        create_employee(session, layout, key, entry=CONTRACT, today=TODAY)

    message = str(refused.value)
    assert message == (
        f"Yeni çalışan açılmaz (§20.2.2 satır 6, 6b; R9): eşleştirme hükmü {rule.value}."
    )
    _assert_no_personal_values(message)
    assert _counts(session) == before
    assert _events(session) == []
    assert _folders(layout) == []


def test_name_only_match_stays_unresolved_and_opens_nobody(session: Session) -> None:
    # R8 (S10): ad bir alias'la eşleşir, doğum tarihi farklı → satır 5; satır 6b'ye inilmez.
    _employee(session, "E0001", born=date(1980, 1, 1), aliases=("ORNEKOVA TEST",))
    key = _key(numbers=())

    match = match_employee(session, key)

    assert match == EmployeeMatch(MatchRule.NAME_ONLY, ("E0001",))
    assert (match.action, match.queue) == (EmployeeAction.NONE, QueueKind.UNRESOLVED)
    assert match.reason is not None and match.reason.startswith(NAME_ONLY_REASON)
    assert not can_create_employee(key, match, entry=CONTRACT, today=TODAY)
    with pytest.raises(ValueError, match="eşleştirme hükmü name_only"):
        resolve_unmatched(key, match, entry=CONTRACT, today=TODAY)


def test_row_6b_is_not_proposed_as_a_pending_profile(session: Session, layout: DataLayout) -> None:
    with pytest.raises(PendingProfileRefusedError) as refused:
        propose_pending_profile(session, _key(numbers=()), entry=CONTRACT, today=TODAY)

    assert str(refused.value) == (
        "Onay bekleyen profil önerilmez (§20.2.2 satır 7, K7): satır 6–8 kararı create."
    )
    assert _counts(session) == (0, 0, 0)
    assert _events(session) == []


def test_implausible_birth_date_is_proposed_not_created(
    session: Session, layout: DataLayout
) -> None:
    key = _key(numbers=(), born=date(2020, 1, 1))

    with pytest.raises(EmployeeCreationRefusedError, match="makul yaş"):
        create_employee(session, layout, key, entry=CONTRACT, today=TODAY)
    profile = propose_pending_profile(session, key, entry=CONTRACT, today=TODAY)

    assert profile.date_of_birth == date(2020, 1, 1)
    assert _counts(session) == (0, 0, 0)
    assert [event.type for event in _events(session)] == [EventType.EMPLOYEE_PENDING]


# --- entegrasyon: kayıtlı yanıt → anahtar → satır 6b ---------------------------------------------


def test_recorded_passport_with_a_blurred_number_opens_by_name_and_birth_date(
    session: Session, layout: DataLayout
) -> None:
    # Anahtar düzeyinde: numarası bulanık pasaportun okunaklı doğum tarihi satır 6b'ye uyar ve
    # bulanık numara hiçbir yere yazılmaz. (Boru hattında S9 yine Unreadable'dır: zorunlu numara
    # okunaksız, K1 çalışan kararından önce gelir — `tests/test_scenarios_s06_s10.py`.)
    upload, key, entry = _recorded_key(session, layout, "s9_blurred_passport")
    assert entry is PASSPORT
    assert (key.date_of_birth, key.date_of_birth_legible) == (BORN, True)
    first = upload.files[0].id

    with event_context(upload_id=upload.id):
        match = match_employee(session, key, file_id=first, page_index=0)
        resolution = resolve_unmatched(key, match, entry=entry, today=TODAY)
        employee = create_employee(
            session, layout, key, entry=entry, today=TODAY, file_id=first, page_index=0
        )
    session.commit()

    assert resolution == NAME_DOB
    assert (employee.id, employee.folder_name, employee.identifiers) == ("E0001", FOLDER, [])
    (created,) = [event for event in _events(session) if event.type == EventType.EMPLOYEE_CREATED]
    assert (created.upload_id, created.file_id, created.data_json["basis"]) == (
        UPLOAD_ID,
        first,
        "name_dob",
    )
    _assert_no_personal_values(
        json.dumps(
            [[event.data_json, event.message] for event in _events(session)], ensure_ascii=False
        )
    )
    assert NUMBER not in json.dumps([event.data_json for event in _events(session)])
