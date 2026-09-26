"""05.6.1 — temiz okunmuş belge numarası varsa yeni çalışan ve klasörü açılır (R9, K7, K8).
Kabul senaryosu: S11 (temiz pasaport numarası, kayıtlı çalışan yok → yeni çalışan ve klasör).

Birim testleri §20.2.3'ün üç koşulunu ve §20.2.2 satır 6'yı elle kurulan `PersonKey` ve geçici
SQLite'taki sentetik çalışanlarla sınar. Satır 6b (ad + doğum tarihi, 05.6.2) ayrı dosyadadır
(`test_name_dob_creation.py`); burada satır 6'nın uymadığı anahtar 6b'ye de bilerek uymaz (doğum
tarihi okunmamış, okunaklı değil ya da türün zorunlu alanı değil). Entegrasyon testleri sentetik
PDF'i gerçek render adımlarından ve kayıtlı yanıt sağlayıcısıyla (03.6) analizden geçirip
`group_upload` →
`build_person_key` → `match_employee` → `create_employee` zincirini koşar — gerçek kişi/belge yok,
ağ çağrısı yok.
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
    Upload,
    UploadFile,
    UploadStatus,
)
from app.events import EventType, event_context
from app.matching.match import (
    CLEAN_DOCUMENT_NUMBER_MIN_LENGTH,
    DocumentNumberKey,
    EmployeeCreationRefusedError,
    EmployeeMatch,
    MatchRule,
    PersonKey,
    build_person_key,
    can_create_employee,
    clean_document_number,
    create_employee,
    match_employee,
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
# Satır 6b'nin (§20.2.4 koşul 1) dışında kalan tür: doğum tarihi zorunlu alan değil.
PASSPORT_WITHOUT_DOB = PASSPORT.model_copy(
    update={"required_fields": tuple(f for f in PASSPORT.required_fields if f != "date_of_birth")}
)
TODAY = date(2026, 9, 15)
UPLOAD_ID = "u_20260915_0001"

NUMBER = "000000001"
BORN = date(1990, 1, 1)
CYRILLIC = "Орнекова Тест"
# Latin harfli ama klasör adına (ASCII) inmeyen ad-soyad (D9): `ə`, `ʃ` Latin harfidir.
LATIN_WITHOUT_SLUG = ("Əə", "ʃ")
# Anahtarın kişisel değerleri ve normalize biçimleri: olay logunda ve ret mesajında geçmez.
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
    aliases: tuple[str, ...] = (),
    numbers: tuple[str, ...] = (),
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"Baska_Kisi_{employee_id}",
        given_names="Baska",
        surname="Kisi",
        date_of_birth=date(1980, 1, 1),
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


def _events(session: Session, event_type: EventType | None = None) -> list[Event]:
    query = select(Event).order_by(Event.id)
    if event_type is not None:
        query = query.where(Event.type == event_type.value)
    return list(session.scalars(query))


def _folders(layout: DataLayout) -> list[str]:
    return sorted(path.name for path in layout.employees.iterdir())


# --- §20.2.3 temiz belge numarası ---------------------------------------------------------------


def test_number_meeting_all_three_conditions_is_clean() -> None:
    assert clean_document_number(_key(), PASSPORT) == NUMBER


def test_five_characters_are_enough() -> None:
    assert CLEAN_DOCUMENT_NUMBER_MIN_LENGTH == 5
    assert clean_document_number(_key(numbers=_number("AB123")), PASSPORT) == "AB123"


@pytest.mark.parametrize(
    ("key", "entry"),
    [
        (_key(), PHOTO),
        (_key(), PASSPORT.model_copy(update={"required_fields": ("surname", "given_names")})),
        (_key(numbers=_number(legible=False)), PASSPORT),
        (_key(numbers=_number("AB12")), PASSPORT),
        (_key(mrz_allows=False), PASSPORT),
        (_key(numbers=()), PASSPORT),
        (
            _key(numbers=(*_number(), *_number("000000002")), conflicts=("document_number",)),
            PASSPORT,
        ),
    ],
    ids=[
        "type-without-number",
        "number-not-required",
        "illegible",
        "four-characters",
        "mrz-check-digits-fail",
        "no-number",
        "several-numbers",
    ],
)
def test_number_failing_a_condition_is_not_clean(key: PersonKey, entry: CatalogEntry) -> None:
    # Koşul 1: tür numarayı beklemiyor; koşul 2: okunaklı ve en az 5 karakter; koşul 3: MRZ
    # alan ve bileşik haneleri tutuyor. Birden fazla numaradan biri seçilmez (D8).
    assert clean_document_number(key, entry) is None


# --- §20.2.2 satır 6: karar -----------------------------------------------------------------------


def test_no_match_with_clean_number_and_name_may_create_an_employee() -> None:
    assert can_create_employee(_key(), EmployeeMatch(MatchRule.NO_MATCH), entry=PASSPORT)


@pytest.mark.parametrize(
    "match",
    [EmployeeMatch(rule) for rule in MatchRule if rule is not MatchRule.NO_MATCH],
    ids=[rule.value for rule in MatchRule if rule is not MatchRule.NO_MATCH],
)
def test_any_match_verdict_but_no_match_creates_nobody(match: EmployeeMatch) -> None:
    # Satır 1–5 ve çelişkili anahtar satır 6'ya inmez (R8, D8).
    assert not can_create_employee(_key(), match, entry=PASSPORT)


@pytest.mark.parametrize(
    "key",
    [
        _key(numbers=_number(legible=False), born=None),
        _key(surname=None),
        _key(given_names=None, original=None),
        _key(given_names=LATIN_WITHOUT_SLUG[0], surname=LATIN_WITHOUT_SLUG[1], original=None),
        _key(given_names="李", surname="王", original=None),
    ],
    ids=[
        "unclean-number",
        "surname-not-read",
        "given-names-not-read",
        "name-without-folder-name",
        "name-without-latin-spelling",
    ],
)
def test_key_without_clean_number_or_folder_name_creates_nobody(key: PersonKey) -> None:
    # Temiz numara ve doğum tarihi yoksa satır 7–8 (05.7); ad-soyad klasör adı vermiyorsa (D9) ya da
    # Latin yazımı yoksa (05.2.2) numara temiz olsa da çalışan açılmaz.
    assert not can_create_employee(key, EmployeeMatch(MatchRule.NO_MATCH), entry=PASSPORT)


# --- §20.2.2 satır 6: çalışan ve klasör ---------------------------------------------------------


def test_clean_number_without_registered_employee_opens_employee_and_folder(
    session: Session, layout: DataLayout
) -> None:
    # S11 (birim): yeni çalışan kaydı, isim yazımları, numara, klasör ve olay.
    employee = create_employee(session, layout, _key(), entry=PASSPORT, page_index=2)

    assert (employee.id, employee.folder_name, employee.status) == (
        "E0001",
        "Test_Ornekova_E0001",
        "active",
    )
    assert session.get(Employee, "E0001") is employee
    assert (
        employee.given_names,
        employee.surname,
        employee.other_names,
        employee.original_script_name,
        employee.date_of_birth,
        employee.nationality,
    ) == ("TEST", "ORNEKOVA", "IVANOVNA", CYRILLIC, BORN, "RUS")
    aliases = {(alias.raw_name, alias.normalized_name, alias.script) for alias in employee.aliases}
    assert aliases == {
        ("TEST ORNEKOVA", "ornekova test", "latin"),
        (CYRILLIC, "ornekova test", "cyrillic"),
    }
    assert [
        (number.kind, number.value, number.source_document_id) for number in employee.identifiers
    ] == [("russian_passport", NUMBER, None)]

    assert _folders(layout) == ["Test_Ornekova_E0001"]
    assert layout.received_dir(employee.folder_name).is_dir()
    assert layout.ready_dir(employee.folder_name).is_dir()
    # profil.md 09.1.1'in işidir.
    assert not layout.profile_path(employee.folder_name).exists()

    (event,) = _events(session)
    assert (event.type, event.employee_id, event.file_id, event.page_index, event.message) == (
        EventType.EMPLOYEE_CREATED,
        "E0001",
        None,
        2,
        None,
    )
    assert event.data_json == {
        "action": "create",
        "basis": "document_number",
        "document_type_slug": "russian_passport",
    }


def test_created_employee_is_found_by_the_following_documents(
    session: Session, layout: DataLayout
) -> None:
    # Numara normalize, isim yazımları alias olarak saklandığı için sonraki belge 05.5'te eşleşir
    # ve aynı kişiden ikinci çalışan açılmaz.
    create_employee(session, layout, _key(), entry=PASSPORT)

    by_name = _key(numbers=(), original=None)
    by_original = _key(numbers=(), given_names=None, surname=None)
    assert match_employee(session, _key()) == EmployeeMatch(MatchRule.DOCUMENT_NUMBER, ("E0001",))
    assert match_employee(session, by_name) == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))
    assert match_employee(session, by_original) == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))

    with pytest.raises(EmployeeCreationRefusedError, match="eşleştirme hükmü document_number"):
        create_employee(session, layout, _key(), entry=PASSPORT)
    assert _count(session, Employee) == 1
    assert _folders(layout) == ["Test_Ornekova_E0001"]


def test_new_employee_takes_the_next_employee_number(session: Session, layout: DataLayout) -> None:
    _employee(session, "E0041", aliases=("BASKA KISI",), numbers=("000000099",))

    employee = create_employee(session, layout, _key(), entry=PASSPORT)

    assert (employee.id, employee.folder_name) == ("E0042", "Test_Ornekova_E0042")
    assert _folders(layout) == ["Test_Ornekova_E0042"]


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        (None, {"TEST ORNEKOVA"}),
        ("TEST ORNEKOVA", {"TEST ORNEKOVA"}),
        ("ORNEKOVA TEST", {"TEST ORNEKOVA", "ORNEKOVA TEST"}),
    ],
    ids=["no-original", "same-spelling", "other-spelling"],
)
def test_each_spelling_is_one_alias(
    session: Session, layout: DataLayout, original: str | None, expected: set[str]
) -> None:
    employee = create_employee(session, layout, _key(original=original), entry=PASSPORT)

    assert {alias.raw_name for alias in employee.aliases} == expected
    assert _count(session, EmployeeAlias) == len(expected)


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("عبدالله محمد", "arabic"),
        ("Δημήτρης Παπαδόπουλος", "other"),
    ],
    ids=["arabic", "greek-other"],
)
def test_alias_script_matches_the_original_writing_system(
    session: Session, layout: DataLayout, original: str, expected: str
) -> None:
    # 05.8.3: `employee_aliases.script` yazımın alfabesidir; ICAO tablosunun dışındaki alfabeler
    # (Arapça dışında) `other`'dır.
    employee = create_employee(session, layout, _key(original=original), entry=PASSPORT)

    scripts = {alias.raw_name: alias.script for alias in employee.aliases}
    assert scripts["TEST ORNEKOVA"] == "latin"
    assert scripts[original] == expected


@pytest.mark.parametrize(
    ("given_names", "surname", "expected"),
    [
        ("007", "BOND", "latin"),
        ("007", "1990", None),
    ],
    ids=["leading-digits-before-a-letter", "no-letter-at-all"],
)
def test_alias_script_skips_leading_non_letters_and_is_none_without_any(
    session: Session, layout: DataLayout, given_names: str, surname: str, expected: str | None
) -> None:
    key = _key(given_names=given_names, surname=surname, original=None)

    employee = create_employee(session, layout, key, entry=PASSPORT)

    (alias,) = employee.aliases
    assert alias.script == expected


def test_employee_is_named_after_the_latin_reading_and_keeps_the_original(
    session: Session, layout: DataLayout
) -> None:
    # 05.2.2: okuma Kiril, Latin yazımı (`build_person_key`'in bulduğu) çalışan kaydına ve klasör
    # adına gider; Kiril yazım orijinal yazımda durur, isim yazımı (alias) okunduğu gibi kalır.
    key = replace(
        _key(given_names="Юлья", surname="Тестова-Щёлкина", original="Тестова-Щёлкина Юлья"),
        latin_given_names="Iulia",
        latin_surname="Testova-Shchelkina",
    )

    employee = create_employee(session, layout, key, entry=PASSPORT)

    assert employee.folder_name == "Iulia_Testova_Shchelkina_E0001"
    assert (employee.given_names, employee.surname, employee.original_script_name) == (
        "Iulia",
        "Testova-Shchelkina",
        "Тестова-Щёлкина Юлья",
    )
    assert employee.other_names == "IVANOVNA"
    assert "Юлья Тестова-Щёлкина" in {alias.raw_name for alias in employee.aliases}


def _registered_number(session: Session) -> None:
    _employee(session, "E0001", numbers=(NUMBER,))


def _registered_name(session: Session) -> None:
    _employee(session, "E0001", aliases=("ORNEKOVA TEST",))


def _nobody(session: Session) -> None:
    pass


@pytest.mark.parametrize(
    ("registered", "key", "entry", "reason"),
    [
        (_registered_number, _key(), PASSPORT, "eşleştirme hükmü document_number"),
        (_registered_name, _key(), PASSPORT, "eşleştirme hükmü name_only"),
        (
            _nobody,
            _key(conflicts=("date_of_birth",)),
            PASSPORT,
            "eşleştirme hükmü conflicting_key",
        ),
        (
            _nobody,
            _key(numbers=_number(legible=False), born=None),
            PASSPORT,
            "temiz belge numarası yok (§20.2.3) ve doğum tarihi okunmadı",
        ),
        (
            _nobody,
            _key(numbers=(), dob_legible=False),
            PASSPORT,
            "temiz belge numarası yok (§20.2.3) ve doğum tarihi okunaklı okunmadı",
        ),
        (
            _nobody,
            _key(numbers=(), born=date(2020, 1, 1)),
            PASSPORT,
            "doğum tarihi makul yaş doğrulamasından geçmedi",
        ),
        (
            _nobody,
            _key(mrz_allows=False),
            PASSPORT_WITHOUT_DOB,
            "temiz belge numarası yok (§20.2.3) ve doğum tarihi türün zorunlu alanı değil",
        ),
        (_nobody, _key(), PHOTO, "doğum tarihi türün zorunlu alanı değil"),
        (_nobody, _key(surname=None), PASSPORT, "ad-soyad okunmadı"),
        (_nobody, replace(_key(), given_names=None), PASSPORT, "ad-soyad okunmadı"),
        (
            _nobody,
            _key(given_names=LATIN_WITHOUT_SLUG[0], surname=LATIN_WITHOUT_SLUG[1], original=None),
            PASSPORT,
            "ad-soyad klasör adına çevrilemiyor",
        ),
        (
            _nobody,
            _key(given_names="李", surname="王", original=None),
            PASSPORT,
            "Latin yazım belgede yok",
        ),
        (
            _nobody,
            _key(given_names="Тест", surname="Орнекова"),
            PASSPORT,
            "Latin yazım belgede yok",
        ),
    ],
    ids=[
        "number-registered",
        "name-only",
        "conflicting-key",
        "illegible-number-without-date-of-birth",
        "no-number-illegible-date-of-birth",
        "no-number-implausible-date-of-birth",
        "mrz-check-digits-fail-date-of-birth-not-required",
        "type-without-number",
        "surname-not-read",
        "given-names-reading-missing-beside-name-key",
        "name-without-folder-name",
        "name-without-latin-spelling",
        "cyrillic-reading-without-latin-spelling",
    ],
)
def test_creation_is_refused_without_writing_anything(
    session: Session,
    layout: DataLayout,
    registered: Callable[[Session], None],
    key: PersonKey,
    entry: CatalogEntry,
    reason: str,
) -> None:
    # R9: temiz numarası ve §20.2.4'e uyan doğum tarihi olmayan belgeden, eşleşen belgeden
    # çalışan doğmaz.
    registered(session)
    before = (_count(session, Employee), _count(session, EmployeeAlias))

    with pytest.raises(EmployeeCreationRefusedError) as refused:
        create_employee(session, layout, key, entry=entry, today=TODAY, page_index=0)

    message = str(refused.value)
    assert message.startswith("Yeni çalışan açılmaz (§20.2.2 satır 6, 6b; R9): ")
    assert reason in message
    for value in (*PERSONAL_VALUES, "2020-01-01"):
        assert value not in message
    assert (_count(session, Employee), _count(session, EmployeeAlias)) == before
    assert _count(session, EmployeeIdentifier) == (1 if registered is _registered_number else 0)
    assert _events(session) == []
    assert _folders(layout) == []


def test_creation_does_not_commit(session: Session, layout: DataLayout) -> None:
    create_employee(session, layout, _key(), entry=PASSPORT)

    session.rollback()

    assert (_count(session, Employee), _count(session, EmployeeAlias)) == (0, 0)
    assert (_count(session, EmployeeIdentifier), _events(session)) == (0, [])
    # Dosya sistemi işleme bağlı değil: boş klasör kalır, E numarası sonraki çağrıya yine verilir.
    assert _folders(layout) == ["Test_Ornekova_E0001"]
    assert create_employee(session, layout, _key(), entry=PASSPORT).id == "E0001"


# --- entegrasyon: kayıtlı yanıt → gruplama → anahtar → eşleştirme → yeni çalışan ------------------


def _analyzed_upload(session: Session, layout: DataLayout, recording: str) -> Upload:
    """Tek sayfalık sentetik PDF'i Inbox'a yazar, gerçek render adımlarından ve kayıtlı yanıtla
    analizden geçirir."""
    upload = Upload(id=UPLOAD_ID, channel="web", status=UploadStatus.ANALYZING.value)
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


@pytest.mark.parametrize(
    ("recording", "folder_name", "original", "number"),
    [
        ("russian_passport", "Test_Ornekova_E0001", CYRILLIC, NUMBER),
        (
            "s13_cyrillic_name",
            "Iulia_Testova_Shchelkina_E0001",
            "Тестова-Щёлкина Юлья",
            "000000013",
        ),
    ],
    ids=["s11-passport", "s13-cyrillic-name"],
)
def test_s11_recorded_passport_without_registered_employee_opens_employee_and_folder(
    session: Session,
    layout: DataLayout,
    recording: str,
    folder_name: str,
    original: str,
    number: str,
) -> None:
    upload = _analyzed_upload(session, layout, recording)
    grouping = group_upload(session, upload, catalog=CATALOG, layout=layout)
    (candidate,) = grouping.candidates
    entry = CATALOG.get(candidate.pages[0].analysis.document_type_slug or "")
    assert entry is PASSPORT
    key = build_person_key((page.analysis for page in candidate.pages), today=TODAY)
    first = candidate.pages[0]

    with event_context(upload_id=upload.id):
        match = match_employee(session, key, file_id=first.file_id, page_index=first.index)
        assert match == EmployeeMatch(MatchRule.NO_MATCH)
        assert clean_document_number(key, entry) == number
        assert can_create_employee(key, match, entry=entry)
        employee = create_employee(
            session, layout, key, entry=entry, file_id=first.file_id, page_index=first.index
        )
    session.commit()

    assert (employee.id, employee.folder_name, employee.original_script_name) == (
        "E0001",
        folder_name,
        original,
    )
    assert [(item.kind, item.value) for item in employee.identifiers] == [
        ("russian_passport", number)
    ]
    assert _folders(layout) == [folder_name]
    assert layout.ready_dir(folder_name).is_dir() and layout.received_dir(folder_name).is_dir()
    events = [
        event
        for event in _events(session)
        if event.type in {EventType.PERSON_NOT_MATCHED, EventType.EMPLOYEE_CREATED}
    ]
    assert [(event.type, event.employee_id) for event in events] == [
        (EventType.PERSON_NOT_MATCHED, None),
        (EventType.EMPLOYEE_CREATED, "E0001"),
    ]
    for event in events:
        assert (event.upload_id, event.file_id, event.page_index) == (
            UPLOAD_ID,
            upload.files[0].id,
            0,
        )
    logged = json.dumps([[event.data_json, event.message] for event in events], ensure_ascii=False)
    for value in (*PERSONAL_VALUES, "TESTOVA", "Тестова", "IULIA", "000000013"):
        assert value not in logged

    # Aynı kişinin sonraki belgesi yeni çalışanla numarasından eşleşir.
    assert match_employee(session, key) == EmployeeMatch(MatchRule.DOCUMENT_NUMBER, ("E0001",))


def test_s9_blurred_passport_number_opens_no_employee(session: Session, layout: DataLayout) -> None:
    # R9: belge numarası okunamayan pasaporttan satır 6 (temiz numara) çalışan açmaz. Satır 6b
    # ad + doğum tarihine bakar (`test_name_dob_creation.py`); burada yalnız numara yolu sınanır,
    # bu yüzden tür doğum tarihini zorunlu tutmaz. Boru hattında S9 zaten Unreadable'dır: zorunlu
    # numara okunaksız (K1), çalışan kararına inilmez.
    upload = _analyzed_upload(session, layout, "s9_blurred_passport")
    grouping = group_upload(session, upload, catalog=CATALOG, layout=layout)
    (candidate,) = grouping.candidates
    key = build_person_key((page.analysis for page in candidate.pages), today=TODAY)
    match = match_employee(session, key)

    assert match == EmployeeMatch(MatchRule.NO_MATCH)
    assert key.normalized_name == "ornekova test"
    assert clean_document_number(key, PASSPORT) is None
    assert not can_create_employee(key, match, entry=PASSPORT_WITHOUT_DOB, today=TODAY)
    with pytest.raises(EmployeeCreationRefusedError, match="temiz belge numarası yok"):
        create_employee(session, layout, key, entry=PASSPORT_WITHOUT_DOB, today=TODAY)
    assert _count(session, Employee) == 0
    assert _events(session, EventType.EMPLOYEE_CREATED) == []
    assert _folders(layout) == []
