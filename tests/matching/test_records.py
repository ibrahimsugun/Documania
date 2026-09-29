"""10.5.8 — profil alt kayıtları (`app.matching.records`): kaldırılan isim yazımı, belge numarası
ve iletişim bilgisi silinmez, eşleştirmeye girmez (K6), belgeden yeniden gelirse geri açılmaz; geri
alma tek adımdır; iletişim bilgisi elle eklenir (05.8.2). Olaylar değer taşımaz (CONVENTIONS §6).

Kayıtlar ve kişi anahtarları sentetiktir; gerçek kişi ya da belge yok, ağ çağrısı yok. Web akışı
`tests/web/test_profile_records.py`'dedir.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import load_seed_catalog
from app.db.models import (
    ContactKind,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    EmployeeStatus,
    Event,
    record_contact_sighting,
    utcnow,
)
from app.events import EventType
from app.matching.context import (
    ContextPersonBasis,
    ContextPersonResult,
    context_person_verdict,
    context_profile,
)
from app.matching.match import (
    DocumentNumberKey,
    EmployeeMatch,
    MatchRule,
    PersonKey,
    accumulate_identity,
    create_employee,
    match_employee,
)
from app.matching.names import normalize_name
from app.matching.records import (
    CONTACT_VALUE_MAX_LENGTH,
    ContactFormError,
    ProfileRecordStateError,
    RecordKind,
    add_contact,
    employee_records,
    find_record,
    number_owners,
    record_kind,
    record_label,
    remove_record,
    restore_record,
    seen_after_removal_warning,
)
from app.profiles.render import render_profile
from app.storage import DataLayout

CATALOG = load_seed_catalog()
PASSPORT = CATALOG.get("russian_passport")
assert PASSPORT is not None
NUMBER = "000000001"
OTHER_NUMBER = "000000002"
BORN = date(1990, 1, 1)
ACTOR = "ik.admin"
TODAY = date(2026, 9, 29)
# Kaydın değerleri: olay verisinde geçmez.
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "ornekova", NUMBER, "+90 555 000 00 01", "a@b.test")


def _key(
    *,
    number: str | None = NUMBER,
    given_names: str = "TEST",
    surname: str = "ORNEKOVA",
    born: date | None = BORN,
) -> PersonKey:
    return PersonKey(
        document_numbers=() if number is None else (DocumentNumberKey(number, legible=True),),
        normalized_name=normalize_name(given_names, surname),
        date_of_birth=born,
        original_script_name=None,
        normalized_original_name=None,
        mrz_allows_clean_document_number=True,
        conflicts=(),
        surname=surname,
        given_names=given_names,
        date_of_birth_legible=born is not None,
    )


def _employee(
    session: Session,
    employee_id: str = "E0001",
    *,
    born: date | None = BORN,
    aliases: tuple[str, ...] = ("ORNEKOVA TEST",),
    numbers: tuple[str, ...] = (),
    status: str = EmployeeStatus.ACTIVE.value,
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"Test_Ornekova_{employee_id}",
        given_names="Test",
        surname="Ornekova",
        date_of_birth=born,
        status=status,
    )
    session.add(employee)
    for raw in aliases:
        session.add(
            EmployeeAlias(employee=employee, raw_name=raw, normalized_name=normalize_name(raw))
        )
    for number in numbers:
        session.add(EmployeeIdentifier(employee=employee, kind=PASSPORT.slug, value=number))
    session.flush()
    return employee


def _alias(session: Session, employee_id: str, raw: str = "ORNEKOVA TEST") -> EmployeeAlias:
    return session.scalars(
        select(EmployeeAlias).where(
            EmployeeAlias.employee_id == employee_id, EmployeeAlias.raw_name == raw
        )
    ).one()


def _identifier(session: Session, employee_id: str, value: str = NUMBER) -> EmployeeIdentifier:
    return session.scalars(
        select(EmployeeIdentifier).where(
            EmployeeIdentifier.employee_id == employee_id, EmployeeIdentifier.value == value
        )
    ).one()


def _removed(record: EmployeeAlias | EmployeeIdentifier | EmployeeContact) -> None:
    record.removed_at = utcnow()
    record.removed_by = ACTOR


def _events(session: Session, *types: EventType) -> list[Event]:
    return list(
        session.scalars(
            select(Event).where(Event.type.in_([kind.value for kind in types])).order_by(Event.id)
        )
    )


def _assert_no_personal_values(text: str) -> None:
    for value in PERSONAL_VALUES:
        assert value not in text


# --- eşleştirme: yalnız etkin kayıtlar (K6, §20.2.2) --------------------------------------------


def test_a_removed_number_no_longer_matches_its_employee(
    session: Session, layout: DataLayout
) -> None:
    # Numara E0001'den kaldırıldı, isim de tutmuyor: satır 1 yerine satır 6 — yeni çalışan
    # numarayla açılır, eski satır kaldırılmış kalır.
    employee = _employee(session, aliases=("BASKA KISI",), numbers=(NUMBER,))
    _removed(_identifier(session, employee.id))
    session.flush()

    match = match_employee(session, _key())

    assert match == EmployeeMatch(MatchRule.NO_MATCH)
    created = create_employee(session, layout, _key(), entry=PASSPORT, today=TODAY)
    assert created.id == "E0002"
    assert [(each.employee_id, each.removed_at is None) for each in _numbers(session)] == [
        ("E0001", False),
        ("E0002", True),
    ]


def _numbers(session: Session) -> list[EmployeeIdentifier]:
    return list(session.scalars(select(EmployeeIdentifier).order_by(EmployeeIdentifier.id)))


def test_a_number_removed_from_one_owner_leaves_the_other_as_the_single_owner(
    session: Session,
) -> None:
    # §20.2.2 satır 2 kaldırılmış satırı saymaz: iki çalışanlı numara tek sahipli olur.
    _employee(session, "E0001", aliases=(), numbers=(NUMBER,))
    _employee(session, "E0002", aliases=(), numbers=(NUMBER,))
    assert match_employee(session, _key()).rule is MatchRule.DOCUMENT_NUMBER_AMBIGUOUS

    _removed(_identifier(session, "E0001"))
    session.flush()

    assert number_owners(session, [NUMBER, NUMBER]) == {"E0002"}
    assert number_owners(session, []) == set()
    assert match_employee(session, _key()) == EmployeeMatch(MatchRule.DOCUMENT_NUMBER, ("E0002",))


def test_s12_name_and_birth_date_do_not_see_a_removed_alias(session: Session) -> None:
    # S12: aynı isimli iki çalışan, doğum tarihi birine uyuyor → ona eşleşir. Uyan çalışanın isim
    # yazımı kaldırılınca isim yalnız ötekine uyar ve doğum tarihi tutmaz: Unresolved (satır 5).
    _employee(session, "E0001", born=BORN)
    _employee(session, "E0002", born=date(1985, 5, 5))
    key = _key(number=None)
    assert match_employee(session, key) == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))

    _removed(_alias(session, "E0001"))
    session.flush()

    assert match_employee(session, key) == EmployeeMatch(MatchRule.NAME_ONLY, ("E0002",))


def test_removing_one_alias_resolves_a_name_and_birth_date_tie(session: Session) -> None:
    _employee(session, "E0001")
    _employee(session, "E0002")
    key = _key(number=None)
    assert match_employee(session, key).rule is MatchRule.NAME_DOB_AMBIGUOUS

    _removed(_alias(session, "E0002"))
    session.flush()

    assert match_employee(session, key) == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))


# --- birikim: kaldırılmış kayıt geri açılmaz (05.7.2) --------------------------------------------


def test_a_removed_number_seen_again_is_neither_reopened_nor_added(session: Session) -> None:
    # Numara kaldırıldı; belge isim + doğum tarihiyle eşleşir (satır 3). Birikim numarayı yeniden
    # eklemez, kaldırılmış satır kaldırılmış kalır ve "belgede görüldü" işaretini alır.
    employee = _employee(session, numbers=(NUMBER,))
    number = _identifier(session, employee.id)
    _removed(number)
    session.flush()
    assert match_employee(session, _key()).rule is MatchRule.NAME_DOB

    added = accumulate_identity(session, _key(), entry=PASSPORT)

    assert added.identifiers == ()
    assert session.scalar(select(func.count()).select_from(EmployeeIdentifier)) == 1
    assert number.removed_at is not None and number.removed_by == ACTOR
    assert number.seen_after_removal_at is not None
    assert seen_after_removal_warning(RecordKind.IDENTIFIER, number) == (
        "Belgede görülen belge numarası kaldırılmış bir kayda uyuyor"
    )


def test_an_active_number_is_not_marked_as_seen_after_removal(session: Session) -> None:
    employee = _employee(session, numbers=(NUMBER,))

    accumulate_identity(session, _key(), entry=PASSPORT)

    number = _identifier(session, employee.id)
    assert number.seen_after_removal_at is None
    assert seen_after_removal_warning(RecordKind.IDENTIFIER, number) is None


def test_a_removed_spelling_seen_again_is_not_reopened_even_in_another_case(
    session: Session,
) -> None:
    # Çalışan numarayla eşleşir (satır 1). Belgenin yazımı kaldırılmış yazımla aynı: geri açılmaz.
    # Başka harf büyüklüğündeki yazım da (aynı normalize anahtar) eklenmez — yoksa kaldırılan isim
    # eşleştirmeye geri dönerdi.
    employee = _employee(session, aliases=("TEST ORNEKOVA",), numbers=(NUMBER,))
    removed = _alias(session, employee.id, "TEST ORNEKOVA")
    _removed(removed)
    session.flush()

    same = accumulate_identity(session, _key(), entry=PASSPORT)
    other_case = accumulate_identity(
        session, _key(given_names="Test", surname="Ornekova"), entry=PASSPORT
    )

    assert same.aliases == () and other_case.aliases == ()
    assert session.scalar(select(func.count()).select_from(EmployeeAlias)) == 1
    assert removed.removed_at is not None and removed.seen_after_removal_at is not None
    assert seen_after_removal_warning(RecordKind.ALIAS, removed) == (
        "Belgede görülen isim yazımı kaldırılmış bir kayda uyuyor"
    )
    assert match_employee(session, _key(number=None)).rule is MatchRule.NO_MATCH


def test_a_new_spelling_is_added_when_an_active_alias_carries_the_same_key(
    session: Session,
) -> None:
    # Aynı anahtar etkin bir yazımda da varsa kaldırılmış yazım eşleştirmeyi zaten belirlemiyor:
    # yeni ham yazım 05.7.2 gereği eklenir.
    employee = _employee(session, aliases=("TEST ORNEKOVA", "Ornekova Test"), numbers=(NUMBER,))
    _removed(_alias(session, employee.id, "TEST ORNEKOVA"))
    session.flush()

    added = accumulate_identity(
        session, _key(given_names="Test", surname="ORNEKOVA"), entry=PASSPORT
    )

    assert added.aliases == ("Test ORNEKOVA",)
    assert _alias(session, employee.id, "TEST ORNEKOVA").seen_after_removal_at is None


# --- iletişim bilgisi: kaldırılmış kayıt ve güncel işareti (05.8.2) ------------------------------


def _contact(
    session: Session,
    value: str,
    *,
    kind: str = ContactKind.PHONE.value,
    current: bool = True,
    employee_id: str = "E0001",
) -> EmployeeContact:
    contact = EmployeeContact(employee_id=employee_id, kind=kind, value=value, is_current=current)
    session.add(contact)
    session.flush()
    return contact


def test_a_removed_contact_seen_again_opens_no_row(session: Session) -> None:
    _employee(session)
    removed = _contact(session, "+90 555 000 00 01")
    _removed(removed)
    session.flush()

    sighting = record_contact_sighting(
        session, employee_id="E0001", kind=ContactKind.PHONE.value, value="+90 555 000 00 01"
    )

    assert sighting.changed is False
    assert sighting.contact is removed
    assert session.scalar(select(func.count()).select_from(EmployeeContact)) == 1
    assert removed.removed_at is not None and removed.seen_after_removal_at is not None
    assert seen_after_removal_warning(RecordKind.CONTACT, removed) == (
        "Belgede görülen telefon kaldırılmış bir kayda uyuyor"
    )


def test_a_new_value_after_a_removed_current_contact_becomes_the_only_current_one(
    session: Session,
) -> None:
    # Kaldırılan güncel kayıt güncel sayılmaz; yeni değer türün tek güncel satırı olur ve geri
    # alınan eski kayıt onu ezmez.
    _employee(session)
    removed = _contact(session, "+90 555 000 00 01")
    _removed(removed)
    session.flush()

    sighting = record_contact_sighting(
        session, employee_id="E0001", kind=ContactKind.PHONE.value, value="+90 555 000 00 02"
    )
    restore_record(
        session, session.get_one(Employee, "E0001"), RecordKind.CONTACT, removed, actor=ACTOR
    )

    assert sighting.changed is True
    assert (removed.is_current, sighting.contact.is_current) == (False, True)
    assert removed.removed_at is None


def test_a_restored_contact_is_current_again_when_nothing_newer_came(session: Session) -> None:
    employee = _employee(session)
    contact = _contact(session, "a@b.test", kind=ContactKind.EMAIL.value)
    remove_record(session, employee, RecordKind.CONTACT, contact, actor=ACTOR)

    restore_record(session, employee, RecordKind.CONTACT, contact, actor=ACTOR)

    assert (contact.is_current, contact.removed_at, contact.removed_by) == (True, None, None)


# --- İK işlemleri: kaldır, geri al, iletişim ekle ------------------------------------------------


@pytest.mark.parametrize("kind", list(RecordKind))
def test_remove_and_restore_mark_the_row_and_log_kind_and_id_without_the_value(
    session: Session, kind: RecordKind
) -> None:
    employee = _employee(session, numbers=(NUMBER,))
    record = {
        RecordKind.ALIAS: lambda: _alias(session, employee.id),
        RecordKind.IDENTIFIER: lambda: _identifier(session, employee.id),
        RecordKind.CONTACT: lambda: _contact(session, "+90 555 000 00 01"),
    }[kind]()
    record.seen_after_removal_at = utcnow()

    removed = remove_record(session, employee, kind, record, actor=ACTOR)

    assert record.removed_by == ACTOR and record.removed_at is not None
    assert record.seen_after_removal_at is None
    assert (removed.type, removed.actor, removed.employee_id, removed.data_json) == (
        EventType.PROFILE_RECORD_REMOVED.value,
        ACTOR,
        employee.id,
        {"kind": kind.value, "record_id": record.id},
    )
    assert find_record(session, employee.id, kind, record.id) is record
    with pytest.raises(ProfileRecordStateError):
        remove_record(session, employee, kind, record, actor=ACTOR)

    restored = restore_record(session, employee, kind, record, actor=ACTOR)

    assert (record.removed_at, record.removed_by) == (None, None)
    assert (restored.type, restored.data_json) == (
        EventType.PROFILE_RECORD_RESTORED.value,
        {"kind": kind.value, "record_id": record.id},
    )
    with pytest.raises(ProfileRecordStateError):
        restore_record(session, employee, kind, record, actor=ACTOR)
    for event in _events(
        session, EventType.PROFILE_RECORD_REMOVED, EventType.PROFILE_RECORD_RESTORED
    ):
        _assert_no_personal_values(repr(event.data_json) + (event.message or ""))


def test_record_operations_need_an_actor_and_refuse_a_merged_employee(session: Session) -> None:
    employee = _employee(session, numbers=(NUMBER,))
    number = _identifier(session, employee.id)
    with pytest.raises(ValueError, match="actor"):
        remove_record(session, employee, RecordKind.IDENTIFIER, number, actor=" ")

    employee.status = EmployeeStatus.MERGED.value
    with pytest.raises(ProfileRecordStateError, match="birleştirilmiş"):
        remove_record(session, employee, RecordKind.IDENTIFIER, number, actor=ACTOR)
    with pytest.raises(ProfileRecordStateError):
        add_contact(session, employee, "phone", "+90 555 000 00 01", actor=ACTOR)
    assert number.removed_at is None
    assert _events(session, EventType.PROFILE_RECORD_REMOVED, EventType.CONTACT_ADDED) == []


def test_find_record_only_finds_the_employee_s_own_record(session: Session) -> None:
    _employee(session, "E0001", numbers=(NUMBER,))
    _employee(session, "E0002", aliases=(), numbers=(OTHER_NUMBER,))
    foreign = _identifier(session, "E0002", OTHER_NUMBER)

    assert find_record(session, "E0001", RecordKind.IDENTIFIER, foreign.id) is None
    assert find_record(session, "E0001", RecordKind.IDENTIFIER, 999) is None
    assert record_kind("identifier") is RecordKind.IDENTIFIER
    assert record_kind("employee") is None


def test_a_manual_contact_becomes_current_and_the_older_ones_history(session: Session) -> None:
    employee = _employee(session)
    older = _contact(session, "+90 555 000 00 01")
    removed_current = _contact(session, "+90 555 000 00 03")
    _removed(removed_current)
    email = _contact(session, "a@b.test", kind=ContactKind.EMAIL.value)

    added = add_contact(session, employee, "phone", "  +90 (555) 000-00.02 ", actor=ACTOR)

    assert (added.value, added.kind, added.is_current) == ("+90 (555) 000-00.02", "phone", True)
    assert (added.added_by, added.source_document_id) == (ACTOR, None)
    assert (older.is_current, removed_current.is_current, email.is_current) == (False, False, True)
    (event,) = _events(session, EventType.CONTACT_ADDED)
    assert (event.actor, event.employee_id, event.data_json) == (
        ACTOR,
        employee.id,
        {"kind": "phone", "record_id": added.id},
    )
    _assert_no_personal_values(repr(event.data_json))


@pytest.mark.parametrize(
    ("kind", "value", "field", "message"),
    [
        ("fax", "+90 555 000 00 01", "kind", "Tür telefon, e-posta ya da adres olmalı."),
        ("phone", "   ", "value", "Değer boş olamaz."),
        ("phone", None, "value", "Değer boş olamaz."),
        (
            "address",
            "x" * (CONTACT_VALUE_MAX_LENGTH + 1),
            "value",
            f"Değer en çok {CONTACT_VALUE_MAX_LENGTH} karakter olabilir.",
        ),
        (
            "email",
            "ad-soyad.example.test",
            "value",
            "E-posta adresi ad@alan.uzantı biçiminde olmalı.",
        ),
        ("email", "ad@alan", "value", "E-posta adresi ad@alan.uzantı biçiminde olmalı."),
        ("phone", "abc 123", "value", "Telefon rakam"),
        ("phone", "1234", "value", "5–20 rakam"),
    ],
)
def test_a_manual_contact_is_checked_lightly_and_nothing_is_written_when_refused(
    session: Session, kind: str, value: str | None, field: str, message: str
) -> None:
    employee = _employee(session)

    with pytest.raises(ContactFormError) as refused:
        add_contact(session, employee, kind, value, actor=ACTOR)

    assert message in refused.value.problems[field][0]
    assert session.scalar(select(func.count()).select_from(EmployeeContact)) == 0
    assert _events(session, EventType.CONTACT_ADDED) == []


def test_a_long_address_up_to_the_limit_is_accepted(session: Session) -> None:
    employee = _employee(session)

    added = add_contact(session, employee, "address", "y" * CONTACT_VALUE_MAX_LENGTH, actor=ACTOR)

    assert len(added.value) == CONTACT_VALUE_MAX_LENGTH


def test_a_manual_contact_equal_to_the_current_or_a_removed_value_is_refused(
    session: Session,
) -> None:
    employee = _employee(session)
    _contact(session, "+90 555 000 00 01")
    removed = _contact(session, "+90 555 000 00 09", current=False)
    _removed(removed)
    session.flush()

    with pytest.raises(ContactFormError, match="zaten güncel"):
        add_contact(session, employee, "phone", "+90 555 000 00 01", actor=ACTOR)
    with pytest.raises(ContactFormError, match="Geri al"):
        add_contact(session, employee, "phone", "+90 555 000 00 09", actor=ACTOR)
    assert session.scalar(select(func.count()).select_from(EmployeeContact)) == 2


# --- okuma yardımcıları, bağlam denetimi, profil.md ----------------------------------------------


def test_employee_records_lists_everything_and_the_latest_removal_first(session: Session) -> None:
    employee = _employee(session, aliases=("ORNEKOVA TEST", "TEST ORNEKOVA"), numbers=(NUMBER,))
    first = _alias(session, employee.id)
    second = _identifier(session, employee.id)
    contact = _contact(session, "a@b.test", kind=ContactKind.EMAIL.value)
    now = utcnow()
    first.removed_at, second.removed_at = now - timedelta(minutes=5), now

    records = employee_records(session, employee.id)

    assert [alias.raw_name for alias in records.aliases] == ["ORNEKOVA TEST", "TEST ORNEKOVA"]
    assert records.identifiers == [second] and records.contacts == [contact]
    assert records.removed == [(RecordKind.IDENTIFIER, second), (RecordKind.ALIAS, first)]
    assert record_label(RecordKind.CONTACT, contact) == "e-posta"
    assert record_label(RecordKind.ALIAS, first) == "isim yazımı"


def test_the_upload_context_check_ignores_removed_records(session: Session) -> None:
    # 10.5.5: bağlam çalışanının kaldırılmış numarası "aynı kişi" demez; başka çalışanın kaldırılmış
    # numarası "başka kişi" demez.
    _employee(session, "E0001", aliases=("ORNEKOVA TEST", "Takma Ad"), numbers=(NUMBER,))
    _employee(session, "E0002", aliases=(), numbers=(OTHER_NUMBER,))
    _removed(_identifier(session, "E0001"))
    _removed(_identifier(session, "E0002", OTHER_NUMBER))
    session.flush()

    profile = context_profile(session, "E0001")
    same_name = context_person_verdict(session, _key(), entry=PASSPORT, employee_id="E0001")
    other_number = context_person_verdict(
        session, _key(number=OTHER_NUMBER), entry=PASSPORT, employee_id="E0001"
    )

    assert profile.identifiers == frozenset()
    assert same_name.basis is ContextPersonBasis.NAME
    assert other_number.result is ContextPersonResult.SAME
    assert other_number.basis is ContextPersonBasis.NAME

    assert normalize_name("Takma Ad") in profile.spellings
    _removed(_alias(session, "E0001", "Takma Ad"))
    session.flush()
    assert normalize_name("Takma Ad") not in context_profile(session, "E0001").spellings


def test_profil_md_leaves_out_removed_numbers_and_contacts(session: Session) -> None:
    employee = _employee(session, numbers=(NUMBER, OTHER_NUMBER))
    _removed(_identifier(session, employee.id))
    _removed(_contact(session, "+90 555 000 00 01"))
    _contact(session, "a@b.test", kind=ContactKind.EMAIL.value)
    session.flush()

    text = render_profile(session, employee, today=TODAY)

    assert OTHER_NUMBER in text and NUMBER not in text
    assert "a@b.test" in text and "+90 555 000 00 01" not in text
