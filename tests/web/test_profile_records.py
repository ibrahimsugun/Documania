"""10.5.8 — profil alt kayıtları panelde: isim yazımları, belge numaraları ve iletişim bilgileri
kaynağıyla listelenir; kaldırma iki aşamalı (§20.6 metinleri birebir, belirteç `kind:rid`'e bağlı),
geri alma tek adım, iletişim bilgisi elle eklenir; kaldırılan kayıt aramada kullanılmaz, belgede
yeniden görülürse profil uyarır (K16, R11; S16 kalıbı; PLAN.md §C90-c, §D61, §D68).

Çalışan, kayıtları ve belgesi doğrudan yazılır (`tests/fixtures/gen.py` sentetik PDF'i); gerçek
kimlik belgesi ve ağ çağrısı yoktur. Onay belirteci oturum çerezine bağlıdır; oturum bağımlılığı
testte geçersiz kılındığı için çerez elle konur. Çekirdek `tests/matching/test_records.py`'dedir.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    ConfirmationToken,
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    EmployeeStatus,
    Event,
    KnownDocumentType,
    utcnow,
)
from app.events import EventType
from app.storage import DataLayout, sha256_file
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, Operation
from app.web.routers.employees import (
    RECORD_ALREADY_REMOVED,
    RECORD_NOT_FOUND,
    RECORD_NOT_REMOVED,
    RECORDS_LOCKED,
)
from tests.fixtures.gen import make_pdf_bytes
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

EMPLOYEE_ID = "E0001"
FOLDER = "Ivan_Petrov_E0001"
NUMBER = "711234567"
OLD_PHONE = "+90 555 000 00 01"
PHONE = "+90 555 000 00 02"
EMAIL = "ivan@example.test"
VARIANT = "Jovan Petrovic"
# §20.6 "Profil alt kaydını kaldır" — birebir.
FIRST = "Bu kaydı çalışan profilinden kaldırmak üzeresiniz. Emin misiniz?"
SECOND = "Kayıt eşleştirmede ve aramada kullanılmayacak, geçmişte kalacaktır. Son kararınız mı?"
# Kaydın değerleri: hiçbir olaya girmez.
VALUES = (NUMBER, OLD_PHONE, PHONE, EMAIL, VARIANT, "Иван Петров", "IVAN PETROV")


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


@pytest.fixture
def seeded(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, Any]:
    """E0001 Ivan Petrov: bir etkin pasaport, üç isim yazımı, pasaportla bağlı numara, iki telefon
    (biri geçmiş) ve e-posta; E0002'nin kendi numarası; `profil.md`."""
    with session_factory() as session:
        session.add(
            KnownDocumentType(
                slug="ru_passport",
                name="Rus Pasaportu",
                file_label="Passport",
                sides="single",
                direct=True,
                analyze=True,
                output_format="pdf",
            )
        )
        employee = Employee(
            id=EMPLOYEE_ID,
            folder_name=FOLDER,
            given_names="Ivan",
            surname="Petrov",
            date_of_birth=date(1990, 1, 1),
        )
        other = Employee(
            id="E0002", folder_name="Anna_Ivanova_E0002", given_names="Anna", surname="Ivanova"
        )
        session.add_all([employee, other])
        ready = layout.ensure_employee_tree(FOLDER) / "Hazir"
        (ready / "Ivan_Petrov-Passport.pdf").write_bytes(make_pdf_bytes())
        passport = Document(
            employee_id=EMPLOYEE_ID,
            type_slug="ru_passport",
            path=layout.relative(ready / "Ivan_Petrov-Passport.pdf"),
            format="pdf",
            sequence_no=1,
            source_refs_json=[{"file_id": 3, "pages": [0]}],
            status=DocumentStatus.ACTIVE.value,
        )
        session.add(passport)
        session.flush()
        aliases = [
            EmployeeAlias(employee=employee, raw_name=raw, normalized_name=key, script=script)
            for raw, key, script in (
                ("IVAN PETROV", "ivan petrov", "latin"),
                ("Иван Петров", "ivan petrov", "cyrillic"),
                (VARIANT, "jovan petrovic", "latin"),
            )
        ]
        number = EmployeeIdentifier(
            employee=employee, kind="ru_passport", value=NUMBER, source_document_id=passport.id
        )
        foreign = EmployeeIdentifier(employee=other, kind="ru_passport", value="700000002")
        contacts = [
            EmployeeContact(employee=employee, kind="phone", value=OLD_PHONE, is_current=False),
            EmployeeContact(employee=employee, kind="phone", value=PHONE, is_current=True),
            EmployeeContact(employee=employee, kind="email", value=EMAIL, is_current=True),
        ]
        session.add_all([*aliases, number, foreign, *contacts])
        session.commit()
        ids = {
            "aliases": [alias.id for alias in aliases],
            "number": number.id,
            "foreign": foreign.id,
            "old_phone": contacts[0].id,
            "phone": contacts[1].id,
            "email": contacts[2].id,
            "passport": passport.id,
        }
    layout.profile_path(FOLDER).write_text("# Ivan Petrov\n", encoding="utf-8")
    return {**ids, "tree": _tree(layout.root)}


def _tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "profil.md"
    }


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _url(kind: str, record_id: int, step: str, employee_id: str = EMPLOYEE_ID) -> str:
    return f"/employees/{employee_id}/records/{kind}/{record_id}/{step}"


def _remove(client: TestClient, kind: str, record_id: int, token: str | None) -> Any:
    data = {} if token is None else {"confirmation": token}
    return client.post(_url(kind, record_id, "remove"), data=data, follow_redirects=False)


def _flip(client: TestClient, kind: str, record_id: int) -> Any:
    prepared = client.post(_url(kind, record_id, "remove/prepare"))
    return _remove(client, kind, record_id, _token(prepared.text))


def _events(session_factory: sessionmaker[Session], *types: EventType) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event)
                .where(Event.type.in_([kind.value for kind in types]))
                .order_by(Event.id)
            )
        )


RECORD_EVENTS = (
    EventType.USER_CONFIRMED,
    EventType.PROFILE_RECORD_REMOVED,
    EventType.PROFILE_RECORD_RESTORED,
    EventType.CONTACT_ADDED,
)


def _removed(session_factory: sessionmaker[Session]) -> list[tuple[str, str | None]]:
    with session_factory() as session:
        return [
            (type(record).__name__, record.removed_by)
            for model in (EmployeeAlias, EmployeeIdentifier, EmployeeContact)
            for record in session.scalars(select(model).where(model.removed_at.is_not(None)))
        ]


def _unchanged(
    session_factory: sessionmaker[Session], layout: DataLayout, seeded: dict[str, Any]
) -> None:
    """Hiçbir şey olmadı: kaldırılmış kayıt, yeni iletişim ve olay yok, dosyalar ilk hâlinde."""
    assert _removed(session_factory) == []
    with session_factory() as session:
        assert len(session.scalars(select(EmployeeContact)).all()) == 3
    assert _events(session_factory, *RECORD_EVENTS) == []
    assert _tree(layout.root) == seeded["tree"]


def _section(html: str, marker: str) -> str:
    return html.split(marker, 1)[1].split("</section>", 1)[0]


# --- profil sayfası -------------------------------------------------------------------------------


def test_the_profile_lists_every_record_with_its_source_and_a_remove_link(
    client: TestClient, seeded: dict[str, Any]
) -> None:
    page = client.get(f"/employees/{EMPLOYEE_ID}").text
    records = _section(page, 'id="records"')

    # Görülen yazımlar ilk kez listelenir, katlanmış (`<details>` kapalı).
    assert '<details class="record-group record-aliases" id="records-aliases">' in records
    assert "<summary>Görülen yazımlar (3)</summary>" in records
    assert "<td>IVAN PETROV</td><td>Latin</td>" in records
    assert "<td>Иван Петров</td><td>Kiril</td>" in records
    # Numara: tür, değer ve kaynak belge (dosyası yerinde → yeni sekmede açılır).
    passport = seeded["passport"]
    assert re.search(
        rf"<td>Rus Pasaportu</td><td>{NUMBER}</td><td><a href=\"/employees/E0001/documents/"
        rf"{passport}/file\" target=\"_blank\" rel=\"noopener\">Ivan_Petrov-Passport.pdf</a></td>",
        records,
    )
    # İletişim: kaynak ve güncel/geçmiş.
    assert f"<td>Telefon</td><td>{PHONE}</td><td>belgeden</td><td>Güncel</td>" in records
    assert f"<td>Telefon</td><td>{OLD_PHONE}</td><td>belgeden</td><td>Geçmiş</td>" in records
    assert f"<td>E-posta</td><td>{EMAIL}</td><td>belgeden</td><td>Güncel</td>" in records
    for kind, record_id in (
        *(("alias", each) for each in seeded["aliases"]),
        ("identifier", seeded["number"]),
        ("contact", seeded["phone"]),
        ("contact", seeded["old_phone"]),
        ("contact", seeded["email"]),
    ):
        assert f'href="{_url(kind, record_id, "remove/confirm")}"' in records
    assert f'<form method="post" action="/employees/{EMPLOYEE_ID}/contacts"' in records
    assert "Kaldırılanlar" not in records
    assert "<textarea" not in page


def test_the_first_step_shows_the_record_and_the_first_text_and_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    response = client.get(_url("identifier", seeded["number"], "remove/confirm"))

    assert response.status_code == 200
    html = response.text
    assert FIRST in html
    assert f"<dt>Belge numarası</dt><dd>{NUMBER}</dd>" in html
    action = _url("identifier", seeded["number"], "remove/prepare")
    assert f'<form method="post" action="{action}"' in html
    _unchanged(session_factory, layout, seeded)


@pytest.mark.parametrize(
    ("path", "code", "text"),
    [
        ("/employees/E9999/records/alias/1/remove/confirm", 404, "Çalışan bulunamadı."),
        ("/employees/E0001/records/employee/1/remove/confirm", 404, RECORD_NOT_FOUND),
        ("/employees/E0001/records/identifier/999/remove/confirm", 404, RECORD_NOT_FOUND),
        ("foreign", 404, RECORD_NOT_FOUND),
    ],
)
def test_the_first_step_refuses_a_record_that_is_not_the_employee_s(
    client: TestClient, seeded: dict[str, Any], path: str, code: int, text: str
) -> None:
    url = _url("identifier", seeded["foreign"], "remove/confirm") if path == "foreign" else path

    response = client.get(url)

    assert response.status_code == code
    assert text in response.text
    assert "remove/prepare" not in response.text


def test_prepare_gives_the_second_text_and_a_token_bound_to_kind_and_record(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    response = client.post(_url("contact", seeded["phone"], "remove/prepare"))

    assert response.status_code == 200, response.text
    assert SECOND in response.text
    assert f"<dt>Telefon</dt><dd>{PHONE}</dd>" in response.text
    token = _token(response.text)
    with session_factory() as session:
        row = session.scalars(select(ConfirmationToken)).one()
        assert (row.operation, row.target) == (
            "remove_profile_record",
            f"contact:{seeded['phone']}",
        )
        assert row.token_hash != token
    _unchanged(session_factory, layout, seeded)


def test_prepare_refuses_a_removed_record_or_a_request_without_a_session(
    client: TestClient,
    session_factory: sessionmaker[Session],
    seeded: dict[str, Any],
) -> None:
    _flip(client, "alias", seeded["aliases"][0])
    removed = client.post(_url("alias", seeded["aliases"][0], "remove/prepare"))
    client.cookies.clear()
    no_session = client.post(_url("identifier", seeded["number"], "remove/prepare"))

    assert removed.status_code == 409
    assert RECORD_ALREADY_REMOVED in removed.text
    assert no_session.status_code == 400
    assert f"<dt>Belge numarası</dt><dd>{NUMBER}</dd>" in no_session.text
    assert 'name="confirmation"' not in removed.text + no_session.text
    with session_factory() as session:
        assert len(session.scalars(select(ConfirmationToken)).all()) == 1  # yalnız ilk kaldırma


def test_a_number_source_that_moved_away_or_lost_its_file_opens_the_history(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    # Kaynak belge başka çalışana taşındıysa numara belgenin geçmişine, dosyası yoksa yine geçmişe
    # bağlanır; dosya açılmaz.
    with session_factory() as session:
        moved = Document(
            employee_id="E0002",
            type_slug="ru_passport",
            path="Employees/Anna_Ivanova_E0002/Hazir/Anna_Ivanova-Passport.pdf",
            format="pdf",
            sequence_no=1,
            source_refs_json=[{"file_id": 4, "pages": [0]}],
            status=DocumentStatus.ACTIVE.value,
        )
        session.add(moved)
        session.flush()
        session.add(
            EmployeeIdentifier(
                employee_id=EMPLOYEE_ID,
                kind="ru_passport",
                value="700000009",
                source_document_id=moved.id,
            )
        )
        session.commit()
        moved_id = moved.id
    passport = seeded["passport"]
    (layout.root / "Employees" / FOLDER / "Hazir" / "Ivan_Petrov-Passport.pdf").unlink()

    records = _section(client.get(f"/employees/{EMPLOYEE_ID}").text, 'id="records"')

    assert f'<td><a href="/documents/{moved_id}/history">Belge {moved_id}</a></td>' in records
    assert (
        f'<td><a href="/documents/{passport}/history">Ivan_Petrov-Passport.pdf</a></td>'
    ) in records


def test_the_first_confirmation_alone_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    # S16: birinci onayla gelen (belirteçsiz) istek hiçbir şey değiştirmez.
    client.post(_url("identifier", seeded["number"], "remove/prepare"))

    response = _remove(client, "identifier", seeded["number"], None)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    assert "Onayı yeniden başlatın" in response.text
    _unchanged(session_factory, layout, seeded)


def test_a_token_of_another_record_is_refused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    alias_id = seeded["aliases"][0]
    token = issue_token(session_factory, Operation.REMOVE_PROFILE_RECORD, f"alias:{alias_id}")

    assert _remove(client, "identifier", seeded["number"], token).status_code == 400
    assert _remove(client, "contact", alias_id, token).status_code in (400, 404)
    _unchanged(session_factory, layout, seeded)


def test_removal_marks_the_number_logs_both_events_and_keeps_the_files(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    number = seeded["number"]
    prepared = client.post(_url("identifier", number, "remove/prepare"))
    token = _token(prepared.text)

    response = _remove(client, "identifier", number, token)

    assert response.status_code == 303, response.text
    assert response.headers["location"] == f"/employees/{EMPLOYEE_ID}?notice=record_removed#records"
    assert _removed(session_factory) == [("EmployeeIdentifier", SIGNED_IN.username)]
    confirmed, removed = _events(session_factory, *RECORD_EVENTS)
    assert (confirmed.type, confirmed.actor, confirmed.employee_id) == (
        "USER_CONFIRMED",
        SIGNED_IN.username,
        EMPLOYEE_ID,
    )
    assert confirmed.data_json["operation"] == "remove_profile_record"
    assert confirmed.data_json["target"] == {
        "employee_id": EMPLOYEE_ID,
        "kind": "identifier",
        "record_id": number,
    }
    first = datetime.fromisoformat(confirmed.data_json["first_confirmed_at"])
    assert first <= datetime.fromisoformat(confirmed.data_json["second_confirmed_at"])
    assert (removed.type, removed.actor, removed.employee_id, removed.data_json) == (
        "PROFILE_RECORD_REMOVED",
        SIGNED_IN.username,
        EMPLOYEE_ID,
        {"kind": "identifier", "record_id": number},
    )
    for event in (confirmed, removed):
        assert not any(value in repr(event.data_json) for value in VALUES)
    # R11: satır silinmedi; dosyalar bayt bayt aynı; profil.md numarasız yeniden üretildi.
    with session_factory() as session:
        assert session.get_one(EmployeeIdentifier, number).value == NUMBER
    assert _tree(layout.root) == seeded["tree"]
    profile_md = layout.profile_path(FOLDER).read_text(encoding="utf-8")
    assert "| Durum |" in profile_md and NUMBER not in profile_md
    # Aynı belirteçle ikinci istek: kayıt zaten kaldırılmış (409), olay eklenmez.
    again = _remove(client, "identifier", number, token)
    assert again.status_code == 409
    assert RECORD_ALREADY_REMOVED in again.text
    assert len(_events(session_factory, *RECORD_EVENTS)) == 2


def test_a_removed_record_leaves_the_card_and_waits_under_removed_with_a_restore_button(
    client: TestClient, seeded: dict[str, Any]
) -> None:
    _flip(client, "identifier", seeded["number"])

    page = client.get(f"/employees/{EMPLOYEE_ID}?notice=record_removed").text

    assert "Kayıt kaldırıldı; eşleştirmede ve aramada kullanılmayacak." in page
    card = _section(page, '<section class="profile-card"')
    assert NUMBER not in card
    records = _section(page, 'id="records"')
    assert "Kayıtlı belge numarası yok." in records
    removed = records.split('<details class="removed-records" id="records-removed">', 1)[1]
    assert "<summary>Kaldırılanlar (1)</summary>" in removed
    assert f'<span class="record-kind">Belge numarası</span> {NUMBER}' in removed
    assert f"kaldıran: {SIGNED_IN.username}" in removed
    restore = _url("identifier", seeded["number"], "restore")
    assert f'<form method="post" action="{restore}" class="inline-form">' in removed
    assert "Kaldırılmış kayıt" not in records  # belgede yeniden görülmedi: uyarı yok


def test_a_removed_current_contact_leaves_the_card_without_promoting_an_older_one(
    client: TestClient, seeded: dict[str, Any]
) -> None:
    # Kaldırılan güncel e-posta kartta "—" olur; kaldırılan güncel telefonun yerine geçmişteki
    # telefon güncel sayılmaz (05.8.2: güncel olan en son görülen değerdir).
    _flip(client, "contact", seeded["email"])
    _flip(client, "contact", seeded["phone"])

    page = client.get(f"/employees/{EMPLOYEE_ID}").text

    card = _section(page, '<section class="profile-card"')
    assert re.search(r"<dt>E-posta</dt>\s*<dd>—</dd>", card)
    assert re.search(r"<dt>Telefon</dt>\s*<dd>—</dd>", card)
    assert EMAIL not in card and PHONE not in card and OLD_PHONE not in card
    removed = _section(page, 'id="records"').split('id="records-removed"', 1)[1]
    assert f'<span class="record-kind">E-posta</span> {EMAIL}' in removed
    assert f'<span class="record-kind">Telefon</span> {PHONE}' in removed


def test_search_does_not_find_a_removed_spelling_or_number_until_restored(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, Any]
) -> None:
    variant, number = seeded["aliases"][2], seeded["number"]

    def found(query: str) -> bool:
        return 'href="/employees/E0001"' in client.get("/employees", params={"q": query}).text

    assert found("Jovan") and found("711 234 567")
    _flip(client, "alias", variant)
    _flip(client, "identifier", number)
    assert not found("Jovan") and not found("711 234 567")
    assert found("Ivan Petrov")  # kayıttaki ad aranmaya devam eder

    for kind, record_id in (("alias", variant), ("identifier", number)):
        response = client.post(_url(kind, record_id, "restore"), follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].endswith("?notice=record_restored#records")

    assert found("Jovan") and found("711 234 567")
    restored = _events(session_factory, EventType.PROFILE_RECORD_RESTORED)
    assert [(event.actor, event.data_json) for event in restored] == [
        (SIGNED_IN.username, {"kind": "alias", "record_id": variant}),
        (SIGNED_IN.username, {"kind": "identifier", "record_id": number}),
    ]
    assert _removed(session_factory) == []


def test_restore_refuses_an_active_or_unknown_record(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    response = client.post(_url("contact", seeded["phone"], "restore"))

    assert response.status_code == 409
    assert RECORD_NOT_REMOVED in response.text
    assert client.post(_url("contact", 999, "restore")).status_code == 404
    assert client.post(_url("identifier", seeded["foreign"], "restore")).status_code == 404
    _unchanged(session_factory, layout, seeded)


def test_a_removed_record_seen_again_in_a_document_is_warned_on_the_profile(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, Any]
) -> None:
    _flip(client, "identifier", seeded["number"])
    with session_factory() as session:
        session.get_one(EmployeeIdentifier, seeded["number"]).seen_after_removal_at = utcnow()
        session.commit()

    records = _section(client.get(f"/employees/{EMPLOYEE_ID}").text, 'id="records"')

    warning = "Belgede görülen belge numarası kaldırılmış bir kayda uyuyor"
    assert records.count(warning) == 2  # bölümün üstünde ve kaldırılan satırda
    assert '<details class="removed-records" id="records-removed" open>' in records


# --- iletişim bilgisini elle ekleme ---------------------------------------------------------------


def test_a_manual_contact_becomes_current_carries_its_adder_and_is_logged(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    new_phone = "+90 555 000 00 03"

    response = client.post(
        f"/employees/{EMPLOYEE_ID}/contacts",
        data={"kind": "phone", "value": f"  {new_phone} "},
        follow_redirects=False,
    )

    assert response.status_code == 303, response.text
    assert response.headers["location"] == f"/employees/{EMPLOYEE_ID}?notice=contact_added#records"
    with session_factory() as session:
        phones = session.scalars(
            select(EmployeeContact)
            .where(EmployeeContact.kind == "phone")
            .order_by(EmployeeContact.id)
        ).all()
        assert [(each.value, each.is_current, each.added_by) for each in phones] == [
            (OLD_PHONE, False, None),
            (PHONE, False, None),
            (new_phone, True, SIGNED_IN.username),
        ]
        assert phones[-1].source_document_id is None
        added_id = phones[-1].id
    (event,) = _events(session_factory, *RECORD_EVENTS)
    assert (event.type, event.actor, event.employee_id, event.data_json) == (
        "CONTACT_ADDED",
        SIGNED_IN.username,
        EMPLOYEE_ID,
        {"kind": "phone", "record_id": added_id},
    )
    assert new_phone in layout.profile_path(FOLDER).read_text(encoding="utf-8")
    assert _tree(layout.root) == seeded["tree"]

    page = client.get(f"/employees/{EMPLOYEE_ID}?notice=contact_added").text
    assert "İletişim bilgisi eklendi." in page
    day = utcnow().strftime("%d.%m.%Y")
    assert (
        f"<td>Telefon</td><td>{new_phone}</td><td>elle ({SIGNED_IN.username}, {day})</td>"
        "<td>Güncel</td>"
    ) in _section(page, 'id="records"')
    card = _section(page, '<section class="profile-card"')
    assert new_phone in card and PHONE not in card


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"kind": "email", "value": "ivan.example.test"}, "ad@alan.uzantı"),
        ({"kind": "fax", "value": "123456"}, "Tür telefon, e-posta ya da adres olmalı."),
        ({"kind": "phone", "value": PHONE}, "Bu değer zaten güncel kayıt."),
        ({"kind": "address", "value": "x" * 501}, "en çok 500 karakter"),
    ],
)
def test_a_refused_contact_redraws_the_form_and_writes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
    data: dict[str, str],
    message: str,
) -> None:
    response = client.post(f"/employees/{EMPLOYEE_ID}/contacts", data=data)

    assert response.status_code == 422
    records = _section(response.text, 'id="records"')
    assert message in records
    assert f'value="{data["value"]}"' in records
    _unchanged(session_factory, layout, seeded)


def test_a_contact_for_an_unknown_employee_is_a_404(
    client: TestClient, seeded: dict[str, Any]
) -> None:
    response = client.post("/employees/E9999/contacts", data={"kind": "phone", "value": PHONE})

    assert response.status_code == 404


# --- birleştirilmiş çalışan -----------------------------------------------------------------------


def test_a_merged_employee_s_records_are_shown_but_not_changed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, Any],
) -> None:
    with session_factory() as session:
        session.get_one(Employee, EMPLOYEE_ID).status = EmployeeStatus.MERGED.value
        session.get_one(EmployeeContact, seeded["old_phone"]).removed_at = utcnow()
        session.commit()

    records = _section(client.get(f"/employees/{EMPLOYEE_ID}").text, 'id="records"')
    assert NUMBER in records and "Kaldırılanlar (1)" in records
    assert "remove/confirm" not in records and "/restore" not in records
    assert "/contacts" not in records

    first = client.get(_url("identifier", seeded["number"], "remove/confirm"))
    restore = client.post(_url("contact", seeded["old_phone"], "restore"))
    added = client.post(
        f"/employees/{EMPLOYEE_ID}/contacts", data={"kind": "phone", "value": "+90 555 1234 567"}
    )

    assert (first.status_code, restore.status_code, added.status_code) == (409, 409, 409)
    assert RECORDS_LOCKED in first.text and RECORDS_LOCKED in restore.text
    assert RECORDS_LOCKED in added.text
    assert _events(session_factory, *RECORD_EVENTS) == []
