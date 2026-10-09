"""09.3 — PRD §9 kabul senaryosu S26 uçtan uca: süren parti iptal ediliyor (10.3.6, 10.3.7;
PLAN.md §D114).

Beklenen: tek onayla değişiklik yok / iki onayla parti `cancelled`, işi kuyruktan düşer, Inbox
dosyası, sayfalar, plan ve belgeler yerinde, `UPLOAD_CANCELLED` kullanıcı adıyla; 10 dakikayı aşan
parti kendiliğinden `cancelled` olur (`reason = timeout`, `actor` sistem), 10 dakikayı aşmamış parti
ve son durumdaki parti dokunulmaz; çalışan işleyici iptalden sonra partiye yazmaz (parti
`cancelled` kalır, `failed` olmaz); aynı dosya tekrar yüklenince tekrar sayılmaz, yeniden işlenir.

Kurgu: işleyici kapalıdır (§D114 a) — partiler `POST /api/uploads` ile açılır ve `received`'da
bekler. Elle iptal edilen parti önce planına kadar işlenmiş, uygulama adımında süreç durmuştur
(`executing`: sayfa görüntüsü ve plan commit edilmiş). Otomatik iptalin saati panelin `get_clock`
bağımlılığıyla verilir. Adımın ortasındaki iptal gerçek işleyici işlevi (`run_claimed_upload`)
üzerinden, iptal paneldeki iki onayla yapılarak sınanır. Yapay zekâ canlı çağrılmaz (kayıtlı
yanıt); belge ve kişi sentetiktir (CONVENTIONS §6). Ortam S1–S5'inkidir.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import Catalog
from app.db.models import (
    Document,
    Event,
    JobStatus,
    Page,
    Plan,
    Upload,
    UploadJob,
    UploadStatus,
)
from app.db.session import create_session_factory
from app.events import EventType
from app.pipeline import orchestrate
from app.pipeline.orchestrate import ProcessingWithdrawn, process_upload
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE
from app.web.routers.upload_page import get_clock
from app.worker import claim_upload, run_claimed_upload
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    SyntheticPage,
    SyntheticPerson,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.test_scenarios_s01_s05 import SETTINGS, SIGNED_IN, _upload

engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client

COOKIE = "s26-oturum"
BASE = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
FIRST = "Bu partiyi iptal etmek üzeresiniz. Emin misiniz?"
SECOND = (
    "Partinin işlenmesi durdurulacak; dosyalar ve o ana kadar üretilen belgeler silinmez. İptal "
    "geri alınamaz ama dosyalar yeniden yüklenebilir. Son kararınız mı?"
)


def _passport(person: SyntheticPerson, number: str) -> SyntheticPage:
    return passport_page(person, document_number=number, expiry_date=date(2031, 1, 1))


def _open(client: TestClient, session: Session, name: str, content: bytes) -> str:
    """Partiyi yükleme uç noktasıyla açar; işleyici yok, parti `received`'da bekler."""
    upload_id = _upload(client, session, (name, content)).id
    session.rollback()  # SQLite: okuma işlemi yazma kilidini tutmasın
    return upload_id


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _cancel(client: TestClient, upload_id: str) -> None:
    token = _token(client.post(f"/uploads/{upload_id}/cancel/prepare").text)
    response = client.post(f"/uploads/{upload_id}/cancel", data={"confirmation": token})
    assert response.status_code == 200, response.text


def _state(reader: sessionmaker[Session], upload_id: str) -> tuple[str, str]:
    with reader() as db:
        job = db.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        return db.get_one(Upload, upload_id).status, job.status


def _cancellations(reader: sessionmaker[Session]) -> list[tuple[str | None, str, dict]]:
    with reader() as db:
        return [
            (event.upload_id, event.actor, dict(event.data_json or {}))
            for event in db.scalars(
                select(Event)
                .where(Event.type == EventType.UPLOAD_CANCELLED.value)
                .order_by(Event.id)
            )
        ]


def _kept(reader: sessionmaker[Session], upload_id: str) -> tuple[list[int], list[str]]:
    """Partinin planları ve sayfa görüntüleri."""
    with reader() as db:
        plans = list(db.scalars(select(Plan.id).where(Plan.upload_id == upload_id)))
        images = list(db.scalars(select(Page.image_path).where(Page.image_path.is_not(None))))
        return plans, images


def _files(layout: DataLayout) -> dict[str, str]:
    return {
        path.relative_to(layout.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(layout.root.rglob("*"))
        if path.is_file()
    }


def _set_clock(client: TestClient, moment: datetime) -> None:
    client.app.dependency_overrides[get_clock] = lambda: moment  # type: ignore[attr-defined]


def _stop_at_the_end(_session: Session, status: UploadStatus) -> None:
    # Süreç uygulama adımının sonunda durdu: `executing` ve plan commit edildi, çıktı geri alındı.
    if status in (UploadStatus.DONE, UploadStatus.PARTIAL):
        raise ProcessingWithdrawn("süreç durdu")


def test_s26_a_running_batch_is_cancelled_by_hand_by_the_system_and_under_a_worker(
    client: TestClient,
    session: Session,
    engine: Engine,
    layout: DataLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.cookies.set(SESSION_COOKIE, COOKIE)
    reader = create_session_factory(engine)
    page = _passport(PERSON_ORNEKOVA, "00 0000261")
    content = make_document_pdf_bytes([page])

    # --- elle iptal: planına kadar işlenmiş, `executing`'de kalmış parti ------------------------
    stuck = _open(client, session, "pasaport.pdf", content)
    with reader() as db, pytest.raises(ProcessingWithdrawn):
        process_upload(
            db,
            layout,
            db.get_one(Upload, stuck),
            settings=SETTINGS,
            provider=recorded_provider(tmp_path / "kayit-1", [page]),
            checkpoint=_stop_at_the_end,
        )
    assert _state(reader, stuck) == (UploadStatus.EXECUTING, JobStatus.QUEUED)
    plans, images = _kept(reader, stuck)
    assert len(plans) == 1 and len(images) == 1
    files = _files(layout)

    detail = client.get(f"/uploads/{stuck}")
    assert FIRST in detail.text and "Partiyi iptal et" in detail.text
    prepared = client.post(f"/uploads/{stuck}/cancel/prepare")
    assert SECOND in prepared.text
    one_step = client.post(f"/uploads/{stuck}/cancel")  # tek onay: belirteç yok
    assert one_step.status_code == 400
    assert _state(reader, stuck) == (UploadStatus.EXECUTING, JobStatus.QUEUED)
    assert _cancellations(reader) == []

    done = client.post(f"/uploads/{stuck}/cancel", data={"confirmation": _token(prepared.text)})

    assert done.status_code == 200
    assert _state(reader, stuck) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
    ((upload_id, actor, data),) = _cancellations(reader)
    assert (upload_id, actor, data["reason"], data["stage"]) == (
        stuck,
        SIGNED_IN.username,
        "manual",
        "executing",
    )
    assert _files(layout) == files  # Inbox ve sayfa görüntüsü: hiçbir şey silinmez (K10)
    assert _kept(reader, stuck) == (plans, images)
    assert "tarafından iptal edildi" in client.get(f"/uploads/{stuck}").text

    # --- otomatik iptal: işleyici kapalı, 10 dakikayı aşan parti ---------------------------------
    old = _open(client, session, "a.pdf", make_document_pdf_bytes([_passport(PERSON_SIDOROV, "1")]))
    young = _open(
        client, session, "b.pdf", make_document_pdf_bytes([_passport(PERSON_SIDOROV, "2")])
    )
    ended = _open(
        client, session, "c.pdf", make_document_pdf_bytes([_passport(PERSON_SIDOROV, "3")])
    )
    with reader() as db:
        for upload_id, created in (
            (old, BASE),
            (young, BASE + timedelta(seconds=2)),
            (ended, BASE),
        ):
            db.execute(update(Upload).where(Upload.id == upload_id).values(created_at=created))
        db.execute(update(Upload).where(Upload.id == ended).values(status="done"))
        db.commit()

    _set_clock(client, BASE + timedelta(minutes=10, seconds=1))
    assert client.get("/uploads").status_code == 200

    assert _state(reader, old) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
    assert _state(reader, young) == (UploadStatus.RECEIVED, JobStatus.QUEUED)  # 9 dk 59 sn
    assert _state(reader, ended)[0] == UploadStatus.DONE
    upload_id, actor, data = _cancellations(reader)[-1]
    assert (upload_id, actor, data["reason"]) == (old, "system", "timeout")
    assert "10 dakikada tamamlanamadığı için" in client.get(f"/uploads/{old}").text

    # --- işleyici adımın ortasındayken iptal ------------------------------------------------------
    with reader() as db:
        claim = claim_upload(db, young, token="isleyici", lease_seconds=60)
        db.commit()
    assert claim is not None
    real_export = orchestrate.export_catalog

    def export_after_cancel(worker_session: Session) -> Catalog:
        # `analyzing` commit edildi, analiz başlıyor: İK partiyi panelden iki onayla iptal eder.
        _cancel(client, young)
        return real_export(worker_session)

    monkeypatch.setattr(orchestrate, "export_catalog", export_after_cancel)
    result = run_claimed_upload(
        reader,
        layout,
        claim,
        settings=SETTINGS,
        provider=recorded_provider(tmp_path / "kayit-2", [_passport(PERSON_SIDOROV, "2")]),
    )
    monkeypatch.undo()

    assert result is None
    assert _state(reader, young) == (UploadStatus.CANCELLED, JobStatus.CANCELLED)
    with reader() as db:
        failures = db.scalars(
            select(Event.id).where(Event.type == EventType.PIPELINE_FAILED.value)
        ).all()
        assert failures == []

    # --- aynı dosya yeniden yükleniyor: tekrar sayılmaz, yeniden işlenir --------------------------
    again = _open(client, session, "pasaport.pdf", content)
    assert client.get(f"/api/uploads/{again}").json()["files"][0]["is_duplicate"] is False
    with reader() as db:
        result = process_upload(
            db,
            layout,
            db.get_one(Upload, again),
            settings=SETTINGS,
            provider=recorded_provider(tmp_path / "kayit-3", [page]),
        )
        assert result.status is UploadStatus.DONE and result.plan is not None
        (document,) = db.scalars(select(Document).where(Document.plan_id == result.plan.id)).all()
        assert document.status == "active"
