"""08.3.1 — onay bekleyen profili onaylama: onay sonrası çalışan oluşur (§20.2.2 satır 7; K7, K16).

Birim testleri `approve_pending_profile`'ı elle kurulan `PersonKey` ve geçici SQLite'taki sentetik
çalışanlarla sınar; entegrasyon testi kayıtlı yanıtla analiz edilmiş sentetik pasaportun önerilen
profilini onaylar — gerçek kişi/belge yok, ağ çağrısı yok. Belgenin onayla açılan çalışana
bağlanması kuyruk düzeyindedir (`tests/pipeline/test_route_approve.py`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Employee, EmployeeAlias
from app.events import EventType, event_context
from app.matching.match import (
    EmployeeMatch,
    MatchRule,
    PersonKey,
    ProfileApprovalRefusedError,
    approve_pending_profile,
    match_employee,
    propose_pending_profile,
    resolve_unmatched,
)
from app.storage import DataLayout
from tests.matching.test_pending_profile_and_aliases import (
    BORN,
    CYRILLIC,
    NAME,
    PASSPORT,
    UPLOAD_ID,
    _assert_no_personal_values,
    _counts,
    _employee,
    _events,
    _folders,
    _key,
    _nobody,
    _number,
    _recorded_key,
    _registered_name,
    _registered_name_and_birth_date,
    _registered_number,
)

ACTOR = "ik.ayse"
FOLDER = "Test_Ornekova_E0001"


def _approve(
    session: Session, layout: DataLayout, key: PersonKey, *, page_index: int | None = None
) -> Employee:
    return approve_pending_profile(
        session, layout, key, entry=PASSPORT, actor=ACTOR, page_index=page_index
    )


def _aliases(session: Session) -> list[tuple[str, str, str | None, str]]:
    return sorted(
        (alias.raw_name, alias.normalized_name, alias.script, alias.employee_id)
        for alias in session.scalars(select(EmployeeAlias))
    )


# --- 08.3.1 kabul kriteri: onay sonrası çalışan oluşur ------------------------------------------


def test_approval_opens_the_proposed_profile_as_an_employee(
    session: Session, layout: DataLayout
) -> None:
    # Satır 7: numara okunaksız (temiz değil) — İK onaylayınca önerilen profil çalışan olur.
    key = _key(numbers=_number(legible=False))

    employee = _approve(session, layout, key, page_index=2)

    assert (employee.id, employee.folder_name, employee.status) == ("E0001", FOLDER, "active")
    assert (
        employee.given_names,
        employee.surname,
        employee.other_names,
        employee.original_script_name,
        employee.date_of_birth,
        employee.nationality,
    ) == ("TEST", "ORNEKOVA", "IVANOVNA", CYRILLIC, BORN, "RUS")
    # Yazımlar önerilen profilinkiler, anahtarın normalize değeriyle ve alfabesiyle.
    assert _aliases(session) == [
        ("TEST ORNEKOVA", NAME, "latin", "E0001"),
        (CYRILLIC, NAME, "cyrillic", "E0001"),
    ]
    # Temiz olmayan numara yazılmaz (§20.2.3, D11): çalışan, iki yazım, numara yok.
    assert _counts(session) == (1, 2, 0)
    assert _folders(layout) == [FOLDER]
    assert layout.received_dir(FOLDER).is_dir() and layout.ready_dir(FOLDER).is_dir()

    (event,) = _events(session)
    assert (
        event.type,
        event.employee_id,
        event.actor,
        event.file_id,
        event.page_index,
        event.message,
    ) == (EventType.EMPLOYEE_CREATED, "E0001", ACTOR, None, 2, None)
    assert event.data_json == {"action": "pending", "document_type_slug": "russian_passport"}
    _assert_no_personal_values(json.dumps([event.data_json, event.message], ensure_ascii=False))

    # Onaylanan kişi artık kayıtlı: aynı kişinin sonraki numarasız belgesi satır 3'le eşleşir.
    assert match_employee(session, key) == EmployeeMatch(MatchRule.NAME_DOB, ("E0001",))


def test_approved_employee_takes_the_next_employee_number(
    session: Session, layout: DataLayout
) -> None:
    # K8: E numarası sistemindir ve artar; başka bir kişinin kaydı hükme girmez.
    _employee(session, "E0007", born=date(1980, 1, 1), aliases=("BASKA KISI",))

    employee = _approve(session, layout, _key(numbers=()))

    assert (employee.id, employee.folder_name) == ("E0008", "Test_Ornekova_E0008")
    assert _counts(session) == (2, 3, 0)


@pytest.mark.parametrize(
    ("registered", "key", "verdict"),
    [
        (_registered_number, _key(mrz_allows=False), "eşleştirme hükmü document_number"),
        (_registered_name_and_birth_date, _key(numbers=()), "eşleştirme hükmü name_dob"),
        (_registered_name, _key(numbers=()), "eşleştirme hükmü name_only"),
        (_nobody, _key(numbers=(), conflicts=("surname",)), "eşleştirme hükmü conflicting_key"),
        (_nobody, _key(), "satır 6–8 kararı create"),
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
        "nothing-read",
        "incomplete-person",
    ],
)
def test_approval_is_refused_when_row_7_no_longer_applies(
    session: Session,
    layout: DataLayout,
    registered: Callable[[Session], None],
    key: PersonKey,
    verdict: str,
) -> None:
    # Öneriye güvenilmez: tablo onay anında veritabanında yeniden değerlendirilir. Kişi artık
    # kayıtlı bir çalışanla eşleşiyorsa ikinci çalışan açılmaz (belge ona atanır, 08.2.1).
    registered(session)
    before = _counts(session)

    with pytest.raises(ProfileApprovalRefusedError) as refused:
        _approve(session, layout, key, page_index=0)

    message = str(refused.value)
    assert message == f"Onay bekleyen profil onaylanmaz (§20.2.2 satır 7, K7): {verdict}."
    _assert_no_personal_values(message)
    assert _counts(session) == before
    assert _events(session) == []
    assert _folders(layout) == []


@pytest.mark.parametrize("born", [BORN, None], ids=["name-and-birth-date", "name-only"])
def test_the_same_profile_is_not_approved_twice(
    session: Session, layout: DataLayout, born: date | None
) -> None:
    # Aynı kişinin her numarasız belgesi ayrı öneridir (C29); ilk onaydan sonra öteki öneriler
    # onaylanmaz — kişi kayıtlıdır (satır 3, doğum tarihi yoksa satır 5).
    key = _key(numbers=(), born=born)
    _approve(session, layout, key)

    with pytest.raises(ProfileApprovalRefusedError, match="eşleştirme hükmü name_"):
        _approve(session, layout, key)

    assert _counts(session) == (1, 2, 0)
    assert _folders(layout) == [FOLDER]


@pytest.mark.parametrize("actor", ["", "   "])
def test_approval_needs_the_user_name(session: Session, layout: DataLayout, actor: str) -> None:
    # K16: manuel işlem kullanıcı adıyla loglanır.
    with pytest.raises(ValueError, match="K16"):
        approve_pending_profile(session, layout, _key(numbers=()), entry=PASSPORT, actor=actor)

    assert _counts(session) == (0, 0, 0)
    assert _events(session) == []
    assert _folders(layout) == []


def test_approval_does_not_commit(session: Session, layout: DataLayout) -> None:
    _approve(session, layout, _key(numbers=()))

    session.rollback()

    assert _counts(session) == (0, 0, 0)
    assert _events(session) == []
    # Dizin işlemle geri alınmaz (create_employee ile aynı): boş klasör kalır.
    assert _folders(layout) == [FOLDER]


# --- entegrasyon: kayıtlı yanıt → anahtar → öneri → onay ---------------------------------------


def test_recorded_pending_passport_profile_is_approved(
    session: Session, layout: DataLayout
) -> None:
    # Numarası okunamayan kayıtlı pasaportun önerisi (05.7.1) onaylanır: çalışan önerilen
    # profille açılır, numara yazılmaz; öneri ile açılan kayıt aynı okumalardır.
    upload, key, entry = _recorded_key(session, layout, "s9_blurred_passport")
    file_id = upload.files[0].id
    with event_context(upload_id=upload.id):
        profile = propose_pending_profile(session, key, entry=entry, file_id=file_id, page_index=0)
        employee = approve_pending_profile(
            session, layout, key, entry=entry, actor=ACTOR, file_id=file_id, page_index=0
        )
    session.commit()

    assert (
        profile
        == resolve_unmatched(key, EmployeeMatch(MatchRule.NO_MATCH), entry=entry).proposed_profile
    )
    assert (
        employee.given_names,
        employee.surname,
        employee.other_names,
        employee.original_script_name,
        employee.date_of_birth,
        employee.nationality,
    ) == (
        profile.given_names,
        profile.surname,
        profile.other_names,
        profile.original_script_name,
        profile.date_of_birth,
        profile.nationality,
    )
    assert [(raw, normalized) for raw, normalized, _, _ in _aliases(session)] == sorted(
        profile.aliases
    )
    assert _counts(session) == (1, 2, 0)
    (created,) = [event for event in _events(session) if event.type == EventType.EMPLOYEE_CREATED]
    assert (created.upload_id, created.file_id, created.page_index, created.actor) == (
        UPLOAD_ID,
        file_id,
        0,
        ACTOR,
    )
    _assert_no_personal_values(
        json.dumps(
            [[event.data_json, event.message] for event in _events(session)], ensure_ascii=False
        )
    )
