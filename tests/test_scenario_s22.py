"""09.3 — PRD §9 kabul senaryosu S22 uçtan uca: pasif çalışanın pasaport numarasıyla yeni belge
geliyor (10.5.7; PLAN.md §C90-b, §D61).

Beklenen: belge çalışanın klasörüne otomatik girmez; Unresolved'da "pasif çalışan" gerekçesiyle
bekler (kod `inactive_employee` + E numarası, çalışan kişi tahmini); çalışan etkinleştirilip öğe
atanınca Hazir'a girer. İkinci test aynı partinin öbür çıkışını sınar: etkinleştirmeden sonra
yeniden çalıştırma (06.6.1, S18) donmuş planı uygular ve belge yine yerleşmez; yeniden analiz
(06.6.2, K18) yeni planla Hazir'a koyar.

Senaryo gerçek yoldan geçer: pasife alma ve etkinleştirme profilin iki aşamalı onayıyla
(`/employees/{id}/status/prepare` → `/status`), atama kuyruk öğesinin iki aşamalı onayıyla
(`/queues/{id}/assign/prepare` → `/assign`) yapılır; parti yükleme uç noktasıyla açılır ve
`process_upload` ile render → analiz → plan → uygulama adımlarından geçer. Ortam ve yardımcılar
S1–S5'inkilerdir. Yapay zekâ canlı çağrılmaz (kayıtlı yanıt); belge ve kişi sentetiktir, gerçek
kimlik belgesi yoktur (CONVENTIONS §6).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Employee, Event, Plan, QueueItem, QueueKind
from app.events import EventType
from app.pipeline.plan import Route, read_plan
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    SyntheticPage,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.test_scenarios_s01_s05 import (
    ORNEKOVA_FOLDER,
    PASSPORT_NUMBER,
    PASSPORT_OUTPUT,
    SIGNED_IN,
    _names,
    _process,
    _register_employee,
    _upload,
)
from tests.test_scenarios_s11_s18 import _use_provider

# Ortam fikstürleri S1–S5'inkilerdir; pytest onları bu modüldeki adlarından bulur.
engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client

# Onay belirteci oturum çerezine bağlıdır (10.8.1); oturum bağımlılığı senaryoda geçersiz kılındığı
# için çerez elle konur.
COOKIE = "s22-oturum"


def _passport() -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1)
    )


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _set_status(client: TestClient, employee_id: str, to: str) -> None:
    """Profilin iki aşamalı onayı: birinci metin, hazırlık (belirteç), asıl istek."""
    first = client.get(f"/employees/{employee_id}/status/confirm?to={to}")
    assert first.status_code == 200, first.text
    prepared = client.post(f"/employees/{employee_id}/status/prepare", data={"to": to})
    assert prepared.status_code == 200, prepared.text
    done = client.post(
        f"/employees/{employee_id}/status",
        data={"to": to, "confirmation": _token(prepared.text)},
        follow_redirects=False,
    )
    assert done.status_code == 303, done.text


def _status(session: Session, employee_id: str) -> str:
    session.expire_all()
    status = session.get_one(Employee, employee_id).status
    session.rollback()
    return status


def _documents(session: Session) -> list[tuple[str, str, str]]:
    session.expire_all()
    rows = [
        (document.employee_id, Path(document.path).name, document.status)
        for document in session.scalars(select(Document).order_by(Document.id))
    ]
    session.rollback()
    return rows


def _deactivated_upload(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> tuple[str, str]:
    """Kayıtlı Ornekova pasife alınır, pasaportu yüklenir ve işlenir: (çalışan, parti)."""
    client.cookies.set(SESSION_COOKIE, COOKIE)
    employee_id = _register_employee(
        session, layout, PERSON_ORNEKOVA, [("russian_passport", PASSPORT_NUMBER)]
    ).id
    session.commit()
    _set_status(client, employee_id, "inactive")
    assert _status(session, employee_id) == "inactive"

    passport = _passport()
    upload = _upload(client, session, ("pasaport.pdf", make_document_pdf_bytes([passport])))
    _process(session, layout, upload, recorded_provider(tmp_path / "kayit-1", [passport]))
    upload_id = upload.id
    session.commit()
    return employee_id, upload_id


def _assert_waits_in_unresolved(
    session: Session, layout: DataLayout, employee_id: str, upload_id: str
) -> int:
    """Kuyruk öğesinin kimliği; okuma işlemi bırakılır (SQLite yazma kilidi panel isteğini
    bekletmesin)."""
    # Belge klasöre girmedi: çıktı yok, Hazir boş; Unresolved'da pasif gerekçesiyle bekliyor.
    assert _documents(session) == []
    assert _names(layout.ready_dir(ORNEKOVA_FOLDER)) == []
    session.expire_all()
    (queued,) = session.scalars(select(QueueItem).where(QueueItem.upload_id == upload_id)).all()
    assert queued.kind == QueueKind.UNRESOLVED.value
    assert queued.reason.startswith(
        f"Pasif çalışan ({employee_id}) ile eşleşti (inactive_employee)"
    )
    assert queued.payload_json["employee_guess"] == {
        "action": "match",
        "employee_id": employee_id,
        "matched_by": "document_number",
    }
    assert queued.resolved_at is None
    # Eşleştirme kimliği yine buldu (olay), ama klasöre bir şey yazılmadı.
    matched = session.scalars(
        select(Event).where(
            Event.upload_id == upload_id, Event.type == EventType.PERSON_MATCHED.value
        )
    ).all()
    assert [event.employee_id for event in matched] == [employee_id]
    item_id = queued.id
    session.rollback()
    return item_id


def test_s22_inactive_employees_document_waits_in_unresolved_until_reactivated_and_assigned(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee_id, upload_id = _deactivated_upload(session, layout, client, tmp_path)

    item_id = _assert_waits_in_unresolved(session, layout, employee_id, upload_id)

    # Öğe detayı pasif çalışanı söyler ve profile bağlanır.
    page = client.get(f"/queues/{item_id}").text
    notice = page.split('<p class="notice inactive-notice" role="status">', 1)[1].split("</p>")[0]
    assert "Pasif çalışan" in notice and f'href="/employees/{employee_id}"' in notice
    assert "atayın ya da çalışanı etkinleştirin" in notice

    # İK çalışanı etkinleştirir: bekleyen öğe kendiliğinden yerleşmez (plan donmuş, K9).
    _set_status(client, employee_id, "active")
    assert _status(session, employee_id) == "active"
    assert _documents(session) == []

    # İK öğeyi çalışana atar (iki aşamalı onay): belge Hazir'a girer.
    prepared = client.post(f"/queues/{item_id}/assign/prepare", data={"employee_id": employee_id})
    assert prepared.status_code == 200, prepared.text
    assigned = client.post(
        f"/queues/{item_id}/assign",
        data={"employee_id": employee_id, "confirmation": _token(prepared.text)},
    )
    assert assigned.status_code == 200, assigned.text

    assert _documents(session) == [(employee_id, PASSPORT_OUTPUT, "active")]
    assert _names(layout.ready_dir(ORNEKOVA_FOLDER)) == [PASSPORT_OUTPUT]
    session.expire_all()
    resolved = session.get_one(QueueItem, item_id)
    assert resolved.resolved_by == SIGNED_IN.username
    kinds = [
        event.type
        for event in session.scalars(
            select(Event)
            .where(
                Event.employee_id == employee_id,
                Event.type.in_(
                    [EventType.EMPLOYEE_DEACTIVATED.value, EventType.EMPLOYEE_REACTIVATED.value]
                ),
            )
            .order_by(Event.id)
        )
    ]
    assert kinds == ["EMPLOYEE_DEACTIVATED", "EMPLOYEE_REACTIVATED"]
    session.rollback()


def test_s22_after_reactivation_a_rerun_keeps_the_frozen_plan_and_a_reanalysis_places_it(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee_id, upload_id = _deactivated_upload(session, layout, client, tmp_path)
    _assert_waits_in_unresolved(session, layout, employee_id, upload_id)
    _set_status(client, employee_id, "active")

    # S18: yeniden çalıştırma aynı planı uygular — plan pasif hükmüyle donmuştur, belge yerleşmez.
    rerun = client.post(f"/api/uploads/{upload_id}/rerun")
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["version"] == 1
    assert _documents(session) == []

    # Yeniden analiz yeni plan sürümü açar; çalışan artık etkin olduğu için belge Hazir'a girer.
    passport = _passport()
    _use_provider(client, recorded_provider(tmp_path / "kayit-2", [passport]))
    reanalyzed = client.post(f"/api/uploads/{upload_id}/reanalyze")
    assert reanalyzed.status_code == 200, reanalyzed.text
    assert reanalyzed.json()["version"] == 2

    assert _documents(session) == [(employee_id, PASSPORT_OUTPUT, "active")]
    assert _names(layout.ready_dir(ORNEKOVA_FOLDER)) == [PASSPORT_OUTPUT]
    session.expire_all()
    plans = sorted(
        session.scalars(select(QueueItem.plan_id).where(QueueItem.upload_id == upload_id)).all()
    )
    assert len(plans) == 1  # yeni sürüm kuyruğa öğe açmadı
    latest = session.scalars(
        select(Plan).where(Plan.upload_id == upload_id).order_by(Plan.version.desc())
    ).first()
    assert latest is not None
    (item,) = read_plan(latest).items
    assert (item.route, item.employee.employee_id) == (Route.READY, employee_id)
    session.rollback()
