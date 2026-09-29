"""05.7.3 — eşleşen ya da yeni açılan çalışanın boş profil alanları belgede okunaklı okunan
değerlerle dolar, MRZ önce gelir; dolu alan değişmez, farklı değer uyarı olarak kaydedilir; her
alanın kaynağı belgeye bağlanır (PLAN.md §C82).

Birim testleri `complete_profile_fields`'ı elle kurulan ya da sentetik sayfa analizlerinden
(`build_person_key`) üretilen anahtarla geçici SQLite'taki sentetik çalışana karşı sınar. Gerçek
kişi/belge yok; ağ çağrısı yok.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import PageAnalysis
from app.db.models import (
    Employee,
    EmployeeFieldObservation,
    Event,
    ProfileField,
    Upload,
    UploadFile,
)
from app.events import EventType, event_context
from app.matching.fields import FieldCompletion, complete_profile_fields, document_field_values
from app.matching.match import DocumentNumberKey, PersonKey, build_person_key
from app.matching.mrz import MrzFormat
from app.matching.names import normalize_name, transliterate_name
from tests.ai.payloads import analysis_payload
from tests.matching.test_mrz import PASSPORT, make_mrz

TODAY = date(2026, 9, 15)
BORN = date(1990, 1, 1)
CYRILLIC = "Орнекова Тест"
UPLOAD_ID = "u_20260915_0001"
# Anahtarın kişisel değerleri: olay verisinde ve gözlem satırında geçmez.
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "TEST", "Орнекова", "1990-01-01", "RUS", "IVANOVNA")


def _key(
    *,
    given_names: str | None = "TEST",
    surname: str | None = "ORNEKOVA",
    other_names: str | None = "IVANOVNA",
    original: str | None = CYRILLIC,
    born: date | None = BORN,
    nationality: str | None = "RUS",
) -> PersonKey:
    named = given_names is not None and surname is not None
    return PersonKey(
        document_numbers=(DocumentNumberKey("000000001", legible=True),),
        normalized_name=normalize_name(given_names, surname) if named else None,
        date_of_birth=born,
        original_script_name=None if original is None else transliterate_name(original),
        normalized_original_name=None if original is None else normalize_name(original),
        mrz_allows_clean_document_number=True,
        conflicts=(),
        surname=surname,
        given_names=given_names,
        other_names=other_names,
        nationality=nationality,
    )


def _employee(session: Session, employee_id: str = "E0001", **fields: Any) -> Employee:
    values: dict[str, Any] = {"given_names": "Test", "surname": "Ornekova"} | fields
    employee = Employee(id=employee_id, folder_name=f"Test_Ornekova_{employee_id}", **values)
    session.add(employee)
    session.flush()
    return employee


def _source(session: Session, name: str = "pasaport.pdf") -> int:
    upload = session.get(Upload, UPLOAD_ID) or Upload(id=UPLOAD_ID, channel="web")
    upload_file = UploadFile(
        upload=upload,
        original_name=name,
        stored_path=f"Inbox/{UPLOAD_ID}/{name}",
        sha256="0" * 64,
        mime="application/pdf",
    )
    session.add(upload_file)
    session.flush()
    return upload_file.id


def _complete(
    session: Session, key: PersonKey, file_id: int, *, page_index: int = 0, **options: Any
) -> FieldCompletion:
    return complete_profile_fields(
        session, key, employee_id="E0001", file_id=file_id, page_index=page_index, **options
    )


def _observations(session: Session) -> list[tuple[str, str, int, int]]:
    rows = session.scalars(select(EmployeeFieldObservation).order_by(EmployeeFieldObservation.id))
    return [(row.field, row.outcome, row.file_id, row.page_index) for row in rows]


def _filled_events(session: Session) -> list[Event]:
    return list(
        session.scalars(
            select(Event)
            .where(Event.type == EventType.EMPLOYEE_FIELD_FILLED.value)
            .order_by(Event.id)
        )
    )


def _page(
    *, fields: dict[str, Any] | None = None, mrz: bool = False, **person: Any
) -> PageAnalysis:
    payload = analysis_payload()
    if fields is not None:
        payload["fields"] = fields
    payload["person"].update(person)
    if mrz:
        payload["person"]["mrz_lines"] = make_mrz(MrzFormat.TD3, **PASSPORT)
    return PageAnalysis.model_validate(payload)


# --- değer: anahtarın çalışan kaydına yazdığı alanlar -------------------------------------------


def test_document_values_are_the_latin_employee_fields_of_the_key() -> None:
    values = document_field_values(_key())

    assert values == {
        ProfileField.GIVEN_NAMES: "TEST",
        ProfileField.SURNAME: "ORNEKOVA",
        ProfileField.OTHER_NAMES: "IVANOVNA",
        ProfileField.ORIGINAL_SCRIPT_NAME: CYRILLIC,
        ProfileField.DATE_OF_BIRTH: BORN,
        ProfileField.NATIONALITY: "RUS",
    }
    assert document_field_values(_key(other_names=None, born=None, nationality=None)) == {
        ProfileField.GIVEN_NAMES: "TEST",
        ProfileField.SURNAME: "ORNEKOVA",
        ProfileField.ORIGINAL_SCRIPT_NAME: CYRILLIC,
    }


# --- kural: boş alan dolar, dolu alan değişmez ---------------------------------------------------


def test_empty_fields_are_filled_from_the_document_and_the_source_is_recorded(
    session: Session,
) -> None:
    employee = _employee(session)
    file_id = _source(session)

    with event_context(upload_id=UPLOAD_ID):
        result = _complete(session, _key(), file_id, page_index=2, actor="ik.admin")

    filled = ("other_names", "original_script_name", "date_of_birth", "nationality")
    assert result == FieldCompletion("E0001", filled=filled, same=("given_names", "surname"))
    assert (employee.other_names, employee.original_script_name) == ("IVANOVNA", CYRILLIC)
    assert (employee.date_of_birth, employee.nationality) == (BORN, "RUS")
    assert _observations(session) == [
        ("given_names", "same", file_id, 2),
        ("surname", "same", file_id, 2),
        *[(name, "filled", file_id, 2) for name in filled],
    ]
    events = _filled_events(session)
    assert [
        (e.upload_id, e.file_id, e.page_index, e.document_id, e.employee_id, e.actor, e.data_json)
        for e in events
    ] == [
        (
            UPLOAD_ID,
            file_id,
            2,
            None,
            "E0001",
            "ik.admin",
            {"field": name, "source": "document", "rule": "05.7.3"},
        )
        for name in filled
    ]


def test_a_filled_field_never_changes_and_a_different_value_is_a_conflict(
    session: Session,
) -> None:
    employee = _employee(
        session,
        given_names="Marta",
        other_names="Petrovna",
        original_script_name="Марта Орнекова",
        date_of_birth=date(1991, 2, 2),
        nationality="SRB",
    )
    file_id = _source(session)

    result = _complete(session, _key(), file_id)

    assert result == FieldCompletion(
        "E0001",
        same=("surname",),
        conflicts=(
            "given_names",
            "other_names",
            "original_script_name",
            "date_of_birth",
            "nationality",
        ),
    )
    assert (employee.given_names, employee.surname, employee.other_names) == (
        "Marta",
        "Ornekova",
        "Petrovna",
    )
    assert (employee.original_script_name, employee.date_of_birth, employee.nationality) == (
        "Марта Орнекова",
        date(1991, 2, 2),
        "SRB",
    )
    assert _filled_events(session) == []


@pytest.mark.parametrize(
    ("stored", "read"),
    [
        # aksan ve büyük/küçük harf
        ({"surname": "Örnekova"}, {"surname": "ORNEKOVA"}),
        # harf çevirisi: eski kayıttaki Kiril yazım ile belgenin Latin yazımı
        ({"surname": "ОРНЕКОВА"}, {"surname": "ORNEKOVA"}),
        # kelime sırası ve noktalama
        ({"other_names": "Ivanovna-Maria"}, {"other_names": "MARIA IVANOVNA"}),
        ({"original_script_name": "Тест Орнекова"}, {"original": "ОРНЕКОВА ТЕСТ"}),
        ({"nationality": "rus"}, {"nationality": "RUS"}),
    ],
    ids=["accent-case", "transliteration", "order-punctuation", "original-order", "code-case"],
)
def test_spelling_differences_that_normalize_alike_are_not_conflicts(
    session: Session, stored: dict[str, Any], read: dict[str, Any]
) -> None:
    employee = _employee(session, **stored)
    field = next(iter(stored))
    before = getattr(employee, field)

    result = _complete(session, _key(**read), _source(session))

    assert field in result.same
    assert result.conflicts == ()
    assert getattr(employee, field) == before


def test_a_stored_name_without_letters_is_not_the_same_as_a_read_name(session: Session) -> None:
    # Harfsiz kayıt anahtara inmez: boş sayılmaz (değişmez), belgedeki adla aynı da sayılmaz.
    employee = _employee(session, other_names="—")

    result = _complete(session, _key(), _source(session))

    assert "other_names" in result.conflicts
    assert employee.other_names == "—"


def test_blank_text_counts_as_an_empty_field(session: Session) -> None:
    employee = _employee(session, other_names="  ")

    result = _complete(session, _key(), _source(session))

    assert "other_names" in result.filled
    assert employee.other_names == "IVANOVNA"


def test_fields_without_a_document_value_are_neither_written_nor_observed(
    session: Session,
) -> None:
    # 05.2.2: Latin yazımı olmayan ad-soyad Latin alana yazılmaz; okunmayan alan gözlenmez.
    employee = _employee(session)
    key = _key(
        given_names="ТЕСТ",
        surname="ОРНЕКОВА",
        other_names=None,
        original=None,
        born=None,
        nationality=None,
    )
    assert key.latin_given_names is None and key.latin_surname is None

    result = _complete(session, key, _source(session))

    assert result == FieldCompletion("E0001", filled=("original_script_name",))
    assert (employee.given_names, employee.surname) == ("Test", "Ornekova")
    assert employee.original_script_name == "ТЕСТ ОРНЕКОВА"
    assert (employee.date_of_birth, employee.nationality) == (None, None)
    assert [field for field, *_ in _observations(session)] == ["original_script_name"]


# --- okunaklılık ve MRZ önceliği (anahtarın kuralları) -------------------------------------------


def test_an_illegible_value_is_not_written(session: Session) -> None:
    # K1: sayfa doğum tarihini okunamadı diyor; `person`'daki değer de alana girmez.
    employee = _employee(session)
    fields = {
        "surname": {"value": "ORNEKOVA", "legible": True},
        "date_of_birth": {"value": None, "legible": False},
        "expiry_date": {"value": None, "legible": False},
    }
    key = build_person_key([_page(fields=fields, date_of_birth="1990-01-01")], today=TODAY)

    result = _complete(session, key, _source(session))

    assert "date_of_birth" not in (*result.filled, *result.same, *result.conflicts)
    assert employee.date_of_birth is None
    assert "date_of_birth" not in [field for field, *_ in _observations(session)]


def test_the_mrz_value_comes_before_the_visible_text(session: Session) -> None:
    # K6, 05.3.3: görünen doğum tarihi MRZ'yle çelişiyor; alan MRZ'nin değeriyle dolar.
    employee = _employee(session)
    visible = {
        "surname": {"value": "ORNEKOVA", "legible": True},
        "date_of_birth": {"value": "1991-02-02", "legible": True},
    }
    page = _page(fields=visible, mrz=True, date_of_birth="1991-02-02")

    result = _complete(session, build_person_key([page], today=TODAY), _source(session))

    assert "date_of_birth" in result.filled
    assert employee.date_of_birth == BORN


# --- kaynak: bir alan bir kaynaktan bir kez ------------------------------------------------------


def test_the_same_source_is_observed_once_and_another_source_adds_its_own_rows(
    session: Session,
) -> None:
    employee = _employee(session)
    first, second = _source(session), _source(session, "kart.pdf")
    _complete(session, _key(), first)
    rows = _observations(session)
    events = len(_filled_events(session))

    again = _complete(session, _key(born=date(1991, 2, 2)), first)

    assert again == FieldCompletion("E0001")
    assert _observations(session) == rows
    assert len(_filled_events(session)) == events
    assert employee.date_of_birth == BORN

    other = _complete(session, _key(born=date(1991, 2, 2)), second)

    assert other.conflicts == ("date_of_birth",)
    assert other.filled == ()
    assert employee.date_of_birth == BORN
    assert _observations(session)[len(rows) :] == [
        ("given_names", "same", second, 0),
        ("surname", "same", second, 0),
        ("other_names", "same", second, 0),
        ("original_script_name", "same", second, 0),
        ("date_of_birth", "conflict", second, 0),
        ("nationality", "same", second, 0),
    ]


def test_a_new_employee_records_its_document_fields_as_filled(session: Session) -> None:
    # Satır 6: `create_employee` alanları bu anahtardan yazdı; kaynak bu belgedir.
    _employee(
        session,
        given_names="TEST",
        surname="ORNEKOVA",
        other_names="IVANOVNA",
        original_script_name=CYRILLIC,
        date_of_birth=BORN,
        nationality="RUS",
    )

    result = _complete(session, _key(), _source(session), created=True)

    assert result.filled == tuple(field.value for field in ProfileField)
    assert result.same == result.conflicts == ()
    assert len(_filled_events(session)) == len(ProfileField)


def test_neither_the_events_nor_the_observations_carry_values(session: Session) -> None:
    _employee(session, given_names="Marta")

    _complete(session, _key(), _source(session))

    # 10.5.6 kaynak türünü ve düzenleyen kullanıcıyı ekledi; değer sütunu yine yok.
    assert set(EmployeeFieldObservation.__table__.columns.keys()) == {
        "id",
        "employee_id",
        "field",
        "outcome",
        "file_id",
        "page_index",
        "observed_at",
        "source",
        "actor",
    }
    rows = session.scalars(select(EmployeeFieldObservation)).all()
    assert rows and {(row.source, row.actor) for row in rows} == {("document", None)}
    logged = json.dumps(
        [[event.message, event.data_json] for event in _filled_events(session)],
        ensure_ascii=False,
    )
    for value in PERSONAL_VALUES:
        assert value not in logged
