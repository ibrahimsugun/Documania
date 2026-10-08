"""10.7.3 — önerilen profil düzenlenip onaylanır (§20.2.2 satır 7; K7, K8, K16, K17).

Birim testleri `approve_pending_profile`'ı ve `review_pending_profile`'ı İK'nın düzelttiği alanlarla
(`ProfileFields`) elle kurulan `PersonKey` ve geçici SQLite'taki sentetik çalışanlarla sınar —
gerçek kişi/belge yok, ağ çağrısı yok. Düzeltme yalnız çalışan kaydına gider; belgenin çıktısı
kuyruk düzeyindedir (`tests/pipeline/test_route_approve.py`).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.events import EventType
from app.matching.match import (
    LATIN_MISSING_PROBLEM,
    LATIN_ONLY_PROBLEM,
    PROFILE_FIELDS,
    ProfileApprovalRefusedError,
    ProfileFields,
    ProfileFieldsError,
    approve_pending_profile,
    check_profile_fields,
    edited_profile_fields,
    review_pending_profile,
)
from app.matching.names import normalize_name
from app.storage import DataLayout
from tests.matching.test_pending_profile_and_aliases import (
    BORN,
    CYRILLIC,
    LATIN_WITHOUT_SLUG,
    NAME,
    PASSPORT,
    PROFILE,
    _assert_no_personal_values,
    _counts,
    _employee,
    _events,
    _folders,
    _key,
    _number,
)
from tests.matching.test_profile_approval import ACTOR, FOLDER, _aliases

# Satır 7: numara okunaksız (temiz değil) — onay bekleyen profil.
PENDING_KEY = _key(numbers=_number(legible=False))
EDITED_SURNAME = "ORNEKOVIC"
EDITED_BORN = date(1990, 2, 1)


def _fields(**changes: Any) -> ProfileFields:
    """Önerinin alanları (`PROFILE`), `changes` ile düzeltilmiş."""
    values = {
        "given_names": PROFILE.given_names,
        "surname": PROFILE.surname,
        "other_names": PROFILE.other_names,
        "original_script_name": PROFILE.original_script_name,
        "date_of_birth": PROFILE.date_of_birth,
        "nationality": PROFILE.nationality,
    }
    values.update(changes)
    return ProfileFields(**values)


def _approve(session: Session, layout: DataLayout, fields: ProfileFields | None) -> Any:
    return approve_pending_profile(
        session, layout, PENDING_KEY, entry=PASSPORT, actor=ACTOR, fields=fields, page_index=0
    )


def _nothing_written(session: Session, layout: DataLayout) -> None:
    assert _counts(session) == (0, 0, 0)
    assert _events(session) == []
    assert _folders(layout) == []


# --- 10.7.3 kabul kriteri: önerilen profil düzenlenip onaylanabilir -------------------------------


def test_edited_profile_is_written_to_the_employee_and_its_folder_name(
    session: Session, layout: DataLayout
) -> None:
    fields = _fields(
        surname=EDITED_SURNAME, other_names=None, date_of_birth=EDITED_BORN, nationality="SRB"
    )

    employee = _approve(session, layout, fields)

    # Çalışan kaydı ve klasör adı (K8) onaylanan alanlardan; E numarası sistemin.
    assert (employee.id, employee.folder_name) == ("E0001", "Test_Ornekovic_E0001")
    assert (
        employee.given_names,
        employee.surname,
        employee.other_names,
        employee.original_script_name,
        employee.date_of_birth,
        employee.nationality,
    ) == ("TEST", EDITED_SURNAME, None, CYRILLIC, EDITED_BORN, "SRB")
    assert _folders(layout) == ["Test_Ornekovic_E0001"]
    # Belgenin yazımları kalır (belge böyle yazıyor), düzeltilmiş ad-soyad da eklenir: çalışan iki
    # yazımla da bulunur.
    assert _aliases(session) == sorted(
        [
            ("TEST ORNEKOVA", NAME, "latin", "E0001"),
            (CYRILLIC, NAME, "cyrillic", "E0001"),
            ("TEST ORNEKOVIC", normalize_name("TEST", EDITED_SURNAME), "latin", "E0001"),
        ]
    )
    assert _counts(session) == (1, 3, 0)  # temiz olmayan numara yine yazılmaz (D11)

    # Olay hangi alanların düzeltildiğini söyler, değerlerini değil (CONVENTIONS §6).
    (event,) = _events(session)
    assert (event.type, event.actor) == (EventType.EMPLOYEE_CREATED, ACTOR)
    assert event.data_json == {
        "action": "pending",
        "document_type_slug": "russian_passport",
        "edited_fields": ["surname", "other_names", "date_of_birth", "nationality"],
    }
    logged = json.dumps([event.data_json, event.message], ensure_ascii=False)
    _assert_no_personal_values(logged)
    for value in (EDITED_SURNAME, "Ornekovic", EDITED_BORN.isoformat(), "SRB"):
        assert value not in logged


def test_unchanged_fields_approve_the_proposal_as_it_is(
    session: Session, layout: DataLayout
) -> None:
    # Panel formu öneriyle dolar; değiştirilmeden onaylanan profil alanı vermeyen onayla aynıdır.
    employee = _approve(session, layout, PROFILE.fields())

    assert (employee.folder_name, employee.surname, employee.date_of_birth) == (
        FOLDER,
        "ORNEKOVA",
        BORN,
    )
    assert _aliases(session) == [
        ("TEST ORNEKOVA", NAME, "latin", "E0001"),
        (CYRILLIC, NAME, "cyrillic", "E0001"),
    ]
    (event,) = _events(session)
    assert event.data_json == {"action": "pending", "document_type_slug": "russian_passport"}


def test_edited_original_spelling_is_added_as_an_alias(
    session: Session, layout: DataLayout
) -> None:
    edited = "Орнекович Тест"

    employee = _approve(session, layout, _fields(original_script_name=edited))

    assert employee.original_script_name == edited
    assert (edited, normalize_name(edited), "cyrillic", "E0001") in _aliases(session)
    assert (CYRILLIC, NAME, "cyrillic", "E0001") in _aliases(session)
    (event,) = _events(session)
    assert event.data_json is not None
    assert event.data_json["edited_fields"] == ["original_script_name"]


def test_edited_fields_are_named_in_form_order() -> None:
    assert edited_profile_fields(PROFILE, PROFILE.fields()) == ()
    assert edited_profile_fields(
        PROFILE, _fields(nationality=None, given_names="Test", date_of_birth=None)
    ) == ("given_names", "date_of_birth", "nationality")
    assert PROFILE.fields().values() == {
        "given_names": "TEST",
        "surname": "ORNEKOVA",
        "other_names": "IVANOVNA",
        "original_script_name": CYRILLIC,
        "date_of_birth": "1990-01-01",
        "nationality": "RUS",
    }
    assert tuple(PROFILE.fields().values()) == PROFILE_FIELDS


# --- düzeltme ikinci çalışan açtırmaz (satır 3–5a) ------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "verdict"),
    [
        (
            _fields(given_names="KAYITLI", surname="KISI", date_of_birth=date(1985, 5, 5)),
            "name_dob (E0042)",
        ),
        # Doğum tarihi silinen düzeltme satır 5a'yla (05.5.4) aynı çalışana uyar.
        (_fields(given_names="KAYITLI", surname="KISI", date_of_birth=None), "name (E0042)"),
        (
            _fields(original_script_name="Кисі Кайитли", date_of_birth=date(1985, 5, 5)),
            "name_dob (E0042)",
        ),
    ],
    ids=["name-and-birth-date", "name-only", "original-spelling"],
)
def test_edited_profile_matching_a_registered_employee_is_refused(
    session: Session, layout: DataLayout, fields: ProfileFields, verdict: str
) -> None:
    # Belgenin kişisi kimseye uymuyor (satır 7), ama İK'nın düzelttiği ad ya da orijinal yazım
    # kayıtlı bir çalışana uyuyor: ikinci çalışan açılmaz, belge o çalışana atanır (08.2.1).
    _employee(
        session,
        "E0042",
        born=date(1985, 5, 5),
        aliases=("KAYITLI KISI", "Кисі Кайитли"),
    )
    before = _counts(session)

    for review in (True, False):
        with pytest.raises(ProfileApprovalRefusedError) as refused:
            if review:
                review_pending_profile(session, PENDING_KEY, entry=PASSPORT, fields=fields)
            else:
                _approve(session, layout, fields)

        message = str(refused.value)
        assert message == (
            "Onay bekleyen profil onaylanmaz (§20.2.2 satır 7, K7): onaylanan profil kayıtlı "
            f"çalışanla eşleşiyor: eşleştirme hükmü {verdict}."
        )
        _assert_no_personal_values(message)
        assert "KAYITLI" not in message
    assert _counts(session) == before
    assert _events(session) == []
    assert _folders(layout) == []


# --- geçersiz alan hiçbir şey yazdırmaz -----------------------------------------------------------

TOMORROW = date.today() + timedelta(days=1)


@pytest.mark.parametrize(
    ("changes", "errors"),
    [
        ({"given_names": ""}, {"given_names": "boş olamaz"}),
        ({"surname": "   "}, {"surname": "boş olamaz"}),
        ({"other_names": ""}, {"other_names": "boş olamaz"}),
        ({"given_names": "A" * 256}, {"given_names": "en fazla 255 karakter olabilir"}),
        ({"surname": "ORNEK\nOVA"}, {"surname": "denetim karakteri içeremez"}),
        ({"original_script_name": "---"}, {"original_script_name": "harf ya da rakam içermiyor"}),
        (
            {"given_names": LATIN_WITHOUT_SLUG[0], "surname": LATIN_WITHOUT_SLUG[1]},
            {"given_names": "ad-soyad klasör adına çevrilemiyor (K8)"},
        ),
        (
            {"given_names": "日本", "surname": "語"},
            {"given_names": LATIN_ONLY_PROBLEM, "surname": LATIN_ONLY_PROBLEM},
        ),
        ({"surname": "Орнекова"}, {"surname": LATIN_ONLY_PROBLEM}),
        ({"other_names": "Ивановна"}, {"other_names": LATIN_ONLY_PROBLEM}),
        ({"given_names": "Test محمد"}, {"given_names": LATIN_ONLY_PROBLEM}),
        ({"date_of_birth": TOMORROW}, {"date_of_birth": "gelecekte olamaz"}),
        (
            {"nationality": "rus"},
            {"nationality": "ICAO uyruk kodu olmalı (1–3 büyük harf, ör. RUS, D)"},
        ),
        (
            {"nationality": "RUSX"},
            {"nationality": "ICAO uyruk kodu olmalı (1–3 büyük harf, ör. RUS, D)"},
        ),
        (
            {"given_names": "", "surname": "", "date_of_birth": TOMORROW},
            {
                "given_names": "boş olamaz",
                "surname": "boş olamaz",
                "date_of_birth": "gelecekte olamaz",
            },
        ),
    ],
    ids=[
        "empty-given-names",
        "blank-surname",
        "empty-optional",
        "too-long",
        "control-character",
        "no-letters",
        "no-folder-name",
        "non-latin-names",
        "cyrillic-surname",
        "cyrillic-other-names",
        "mixed-script-given-names",
        "future-birth-date",
        "lowercase-nationality",
        "long-nationality",
        "several",
    ],
)
def test_invalid_fields_are_refused_before_anything_is_written(
    session: Session, layout: DataLayout, changes: dict[str, Any], errors: dict[str, str]
) -> None:
    fields = _fields(**changes)

    assert check_profile_fields(fields) == errors
    with pytest.raises(ProfileFieldsError) as refused:
        _approve(session, layout, fields)

    assert refused.value.errors == errors
    assert str(refused.value).startswith("Profil alanları geçersiz: ")
    _nothing_written(session, layout)


def test_valid_fields_have_no_problems() -> None:
    assert check_profile_fields(PROFILE.fields()) == {}
    assert check_profile_fields(ProfileFields(given_names="Ana", surname="Test")) == {}
    # 05.2.2: aksanlı Latin serbest; Latin olmayan yazımın yeri orijinal yazımdır.
    accented = ProfileFields(
        given_names="Đorđe", surname="Šćepanović-O'Brien", original_script_name="Ђорђе Шћепановић"
    )
    assert check_profile_fields(accented) == {}
    assert check_profile_fields(_fields(nationality="D", date_of_birth=date.today())) == {}
    assert check_profile_fields(
        _fields(date_of_birth=date(2000, 1, 2)), today=date(2000, 1, 1)
    ) == {"date_of_birth": "gelecekte olamaz"}


# --- önizleme yazmaz ------------------------------------------------------------------------------


def test_review_returns_the_proposal_and_writes_nothing(
    session: Session, layout: DataLayout
) -> None:
    assert review_pending_profile(session, PENDING_KEY, entry=PASSPORT) == PROFILE
    assert (
        review_pending_profile(
            session, PENDING_KEY, entry=PASSPORT, fields=_fields(surname=EDITED_SURNAME)
        )
        == PROFILE
    )
    _nothing_written(session, layout)


def test_review_refuses_invalid_fields_and_a_key_that_is_no_longer_row_7(
    session: Session, layout: DataLayout
) -> None:
    with pytest.raises(ProfileFieldsError):
        review_pending_profile(session, PENDING_KEY, entry=PASSPORT, fields=_fields(surname=""))
    with pytest.raises(ProfileApprovalRefusedError, match="satır 6–8 kararı create"):
        review_pending_profile(session, _key(), entry=PASSPORT)
    _nothing_written(session, layout)


# --- 05.2.2: Latin yazımı belgede olmayan öneri ---------------------------------------------------

ARABIC_KEY = _key(numbers=(), given_names="محمد", surname="علي", original=None)


def test_proposal_without_latin_spelling_is_shown_but_not_approved_as_is(
    session: Session, layout: DataLayout
) -> None:
    # Önizleme formu doldurur (ad ve soyad boş); öneri İK Latin adı yazmadan onaylanamaz.
    proposal = review_pending_profile(session, ARABIC_KEY, entry=PASSPORT)
    assert proposal.latin_missing
    assert (proposal.fields().given_names, proposal.fields().surname) == ("", "")

    with pytest.raises(ProfileFieldsError) as refused:
        approve_pending_profile(
            session, layout, ARABIC_KEY, entry=PASSPORT, actor=ACTOR, page_index=0
        )

    assert refused.value.errors == {
        "given_names": LATIN_MISSING_PROBLEM,
        "surname": LATIN_MISSING_PROBLEM,
    }
    _assert_no_personal_values(str(refused.value))
    _nothing_written(session, layout)


def test_hr_writes_the_latin_name_of_a_proposal_without_latin_spelling(
    session: Session, layout: DataLayout
) -> None:
    fields = ProfileFields(
        given_names="Muhammad",
        surname="Ali",
        other_names="IVANOVNA",
        original_script_name="محمد علي",
        date_of_birth=BORN,
        nationality="RUS",
    )

    employee = approve_pending_profile(
        session, layout, ARABIC_KEY, entry=PASSPORT, actor=ACTOR, fields=fields, page_index=0
    )

    assert (employee.given_names, employee.surname, employee.original_script_name) == (
        "Muhammad",
        "Ali",
        "محمد علي",
    )
    assert employee.folder_name == "Muhammad_Ali_E0001"
    # Belgenin yazımı (Arap) ve İK'nın yazdığı Latin ad birlikte isim yazımıdır.
    assert _aliases(session) == sorted(
        [
            ("محمد علي", normalize_name("محمد", "علي"), "arabic", "E0001"),
            ("Muhammad Ali", normalize_name("Muhammad Ali"), "latin", "E0001"),
        ]
    )
    (created,) = _events(session)
    # Orijinal yazım öneride zaten vardı (Latin alanlara okunan Arap yazım oraya taşındı).
    assert created.data_json["edited_fields"] == ["given_names", "surname"]
