"""10.8.2 — belgeyi başka çalışana taşıma: iki onay verilmeden işlem gerçekleşmez; iki profil de
güncellenir; olay kullanıcı adıyla loglanır (K16, §20.6, §20.6.1, §20.6.2; kabul senaryosu S16).

Taşınan belge gerçek boru hattından geçer (`process_upload`, kayıtlı yanıt sağlayıcısı; canlı yapay
zekâ çağrısı yok): temiz numaralı sentetik pasaport yeni çalışan (E0001) açar, çıktısı `Hazir/`'a,
orijinali `Alinan/`'a yazılır, `profil.md` üretilir. Belgenin taşınacağı kayıtlı çalışan (E0042)
elle eklenir. Onay belirteci 10.8.1'in tek kullanımlık belirtecidir ve oturum çerezine bağlıdır;
oturum bağımlılığı testte geçersiz kılındığı için çerez elle konur. Gerçek kimlik belgesi
kullanılmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.web.confirm as confirm
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    ConfirmationToken,
    Document,
    DocumentStatus,
    Employee,
    Event,
    Upload,
    UploadFile,
    utcnow,
)
from app.events import EventType
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, Operation
from app.web.routers.documents import (
    DOCUMENT_NOT_FOUND,
    MOVE_TARGET_NOT_FOUND,
    SAME_OWNER,
    move_subject,
)
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
OWNER, OWNER_FOLDER = "E0001", "Test_Ornekova_E0001"
TARGET, TARGET_FOLDER, TARGET_NAME = "E0042", "Kayitli_Kisi_E0042", "Kayitli Kisi"
OTHER = "E0043"
MOVED_NAME = "Kayitli_Kisi-Passport.pdf"
# §20.6 "Belgeyi başka çalışana taşı" — birebir.
FIRST_TEXT = "Bu belgeyi başka bir çalışana taşımak üzeresiniz. Emin misiniz?"
SECOND_TEXT = "Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?"


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


@dataclass(frozen=True)
class Moving:
    document_id: int
    old_path: Path
    content: bytes
    original: bytes


@pytest.fixture
def moving(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> Moving:
    """Boru hattından geçmiş etkin pasaport (E0001) ve iki kayıtlı çalışan (E0042, E0043)."""
    pages = [
        passport_page(PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1))
    ]
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
    uploaded = client.post(
        "/api/uploads",
        files=[("files", ("pasaport.pdf", make_document_pdf_bytes(pages), "application/pdf"))],
    )
    assert uploaded.status_code == 201, uploaded.text
    with session_factory() as session:
        process_upload(
            session,
            layout,
            session.get_one(Upload, uploaded.json()["upload_id"]),
            settings=SETTINGS,
            provider=recorded_provider(tmp_path / "kayit", pages),
        )
    with session_factory() as session:
        session.add(
            Employee(id=TARGET, folder_name=TARGET_FOLDER, given_names="Kayitli", surname="Kisi")
        )
        session.add(
            Employee(id=OTHER, folder_name="Baska_Biri_E0043", given_names="Baska", surname="Biri")
        )
        session.commit()
        document = session.scalars(select(Document)).one()
        assert document.employee_id == OWNER
        old_path = layout.resolve(document.path)
        (upload_file,) = session.scalars(select(UploadFile)).all()
        original = layout.resolve(upload_file.stored_path).read_bytes()
        moving = Moving(document.id, old_path, old_path.read_bytes(), original)
    layout.ensure_employee_tree(TARGET_FOLDER)
    return moving


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _prepare(client: TestClient, document_id: int, employee_id: str = TARGET) -> str:
    response = client.post(
        f"/documents/{document_id}/move/prepare", data={"employee_id": employee_id}
    )
    assert response.status_code == 200, response.text
    return _token(response.text)


def _move(
    client: TestClient, document_id: int, token: str | None, employee_id: str = TARGET
) -> Any:  # TestClient yanıtı
    data = {"employee_id": employee_id}
    if token is not None:
        data["confirmation"] = token
    return client.post(f"/documents/{document_id}/move", data=data)


def _count(session: Session, event_type: EventType) -> int:
    return session.scalar(select(func.count()).where(Event.type == event_type.value)) or 0


def _profile(layout: DataLayout, folder: str) -> str | None:
    path = layout.profile_path(folder)
    return path.read_text(encoding="utf-8") if path.exists() else None


def _unchanged(session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving) -> None:
    """Hiçbir şey olmadı: belge eski sahibinde, dosyası yerinde, onay ve taşıma olayı yok."""
    with session_factory() as session:
        document = session.get_one(Document, moving.document_id)
        assert document.employee_id == OWNER
        assert layout.resolve(document.path) == moving.old_path
        assert _count(session, EventType.USER_CONFIRMED) == 0
        assert _count(session, EventType.MANUAL_MOVE) == 0
    assert moving.old_path.read_bytes() == moving.content
    assert list(layout.ready_dir(TARGET_FOLDER).iterdir()) == []
    assert list(layout.received_dir(TARGET_FOLDER).iterdir()) == []
    assert _profile(layout, TARGET_FOLDER) is None


def _section(html: str, section_id: str) -> str:
    match = re.search(rf'<section id="{section_id}".*?</section>', html, re.S)
    assert match is not None, html
    return match.group(0)


# --- geçmiş sayfasındaki taşıma bölümü ------------------------------------------------------------


def test_an_active_document_offers_the_employee_search(client: TestClient, moving: Moving) -> None:
    html = client.get(f"/documents/{moving.document_id}/history").text

    section = _section(html, "move")
    assert "Başka çalışana taşı" in section
    assert f'hx-get="/documents/{moving.document_id}/move/employees"' in section
    assert 'name="q"' in section
    assert '<div id="move-results"' in section and '<div id="move-step"' in section


@pytest.mark.parametrize(
    ("status", "label"),
    [(DocumentStatus.SUPERSEDED, "Eski sürüm"), (DocumentStatus.ARCHIVED, "Arşivlendi")],
)
def test_a_document_that_is_not_active_says_it_cannot_be_moved_at_every_step(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    moving: Moving,
    status: DocumentStatus,
    label: str,
) -> None:
    with session_factory() as session:
        session.get_one(Document, moving.document_id).status = status.value
        session.commit()
    token = issue_token(session_factory, Operation.MOVE, move_subject(moving.document_id, TARGET))

    section = _section(client.get(f"/documents/{moving.document_id}/history").text, "move")
    responses = _steps(client, moving.document_id, token)

    assert f"bu belgenin durumu: {label}" in section
    assert "/move/employees" not in section
    for response in responses:
        assert response.status_code == 409
        assert "Yalnız etkin belge başka çalışana taşınabilir" in response.text
    with session_factory() as session:
        assert session.get_one(Document, moving.document_id).employee_id == OWNER


# --- arama ile seçim ------------------------------------------------------------------------------


def test_search_finds_the_employee_and_the_owner_cannot_be_selected(
    client: TestClient, moving: Moving
) -> None:
    target = client.get(f"/documents/{moving.document_id}/move/employees", params={"q": "kayitli"})
    owner = client.get(f"/documents/{moving.document_id}/move/employees", params={"q": "ornekova"})

    assert target.status_code == 200 and owner.status_code == 200
    assert f"<td>{TARGET}</td>" in target.text and TARGET_NAME in target.text
    assert OTHER not in target.text  # arama daraltır
    assert (
        f'hx-get="/documents/{moving.document_id}/move/confirm?employee_id={TARGET}"' in target.text
    )
    assert 'hx-target="#move-step"' in target.text
    assert f"<td>{OWNER}</td>" in owner.text
    assert "Belgenin sahibi" in owner.text
    assert "/move/confirm" not in owner.text


def test_search_finds_an_inactive_employee_with_the_suffix(
    client: TestClient, session_factory: sessionmaker[Session], moving: Moving
) -> None:
    # 10.5.7: taşıma araması pasif çalışanı da bulur ("(pasif)" ekiyle); seçilebilir.
    with session_factory() as session:
        session.get_one(Employee, TARGET).status = "inactive"
        session.commit()

    html = client.get(
        f"/documents/{moving.document_id}/move/employees", params={"q": "kayitli"}
    ).text

    row = html.split(f"<td>{TARGET}</td>", 1)[1].split("</tr>", 1)[0]
    assert '<span class="status-badge status-passive">(pasif)</span>' in row
    assert f"/move/confirm?employee_id={TARGET}" in row


def test_empty_search_lists_nobody_and_no_match_says_so(client: TestClient, moving: Moving) -> None:
    empty = client.get(f"/documents/{moving.document_id}/move/employees", params={"q": " "})
    missing = client.get(f"/documents/{moving.document_id}/move/employees", params={"q": "yok"})

    assert "<table" not in empty.text and "taşınacağı çalışanı bulmak için" in empty.text
    assert "<table" not in missing.text and "“yok” ile eşleşen çalışan yok." in missing.text


# --- iki aşamalı onay ve S16 ----------------------------------------------------------------------


def test_selecting_an_employee_shows_the_first_confirmation_verbatim_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    response = client.get(
        f"/documents/{moving.document_id}/move/confirm", params={"employee_id": TARGET}
    )

    assert response.status_code == 200
    html = response.text
    assert f'<p class="confirm-text" role="alert">{FIRST_TEXT}</p>' in html
    assert f"Seçilen çalışan: {TARGET_NAME} ({TARGET})" in html
    assert f'hx-post="/documents/{moving.document_id}/move/prepare"' in html
    assert f'<input type="hidden" name="employee_id" value="{TARGET}">' in html
    assert 'name="confirmation"' not in html  # belirteç birinci onaydan sonra gelir
    _unchanged(session_factory, layout, moving)


def test_the_first_confirmation_gives_the_second_one_with_a_token_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    response = client.post(
        f"/documents/{moving.document_id}/move/prepare", data={"employee_id": TARGET}
    )

    assert response.status_code == 200
    html = response.text
    assert f'<p class="confirm-text" role="alert">{SECOND_TEXT}</p>' in html
    assert f'hx-post="/documents/{moving.document_id}/move"' in html
    assert f'<input type="hidden" name="employee_id" value="{TARGET}">' in html
    assert _token(html)
    _unchanged(session_factory, layout, moving)
    with session_factory() as session:  # yalnız belirteç (özeti) saklandı
        (row,) = session.scalars(select(ConfirmationToken)).all()
        assert (row.operation, row.target, row.consumed_at) == (
            "move",
            f"{moving.document_id}:{TARGET}",
            None,
        )


def test_s16_one_confirmation_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    # S16 — tek onay: birinci onay verilir (hazırlık), ikinci onay verilmeden asıl istek gelir.
    owner_profile = _profile(layout, OWNER_FOLDER)
    client.get(f"/documents/{moving.document_id}/move/confirm", params={"employee_id": TARGET})
    _prepare(client, moving.document_id)

    response = _move(client, moving.document_id, None)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    _unchanged(session_factory, layout, moving)
    assert _profile(layout, OWNER_FOLDER) == owner_profile


def test_s16_two_confirmations_move_the_document_update_both_profiles_and_log_the_user(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    # S16 — iki onay: taşınır, iki profil güncellenir, olay kullanıcı adıyla.
    old_name = moving.old_path.name
    owner_profile = _profile(layout, OWNER_FOLDER)
    assert owner_profile is not None and old_name in owner_profile
    token = _prepare(client, moving.document_id)

    response = _move(client, moving.document_id, token)

    assert response.status_code == 200, response.text
    new_path = layout.ready_dir(TARGET_FOLDER) / MOVED_NAME
    assert new_path.read_bytes() == moving.content  # K11: içerik bayt bayt aynı
    assert not moving.old_path.exists()
    received = list(layout.received_dir(TARGET_FOLDER).iterdir())
    assert [path.read_bytes() for path in received] == [moving.original]  # K10
    with session_factory() as session:
        document = session.get_one(Document, moving.document_id)
        assert (document.employee_id, layout.resolve(document.path)) == (TARGET, new_path)
        assert document.status == DocumentStatus.ACTIVE.value
        events = list(
            session.scalars(
                select(Event).where(Event.document_id == moving.document_id).order_by(Event.id)
            )
        )
        types = [event.type for event in events]
        assert types.index(EventType.USER_CONFIRMED) < types.index(EventType.MANUAL_MOVE)
        confirmed = next(e for e in events if e.type == EventType.USER_CONFIRMED)
        manual = next(e for e in events if e.type == EventType.MANUAL_MOVE)
        assert confirmed.actor == manual.actor == SIGNED_IN.username
        assert manual.employee_id == TARGET
        assert manual.data_json is not None
        assert (manual.data_json["from_employee_id"], manual.data_json["to_employee_id"]) == (
            OWNER,
            TARGET,
        )
        data = confirmed.data_json
        assert data is not None
        assert data["operation"] == "move"
        assert data["target"] == {"document_id": moving.document_id, "employee_id": TARGET}
        first = datetime.fromisoformat(data["first_confirmed_at"])
        second = datetime.fromisoformat(data["second_confirmed_at"])
        assert first <= second <= utcnow()
        assert TARGET_NAME not in str(data)  # olay kişisel değer taşımaz (CONVENTIONS §6)
        assert session.scalars(select(ConfirmationToken)).one().consumed_at is not None
    # İki profil de güncellendi: profil.md ve profil sayfası.
    old_profile, new_profile = _profile(layout, OWNER_FOLDER), _profile(layout, TARGET_FOLDER)
    assert old_profile is not None and old_name not in old_profile
    assert "Henüz belge yok." in old_profile
    assert new_profile is not None and MOVED_NAME in new_profile
    owner_page = client.get(f"/employees/{OWNER}").text
    target_page = client.get(f"/employees/{TARGET}").text
    assert f"/documents/{moving.document_id}/" not in owner_page
    assert f"/employees/{TARGET}/documents/{moving.document_id}/file" in target_page
    html = response.text
    assert f"{TARGET_NAME} ({TARGET}) çalışanına taşındı: {MOVED_NAME}" in html
    assert f'<a href="/employees/{OWNER}">' in html and f'<a href="/employees/{TARGET}">' in html
    assert '<div id="move-results" hx-swap-oob="true"></div>' in html


def test_after_the_move_the_history_shows_the_new_owner_and_the_user(
    client: TestClient, moving: Moving
) -> None:
    assert (
        _move(client, moving.document_id, _prepare(client, moving.document_id)).status_code == 200
    )

    html = client.get(f"/documents/{moving.document_id}/history").text

    assert f'<a href="/employees/{TARGET}">{TARGET} — {TARGET_NAME}</a>' in html
    timeline = _section(html, "timeline")
    assert EventType.USER_CONFIRMED.value in timeline
    assert EventType.MANUAL_MOVE.value in timeline and SIGNED_IN.username in timeline


# --- belirteç kuralları (§20.6.1 adım 4–5, §20.6.2) -----------------------------------------------


@pytest.mark.parametrize("token", [None, "", "abc", "123.deadbeef"], ids=repr)
def test_a_move_without_a_valid_token_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    moving: Moving,
    token: str | None,
) -> None:
    response = _move(client, moving.document_id, token)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    _unchanged(session_factory, layout, moving)


def test_the_same_token_twice_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    token = _prepare(client, moving.document_id)
    assert _move(client, moving.document_id, token).status_code == 200

    replay = _move(client, moving.document_id, token)

    assert replay.status_code == 409  # belge artık E0042'nin
    assert SAME_OWNER in replay.text
    with session_factory() as session:
        assert _count(session, EventType.USER_CONFIRMED) == 1
        assert _count(session, EventType.MANUAL_MOVE) == 1
    assert [path.name for path in layout.ready_dir(TARGET_FOLDER).iterdir()] == [MOVED_NAME]


def test_a_used_token_is_refused_even_for_the_same_move_again(
    client: TestClient, session_factory: sessionmaker[Session], moving: Moving
) -> None:
    # Belge geri taşınıp aynı hedef yeniden geçerli olsa da tüketilmiş belirteç geçmez.
    token = _prepare(client, moving.document_id)
    assert _move(client, moving.document_id, token).status_code == 200
    back = _prepare(client, moving.document_id, OWNER)
    assert _move(client, moving.document_id, back, OWNER).status_code == 200

    replay = _move(client, moving.document_id, token)

    assert replay.status_code == 400
    assert CONFIRMATION_REFUSED in replay.text
    with session_factory() as session:
        assert session.get_one(Document, moving.document_id).employee_id == OWNER
        assert _count(session, EventType.MANUAL_MOVE) == 2


def test_an_expired_token_is_refused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    moving: Moving,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _prepare(client, moving.document_id)
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=5)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)

    response = _move(client, moving.document_id, token)

    assert response.status_code == 400
    _unchanged(session_factory, layout, moving)


def test_a_token_is_bound_to_its_employee_its_document_its_operation_and_its_session(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    token = _prepare(client, moving.document_id)
    # Aynı hedef kimliğine başka işlemin (atama) belirteci taşımada geçmez.
    foreign = issue_token(
        session_factory, Operation.ASSIGN, move_subject(moving.document_id, TARGET)
    )

    other_employee = _move(client, moving.document_id, token, employee_id=OTHER)
    other_operation = _move(client, moving.document_id, foreign)
    client.cookies.set(SESSION_COOKIE, "oturum-iki")
    other_session = _move(client, moving.document_id, token)

    for response in (other_employee, other_operation, other_session):
        assert response.status_code == 400, response.text
    _unchanged(session_factory, layout, moving)
    client.cookies.set(SESSION_COOKIE, SESSION)
    assert _move(client, moving.document_id, token).status_code == 200  # reddedilenler tüketmez


def test_prepare_needs_a_session_cookie(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    client.cookies.clear()

    response = client.post(
        f"/documents/{moving.document_id}/move/prepare", data={"employee_id": TARGET}
    )

    assert response.status_code == 400
    assert "Oturum çerezi yok." in response.text
    _unchanged(session_factory, layout, moving)


def test_a_failed_move_does_not_keep_the_confirmation_event_nor_use_up_the_token(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    # Onay olayı ve taşıma tek işlemdedir: Inbox'taki orijinal değişmişse (K10) taşıma düşer,
    # `USER_CONFIRMED` de geri alınır; belirteç tüketilmez.
    token = _prepare(client, moving.document_id)
    with session_factory() as session:
        (upload_file,) = session.scalars(select(UploadFile)).all()
        inbox = layout.resolve(upload_file.stored_path)
    inbox.write_bytes(b"degistirildi")

    response = _move(client, moving.document_id, token)

    assert response.status_code == 409
    assert "SHA-256" in response.text
    _unchanged(session_factory, layout, moving)
    inbox.write_bytes(moving.original)
    assert _move(client, moving.document_id, token).status_code == 200
    assert (layout.ready_dir(TARGET_FOLDER) / MOVED_NAME).read_bytes() == moving.content


# --- taşınamayan belge, bilinmeyen kayıt ----------------------------------------------------------


def _steps(
    client: TestClient, document_id: int, token: str = "1.x", employee_id: str = TARGET
) -> list[Any]:
    return [
        client.get(f"/documents/{document_id}/move/employees", params={"q": "kayitli"}),
        client.get(f"/documents/{document_id}/move/confirm", params={"employee_id": employee_id}),
        client.post(f"/documents/{document_id}/move/prepare", data={"employee_id": employee_id}),
        _move(client, document_id, token, employee_id),
    ]


def test_every_step_reports_a_missing_document(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    for response in _steps(client, moving.document_id + 100):
        assert response.status_code == 404
        assert DOCUMENT_NOT_FOUND in response.text
    _unchanged(session_factory, layout, moving)


def test_an_unknown_employee_or_the_current_owner_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    unknown = _steps(client, moving.document_id, employee_id="E9999")[1:]
    owner = _steps(client, moving.document_id, employee_id=OWNER)[1:]

    for response in unknown:
        assert response.status_code == 404
        assert MOVE_TARGET_NOT_FOUND in response.text
    for response in owner:
        assert response.status_code == 409
        assert SAME_OWNER in response.text
    _unchanged(session_factory, layout, moving)


def test_missing_employee_field_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, moving: Moving
) -> None:
    for path in ("move/prepare", "move"):
        response = client.post(f"/documents/{moving.document_id}/{path}", data={})
        assert response.status_code == 422
    confirm_step = client.get(f"/documents/{moving.document_id}/move/confirm")
    assert confirm_step.status_code == 422
    _unchanged(session_factory, layout, moving)
