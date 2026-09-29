"""10.5.7 — çalışanı pasife alma ve yeniden etkinleştirme panelde: iki aşamalı onay (§20.6 metinleri
birebir, tek kullanımlık belirteç hedef duruma ve nota bağlı), olaylar kullanıcı adıyla, profil
bildirimi, profilden yüklemenin kapanması (409, parti açılmaz) ve `profil.md` durum satırı (K16,
R11; kabul senaryosu S16 kalıbı; PLAN.md §C90-b, §D61).

Çalışan ve belgesi doğrudan yazılır (`tests/fixtures/gen.py` sentetik PDF'i); gerçek kimlik belgesi
ve ağ çağrısı yoktur. Onay belirteci oturum çerezine bağlıdır; oturum bağımlılığı testte geçersiz
kılındığı için çerez elle konur. Çekirdek `tests/matching/test_employee_status.py`'de, rota
`tests/pipeline/test_plan.py`'de, uçtan uca akış `tests/test_scenario_s22.py`'dedir.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.web.confirm as confirm
from app.db.models import (
    ConfirmationToken,
    Document,
    DocumentStatus,
    Employee,
    EmployeeStatus,
    Event,
    KnownDocumentType,
    Upload,
    utcnow,
)
from app.events import EventType
from app.storage import DataLayout, sha256_file
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, Operation
from app.web.routers.employees import (
    BAD_STATUS_TARGET,
    STATUS_NOT_CHANGEABLE,
    status_subject,
)
from app.web.routers.uploads import INACTIVE_CONTEXT_MESSAGE
from tests.fixtures.gen import make_pdf_bytes
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

EMPLOYEE_ID = "E0001"
FOLDER = "Ivan_Petrov_E0001"
# §20.6 "Çalışanı pasife al" / "Çalışanı yeniden etkinleştir" — birebir.
DEACTIVATE_FIRST = "Ivan Petrov çalışanını pasife almak üzeresiniz. Emin misiniz?"
DEACTIVATE_SECOND = (
    "Bu çalışana gelen yeni belgeler otomatik yerleşmeyecek, kuyruğa düşecektir. Son kararınız mı?"
)
REACTIVATE_FIRST = "Ivan Petrov çalışanını yeniden etkinleştirmek üzeresiniz. Emin misiniz?"
REACTIVATE_SECOND = (
    "Çalışan listeye dönecek ve yeni belgeleri yeniden otomatik yerleşecektir. Son kararınız mı?"
)
NOTE = "Sözleşmesi bitti"


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


@pytest.fixture
def seeded(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, str]:
    """E0001 Ivan Petrov (etkin): bir etkin pasaport ve `profil.md`."""
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
        session.add(
            Employee(
                id=EMPLOYEE_ID,
                folder_name=FOLDER,
                given_names="Ivan",
                surname="Petrov",
                date_of_birth=date(1990, 1, 1),
                nationality="RUS",
            )
        )
        ready = layout.ensure_employee_tree(FOLDER) / "Hazir"
        (ready / "Ivan_Petrov-Passport.pdf").write_bytes(make_pdf_bytes())
        session.add(
            Document(
                employee_id=EMPLOYEE_ID,
                type_slug="ru_passport",
                path=layout.relative(ready / "Ivan_Petrov-Passport.pdf"),
                format="pdf",
                sequence_no=1,
                source_refs_json=[{"file_id": 3, "pages": [0]}],
                status=DocumentStatus.ACTIVE.value,
            )
        )
        session.commit()
    layout.profile_path(FOLDER).write_text("# Ivan Petrov\n", encoding="utf-8")
    return _tree(layout.root)


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


def _prepare(client: TestClient, to: str = "inactive", reason: str = "") -> Any:
    return client.post(
        f"/employees/{EMPLOYEE_ID}/status/prepare", data={"to": to, "reason": reason}
    )


def _change(client: TestClient, token: str | None, to: str = "inactive", reason: str = "") -> Any:
    data = {"to": to, "reason": reason}
    if token is not None:
        data["confirmation"] = token
    return client.post(f"/employees/{EMPLOYEE_ID}/status", data=data, follow_redirects=False)


def _flip(client: TestClient, to: str, reason: str = "") -> Any:
    return _change(client, _token(_prepare(client, to, reason).text), to, reason)


def _status(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        return session.get_one(Employee, EMPLOYEE_ID).status


def _events(session_factory: sessionmaker[Session], *types: EventType) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event)
                .where(Event.type.in_([kind.value for kind in types]))
                .order_by(Event.id)
            )
        )


def _unchanged(
    session_factory: sessionmaker[Session], layout: DataLayout, tree: dict[str, str]
) -> None:
    """Hiçbir şey olmadı: çalışan etkin, onay ve durum olayı yok, dosyalar ilk hâlinde."""
    assert _status(session_factory) == "active"
    assert (
        _events(
            session_factory,
            EventType.USER_CONFIRMED,
            EventType.EMPLOYEE_DEACTIVATED,
            EventType.EMPLOYEE_REACTIVATED,
        )
        == []
    )
    assert _tree(layout.root) == tree


# --- profil sayfası ---------------------------------------------------------------------------


def test_an_active_profile_links_to_deactivation_and_keeps_the_upload_form(
    client: TestClient, seeded: dict[str, str]
) -> None:
    page = client.get(f"/employees/{EMPLOYEE_ID}").text

    assert f'href="/employees/{EMPLOYEE_ID}/status/confirm?to=inactive"' in page
    assert "Pasife al" in page
    assert "Yeniden etkinleştir" not in page
    assert 'id="upload-form"' in page
    assert "inactive-notice" not in page


def test_the_first_step_shows_the_first_text_and_an_optional_note_and_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    response = client.get(f"/employees/{EMPLOYEE_ID}/status/confirm?to=inactive")

    assert response.status_code == 200
    html = response.text
    assert DEACTIVATE_FIRST in html
    assert f'<form method="post" action="/employees/{EMPLOYEE_ID}/status/prepare"' in html
    assert '<input type="hidden" name="to" value="inactive">' in html
    assert re.search(r'<input id="status-reason" name="reason" type="text" maxlength="200"', html)
    assert "<textarea" not in html
    _unchanged(session_factory, layout, seeded)


@pytest.mark.parametrize(
    ("url", "code", "text"),
    [
        ("/employees/E9999/status/confirm?to=inactive", 404, "Çalışan bulunamadı."),
        (f"/employees/{EMPLOYEE_ID}/status/confirm?to=merged", 422, BAD_STATUS_TARGET),
        (f"/employees/{EMPLOYEE_ID}/status/confirm?to=aktif", 422, BAD_STATUS_TARGET),
        (f"/employees/{EMPLOYEE_ID}/status/confirm?to=active", 409, "Çalışan zaten etkin."),
    ],
)
def test_the_first_step_refuses_what_cannot_change(
    client: TestClient, seeded: dict[str, str], url: str, code: int, text: str
) -> None:
    response = client.get(url)

    assert response.status_code == code
    assert text in response.text
    assert "status/prepare" not in response.text


# --- hazırlık ve değişiklik -----------------------------------------------------------------------


def test_prepare_gives_the_second_text_and_a_token_bound_to_status_and_note(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    response = _prepare(client, "inactive", f"  {NOTE} ")

    assert response.status_code == 200, response.text
    html = response.text
    assert DEACTIVATE_SECOND in html
    assert f"Not: {NOTE}" in html
    assert f'<input type="hidden" name="reason" value="{NOTE}">' in html
    token = _token(html)
    with session_factory() as session:
        row = session.scalars(select(ConfirmationToken)).one()
        assert (row.operation, row.target) == (
            "deactivate_employee",
            status_subject(EMPLOYEE_ID, EmployeeStatus.INACTIVE, NOTE),
        )
        assert row.token_hash != token
    _unchanged(session_factory, layout, seeded)


def test_the_first_confirmation_alone_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    # S16: birinci onayla gelen (belirteçsiz) istek hiçbir şey değiştirmez.
    _prepare(client)

    response = _change(client, None)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    _unchanged(session_factory, layout, seeded)


def test_deactivation_flips_the_status_logs_both_events_and_keeps_the_files(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    response = _flip(client, "inactive", NOTE)

    assert response.status_code == 303, response.text
    assert response.headers["location"] == f"/employees/{EMPLOYEE_ID}?notice=status_inactive"
    assert _status(session_factory) == "inactive"
    confirmed, deactivated = _events(
        session_factory, EventType.USER_CONFIRMED, EventType.EMPLOYEE_DEACTIVATED
    )
    assert (confirmed.actor, confirmed.employee_id) == (SIGNED_IN.username, EMPLOYEE_ID)
    assert confirmed.data_json["operation"] == "deactivate_employee"
    assert confirmed.data_json["target"] == {"employee_id": EMPLOYEE_ID, "status": "inactive"}
    first = datetime.fromisoformat(confirmed.data_json["first_confirmed_at"])
    assert first <= datetime.fromisoformat(confirmed.data_json["second_confirmed_at"])
    assert (deactivated.actor, deactivated.employee_id, deactivated.data_json) == (
        SIGNED_IN.username,
        EMPLOYEE_ID,
        {"from": "active", "to": "inactive", "reason": NOTE},
    )
    # R11: klasör ve belgeler yerinde, bayt bayt aynı; belge etkin kalır.
    assert _tree(layout.root) == seeded
    with session_factory() as session:
        assert session.scalars(select(Document.status)).all() == ["active"]
    # 09.1.1: profil.md durum satırıyla yeniden üretildi.
    assert "| Durum | Pasif |" in layout.profile_path(FOLDER).read_text(encoding="utf-8")


def test_an_inactive_profile_shows_the_notice_hides_the_upload_and_offers_reactivation(
    client: TestClient, seeded: dict[str, str]
) -> None:
    _flip(client, "inactive", NOTE)

    page = client.get(f"/employees/{EMPLOYEE_ID}?notice=status_inactive").text

    assert "Çalışan pasife alındı; yeni belgeleri otomatik yerleşmeyecek." in page
    notice = page.split('<div class="notice inactive-notice"', 1)[1].split("</div>", 1)[0]
    assert "Pasif çalışan" in notice
    assert f"Pasife alan: {SIGNED_IN.username}" in notice and f"Not: {NOTE}" in notice
    assert f'href="/employees/{EMPLOYEE_ID}/status/confirm?to=active"' in notice
    assert f'href="/employees/{EMPLOYEE_ID}/status/confirm?to=inactive"' not in page
    assert 'id="upload-form"' not in page
    assert 'name="context_employee_id"' not in page
    assert "Pasif çalışana belge yüklenmez." in page
    assert '<span class="status-badge status-passive">Pasif</span>' in page


def test_an_inactive_employee_without_a_logged_deactivation_still_gets_the_notice(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, str]
) -> None:
    # Olayı olmayan (elle yazılmış) pasif kayıt: bildirim ve yükleme kapısı durumdan gelir.
    with session_factory() as session:
        session.get_one(Employee, EMPLOYEE_ID).status = "inactive"
        session.commit()

    page = client.get(f"/employees/{EMPLOYEE_ID}").text

    notice = page.split('<div class="notice inactive-notice"', 1)[1].split("</div>", 1)[0]
    assert "Pasif çalışan" in notice and "Pasife alan" not in notice
    assert 'id="upload-form"' not in page


def test_reactivation_returns_the_employee_to_the_list_and_the_upload_form(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    _flip(client, "inactive")
    assert EMPLOYEE_ID not in client.get("/employees").text
    first = client.get(f"/employees/{EMPLOYEE_ID}/status/confirm?to=active")
    assert REACTIVATE_FIRST in first.text

    prepared = _prepare(client, "active")
    assert REACTIVATE_SECOND in prepared.text
    response = _change(client, _token(prepared.text), "active")

    assert response.headers["location"] == f"/employees/{EMPLOYEE_ID}?notice=status_active"
    assert _status(session_factory) == "active"
    (reactivated,) = _events(session_factory, EventType.EMPLOYEE_REACTIVATED)
    assert (reactivated.actor, reactivated.data_json) == (
        SIGNED_IN.username,
        {"from": "inactive", "to": "active"},
    )
    page = client.get(response.headers["location"]).text
    assert "Çalışan yeniden etkinleştirildi." in page
    assert 'id="upload-form"' in page and "inactive-notice" not in page
    assert f'href="/employees/{EMPLOYEE_ID}"' in client.get("/employees").text
    assert "| Durum | Aktif |" in layout.profile_path(FOLDER).read_text(encoding="utf-8")


def test_a_token_is_bound_to_the_target_status_and_the_note(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    token = _token(_prepare(client, "inactive", NOTE).text)

    assert _change(client, token, "inactive", "başka not").status_code == 400
    assert _change(client, token, "inactive", "").status_code == 400
    _unchanged(session_factory, layout, seeded)
    # Reddedilen deneme belirteci tüketmez: hazırlanan notla geçer.
    assert _change(client, token, "inactive", NOTE).status_code == 303


def test_a_used_expired_or_foreign_token_is_refused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = status_subject(EMPLOYEE_ID, EmployeeStatus.INACTIVE, None)
    foreign = issue_token(session_factory, Operation.EDIT_EMPLOYEE, subject)
    reactivation = issue_token(session_factory, Operation.REACTIVATE_EMPLOYEE, subject)
    other_session = issue_token(
        session_factory, Operation.DEACTIVATE_EMPLOYEE, subject, cookie="iki"
    )
    other_employee = issue_token(
        session_factory,
        Operation.DEACTIVATE_EMPLOYEE,
        status_subject("E0002", EmployeeStatus.INACTIVE, None),
    )
    for token in (foreign, reactivation, other_session, other_employee, "uydurma"):
        assert _change(client, token).status_code == 400
    token = _token(_prepare(client).text)
    with session_factory() as session:
        issued = (
            session.scalars(select(ConfirmationToken).where(ConfirmationToken.target == subject))
            .all()[-1]
            .created_at
        )
    monkeypatch.setattr(confirm, "utcnow", lambda: issued + timedelta(minutes=10, seconds=1))
    assert _change(client, token).status_code == 400
    _unchanged(session_factory, layout, seeded)
    monkeypatch.setattr(confirm, "utcnow", utcnow)

    assert _change(client, token).status_code == 303
    # Çalışan yeniden etkinleştirilse de kullanılmış belirteç ikinci kez geçmez.
    assert _flip(client, "active").status_code == 303
    again = _change(client, token)
    assert again.status_code == 400
    assert CONFIRMATION_REFUSED in again.text
    assert f'href="/employees/{EMPLOYEE_ID}/status/confirm?to=inactive"' in again.text
    assert _status(session_factory) == "active"


def test_an_already_inactive_or_merged_employee_is_a_conflict(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, str]
) -> None:
    token = _token(_prepare(client).text)
    assert _change(client, token).status_code == 303

    again = _prepare(client)
    assert again.status_code == 409
    assert "Çalışan zaten pasif." in again.text

    with session_factory() as session:
        session.get_one(Employee, EMPLOYEE_ID).status = "merged"
        session.commit()
    page = client.get(f"/employees/{EMPLOYEE_ID}").text
    assert "status/confirm" not in page
    for response in (
        client.get(f"/employees/{EMPLOYEE_ID}/status/confirm?to=active"),
        _prepare(client, "active"),
        _change(client, "uydurma", "active"),
    ):
        assert response.status_code == 409
        assert STATUS_NOT_CHANGEABLE in response.text
    assert _status(session_factory) == "merged"


def test_a_too_long_note_is_refused_with_the_first_form(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    response = _prepare(client, "inactive", "x" * 201)

    assert response.status_code == 422
    assert "en çok 200 karakter" in response.text
    assert DEACTIVATE_FIRST in response.text
    assert 'action="/employees/E0001/status/prepare"' in response.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConfirmationToken)) == 0
    _unchanged(session_factory, layout, seeded)


def test_prepare_without_a_session_cookie_issues_no_token(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, str]
) -> None:
    client.cookies.clear()

    response = _prepare(client)

    assert response.status_code == 400
    assert 'name="confirmation"' not in response.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConfirmationToken)) == 0


# --- 10.5.3: profilden yükleme pasif çalışana kapalı -------------------------------------------


def test_context_upload_to_an_inactive_employee_is_a_conflict_and_opens_no_batch(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    seeded: dict[str, str],
) -> None:
    _flip(client, "inactive")
    files = [("files", ("cv.pdf", make_pdf_bytes(), "application/octet-stream"))]

    panel = client.post("/upload", files=files, data={"context_employee_id": EMPLOYEE_ID})
    api = client.post("/api/uploads", files=files, data={"context_employee_id": EMPLOYEE_ID})

    assert panel.status_code == api.status_code == 409
    assert INACTIVE_CONTEXT_MESSAGE in panel.text
    assert api.json()["detail"] == INACTIVE_CONTEXT_MESSAGE
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Upload)) == 0
    assert not (layout.root / "Inbox").exists() or not any((layout.root / "Inbox").iterdir())
    # Yükleme sayfasının çalışan seçiminde pasif çalışan yoktur; etkinleşince döner.
    assert f'value="{EMPLOYEE_ID}"' not in client.get("/upload").text
    _flip(client, "active")
    assert f'value="{EMPLOYEE_ID}"' in client.get("/upload").text
    assert (
        client.post("/upload", files=files, data={"context_employee_id": EMPLOYEE_ID}).status_code
        == 201
    )
