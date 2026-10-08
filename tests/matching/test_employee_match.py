"""05.5.1 — önce belge numarası, sonra normalize isim + doğum tarihi denenir; 05.5.2 — yalnız isim
eşleşmesi Unresolved'a gider, otomatik eşleştirme sayılmaz (R8); 05.5.3 — birden fazla çalışan
eşleşirse Unresolved'a gider ve olay loguna yazılır; 05.5.4 — doğum tarihi taşımayan belgenin adı
birleştirilmemiş tek çalışana uyuyorsa eşleşir (`matched_by: name`, §20.2.2 satır 5a). Kabul
senaryoları: S10, S12, S23.

Birim testleri §20.2.2 karar tablosunu elle kurulan `PersonKey` ve geçici SQLite'taki sentetik
çalışanlarla sınar. Entegrasyon testleri sentetik PDF'i gerçek render adımlarından ve kayıtlı yanıt
sağlayıcısıyla (03.6) analizden geçirip `group_upload` → `build_person_key` → `match_employee`
zincirini koşar — gerçek kişi/belge yok, ağ çağrısı yok.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import build_page_analysis_instructions
from app.ai.recording_provider import RecordingProvider
from app.catalog import load_seed_catalog
from app.config import Settings
from app.db.models import (
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    EmployeeStatus,
    Event,
    QueueKind,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.events import EventType, event_context
from app.matching.match import (
    NAME_ONLY_REASON,
    DocumentNumberKey,
    EmployeeAction,
    EmployeeMatch,
    MatchedBy,
    MatchRule,
    PersonKey,
    build_person_key,
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
TODAY = date(2026, 9, 15)
UPLOAD_ID = "u_20260915_0001"

NUMBER = "000000001"
OTHER_NUMBER = "000000099"
BORN = date(1990, 1, 1)
OTHER_BIRTH = date(1991, 1, 1)
NAME = normalize_name("TEST", "ORNEKOVA")
CYRILLIC = "Орнекова Тест"
# `russian_passport` kaydının kişisel değerleri ve normalize biçimleri: olay logunda geçmez.
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "ornekova", "TEST", "00 0000001", NUMBER, "1990-01-01")


def _employee(
    session: Session,
    employee_id: str,
    *,
    born: date | None = BORN,
    aliases: tuple[str, ...] = ("ORNEKOVA TEST",),
    numbers: tuple[str, ...] = (),
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"Test_Ornekova_{employee_id}",
        given_names="Test",
        surname="Ornekova",
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


def _key(
    *,
    numbers: tuple[str, ...] = (NUMBER,),
    name: str | None = NAME,
    born: date | None = BORN,
    original: str | None = None,
    conflicts: tuple[str, ...] = (),
) -> PersonKey:
    return PersonKey(
        document_numbers=tuple(DocumentNumberKey(number, legible=True) for number in numbers),
        normalized_name=name,
        date_of_birth=born,
        original_script_name=None if original is None else transliterate_name(original),
        normalized_original_name=None if original is None else normalize_name(original),
        mrz_allows_clean_document_number=True,
        conflicts=conflicts,
    )


def _events(session: Session) -> list[Event]:
    return list(session.scalars(select(Event).order_by(Event.id)))


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


# --- satır 1–2: belge numarası --------------------------------------------------------------


def test_document_number_owned_by_one_employee_matches(session: Session) -> None:
    # §20.2.2 satır 1.
    _employee(session, "E0001", numbers=(NUMBER,))
    _employee(session, "E0002", aliases=("BASKA KISI",), numbers=(OTHER_NUMBER,))

    result = match_employee(session, _key())

    assert result == EmployeeMatch(MatchRule.DOCUMENT_NUMBER, ("E0001",))
    assert (result.employee_id, result.matched_by, result.action) == (
        "E0001",
        MatchedBy.DOCUMENT_NUMBER,
        EmployeeAction.MATCH,
    )
    assert (result.queue, result.reason) == (None, None)
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message) == (
        EventType.PERSON_MATCHED,
        "E0001",
        None,
    )
    assert event.data_json == {
        "rule": "document_number",
        "matched_by": "document_number",
        "employee_ids": ["E0001"],
    }


def test_document_number_is_tried_before_name_and_birth_date(session: Session) -> None:
    # 05.5.1: ilk uyan satır kazanır — numara başka bir çalışanın isim + doğum tarihinden önce.
    _employee(session, "E0001", born=OTHER_BIRTH, aliases=("BASKA KISI",), numbers=(NUMBER,))
    _employee(session, "E0002")

    result = match_employee(session, _key())

    assert result == EmployeeMatch(MatchRule.DOCUMENT_NUMBER, ("E0001",))


def test_number_registered_twice_for_the_same_employee_is_one_owner(session: Session) -> None:
    employee = _employee(session, "E0001", numbers=(NUMBER,))
    session.add(EmployeeIdentifier(employee=employee, kind="serbian_residence_card", value=NUMBER))
    session.flush()

    assert match_employee(session, _key()) == EmployeeMatch(MatchRule.DOCUMENT_NUMBER, ("E0001",))


def test_number_owned_by_several_employees_is_ambiguous(session: Session) -> None:
    # §20.2.2 satır 2 (05.5.3): isim + doğum tarihi tek bir çalışana uysa bile satır 3'e inilmez.
    _employee(session, "E0010", aliases=("BIRINCI KISI",), numbers=(NUMBER,))
    _employee(session, "E0002", aliases=("IKINCI KISI",), numbers=(NUMBER,))
    _employee(session, "E0003")

    result = match_employee(session, _key())

    assert result == EmployeeMatch(MatchRule.DOCUMENT_NUMBER_AMBIGUOUS, ("E0002", "E0010"))
    assert (result.employee_id, result.matched_by, result.action, result.queue) == (
        None,
        None,
        EmployeeAction.NONE,
        QueueKind.UNRESOLVED,
    )
    assert result.reason == (
        "Belirsiz eşleşme: belge numarası birden fazla çalışana ait (E0002, E0010). "
        "Çalışan otomatik eşleştirilmez."
    )
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message) == (
        EventType.PERSON_AMBIGUOUS,
        None,
        result.reason,
    )
    assert event.data_json == {
        "rule": "document_number_ambiguous",
        "queue": "unresolved",
        "employee_ids": ["E0002", "E0010"],
    }


# --- satır 3–5: isim + doğum tarihi ---------------------------------------------------------


@pytest.mark.parametrize("numbers", [(), (OTHER_NUMBER,)], ids=["no-number", "unmatched-number"])
def test_name_and_birth_date_match_one_employee_when_number_does_not(
    session: Session, numbers: tuple[str, ...]
) -> None:
    # §20.2.2 satır 3: çalışanın kayıtlı başka bir numarası olması satırı değiştirmez.
    _employee(session, "E0001", numbers=("000000055",))
    _employee(session, "E0002", born=OTHER_BIRTH)

    result = match_employee(session, _key(numbers=numbers))

    assert result == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))
    assert (result.employee_id, result.matched_by, result.action, result.queue) == (
        "E0001",
        MatchedBy.NAME_DOB,
        EmployeeAction.MATCH,
        None,
    )
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message) == (
        EventType.PERSON_MATCHED,
        "E0001",
        None,
    )
    assert event.data_json == {
        "rule": "name_dob",
        "matched_by": "name_dob",
        "employee_ids": ["E0001"],
    }


@pytest.mark.parametrize(
    ("name", "original", "aliases"),
    [
        (None, CYRILLIC, (CYRILLIC,)),
        (NAME, CYRILLIC, (CYRILLIC,)),
        (NAME, CYRILLIC, ("Test Ornekova",)),
        (None, "ORNEKOVA TEST", ("Ornekova, Test",)),
    ],
    ids=["original-only", "original-alias", "latin-alias", "original-in-latin"],
)
def test_every_name_key_is_compared_with_aliases(
    session: Session, name: str | None, original: str, aliases: tuple[str, ...]
) -> None:
    # 05.4 anahtarının ad-soyad ve orijinal yazım anahtarlarından biri alias'la eşleşmesi yeter.
    _employee(session, "E0001", aliases=aliases)

    result = match_employee(session, _key(numbers=(), name=name, original=original))

    assert result == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))


def test_name_and_birth_date_fitting_several_employees_is_ambiguous(session: Session) -> None:
    # §20.2.2 satır 4 (05.5.3).
    _employee(session, "E0002")
    _employee(session, "E0001", aliases=("Ornekova Test", "Орнекова Тест"))
    _employee(session, "E0003", born=OTHER_BIRTH)

    result = match_employee(session, _key(numbers=(OTHER_NUMBER,), original=CYRILLIC))

    assert result == EmployeeMatch(MatchRule.NAME_DOB_AMBIGUOUS, ("E0001", "E0002"))
    assert (result.employee_id, result.action, result.queue) == (
        None,
        EmployeeAction.NONE,
        QueueKind.UNRESOLVED,
    )
    assert result.reason == (
        "Belirsiz eşleşme: ad-soyad ve doğum tarihi birden fazla çalışana uyuyor "
        "(E0001, E0002). Çalışan otomatik eşleştirilmez."
    )
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message) == (
        EventType.PERSON_AMBIGUOUS,
        None,
        result.reason,
    )
    assert event.data_json == {
        "rule": "name_dob_ambiguous",
        "queue": "unresolved",
        "employee_ids": ["E0001", "E0002"],
    }


@pytest.mark.parametrize(
    ("document_birth", "employee_birth"),
    [(OTHER_BIRTH, BORN), (BORN, None)],
    ids=["different", "employee-without-birth"],
)
@pytest.mark.parametrize("numbers", [(), (OTHER_NUMBER,)], ids=["no-number", "unmatched-number"])
def test_name_only_match_goes_to_unresolved(
    session: Session,
    document_birth: date | None,
    employee_birth: date | None,
    numbers: tuple[str, ...],
) -> None:
    # §20.2.2 satır 5 (05.5.2, R8, S10): belgede doğum tarihi var ama çalışanınkiyle aynı değil ya
    # da çalışanınki kayıtlı değil — otomatik eşleştirme yok, yeni çalışan da yok.
    _employee(session, "E0001", born=employee_birth)

    result = match_employee(session, _key(numbers=numbers, born=document_birth))

    assert result == EmployeeMatch(MatchRule.NAME_ONLY, ("E0001",))
    assert (result.employee_id, result.matched_by, result.action, result.queue) == (
        None,
        None,
        EmployeeAction.NONE,
        QueueKind.UNRESOLVED,
    )
    assert result.reason == (
        f"{NAME_ONLY_REASON}. İsmi eşleşen çalışan: E0001. Yalnız isim eşleşmesi otomatik "
        "eşleştirme sayılmaz (R8)."
    )
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message) == (
        EventType.PERSON_NOT_MATCHED,
        None,
        result.reason,
    )
    assert event.data_json == {
        "rule": "name_only",
        "queue": "unresolved",
        "employee_ids": ["E0001"],
    }
    assert (_count(session, Employee), _count(session, EmployeeAlias)) == (1, 1)
    assert _count(session, EmployeeIdentifier) == 0


# --- satır 5a: doğum tarihi taşımayan belgenin tekil isim eşleşmesi (05.5.4) -------------------


@pytest.mark.parametrize(
    "employee_birth", [BORN, None], ids=["employee-birth", "no-employee-birth"]
)
@pytest.mark.parametrize("numbers", [(), (OTHER_NUMBER,)], ids=["no-number", "unmatched-number"])
def test_name_without_a_document_birth_date_matches_the_single_employee(
    session: Session, employee_birth: date | None, numbers: tuple[str, ...]
) -> None:
    # §20.2.2 satır 5a (S23): numara eşleşmedi, belgede doğum tarihi yok, ad tek çalışana uyuyor →
    # eşleşme (`matched_by: name`). Bu adım veritabanına olaydan başka bir şey yazmaz.
    _employee(session, "E0001", born=employee_birth)

    result = match_employee(session, _key(numbers=numbers, born=None))

    assert result == EmployeeMatch(MatchRule.NAME, ("E0001",))
    assert (result.employee_id, result.matched_by, result.action, result.queue, result.reason) == (
        "E0001",
        MatchedBy.NAME,
        EmployeeAction.MATCH,
        None,
        None,
    )
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message) == (
        EventType.PERSON_MATCHED,
        "E0001",
        None,
    )
    assert event.data_json == {"rule": "name", "matched_by": "name", "employee_ids": ["E0001"]}
    assert (_count(session, Employee), _count(session, EmployeeAlias)) == (1, 1)
    assert _count(session, EmployeeIdentifier) == 0


def test_name_without_a_birth_date_counts_an_employee_with_two_spellings_once(
    session: Session,
) -> None:
    # Ad-soyad ve orijinal yazım aynı çalışanın iki alias'ına uyuyor: tek kayıt, eşleşme.
    _employee(session, "E0001", aliases=("ORNEKOVA TEST", CYRILLIC))

    result = match_employee(session, _key(numbers=(), born=None, original=CYRILLIC))

    assert result == EmployeeMatch(MatchRule.NAME, ("E0001",))


def test_name_without_a_birth_date_finds_an_inactive_employee(session: Session) -> None:
    # Pasif çalışan da sayılır ve bulunur (10.5.7); belgeyi yerleştirmemek planlayıcının işidir.
    _employee(session, "E0001").status = EmployeeStatus.INACTIVE.value
    session.flush()

    assert match_employee(session, _key(numbers=(), born=None)) == EmployeeMatch(
        MatchRule.NAME, ("E0001",)
    )


def test_name_without_a_birth_date_does_not_count_a_merged_or_removed_spelling(
    session: Session,
) -> None:
    # Birleştirilmiş kayıt (10.5.9) ve İK'nın kaldırdığı isim yazımı (10.5.8) sayıma girmez.
    _employee(session, "E0001").status = EmployeeStatus.MERGED.value
    removed = _employee(session, "E0002")
    removed.aliases[0].removed_at = datetime(2026, 9, 1, tzinfo=UTC)
    _employee(session, "E0003")
    session.flush()

    assert match_employee(session, _key(numbers=(), born=None)) == EmployeeMatch(
        MatchRule.NAME, ("E0003",)
    )


@pytest.mark.parametrize(
    "second_status",
    [EmployeeStatus.ACTIVE, EmployeeStatus.INACTIVE],
    ids=["both-active", "one-inactive"],
)
def test_name_without_a_birth_date_fitting_two_employees_is_ambiguous(
    session: Session, second_status: EmployeeStatus
) -> None:
    # Satır 5a'nın belirsizi: ad birden çok kayda uyuyor (biri pasif olsa da) → Unresolved +
    # `PERSON_AMBIGUOUS`, satır 4'ün kalıbıyla; satır 5'in gerekçesine düşmez.
    _employee(session, "E0001")
    _employee(session, "E0002", born=OTHER_BIRTH).status = second_status.value
    session.flush()

    result = match_employee(session, _key(numbers=(), born=None))

    assert result == EmployeeMatch(MatchRule.NAME_AMBIGUOUS, ("E0001", "E0002"))
    assert (result.employee_id, result.matched_by, result.action, result.queue) == (
        None,
        None,
        EmployeeAction.NONE,
        QueueKind.UNRESOLVED,
    )
    assert result.reason == (
        "Belirsiz eşleşme: belgede doğum tarihi yok, ad-soyad birden fazla çalışana uyuyor "
        "(E0001, E0002). Çalışan otomatik eşleştirilmez."
    )
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message) == (
        EventType.PERSON_AMBIGUOUS,
        None,
        result.reason,
    )
    assert event.data_json == {
        "rule": "name_ambiguous",
        "queue": "unresolved",
        "employee_ids": ["E0001", "E0002"],
    }


def test_name_only_reason_is_the_prd_text() -> None:
    assert NAME_ONLY_REASON == "İsim eşleşti ama doğum tarihi veya belge numarası doğrulanamadı"


@pytest.mark.parametrize(
    ("first_birth", "second_birth", "expected"),
    [
        (BORN, OTHER_BIRTH, EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))),
        (OTHER_BIRTH, BORN, EmployeeMatch(MatchRule.NAME_DOB, ("E0002",))),
        (BORN, BORN, EmployeeMatch(MatchRule.NAME_DOB_AMBIGUOUS, ("E0001", "E0002"))),
        (OTHER_BIRTH, None, EmployeeMatch(MatchRule.NAME_ONLY, ("E0001", "E0002"))),
    ],
    ids=["fits-first", "fits-second", "fits-both", "fits-none"],
)
def test_s12_same_named_employees_are_told_apart_by_birth_date(
    session: Session, first_birth: date | None, second_birth: date | None, expected: EmployeeMatch
) -> None:
    # S12: aynı isimli iki çalışan; doğum tarihi birine uyuyorsa o çalışan, ikisine ya da
    # hiçbirine uymuyorsa Unresolved.
    _employee(session, "E0001", born=first_birth)
    _employee(session, "E0002", born=second_birth, aliases=("Test Ornekova",))

    result = match_employee(session, _key(numbers=()))

    assert result == expected
    assert result.queue is (None if expected.matched_by else QueueKind.UNRESOLVED)
    if expected.rule is MatchRule.NAME_ONLY:
        assert result.reason is not None
        assert "İsmi eşleşen çalışanlar: E0001, E0002." in result.reason


# --- eşleşme yok ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "aliases", "numbers"),
    [
        (_key(), ("BASKA KISI",), (OTHER_NUMBER,)),
        (_key(numbers=(), name=None, born=None), ("ORNEKOVA TEST",), (NUMBER,)),
        (_key(name=None), ("ORNEKOVA TEST",), (OTHER_NUMBER,)),
        (_key(numbers=()), ("ORNEKOVA",), ()),
        (_key(numbers=()), ("ANNA ORNEKOVA TEST",), ()),
    ],
    ids=["nobody", "empty-key", "unmatched-number-without-name", "alias-subset", "alias-superset"],
)
def test_key_matching_no_employee_is_left_to_the_following_rows(
    session: Session, key: PersonKey, aliases: tuple[str, ...], numbers: tuple[str, ...]
) -> None:
    # Satır 6–8'in eylemi 05.6/05.7'nin: hüküm ne eşleşme ne kuyruk. İsim tam eşitlikle
    # karşılaştırılır.
    _employee(session, "E0001", aliases=aliases, numbers=numbers)

    result = match_employee(session, key)

    assert result == EmployeeMatch(MatchRule.NO_MATCH)
    assert (result.employee_id, result.matched_by, result.action, result.queue, result.reason) == (
        None,
        None,
        None,
        None,
        None,
    )
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message, event.data_json) == (
        EventType.PERSON_NOT_MATCHED,
        None,
        None,
        {"rule": "no_match"},
    )


def test_employee_name_columns_are_not_aliases(session: Session) -> None:
    # §20.2.2 isim eşleşmesini `employee_aliases`'ta arar; çalışanın adı alias olarak birikmelidir.
    _employee(session, "E0001", aliases=())

    assert match_employee(session, _key(numbers=())) == EmployeeMatch(MatchRule.NO_MATCH)


def test_stored_numbers_are_compared_exactly(session: Session) -> None:
    # Numara yazan adım (05.6, 05.7.2) §20.2.1 normalize değeri saklar; karşılaştırma tam eşitlik.
    _employee(session, "E0001", aliases=(), numbers=("00 0000001",))

    assert match_employee(session, _key()) == EmployeeMatch(MatchRule.NO_MATCH)


# --- çelişkili anahtar (D8) -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "conflicts"),
    [
        (
            _key(numbers=(NUMBER, OTHER_NUMBER), conflicts=("document_number",)),
            "document_number",
        ),
        (_key(born=None, conflicts=("date_of_birth",)), "date_of_birth"),
        (
            _key(name=None, original=CYRILLIC, conflicts=("surname", "original_script_name")),
            "surname, original_script_name",
        ),
    ],
    ids=["numbers", "birth-date", "names"],
)
def test_conflicting_key_goes_to_unresolved_before_any_row(
    session: Session, key: PersonKey, conflicts: str
) -> None:
    # Tabloda karşılığı yok (D8): numara tek bir çalışana ait olsa bile otomatik eşleştirilmez.
    _employee(session, "E0001", numbers=(NUMBER,))

    result = match_employee(session, key)

    assert result == EmployeeMatch(MatchRule.CONFLICTING_KEY, conflicts=key.conflicts)
    assert (result.employee_id, result.action, result.queue) == (
        None,
        EmployeeAction.NONE,
        QueueKind.UNRESOLVED,
    )
    assert result.reason == (
        f"Kişi anahtarı çelişkili: adayın sayfaları şu alanları farklı okuyor: {conflicts}. "
        "Çalışan otomatik eşleştirilmez."
    )
    (event,) = _events(session)
    assert (event.type, event.employee_id, event.message) == (
        EventType.PERSON_NOT_MATCHED,
        None,
        result.reason,
    )
    assert event.data_json == {
        "rule": "conflicting_key",
        "queue": "unresolved",
        "conflicts": list(key.conflicts),
    }


# --- olay ve işlem sınırı ---------------------------------------------------------------------


def test_employee_numbers_are_ordered_numerically(session: Session) -> None:
    for employee_id in ("E10000", "E9999", "E0002"):
        _employee(session, employee_id, aliases=(f"KISI {employee_id}",), numbers=(NUMBER,))

    result = match_employee(session, _key())

    assert result.employee_ids == ("E0002", "E9999", "E10000")


def test_match_writes_only_the_event_and_does_not_commit(session: Session) -> None:
    _employee(session, "E0001", numbers=(NUMBER,))
    session.commit()

    result = match_employee(session, _key(numbers=("000000077", NUMBER), name=None))

    assert result == EmployeeMatch(MatchRule.DOCUMENT_NUMBER, ("E0001",))

    assert (_count(session, Employee), _count(session, EmployeeAlias)) == (1, 1)
    assert _count(session, EmployeeIdentifier) == 1
    assert len(_events(session)) == 1
    session.rollback()
    assert _events(session) == []


# --- entegrasyon: kayıtlı yanıt → gruplama → anahtar → eşleştirme ----------------------------


def _passport_upload(session: Session, layout: DataLayout) -> Upload:
    """Tek sayfalık sentetik PDF'i Inbox'a yazar, gerçek render adımlarından ve `russian_passport`
    kaydıyla analizden geçirir."""
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
        provider=RecordingProvider.from_directory(RECORDINGS / "russian_passport"),
        instructions=build_page_analysis_instructions(CATALOG),
    )
    return upload


def _employees_s1(session: Session) -> None:
    _employee(session, "E0007", born=OTHER_BIRTH, aliases=("BASKA KISI",), numbers=(NUMBER,))
    _employee(session, "E0008")


def _employees_s10(session: Session) -> None:
    _employee(session, "E0001", born=OTHER_BIRTH, numbers=(OTHER_NUMBER,))


def _employees_s12_one(session: Session) -> None:
    _employee(session, "E0001", born=OTHER_BIRTH)
    _employee(session, "E0002")


def _employees_s12_both(session: Session) -> None:
    _employee(session, "E0001")
    _employee(session, "E0002", aliases=("Орнекова Тест",))


@pytest.mark.parametrize(
    ("employees", "expected", "event_type"),
    [
        (
            _employees_s1,
            EmployeeMatch(MatchRule.DOCUMENT_NUMBER, ("E0007",)),
            EventType.PERSON_MATCHED,
        ),
        (
            _employees_s10,
            EmployeeMatch(MatchRule.NAME_ONLY, ("E0001",)),
            EventType.PERSON_NOT_MATCHED,
        ),
        (
            _employees_s12_one,
            EmployeeMatch(MatchRule.NAME_DOB, ("E0002",)),
            EventType.PERSON_MATCHED,
        ),
        (
            _employees_s12_both,
            EmployeeMatch(MatchRule.NAME_DOB_AMBIGUOUS, ("E0001", "E0002")),
            EventType.PERSON_AMBIGUOUS,
        ),
    ],
    ids=["s1-number", "s10-name-only", "s12-birth-date-fits-one", "s12-birth-date-fits-both"],
)
def test_recorded_passport_is_matched_in_table_order(
    session: Session,
    layout: DataLayout,
    employees: Callable[[Session], None],
    expected: EmployeeMatch,
    event_type: EventType,
) -> None:
    upload = _passport_upload(session, layout)
    employees(session)
    grouping = group_upload(session, upload, catalog=CATALOG, layout=layout)
    (candidate,) = grouping.candidates
    key = build_person_key((page.analysis for page in candidate.pages), today=TODAY)
    first = candidate.pages[0]
    before = _count(session, Employee)

    with event_context(upload_id=upload.id):
        result = match_employee(session, key, file_id=first.file_id, page_index=first.index)

    assert result == expected
    assert _count(session, Employee) == before
    (event,) = session.scalars(select(Event).where(Event.type.like("PERSON_%")))
    assert (event.type, event.upload_id, event.file_id, event.page_index) == (
        event_type,
        UPLOAD_ID,
        upload.files[0].id,
        0,
    )
    assert (event.employee_id, event.message) == (result.employee_id, result.reason)
    logged = json.dumps([event.data_json, event.message], ensure_ascii=False)
    for value in PERSONAL_VALUES:
        assert value not in logged
