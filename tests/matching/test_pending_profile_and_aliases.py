"""05.7.1 — temiz belge numarası yoksa profil önerisi Unresolved'a düşer, onaysız çalışan oluşmaz
(K7, R9); 05.7.2 — her eşleşmede görülen yeni isim yazımı ve belge numarası çalışana eklenir.

Birim testleri §20.2.2 satır 6–8'i ve satır 1/3 sonrasındaki birikimi elle kurulan `PersonKey` ve
geçici SQLite'taki sentetik çalışanlarla sınar. Entegrasyon testleri sentetik PDF'i gerçek render
adımlarından ve kayıtlı yanıt sağlayıcısıyla (03.6) analizden geçirip `group_upload` →
`build_person_key` → `match_employee` → `resolve_unmatched` / `propose_pending_profile` /
`accumulate_identity` zincirini koşar — gerçek kişi/belge yok, ağ çağrısı yok.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import build_page_analysis_instructions
from app.ai.recording_provider import RecordingProvider
from app.catalog import CatalogEntry, load_seed_catalog
from app.config import Settings
from app.db.models import (
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    Event,
    QueueKind,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.events import EventType, event_context
from app.matching.match import (
    NO_PERSON_REASON,
    PENDING_PROFILE_LATIN_REASON,
    PENDING_PROFILE_REASON,
    CreationBasis,
    DocumentNumberKey,
    EmployeeAction,
    EmployeeCreationRefusedError,
    EmployeeMatch,
    IdentityAccumulation,
    IdentityAccumulationRefusedError,
    MatchRule,
    PendingProfileRefusedError,
    PersonKey,
    ProposedProfile,
    UnmatchedResolution,
    UnmatchedRule,
    accumulate_identity,
    build_person_key,
    can_create_employee,
    create_employee,
    match_employee,
    propose_pending_profile,
    resolve_unmatched,
)
from app.matching.names import normalize_name, transliterate_name
from app.pipeline.analyze import analyze_upload
from app.pipeline.group import group_upload
from app.pipeline.render import (
    extract_upload_file_text,
    mark_upload_file_blank_pages,
    render_upload_file,
)
from app.storage import DataLayout, write_to_inbox
from tests.fixtures.gen import make_text_pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()
PASSPORT = CATALOG.get("russian_passport")
PHOTO = CATALOG.get("profile_picture")
assert PASSPORT is not None and PHOTO is not None
# Satır 6b'nin (§20.2.4 koşul 1) dışında kalan tür: doğum tarihi zorunlu alan değil. Satır 7'yi
# (onay bekleyen profil) sınayan fixture'lar bununla kurulur; pasaportla aynı anahtar artık 6b'dir.
PASSPORT_WITHOUT_DOB = PASSPORT.model_copy(
    update={"required_fields": tuple(f for f in PASSPORT.required_fields if f != "date_of_birth")}
)
TODAY = date(2026, 9, 15)
UPLOAD_ID = "u_20260915_0001"

NUMBER = "000000001"
BORN = date(1990, 1, 1)
CYRILLIC = "Орнекова Тест"
NAME = normalize_name("TEST", "ORNEKOVA")
# Latin harfli ama klasör adına (ASCII) inmeyen ad-soyad (D9): `ə`, `ʃ` Latin harfidir.
LATIN_WITHOUT_SLUG = ("Əə", "ʃ")
# Anahtarın kişisel değerleri ve normalize biçimleri: olay logunda, gerekçede ve ret mesajında
# geçmez.
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "ornekova", "TEST", "Орнекова", NUMBER, "1990-01-01")


def _key(
    *,
    numbers: tuple[DocumentNumberKey, ...] = (DocumentNumberKey(NUMBER, legible=True),),
    given_names: str | None = "TEST",
    surname: str | None = "ORNEKOVA",
    original: str | None = CYRILLIC,
    born: date | None = BORN,
    dob_legible: bool = True,
    mrz_allows: bool = True,
    conflicts: tuple[str, ...] = (),
) -> PersonKey:
    # Doğum tarihi `build_person_key`'in okunaklı `fields` okumasından verdiği gibi okunaklıdır.
    named = given_names is not None and surname is not None
    return PersonKey(
        document_numbers=numbers,
        normalized_name=normalize_name(given_names, surname) if named else None,
        date_of_birth=born,
        original_script_name=None if original is None else transliterate_name(original),
        normalized_original_name=None if original is None else normalize_name(original),
        mrz_allows_clean_document_number=mrz_allows,
        conflicts=conflicts,
        surname=surname,
        given_names=given_names,
        other_names="IVANOVNA",
        nationality="RUS",
        date_of_birth_legible=born is not None and dob_legible,
    )


def _number(value: str = NUMBER, *, legible: bool = True) -> tuple[DocumentNumberKey, ...]:
    return (DocumentNumberKey(value, legible=legible),)


def _employee(
    session: Session,
    employee_id: str,
    *,
    born: date | None = BORN,
    aliases: tuple[str, ...] = (),
    numbers: tuple[str, ...] = (),
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"Kayitli_Kisi_{employee_id}",
        given_names="Kayitli",
        surname="Kisi",
        date_of_birth=born,
    )
    session.add(employee)
    for raw in aliases:
        session.add(
            EmployeeAlias(employee=employee, raw_name=raw, normalized_name=normalize_name(raw))
        )
    for number in numbers:
        session.add(EmployeeIdentifier(employee=employee, kind="russian_passport", value=number))
    session.flush()
    return employee


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _counts(session: Session) -> tuple[int, int, int]:
    return (
        _count(session, Employee),
        _count(session, EmployeeAlias),
        _count(session, EmployeeIdentifier),
    )


def _events(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).order_by(Event.id)))


def _folders(layout: DataLayout) -> list[str]:
    return sorted(path.name for path in layout.employees.iterdir())


def _assert_no_personal_values(text: str) -> None:
    for value in PERSONAL_VALUES:
        assert value not in text


NO_MATCH = EmployeeMatch(MatchRule.NO_MATCH)
PROFILE = ProposedProfile(
    given_names="TEST",
    surname="ORNEKOVA",
    other_names="IVANOVNA",
    original_script_name=CYRILLIC,
    date_of_birth=BORN,
    nationality="RUS",
    aliases=(("TEST ORNEKOVA", NAME), (CYRILLIC, NAME)),
)


# --- §20.2.2 satır 7: onay bekleyen profil kararı -------------------------------------------------


@pytest.mark.parametrize(
    ("key", "entry"),
    [
        (_key(numbers=_number(legible=False)), PASSPORT_WITHOUT_DOB),
        (_key(numbers=_number("AB12")), PASSPORT_WITHOUT_DOB),
        (_key(mrz_allows=False), PASSPORT_WITHOUT_DOB),
        (_key(numbers=()), PASSPORT_WITHOUT_DOB),
        (_key(), PHOTO),
    ],
    ids=[
        "illegible-number",
        "four-characters",
        "mrz-check-digits-fail",
        "no-number",
        "type-no-number",
    ],
)
def test_name_without_clean_number_is_a_pending_profile_in_unresolved(
    key: PersonKey, entry: CatalogEntry
) -> None:
    # K7: temiz numara yoksa (§20.2.3'ün herhangi bir koşulu) ve tür doğum tarihini zorunlu
    # tutmuyorsa (§20.2.4 koşul 1, satır 6b yok) çalışan açılmaz, profil önerilir.
    resolution = resolve_unmatched(key, NO_MATCH, entry=entry)

    assert resolution == UnmatchedResolution(UnmatchedRule.PENDING_PROFILE, PROFILE)
    assert (resolution.action, resolution.queue) == (EmployeeAction.PENDING, QueueKind.UNRESOLVED)
    assert resolution.reason == PENDING_PROFILE_REASON
    assert not can_create_employee(key, NO_MATCH, entry=entry)


def test_proposed_profile_payload_is_json_and_carries_no_document_number() -> None:
    payload = PROFILE.payload()

    assert json.loads(json.dumps(payload, ensure_ascii=False)) == {
        "proposed_profile": {
            "given_names": "TEST",
            "surname": "ORNEKOVA",
            "other_names": "IVANOVNA",
            "original_script_name": CYRILLIC,
            "date_of_birth": "1990-01-01",
            "nationality": "RUS",
            "aliases": [
                {"raw_name": "TEST ORNEKOVA", "normalized_name": "ornekova test"},
                {"raw_name": CYRILLIC, "normalized_name": "ornekova test"},
            ],
        }
    }
    unclean = resolve_unmatched(
        _key(numbers=_number(legible=False)), NO_MATCH, entry=PASSPORT_WITHOUT_DOB
    )
    assert unclean.proposed_profile is not None
    assert NUMBER not in json.dumps(unclean.proposed_profile.payload())


@pytest.mark.parametrize(
    ("original", "expected_original", "born", "aliases"),
    [
        # Belgeden orijinal yazım okunmadıysa (Latin belge) alan boş kalmaz: okumaların kendisi
        # ismin basılı hâlidir (05.2.2).
        (None, "TEST IVANOVNA ORNEKOVA", BORN, (("TEST ORNEKOVA", NAME),)),
        ("TEST ORNEKOVA", "TEST ORNEKOVA", BORN, (("TEST ORNEKOVA", NAME),)),
        (CYRILLIC, CYRILLIC, None, (("TEST ORNEKOVA", NAME), (CYRILLIC, NAME))),
    ],
    ids=["latin-reading-is-the-original", "same-spelling", "no-birth-date"],
)
def test_proposed_profile_holds_what_was_read(
    original: str | None,
    expected_original: str,
    born: date | None,
    aliases: tuple[tuple[str, str], ...],
) -> None:
    key = _key(numbers=(), original=original, born=born)

    profile = resolve_unmatched(key, NO_MATCH, entry=PASSPORT_WITHOUT_DOB).proposed_profile

    assert profile is not None
    assert (profile.original_script_name, profile.date_of_birth, profile.aliases) == (
        expected_original,
        born,
        aliases,
    )
    assert profile.payload()["proposed_profile"]["date_of_birth"] == (
        None if born is None else born.isoformat()
    )


@pytest.mark.parametrize(
    ("given_names", "surname", "original", "expected_original"),
    [
        ("محمد", "علي", "علي محمد", "علي محمد"),
        ("محمد", "علي", None, "محمد علي"),
        ("李", "王", None, "李 王"),
    ],
    ids=["arabic-with-original", "arabic-moved-to-original", "chinese-moved-to-original"],
)
@pytest.mark.parametrize("numbers", [_number(), ()], ids=["clean-number", "no-number"])
def test_name_without_latin_spelling_is_a_pending_profile_without_names(
    given_names: str,
    surname: str,
    original: str | None,
    expected_original: str,
    numbers: tuple[DocumentNumberKey, ...],
) -> None:
    # 05.2.2: Latin yazım ne basılı ne MRZ'de; Arap ve öteki alfabeler tahminle çevrilmez. Temiz
    # numara olsa da çalışan açılmaz: öneride ad ve soyad boş, Latin olmayan yazım orijinal
    # yazımda; isim yazımları (alias) okunduğu gibi.
    key = _key(numbers=numbers, given_names=given_names, surname=surname, original=original)

    resolution = resolve_unmatched(key, NO_MATCH, entry=PASSPORT)

    assert (resolution.rule, resolution.latin_missing) == (UnmatchedRule.PENDING_PROFILE, True)
    assert (resolution.action, resolution.queue) == (EmployeeAction.PENDING, QueueKind.UNRESOLVED)
    assert resolution.reason == PENDING_PROFILE_LATIN_REASON
    assert "Latin yazım belgede yok" in resolution.reason
    profile = resolution.proposed_profile
    assert profile is not None and profile.latin_missing
    assert (profile.given_names, profile.surname, profile.other_names) == (None, None, "IVANOVNA")
    assert profile.original_script_name == expected_original
    assert f"{given_names} {surname}" in dict(profile.aliases)
    assert (profile.fields().given_names, profile.fields().surname) == ("", "")
    assert not can_create_employee(key, NO_MATCH, entry=PASSPORT)


def test_cyrillic_reading_with_its_latin_spelling_is_named_in_latin() -> None:
    # `build_person_key`'in bulduğu Latin yazım öneriye gider; Kiril okuma orijinal yazıma.
    key = replace(
        _key(numbers=(), given_names="Тест", surname="Орнекова", original=None),
        latin_given_names="Test",
        latin_surname="Ornekova",
    )

    resolution = resolve_unmatched(key, NO_MATCH, entry=PASSPORT_WITHOUT_DOB)

    assert (resolution.reason, resolution.latin_missing) == (PENDING_PROFILE_REASON, False)
    profile = resolution.proposed_profile
    assert profile is not None
    assert (profile.given_names, profile.surname, profile.original_script_name) == (
        "Test",
        "Ornekova",
        "Тест Орнекова",
    )


def test_original_spelling_key_keeps_the_page_language() -> None:
    # Onay (08.3) alias anahtarını yeniden hesaplamaz: Ukraynaca Kiril yazımı dilsiz normalize
    # edilirse belgenin Latin yazımıyla aynı anahtara inmez.
    original = "Гаврилюк Олег"
    key = PersonKey(
        document_numbers=(),
        normalized_name=normalize_name("OLEH", "HAVRYLIUK"),
        date_of_birth=BORN,
        original_script_name=transliterate_name(original, language="uk"),
        normalized_original_name=normalize_name(original, language="uk"),
        mrz_allows_clean_document_number=True,
        conflicts=(),
        surname="HAVRYLIUK",
        given_names="OLEH",
    )

    profile = resolve_unmatched(key, NO_MATCH, entry=PASSPORT_WITHOUT_DOB).proposed_profile

    assert profile is not None
    assert dict(profile.aliases) == {"OLEH HAVRYLIUK": "havryliuk oleh", original: "havryliuk oleh"}
    assert normalize_name(original) != "havryliuk oleh"


# --- §20.2.2 satır 6, 8 ve tablo dışı eksik kişi --------------------------------------------------


def test_clean_number_and_folder_name_is_row_6_not_a_profile() -> None:
    resolution = resolve_unmatched(_key(), NO_MATCH, entry=PASSPORT)

    assert resolution == UnmatchedResolution(
        UnmatchedRule.CREATE, basis=CreationBasis.DOCUMENT_NUMBER
    )
    assert (resolution.action, resolution.queue, resolution.reason) == (
        EmployeeAction.CREATE,
        None,
        None,
    )


@pytest.mark.parametrize(
    "key",
    [
        _key(numbers=(), given_names=None, surname=None, original=None),
        _key(numbers=(), given_names=None, surname=None, original=None, born=None),
    ],
    ids=["birth-date-only", "nothing"],
)
def test_neither_name_nor_number_is_row_8(key: PersonKey) -> None:
    resolution = resolve_unmatched(key, NO_MATCH, entry=PASSPORT)

    assert resolution == UnmatchedResolution(UnmatchedRule.NO_PERSON)
    assert (resolution.action, resolution.queue) == (EmployeeAction.NONE, QueueKind.UNRESOLVED)
    assert resolution.reason == NO_PERSON_REASON


@pytest.mark.parametrize(
    ("key", "detail"),
    [
        (_key(surname=None), "ad-soyad okunmadı, temiz belge numarası var"),
        (_key(given_names=None, original=None), "ad-soyad okunmadı, temiz belge numarası var"),
        (
            _key(given_names=LATIN_WITHOUT_SLUG[0], surname=LATIN_WITHOUT_SLUG[1], original=None),
            "ad-soyad klasör adına çevrilemiyor (K8), temiz belge numarası var",
        ),
        (
            _key(
                numbers=(),
                given_names=LATIN_WITHOUT_SLUG[0],
                surname=LATIN_WITHOUT_SLUG[1],
                original=None,
            ),
            "ad-soyad klasör adına çevrilemiyor (K8), temiz belge numarası yok",
        ),
        (
            _key(numbers=_number(legible=False), given_names=None, surname=None, original=None),
            "ad-soyad okunmadı, temiz belge numarası yok",
        ),
        (
            _key(numbers=(), given_names=None, surname=None),
            "ad-soyad okunmadı, temiz belge numarası yok",
        ),
        (
            _key(numbers=(), given_names=None, original=None),
            "ad-soyad okunmadı, temiz belge numarası yok",
        ),
    ],
    ids=[
        "clean-number-without-surname",
        "clean-number-without-given-names",
        "clean-number-name-without-folder-name",
        "name-without-folder-name",
        "unclean-number-only",
        "original-spelling-only",
        "surname-only",
    ],
)
def test_incomplete_person_goes_to_unresolved_without_a_profile(
    key: PersonKey, detail: str
) -> None:
    # Tabloda yok (D9, D10): klasör adı kurulamayan kişiden ne çalışan açılır ne profil önerilir.
    resolution = resolve_unmatched(key, NO_MATCH, entry=PASSPORT)

    assert resolution == UnmatchedResolution(UnmatchedRule.INCOMPLETE_PERSON, detail=detail)
    assert (resolution.action, resolution.queue) == (EmployeeAction.NONE, QueueKind.UNRESOLVED)
    assert resolution.reason == (
        f"Kişi eksik okundu: kayıtlı çalışanla eşleşme yok, {detail}. "
        "Yeni çalışan açılmaz, profil önerilmez."
    )
    assert resolution.proposed_profile is None
    assert not can_create_employee(key, NO_MATCH, entry=PASSPORT)


@pytest.mark.parametrize(
    "key",
    [
        _key(),
        _key(numbers=()),
        _key(numbers=(), dob_legible=False),
        _key(numbers=(), born=None),
        _key(numbers=(), born=date(2020, 1, 1)),
        _key(numbers=_number("AB12")),
        _key(surname=None),
        _key(given_names="李", surname="王", original=None),
        _key(given_names=LATIN_WITHOUT_SLUG[0], surname=LATIN_WITHOUT_SLUG[1], original=None),
        _key(numbers=(), given_names=None, surname=None, original=None),
    ],
)
@pytest.mark.parametrize("entry", [PASSPORT, PASSPORT_WITHOUT_DOB], ids=["dob-required", "no-dob"])
def test_row_6_and_6b_verdict_agrees_with_can_create_employee(
    key: PersonKey, entry: CatalogEntry
) -> None:
    resolution = resolve_unmatched(key, NO_MATCH, entry=entry, today=TODAY)

    assert (resolution.rule is UnmatchedRule.CREATE) is can_create_employee(
        key, NO_MATCH, entry=entry, today=TODAY
    )
    assert (resolution.basis is not None) is (resolution.rule is UnmatchedRule.CREATE)


@pytest.mark.parametrize(
    "rule", [rule for rule in MatchRule if rule is not MatchRule.NO_MATCH], ids=str
)
def test_rows_6_to_8_apply_only_when_nothing_matched(rule: MatchRule) -> None:
    # Satır 1–5 ve çelişkili anahtar alttaki satırlara inmez (R8, D8, S10).
    with pytest.raises(ValueError, match=f"eşleştirme hükmü {rule.value}"):
        resolve_unmatched(_key(numbers=()), EmployeeMatch(rule), entry=PASSPORT)


def test_reasons_carry_no_personal_values() -> None:
    for key in (
        _key(numbers=(), dob_legible=False),
        _key(numbers=(), given_names=None, surname=None, original=None),
        _key(given_names="TEST", surname=None),
        _key(given_names="Тест", surname="Орнекова"),
    ):
        reason = resolve_unmatched(key, NO_MATCH, entry=PASSPORT).reason
        assert reason is not None
        _assert_no_personal_values(reason)


# --- §20.2.2 satır 7: onaysız çalışan oluşmaz -----------------------------------------------------


def test_pending_profile_writes_only_the_event(session: Session, layout: DataLayout) -> None:
    key = _key(numbers=_number(legible=False))

    profile = propose_pending_profile(session, key, entry=PASSPORT_WITHOUT_DOB, page_index=3)

    assert profile == PROFILE
    assert _counts(session) == (0, 0, 0)
    assert _folders(layout) == []
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.file_id, event.page_index) == (
        EventType.EMPLOYEE_PENDING,
        None,
        None,
        3,
    )
    assert event.message == PENDING_PROFILE_REASON
    assert event.data_json == {
        "action": "pending",
        "queue": "unresolved",
        "document_type_slug": "russian_passport",
    }
    _assert_no_personal_values(json.dumps([event.data_json, event.message], ensure_ascii=False))

    # Onay yok: aynı anahtardan çalışan açılmaz, sonraki belge de hâlâ kimseyle eşleşmez.
    with pytest.raises(EmployeeCreationRefusedError, match="temiz belge numarası yok"):
        create_employee(session, layout, key, entry=PASSPORT_WITHOUT_DOB)
    assert match_employee(session, key) == NO_MATCH
    assert _counts(session) == (0, 0, 0)


def test_pending_profile_does_not_commit(session: Session) -> None:
    propose_pending_profile(session, _key(numbers=()), entry=PASSPORT_WITHOUT_DOB)

    session.rollback()

    assert _events(session) == []


def _registered_number(session: Session) -> None:
    _employee(session, "E0001", numbers=(NUMBER,))


def _registered_name_and_birth_date(session: Session) -> None:
    _employee(session, "E0001", aliases=("ORNEKOVA TEST",))


def _registered_name(session: Session) -> None:
    _employee(session, "E0001", born=date(1980, 1, 1), aliases=("ORNEKOVA TEST",))


def _nobody(session: Session) -> None:
    pass


@pytest.mark.parametrize(
    ("registered", "key", "verdict"),
    [
        (_registered_number, _key(mrz_allows=False), "eşleştirme hükmü document_number"),
        (_registered_name_and_birth_date, _key(numbers=()), "eşleştirme hükmü name_dob"),
        (_registered_name, _key(numbers=()), "eşleştirme hükmü name_only"),
        (_nobody, _key(numbers=(), conflicts=("surname",)), "eşleştirme hükmü conflicting_key"),
        (_nobody, _key(), "satır 6–8 kararı create"),
        (_nobody, _key(numbers=()), "satır 6–8 kararı create"),
        (
            _nobody,
            _key(numbers=(), given_names=None, surname=None, original=None),
            "satır 6–8 kararı no_person",
        ),
        (_nobody, _key(surname=None), "satır 6–8 kararı incomplete_person"),
    ],
    ids=[
        "number-registered",
        "name-and-birth-date-registered",
        "name-only",
        "conflicting-key",
        "clean-number",
        "name-and-birth-date-row-6b",
        "nothing-read",
        "incomplete-person",
    ],
)
def test_pending_profile_is_refused_without_writing_anything(
    session: Session,
    layout: DataLayout,
    registered: Callable[[Session], None],
    key: PersonKey,
    verdict: str,
) -> None:
    # Çağıranın elindeki hükme güvenilmez: tablo veritabanında yeniden değerlendirilir.
    registered(session)
    before = _counts(session)

    with pytest.raises(PendingProfileRefusedError) as refused:
        propose_pending_profile(session, key, entry=PASSPORT, page_index=0)

    message = str(refused.value)
    assert message == f"Onay bekleyen profil önerilmez (§20.2.2 satır 7, K7): {verdict}."
    _assert_no_personal_values(message)
    assert _counts(session) == before
    assert _events(session) == []
    assert _folders(layout) == []


# --- 05.7.2 alias ve numara birikimi -------------------------------------------------------------


def test_number_match_adds_the_new_spellings(session: Session) -> None:
    employee = _employee(session, "E0001", born=None, aliases=("BASKA YAZIM",), numbers=(NUMBER,))

    added = accumulate_identity(session, _key(), entry=PASSPORT)

    assert added == IdentityAccumulation("E0001", ("TEST ORNEKOVA", CYRILLIC), ())
    assert {
        (alias.raw_name, alias.normalized_name, alias.script) for alias in employee.aliases
    } == {
        ("BASKA YAZIM", "baska yazim", None),
        ("TEST ORNEKOVA", NAME, "latin"),
        (CYRILLIC, NAME, "cyrillic"),
    }
    assert [(number.kind, number.value) for number in employee.identifiers] == [
        ("russian_passport", NUMBER)
    ]


def test_name_and_birth_date_match_adds_the_clean_number(session: Session) -> None:
    employee = _employee(session, "E0001", aliases=("ORNEKOVA TEST",))

    added = accumulate_identity(session, _key(), entry=PASSPORT)

    assert added == IdentityAccumulation("E0001", ("TEST ORNEKOVA", CYRILLIC), (NUMBER,))
    assert [
        (number.kind, number.value, number.source_document_id) for number in employee.identifiers
    ] == [("russian_passport", NUMBER, None)]
    # Sonraki belge numarasından (satır 1) eşleşir; numarası farklı okunmuş kişi bu çalışana inmez.
    by_number = _key(given_names=None, surname=None, original=None, born=None)
    assert match_employee(session, by_number) == EmployeeMatch(
        MatchRule.DOCUMENT_NUMBER, ("E0001",)
    )


def test_known_spellings_and_numbers_are_not_added_again(session: Session) -> None:
    _employee(session, "E0001", aliases=("ORNEKOVA TEST",))
    accumulate_identity(session, _key(), entry=PASSPORT)
    before = _counts(session)

    again = accumulate_identity(session, _key(), entry=PASSPORT)

    assert again == IdentityAccumulation("E0001")
    assert _counts(session) == before


def test_number_known_under_another_type_is_not_added_again(session: Session) -> None:
    # Numara değeriyle eşleşir (tür bakılmaz, C27); aynı değer ikinci türle yeniden yazılmaz.
    employee = _employee(session, "E0001", aliases=("TEST ORNEKOVA", CYRILLIC))
    session.add(EmployeeIdentifier(employee=employee, kind="serbian_residence_card", value=NUMBER))
    session.flush()

    assert accumulate_identity(session, _key(), entry=PASSPORT) == IdentityAccumulation("E0001")
    assert [(number.kind, number.value) for number in employee.identifiers] == [
        ("serbian_residence_card", NUMBER)
    ]


def test_new_spelling_of_the_same_name_key_is_an_alias(session: Session) -> None:
    # Yazım ham hâliyle karşılaştırılır: normalize anahtarı aynı olsa da görülen yeni yazımdır.
    employee = _employee(session, "E0001", aliases=("TEST ORNEKOVA",))

    added = accumulate_identity(
        session, _key(given_names="Test", surname="Ornekova", original=None), entry=PASSPORT
    )

    assert added == IdentityAccumulation("E0001", ("Test Ornekova",), (NUMBER,))
    assert {alias.raw_name for alias in employee.aliases} == {"TEST ORNEKOVA", "Test Ornekova"}
    assert {alias.normalized_name for alias in employee.aliases} == {NAME}


@pytest.mark.parametrize(
    ("key", "entry"),
    [
        (_key(numbers=_number(legible=False)), PASSPORT),
        (_key(numbers=_number("AB12")), PASSPORT),
        (_key(mrz_allows=False), PASSPORT),
        (_key(), PHOTO),
    ],
    ids=["illegible", "four-characters", "mrz-check-digits-fail", "type-without-number"],
)
def test_unclean_number_is_not_added(session: Session, key: PersonKey, entry: CatalogEntry) -> None:
    # D11: yanlış okunmuş numara başka birinin belgesini satır 1'le bu çalışana bağlayabilir.
    employee = _employee(session, "E0001", aliases=("ORNEKOVA TEST",))

    added = accumulate_identity(session, key, entry=entry)

    assert added == IdentityAccumulation("E0001", ("TEST ORNEKOVA", CYRILLIC), ())
    assert employee.identifiers == []


def test_only_the_matched_employee_is_changed(session: Session) -> None:
    other = _employee(session, "E0002", born=date(1980, 1, 1), aliases=("BASKA KISI",))
    _employee(session, "E0001", aliases=("ORNEKOVA TEST",))

    accumulate_identity(session, _key(), entry=PASSPORT)

    assert [alias.raw_name for alias in other.aliases] == ["BASKA KISI"]
    assert other.identifiers == []
    assert _count(session, EmployeeAlias) == 4


def _number_owned_twice(session: Session) -> None:
    _employee(session, "E0001", numbers=(NUMBER,))
    _employee(session, "E0002", numbers=(NUMBER,))


def _name_and_birth_date_twice(session: Session) -> None:
    _employee(session, "E0001", aliases=("ORNEKOVA TEST",))
    _employee(session, "E0002", aliases=(CYRILLIC,))


@pytest.mark.parametrize(
    ("registered", "key", "rule"),
    [
        (_nobody, _key(), MatchRule.NO_MATCH),
        (_registered_name, _key(), MatchRule.NAME_ONLY),
        (_number_owned_twice, _key(), MatchRule.DOCUMENT_NUMBER_AMBIGUOUS),
        (_name_and_birth_date_twice, _key(numbers=()), MatchRule.NAME_DOB_AMBIGUOUS),
        (_registered_number, _key(conflicts=("surname",)), MatchRule.CONFLICTING_KEY),
    ],
    ids=str,
)
def test_accumulation_is_refused_without_a_match(
    session: Session, registered: Callable[[Session], None], key: PersonKey, rule: MatchRule
) -> None:
    registered(session)
    before = _counts(session)

    with pytest.raises(IdentityAccumulationRefusedError) as refused:
        accumulate_identity(session, key, entry=PASSPORT)

    message = str(refused.value)
    assert message == (
        "İsim yazımı ve belge numarası eklenmez (§20.2.2 satır 1, 3): "
        f"eşleştirme hükmü {rule.value}."
    )
    _assert_no_personal_values(message)
    assert _counts(session) == before


def test_accumulation_writes_no_event_and_does_not_commit(session: Session) -> None:
    _employee(session, "E0001", aliases=("ORNEKOVA TEST",))
    session.commit()

    accumulate_identity(session, _key(), entry=PASSPORT)
    assert _counts(session) == (1, 3, 1)
    assert _events(session) == []

    session.rollback()
    assert _counts(session) == (1, 1, 0)


# --- entegrasyon: kayıtlı yanıt → gruplama → anahtar → eşleştirme → satır 7 / birikim -------------


def _analyzed_upload(
    session: Session, layout: DataLayout, recording: str, upload_id: str = UPLOAD_ID
) -> Upload:
    """Tek sayfalık sentetik PDF'i Inbox'a yazar, gerçek render adımlarından ve kayıtlı yanıtla
    analizden geçirir."""
    upload = Upload(id=upload_id, channel="web", status=UploadStatus.ANALYZING.value)
    session.add(upload)
    content = make_text_pdf_bytes(["PASAPORT"])
    stored = write_to_inbox(layout, upload.id, "pasaport.pdf", content)
    upload_file = UploadFile(
        upload=upload,
        original_name="pasaport.pdf",
        stored_path=stored.path.relative_to(layout.root).as_posix(),
        sha256=stored.sha256,
        mime="application/pdf",
    )
    session.add(upload_file)
    session.flush()
    settings = Settings(_env_file=None, database_url="sqlite://")
    render_upload_file(session, layout, settings, upload_file)
    extract_upload_file_text(session, layout, upload_file)
    mark_upload_file_blank_pages(session, layout, upload_file)
    analyze_upload(
        session,
        layout,
        upload,
        provider=RecordingProvider.from_directory(RECORDINGS / recording),
        instructions=build_page_analysis_instructions(CATALOG),
    )
    return upload


def _recorded_key(
    session: Session, layout: DataLayout, recording: str, upload_id: str = UPLOAD_ID
) -> tuple[Upload, PersonKey, CatalogEntry]:
    upload = _analyzed_upload(session, layout, recording, upload_id)
    grouping = group_upload(session, upload, catalog=CATALOG, layout=layout)
    (candidate,) = grouping.candidates
    entry = CATALOG.get(candidate.pages[0].analysis.document_type_slug or "")
    assert entry is not None
    return upload, build_person_key((page.analysis for page in candidate.pages), today=TODAY), entry


def test_s9_recorded_passport_without_number_becomes_a_pending_profile(
    session: Session, layout: DataLayout
) -> None:
    # K7/R9: numarası okunamayan belge, tür doğum tarihini zorunlu tutmuyorsa (satır 6b yok) çalışan
    # açmaz; profil önerisiyle Unresolved'a düşer. Doğum tarihi zorunlu pasaportta aynı anahtar
    # satır 6b'dir (`test_name_dob_creation.py`); boru hattında S9 zaten Unreadable'dır (K1).
    upload, key, _ = _recorded_key(session, layout, "s9_blurred_passport")
    entry = PASSPORT_WITHOUT_DOB
    file_id = upload.files[0].id

    with event_context(upload_id=upload.id):
        match = match_employee(session, key, file_id=file_id, page_index=0)
        resolution = resolve_unmatched(key, match, entry=entry)
        profile = propose_pending_profile(session, key, entry=entry, file_id=file_id, page_index=0)
    session.commit()

    assert match == NO_MATCH
    assert (resolution.rule, resolution.action, resolution.queue) == (
        UnmatchedRule.PENDING_PROFILE,
        EmployeeAction.PENDING,
        QueueKind.UNRESOLVED,
    )
    assert profile == resolution.proposed_profile
    assert profile.payload() == {
        "proposed_profile": {
            "given_names": "TEST",
            "surname": "ORNEKOVA",
            "other_names": None,
            "original_script_name": CYRILLIC,
            "date_of_birth": "1990-01-01",
            "nationality": "RUS",
            "aliases": [
                {"raw_name": "TEST ORNEKOVA", "normalized_name": NAME},
                {"raw_name": CYRILLIC, "normalized_name": NAME},
            ],
        }
    }
    assert _counts(session) == (0, 0, 0)
    assert _folders(layout) == []
    events = [
        event
        for event in _events(session)
        if event.type in {EventType.PERSON_NOT_MATCHED, EventType.EMPLOYEE_PENDING}
    ]
    assert [(event.type, event.employee_id) for event in events] == [
        (EventType.PERSON_NOT_MATCHED, None),
        (EventType.EMPLOYEE_PENDING, None),
    ]
    for event in events:
        assert (event.upload_id, event.file_id, event.page_index) == (UPLOAD_ID, file_id, 0)
    _assert_no_personal_values(
        json.dumps([[event.data_json, event.message] for event in events], ensure_ascii=False)
    )


def test_recorded_passport_matched_by_name_and_birth_date_accumulates_its_number(
    session: Session, layout: DataLayout
) -> None:
    # Kayıtlı çalışan numarasız, yalnız isim ve doğum tarihiyle biliniyor: pasaport satır 3'le
    # eşleşir, numarası ve yeni yazımları eklenir; kişinin sonraki belgesi numarasından eşleşir.
    upload, key, entry = _recorded_key(session, layout, "russian_passport")
    employee = _employee(session, "E0001", aliases=("ORNEKOVA TEST",))

    with event_context(upload_id=upload.id):
        match = match_employee(session, key, file_id=upload.files[0].id, page_index=0)
        added = accumulate_identity(session, key, entry=entry)
    session.commit()

    assert match == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))
    assert added == IdentityAccumulation("E0001", ("TEST ORNEKOVA", CYRILLIC), (NUMBER,))
    assert [(number.kind, number.value) for number in employee.identifiers] == [
        ("russian_passport", NUMBER)
    ]
    assert [event.type for event in _events(session) if event.type.startswith("PERSON_")] == [
        EventType.PERSON_MATCHED
    ]
    # Eklenen numara §20.2.1 normalize değeridir (`00 0000001` okundu).
    by_number = replace(
        key, normalized_name=None, normalized_original_name=None, date_of_birth=None
    )
    assert by_number.name_keys == ()
    assert match_employee(session, by_number) == EmployeeMatch(
        MatchRule.DOCUMENT_NUMBER, ("E0001",)
    )


def test_pending_person_is_matched_once_an_employee_is_opened(
    session: Session, layout: DataLayout
) -> None:
    # Onay bekleyen profil kimseyi kaydetmez; aynı kişinin temiz numaralı belgesi çalışanı açınca
    # numarasız belge artık satır 3'le eşleşir, profil önerilmez ve yeni bir şey eklenmez.
    _, blurred, _ = _recorded_key(session, layout, "s9_blurred_passport")
    propose_pending_profile(session, blurred, entry=PASSPORT_WITHOUT_DOB)
    _, clean, entry = _recorded_key(session, layout, "russian_passport", "u_20260915_0002")
    create_employee(session, layout, clean, entry=entry)

    assert match_employee(session, blurred) == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))
    with pytest.raises(PendingProfileRefusedError, match="eşleştirme hükmü name_dob"):
        propose_pending_profile(session, blurred, entry=PASSPORT_WITHOUT_DOB)
    assert accumulate_identity(session, blurred, entry=entry) == IdentityAccumulation("E0001")
    assert _counts(session) == (1, 2, 1)
