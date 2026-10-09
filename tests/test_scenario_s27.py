"""09.3 — PRD §9 kabul senaryosu S27 uçtan uca: üç rol — `Zvz` (root), bir İK, bir Kullanıcı —
panelde geziyor (10.1.8, 10.1.9; PLAN.md §D115).

Beklenen: Kullanıcı her sayfayı ve belgeyi açar, hiçbir yazma düğmesi görmez, her yazma isteği 403
ve veri değişmez, kendi parolasını ve dilini değiştirir; İK yazar, Kullanıcılar tablosunda root'u
görmez, root'a yönelik istek 404, erişim logu bağlantısı yok ve adresi 404; root erişim logunu ve
kendi ekranında "Root" etiketini görür, Kullanıcılar tablosunda kendisi de listelenmez; ikinci root
açılamaz.

Kurgu: root komut satırından (`python -m app.web create-root`), İK ve Kullanıcı komut satırından
(`create-user --role hr|user`) açılır; üçü de gerçek girişle (`POST /login`, oturum çerezi) gezer —
oturum bağımlılığı geçersiz kılınmaz. Kayıtlı Ornekova'nın pasaportu İK'nın yüklemesiyle gelir ve
kayıtlı yanıtla işlenir; yapay zekâ canlı çağrılmaz. Belge ve kişi sentetiktir, gerçek kimlik
belgesi yoktur (CONVENTIONS §6). Ortam S1–S5'inkidir.
"""

from __future__ import annotations

import io
import re
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AccessLog, Document, DocumentGroup, Event, User
from app.storage import DataLayout
from app.web.__main__ import main as web_command
from app.web.auth import get_current_user
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.test_scenarios_s01_s05 import PASSPORT_NUMBER, _process, _register_employee, _upload

engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client

PASSWORD = "s27-sentetik-parola"
NEW_PASSWORD = "s27-yeni-sentetik-parola"
ROOT_LABEL = '<span class="badge role-badge" translate="no">Root</span>'


def _command(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{PASSWORD}\n"))
    return web_command([*arguments, "--password-stdin"])


def _login(app: object, username: str, password: str = PASSWORD) -> TestClient:
    browser = TestClient(app)  # type: ignore[arg-type]
    response = browser.post(
        "/login", data={"username": username, "password": password}, follow_redirects=False
    )
    assert response.status_code == 303, response.text
    return browser


def _write_controls(html: str) -> list[str]:
    """Kapı dışı olmayan form hedefleri ve HTMX yazma düğmeleri (çıkış, dil, kendi hesabı hariç)."""
    targets = re.findall(r'method="post"\s+action="([^"]+)"', html)
    targets += re.findall(r'hx-post="([^"]+)"', html)
    return [
        t for t in targets if t not in ("/logout", "/language") and not t.startswith("/account")
    ]


def _state(session: Session, layout: DataLayout) -> tuple[object, ...]:
    files = sorted(path.as_posix() for path in layout.root.rglob("*") if path.is_file())
    state = (
        session.scalar(select(func.max(Event.id))),
        session.scalar(select(func.count()).select_from(Document)),
        session.scalar(select(func.count()).select_from(DocumentGroup)),
        session.scalar(select(func.count()).select_from(User)),
        files,
    )
    session.rollback()  # SQLite'ta okuma da yazma kilidini tutar (PLAN.md §C4): panel beklemesin
    return state


def test_s27_root_hr_and_a_read_only_user_browse_the_panel(
    client: TestClient,
    session: Session,
    layout: DataLayout,
    engine: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = client.app
    del app.dependency_overrides[get_current_user]  # type: ignore[attr-defined]
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))  # type: ignore[attr-defined]
    get_settings.cache_clear()
    try:
        assert _command(monkeypatch, "create-root", "--username", "Zvz") == 0
        assert _command(monkeypatch, "create-user", "--username", "ikuzman", "--role", "hr") == 0
        assert _command(monkeypatch, "create-user", "--username", "okur", "--role", "user") == 0
        # İkinci root açılamaz.
        assert _command(monkeypatch, "create-root", "--username", "ikinci-root") == 1
    finally:
        get_settings.cache_clear()
    roles = dict(session.execute(select(User.username, User.role)).tuples().all())
    assert roles == {"Zvz": "root", "ikuzman": "hr", "okur": "user"}
    zvz_id = session.scalars(select(User.id).where(User.username == "Zvz")).one()
    session.rollback()

    # İK yazar: kayıtlı çalışanın pasaportu yüklenir ve işlenir, bir belge grubu açılır.
    _register_employee(session, layout, PERSON_ORNEKOVA, [("russian_passport", PASSPORT_NUMBER)])
    session.commit()
    ik = _login(app, "ikuzman")
    pages = [
        passport_page(
            PERSON_ORNEKOVA, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1)
        )
    ]
    upload = _upload(ik, session, ("pasaport.pdf", make_document_pdf_bytes(pages)))
    _process(session, layout, upload, recorded_provider(tmp_path / "kayit", pages))
    session.commit()
    document_id, upload_id = session.scalars(select(Document.id)).one(), upload.id
    session.rollback()
    created = ik.post("/document-groups", data={"name": "Vize"}, follow_redirects=False)
    assert created.status_code == 303
    # İK root'u görmez; root'a yönelik istek 404; erişim logu bağlantısı yok, adresi 404.
    users = ik.get("/users").text
    assert "Zvz" not in users and 'value="root"' not in users
    assert ik.post(f"/users/{zvz_id}/status", data={"status": "inactive"}).status_code == 404
    assert ik.post(f"/users/{zvz_id}/role", data={"role": "user"}).status_code == 404
    assert "/access-log" not in ik.get("/employees/E0001").text
    assert ik.get("/access-log").status_code == 404
    assert ROOT_LABEL not in users

    # Kullanıcı her sayfayı ve belgeyi açar, hiçbir yazma düğmesi görmez.
    okur = _login(app, "okur")
    file_url = f"/employees/E0001/documents/{document_id}"
    for path in (
        "/employees",
        "/employees/E0001",
        f"/documents/{document_id}/history",
        "/uploads",
        f"/uploads/{upload_id}",
        "/queues",
        "/document-types",
        "/document-types/russian_passport",
        "/document-groups",
        "/training",
        "/users",
    ):
        page = okur.get(path)
        assert page.status_code == 200, path
        assert _write_controls(page.text) == [], (path, _write_controls(page.text))
        assert 'href="/upload"' not in page.text, path
    assert okur.get(f"{file_url}/file").status_code == 200
    assert okur.get(f"{file_url}/download").status_code == 200
    # Her yazma isteği 403 ve veri değişmez.
    before = _state(session, layout)
    group_id = session.scalars(select(DocumentGroup.id)).one()
    session.rollback()
    for path, data in (
        ("/api/uploads", {}),
        (f"/documents/{document_id}/archive/prepare", {}),
        (f"/documents/{document_id}/delete/prepare", {}),
        ("/document-groups", {"name": "Okurun grubu"}),
        (f"/document-groups/{group_id}/archive", {}),
        ("/users", {"username": "yeni", "password": PASSWORD, "role": "hr"}),
        (f"/uploads/{upload_id}/rerun", {}),
    ):
        assert okur.post(path, data=data).status_code == 403, path
    assert okur.get("/upload").status_code == 403
    assert _state(session, layout) == before
    # Kullanıcı kendi parolasını ve dilini değiştirir; erişim logu ona da 404.
    changed = okur.post(
        "/account/password",
        data={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_repeat": NEW_PASSWORD,
        },
        follow_redirects=False,
    )
    assert changed.status_code == 303
    language = okur.post("/language", data={"language": "en", "next": "/"}, follow_redirects=False)
    assert language.status_code == 303
    assert session.scalars(select(User.language).where(User.username == "okur")).one() == "en"
    session.rollback()
    assert okur.get("/access-log").status_code == 404
    assert _login(app, "okur", NEW_PASSWORD).get("/employees").status_code == 200

    # Root erişim logunu ve kendi ekranında "Root" etiketini görür; tabloda kendisi de yok.
    root = _login(app, "Zvz")
    log = root.get("/access-log/employees/E0001")
    assert log.status_code == 200 and "okur" in log.text
    viewers = set(session.scalars(select(User.username).join(AccessLog.user)))
    session.rollback()
    assert viewers == {"okur"}
    employees = root.get("/employees").text
    assert ROOT_LABEL in employees and 'href="/access-log"' in employees
    assert ROOT_LABEL in root.get("/account/password").text
    users = root.get("/users").text
    assert 'id="user-' + str(zvz_id) + '"' not in users
    assert "Zvz" not in users.split("</header>", 1)[1]
