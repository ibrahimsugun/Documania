"""10.5.5 — profilden yüklemede kişi denetimi: belgenin kişisi bağlam çalışanıyla temiz belge
numarası → doğum tarihi → ad sırasıyla karşılaştırılır, ilk kesin sonuç kazanır (PLAN.md §C83).

Saf karşılaştırma (`compare_context_person`) elle kurulan çalışan kayıtlarıyla, kişi anahtarı
sentetik sayfa analizlerinden (`build_person_key`) sınanır; veritabanı okuması
(`context_person_verdict`) geçici SQLite'taki sentetik çalışanlarla. Gerçek kişi/belge yok; ağ
çağrısı yok.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import PageAnalysis
from app.catalog import load_seed_catalog
from app.db.models import Employee, EmployeeAlias, EmployeeIdentifier, Event
from app.matching.context import (
    UNKNOWN,
    ContextPersonBasis,
    ContextPersonResult,
    ContextPersonVerdict,
    ContextProfile,
    compare_context_person,
    context_person_verdict,
    context_profile,
)
from app.matching.match import PersonKey, build_person_key, normalize_document_number
from app.matching.names import normalize_name
from tests.ai.payloads import analysis_payload

TODAY = date(2026, 9, 15)
BORN = date(1990, 1, 1)
NUMBER = "000000001"
CATALOG = load_seed_catalog()
PASSPORT = CATALOG.get("russian_passport")
PHOTO = CATALOG.get("profile_picture")  # zorunlu alanı yok: numarası temiz olmaz (§20.2.3)

SAME_BY_NUMBER = ContextPersonVerdict(ContextPersonResult.SAME, ContextPersonBasis.DOCUMENT_NUMBER)
SAME_BY_NAME = ContextPersonVerdict(ContextPersonResult.SAME, ContextPersonBasis.NAME)
DIFFERENT_BY_NUMBER = ContextPersonVerdict(
    ContextPersonResult.DIFFERENT, ContextPersonBasis.DOCUMENT_NUMBER
)
DIFFERENT_BY_BIRTH = ContextPersonVerdict(
    ContextPersonResult.DIFFERENT, ContextPersonBasis.DATE_OF_BIRTH
)
DIFFERENT_BY_NAME = ContextPersonVerdict(ContextPersonResult.DIFFERENT, ContextPersonBasis.NAME)


def _key(
    *,
    surname: str | None = "ORNEKOVA",
    given_names: str | None = "TEST",
    original: str | None = None,
    born: str | None = "1990-01-01",
    number: str | None = None,
    language: str = "ru",
) -> PersonKey:
    """Tek sayfanın okumalarından kişi anahtarı; okunan her alan okunaklıdır."""
    person: dict[str, Any] = {
        "surname": surname,
        "given_names": given_names,
        "other_names": None,
        "original_script_name": original,
        "date_of_birth": born,
        "nationality": None,
        "document_number": number,
        "mrz_lines": None,
        "contact": {"phone": None, "email": None, "address": None},
    }
    fields = {} if number is None else {"document_number": {"value": number, "legible": True}}
    page = PageAnalysis.model_validate(
        analysis_payload(language=language, person=person, fields=fields)
    )
    return build_person_key([page], today=TODAY)


def _profile(
    *spellings: str,
    surname: str = "Ornekova",
    born: date | None = BORN,
    identifiers: tuple[str, ...] = (),
) -> ContextProfile:
    """Bağlam çalışanı E0001; `spellings` alias'larının ham yazımlarıdır."""
    return ContextProfile(
        employee_id="E0001",
        identifiers=frozenset(identifiers),
        date_of_birth=born,
        spellings=tuple(normalize_name(spelling) for spelling in spellings),
        surname=normalize_name(surname),
    )


ORNEKOVA = _profile("Test Ornekova")


# --- 1. belge numarası ----------------------------------------------------------------------------


def test_clean_number_of_the_context_employee_is_the_same_person_whatever_else_is_read() -> None:
    # Numara ilk adımdır: ad ve doğum tarihi uymasa da kişi aynıdır.
    key = _key(surname="SIDOROV", given_names="IVAN", born="1985-05-05", number=NUMBER)

    verdict = compare_context_person(
        key, _profile("Test Ornekova", identifiers=(NUMBER,)), clean_number=NUMBER
    )

    assert verdict == SAME_BY_NUMBER


def test_clean_number_of_another_employee_is_a_different_person_even_with_the_same_name() -> None:
    verdict = compare_context_person(
        _key(number=NUMBER), ORNEKOVA, clean_number=NUMBER, number_owners=("E0002",)
    )

    assert verdict == DIFFERENT_BY_NUMBER


def test_number_owned_by_the_context_employee_and_another_is_the_same_person() -> None:
    # Numara bağlam çalışanında da var: ilk kural `same`; iki sahipliği eşleştirme çözer (satır 2).
    verdict = compare_context_person(
        _key(number=NUMBER), ORNEKOVA, clean_number=NUMBER, number_owners=("E0002", "E0001")
    )

    assert verdict == SAME_BY_NUMBER


@pytest.mark.parametrize("clean_number", [None, NUMBER], ids=["temiz-degil", "kimsede-yok"])
def test_number_that_is_not_clean_or_belongs_to_nobody_leaves_the_decision_to_the_next_steps(
    clean_number: str | None,
) -> None:
    # Temiz olmayan numara başka çalışanda olsa da hüküm vermez: doğum tarihi ve ad karar verir.
    key = _key(surname="SIDOROV", given_names="IVAN", born=None, number=NUMBER)
    owners = ("E0002",) if clean_number is None else ()

    verdict = compare_context_person(key, ORNEKOVA, clean_number=clean_number, number_owners=owners)

    assert verdict == DIFFERENT_BY_NAME


# --- 2. doğum tarihi ------------------------------------------------------------------------------


def test_different_birth_date_is_a_different_person_even_with_the_same_name() -> None:
    verdict = compare_context_person(_key(born="1991-01-01"), ORNEKOVA, clean_number=None)

    assert verdict == DIFFERENT_BY_BIRTH


@pytest.mark.parametrize(
    ("document_born", "employee_born"),
    [(None, BORN), ("1991-01-01", None), (None, None)],
    ids=["belgede-yok", "calisanda-yok", "ikisinde-yok"],
)
def test_birth_date_missing_on_either_side_leaves_the_decision_to_the_name(
    document_born: str | None, employee_born: date | None
) -> None:
    profile = _profile("Test Ornekova", born=employee_born)

    verdict = compare_context_person(_key(born=document_born), profile, clean_number=None)

    assert verdict == SAME_BY_NAME


# --- 3. ad ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("document", "aliases"),
    [
        # Kiril okuma (Latin alanlar boş, yalnız orijinal yazım) ↔ Latin alias.
        ({"surname": None, "given_names": None, "original": "Орнекова Тест"}, ("Test Ornekova",)),
        # Latin okuma ↔ yalnız Kiril alias (orijinal yazım).
        ({}, ("Орнекова Тест",)),
        # Aksan ve büyük/küçük harf.
        ({"surname": "MARKOVIĆ", "given_names": "JELENA"}, ("jelena markovic",)),
        # Kelime sırası.
        ({"surname": "TEST", "given_names": "ORNEKOVA"}, ("Test Ornekova",)),
        # Belgede ikinci ad yazılmamış.
        ({}, ("Test Anna Ornekova",)),
        # Kayıtta ikinci ad yazılmamış.
        ({"given_names": "TEST ANNA"}, ("Test Ornekova",)),
        # Noktalama: tireli soyad.
        ({"surname": "ORNEKOVA-PETROVA"}, ("Test Ornekova Petrova",)),
    ],
    ids=["kiril-latin", "latin-kiril", "aksan", "sira", "belgede-ikinci-ad-yok",
         "kayitta-ikinci-ad-yok", "noktalama"],
)  # fmt: skip
def test_the_same_name_written_differently_is_the_same_person(
    document: dict[str, Any], aliases: tuple[str, ...]
) -> None:
    surname = "Markovic" if "MARKOVIĆ" in document.values() else "Ornekova"
    profile = _profile(*aliases, surname=surname)

    verdict = compare_context_person(_key(**document), profile, clean_number=None)

    assert verdict == SAME_BY_NAME


def test_every_spelling_of_the_employee_is_compared() -> None:
    # İkinci alias uyar: çalışanın bütün yazımlarıyla karşılaştırılır.
    profile = _profile("Ana Prueba", "Test Ornekova")

    assert compare_context_person(_key(), profile, clean_number=None) == SAME_BY_NAME


@pytest.mark.parametrize(
    "document",
    [
        {"surname": "SIDOROVA"},
        {"surname": "SIDOROV", "given_names": "IVAN"},
        # Ad tutuyor ama soyad farklı: kelime kümeleri birbirini kapsamıyor.
        {"surname": "ORNEKOVAS"},
    ],
    ids=["farkli-soyad", "baska-kisi", "benzer-soyad"],
)
def test_a_different_surname_is_a_different_person(document: dict[str, Any]) -> None:
    assert compare_context_person(_key(**document), ORNEKOVA, clean_number=None) == (
        DIFFERENT_BY_NAME
    )


def test_covering_word_set_without_a_common_surname_word_is_a_different_person() -> None:
    # Belgenin kelime kümesi kaydınkini kapsıyor ama belgenin soyadı kayıtta geçmiyor: çalışanın
    # adı ve soyadı belgede ad olarak yazılmış başka biri.
    key = _key(surname="PETROVA", given_names="TEST ORNEKOVA")

    assert compare_context_person(key, ORNEKOVA, clean_number=None) == DIFFERENT_BY_NAME


def test_without_a_surname_on_the_document_the_surname_of_the_employee_is_used() -> None:
    # Yalnız orijinal yazım okundu: soyad kelimesi çalışanın soyadıdır.
    key = _key(surname=None, given_names=None, original="Тест")

    # Kayıttaki soyad belgede yok: yalnız ad tutuyor.
    assert compare_context_person(key, ORNEKOVA, clean_number=None) == DIFFERENT_BY_NAME
    assert (
        compare_context_person(
            _key(surname=None, given_names=None, original="Орнекова"), ORNEKOVA, clean_number=None
        )
        == SAME_BY_NAME
    )


# --- 4. hüküm yok ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("document", "clean_number"),
    [
        ({"surname": None, "given_names": None, "born": None}, None),
        # Yalnız soyad okundu: ad-soyad yazımı yok.
        ({"given_names": None, "born": None}, None),
        # Numara kimsede yok, ad okunmadı.
        ({"surname": None, "given_names": None, "number": NUMBER}, NUMBER),
    ],
    ids=["hicbir-sey", "yalniz-soyad", "numara-kimsede-yok"],
)
def test_without_a_clean_number_or_a_name_the_person_is_unknown(
    document: dict[str, Any], clean_number: str | None
) -> None:
    assert compare_context_person(_key(**document), ORNEKOVA, clean_number=clean_number) == UNKNOWN


# --- veritabanı -----------------------------------------------------------------------------------


def _employee(
    session: Session,
    employee_id: str,
    given_names: str,
    surname: str,
    *,
    born: date | None = BORN,
    original: str | None = None,
    aliases: tuple[str, ...] = (),
    numbers: tuple[str, ...] = (),
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"{given_names}_{surname}_{employee_id}",
        given_names=given_names,
        surname=surname,
        original_script_name=original,
        date_of_birth=born,
    )
    session.add(employee)
    for raw in aliases:
        session.add(
            EmployeeAlias(employee=employee, raw_name=raw, normalized_name=normalize_name(raw))
        )
    for number in numbers:
        session.add(
            EmployeeIdentifier(
                employee=employee, kind="russian_passport", value=normalize_document_number(number)
            )
        )
    session.flush()
    return employee


def test_the_profile_carries_every_recorded_spelling_once(session: Session) -> None:
    _employee(
        session,
        "E0001",
        "Test",
        "Ornekova",
        original="Орнекова Тест",
        aliases=("TEST ORNEKOVA", "Test Anna Ornekova"),
        numbers=("00 0000001",),
    )

    profile = context_profile(session, "E0001")

    assert profile == ContextProfile(
        employee_id="E0001",
        identifiers=frozenset({NUMBER}),
        date_of_birth=BORN,
        # Alias'lar kayıt sırasıyla, sonra kayıttaki ad-soyad ve orijinal yazım; aynı anahtar bir
        # kez.
        spellings=("ornekova test", "anna ornekova test"),
        surname="ornekova",
    )


def test_a_missing_context_employee_is_refused(session: Session) -> None:
    with pytest.raises(LookupError, match="E0009"):
        context_profile(session, "E0009")


def test_the_clean_number_is_looked_up_among_every_employee(session: Session) -> None:
    _employee(session, "E0001", "Test", "Ornekova", aliases=("Test Ornekova",))
    _employee(session, "E0002", "Ivan", "Sidorov", numbers=("00 0000001",))
    key = _key(number="00 0000001")

    verdict = context_person_verdict(session, key, entry=PASSPORT, employee_id="E0001")

    assert verdict == DIFFERENT_BY_NUMBER
    # Zorunlu alanında belge numarası olmayan türde numara temiz değildir (§20.2.3 koşul 1): ad
    # karar verir.
    assert context_person_verdict(session, key, entry=PHOTO, employee_id="E0001") == SAME_BY_NAME


def test_the_number_of_the_context_employee_is_found_in_the_database(session: Session) -> None:
    _employee(session, "E0001", "Test", "Ornekova", numbers=("00 0000001",))
    key = _key(surname="SIDOROV", given_names="IVAN", number="00-0000001")

    verdict = context_person_verdict(session, key, entry=PASSPORT, employee_id="E0001")

    assert verdict == SAME_BY_NUMBER


def test_the_comparison_writes_nothing(session: Session) -> None:
    _employee(session, "E0001", "Test", "Ornekova", aliases=("Test Ornekova",))
    session.commit()

    context_person_verdict(session, _key(surname="SIDOROV"), entry=PASSPORT, employee_id="E0001")

    assert not session.new and not session.dirty and not session.deleted
    assert session.scalar(select(func.count()).select_from(Event)) == 0
