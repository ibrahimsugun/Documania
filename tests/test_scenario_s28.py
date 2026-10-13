"""09.3 — PRD §9 kabul senaryosu S28 uçtan uca: geri bildirim ve yol gösterme (10.11.1–10.11.3;
PLAN.md §D120).

Beklenen: kuyruk satırı öğeye ve aday türe bağlı, "Çözüm" yapılacak işi söyler; onaydan sonra bağlı
bekleyen öğe sayısı ve sonraki adım bildirimle söylenir; pasife alma başarı bildirimi verir,
yenilemede tekrar çıkmaz; bildirim ve ipuçları Sırpçadır; Kullanıcı onay bağlantısı görmez, "İK'ya
bildirin" ipucunu görür.

Kurgu: katalogda olmayan bir CV (aday tür "Curriculum Vitae") yükleme uç noktasıyla gelir ve
`process_upload` ile işlenir; yapay zekâ canlı çağrılmaz (kayıtlı yanıt). Onay paneldeki iki
aşamalı akıştır (`approve/confirm` → `prepare` → `approve`), pasife alma da öyle
(`status/prepare` → `status`). Dil seçici (`POST /language`) hesabın tercihini yazar; oturumdaki
kullanıcı her istekte veritabanından okunur (gerçek oturumdaki gibi). Belge ve kişi sentetiktir,
gerçek kimlik belgesi yoktur (CONVENTIONS §6). Ortam S1–S5'inkidir.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import (
    CandidateDocumentType,
    Employee,
    QueueItem,
    User,
    UserRole,
)
from app.db.session import create_session_factory
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_PRUEBA,
    PERSON_SIDOROV,
    make_document_pdf_bytes,
    recorded_provider,
    unknown_document_page,
)
from tests.i18n.residue import turkish_residue
from tests.test_scenarios_s01_s05 import (
    PASSPORT_NUMBER,
    SIGNED_IN,
    _process,
    _register_employee,
    _upload,
)
from tests.web.flash import flashed, toasts

engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client

READER_ID = 2
CV_NAME = "Curriculum Vitae"
CV_SLUG = "curriculum_vitae"
BASE = "/document-types/candidate-types"
CV_FORM = {
    "slug": CV_SLUG,
    "name": CV_NAME,
    "file_label": "CV",
    "country": "rs",
    "description": "",
    "expected_file_types": ["pdf"],
    "pages_min": "1",
    "pages_max": "3",
    "sides": "single",
    "analyze": "on",
    "required_fields": "surname, given_names",
    "allowed_conversions": ["wrap_image"],
    "output_format": "pdf",
    "acceptance_criteria": [""],
    "prompt_description": "Curriculum vitae: education and work history.",
}


def _accounts(engine: Engine) -> None:
    """İK (S1–S5'in oturumdaki kullanıcısı) ve salt okunur Kullanıcı hesapları."""
    with create_session_factory(engine)() as db:
        db.add(User(id=SIGNED_IN.id, username=SIGNED_IN.username, password_hash="-", role="hr"))
        db.add(User(id=READER_ID, username="okuyucu", password_hash="-", role=UserRole.USER.value))
        db.commit()


def _sign_in(app: FastAPI, engine: Engine, user_id: int) -> None:
    """Oturumdaki kullanıcı her istekte hesabından okunur: dil tercihi (10.10.2) dahil."""
    factory = create_session_factory(engine)

    def current() -> PanelUser:
        with factory() as db:
            account = db.get_one(User, user_id)
            return PanelUser(account.id, account.username, account.role, account.language)

    app.dependency_overrides[get_current_user] = current


def _hidden(html: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for name, value in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', html):
        fields.setdefault(name, []).append(unescape(value))
    return fields


def _queue_row(html: str) -> str:
    table = re.search(r'<table class="queue">.*?</table>', html, re.S)
    assert table is not None
    return unescape(table.group(0))


def test_s28_hr_is_guided_from_the_batch_to_the_candidate_and_notices_follow_the_language(
    client: TestClient, engine: Engine, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    _accounts(engine)
    _sign_in(app, engine, SIGNED_IN.id)
    client.cookies.set(SESSION_COOKIE, "s28-oturum")
    sidorov = _register_employee(session, layout, PERSON_SIDOROV, [("passport", PASSPORT_NUMBER)])
    page = unknown_document_page(PERSON_PRUEBA, candidate_type_name=CV_NAME, title="CV")
    upload = _upload(client, session, ("cv.pdf", make_document_pdf_bytes([page])))
    _process(session, layout, upload, recorded_provider(tmp_path / "kayit", [page]))
    (item,) = session.scalars(select(QueueItem).where(QueueItem.upload_id == upload.id)).all()
    candidate = session.scalars(select(CandidateDocumentType)).one()
    assert (item.kind, candidate.proposed_name) == ("unknown", CV_NAME)
    upload_id, item_id, candidate_id, employee_id = upload.id, item.id, candidate.id, sidorov.id
    # SQLite'ta okuma da yazma kilidini tutar (`app.db.session`): panel isteğinden önce bırakılır.
    session.rollback()

    # 1. İK partiyi açar: satır öğeye ve aday türe bağlı, "Çözüm" yapılacak işi söyler.
    row = _queue_row(client.get(f"/uploads/{upload_id}").text)
    assert f'<a href="/queues/{item_id}">Tür bilinmiyor</a>' in row
    assert "Aday türü onaylayın ya da öğeyi kapatın." in row
    assert f'href="{BASE}/{candidate_id}"' in row
    assert "Bekliyor" not in row

    # 2. Satırdan aday türe gider ve iki aşamalı onayla onaylar.
    assert client.get(f"{BASE}/{candidate_id}").status_code == 200
    first = client.post(f"{BASE}/{candidate_id}/approve/confirm", data=CV_FORM)
    assert first.status_code == 200, first.text
    second = client.post(f"{BASE}/{candidate_id}/approve/prepare", data=_hidden(first.text))
    assert second.status_code == 200, second.text
    approved = client.post(
        f"{BASE}/{candidate_id}/approve", data=_hidden(second.text), follow_redirects=False
    )
    assert approved.status_code == 303, approved.text
    # Onay bekleyen öğeyi çözmez (koddan doğrulandı): bildirim sayıyı ve sonraki adımı söyler.
    assert flashed(approved) == ("catalog.candidate_approved", {"slug": CV_SLUG, "count": 1})
    shown = client.get(approved.headers["location"]).text
    assert toasts(shown) == [
        f"Aday tür standart türler arasına eklendi: {CV_SLUG}. Bağlı bekleyen Unknown öğesi: 1; "
        "öğeler kendiliğinden çözülmez — aşağıdan partilerini yeniden analiz edin."
    ]
    assert session.get_one(QueueItem, item_id).resolved_at is None
    session.rollback()
    assert toasts(client.get(approved.headers["location"]).text) == []
    row = _queue_row(client.get(f"/uploads/{upload_id}").text)
    assert "Aday tür onaylandı: partiyi yeniden analiz edin ya da öğeyi kapatın." in row

    # 3. Bir çalışanı pasife alır; panel dilini Sırpçaya çevirip sayfayı yeniler.
    prepared = client.post(
        f"/employees/{employee_id}/status/prepare", data={"to": "inactive", "reason": ""}
    )
    assert prepared.status_code == 200, prepared.text
    token = _hidden(prepared.text)["confirmation"][0]
    deactivated = client.post(
        f"/employees/{employee_id}/status",
        data={"to": "inactive", "reason": "", "confirmation": token},
        follow_redirects=False,
    )
    assert deactivated.status_code == 303, deactivated.text
    assert flashed(deactivated) == ("employees.status_inactive", {})
    profile = deactivated.headers["location"]
    switched = client.post(
        "/language", data={"language": "sr", "next": profile}, follow_redirects=False
    )
    assert switched.status_code == 303
    # Bildirim dili işlemin değil, gösterildiği isteğin dilidir (10.11.3).
    shown = client.get(profile).text
    assert toasts(shown) == [
        "Zaposleni je deaktiviran; njegovi novi dokumenti neće se raspoređivati automatski."
    ]
    assert toasts(client.get(profile).text) == []
    session.expire_all()
    assert session.get_one(Employee, employee_id).status == "inactive"
    session.rollback()

    # Parti ve kuyruk öğesi Sırpça: ipuçları da seçili dilde.
    detail = client.get(f"/uploads/{upload_id}").text
    assert (
        "Predloženi tip je odobren: ponovo analizirajte seriju ili zatvorite stavku."
        in _queue_row(detail)
    )
    assert not turkish_residue(detail, "sr")
    item_page = client.get(f"/queues/{item_id}").text
    assert "Predloženi koraci" in item_page
    assert (
        "Predloženi tip je odobren: ponovo analizirajte ovu seriju sa stranice predloženog tipa."
        in unescape(item_page)
    )
    assert not turkish_residue(item_page, "sr")

    # 4. Salt okunur Kullanıcı aynı partiyi açar: onay bağlantısı yok, "İK'ya bildirin" var.
    # Dil hesabın tercihidir (10.10.2); Kullanıcı da paneli Sırpça kullanır.
    _sign_in(app, engine, READER_ID)
    assert client.post("/language", data={"language": "sr"}, follow_redirects=False).is_redirect
    reader = client.get(f"/uploads/{upload_id}").text
    assert f"{BASE}/" not in reader
    assert "Čeka odluku HR-a; ako primetite problem, obavestite HR." in _queue_row(reader)
    assert f'<a href="/queues/{item_id}">' in reader
    assert not turkish_residue(reader, "sr")
    reader_item = unescape(client.get(f"/queues/{item_id}").text)
    assert 'id="next-steps-title"' not in reader_item
    assert "Ova stavka čeka odluku HR-a." in reader_item
