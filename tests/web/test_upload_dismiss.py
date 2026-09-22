"""10.3.4 — taramayı yoksay: yükleme detayında iki aşamalı onayla parti listelerden ve kuyruklardan
kalkar; dosya, olay ve üretilmiş çıktı silinmez (K16, §20.6, PLAN.md §C80, §D50).

Parti gerçek boru hattından geçer (`process_upload`, kayıtlı yanıt sağlayıcısı): bir sentetik
pasaport Hazır'a belge üretir, katalogda olmayan bir diploma Unknown kuyruğuna düşer ve aday tür
olarak görülür. Yapay zekâ canlı çağrılmaz. Onay sunucuda sınanır: yalnız birinci onayla gelen
istek hiçbir şey değiştirmez (S16); belirteçsiz, kullanılmış, süresi geçmiş, başka partiye ya da
eski plana ait belirteç 400 (§20.6.2).
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from html import unescape
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.web.confirm as confirm
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    CandidateDocumentType,
    Document,
    DocumentStatus,
    Event,
    KnownDocumentType,
    Plan,
    QueueItem,
    QueueKind,
    QueueResolution,
    Upload,
    UploadStatus,
    utcnow,
)
from app.events import EventType
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE, get_current_user
from app.web.confirm import CONFIRMATION_TEXTS, Operation, second_text
from app.web.routers import upload_page
from app.web.routers.upload_page import (
    CONFIRMATION_REFUSED,
    DISMISSED_MESSAGE,
    dismissal_subject,
)
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    SyntheticPage,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
    unknown_document_page,
)
from tests.web.conftest import SESSION, issue_token

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
USER = "test-yonetici"
DIPLOMA_NAME = "Peruvian Diploma"
# §20.6 "Taramayı yoksay" — birebir.
FIRST_TEXT = "Bu taramayı yoksaymak üzeresiniz. Emin misiniz?"


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    """Onay belirteci oturum çerezinden türetilir; oturum bağımlılığı geçersiz kılındığı için çerez
    testte elle konur."""
    client.cookies.set(SESSION_COOKIE, SESSION)


def _passport(number: str = "00 0000001") -> SyntheticPage:
    return passport_page(PERSON_ORNEKOVA, document_number=number, expiry_date=date(2030, 1, 1))


def _diploma(number: str) -> SyntheticPage:
    return unknown_document_page(
        PERSON_PRUEBA, candidate_type_name=DIPLOMA_NAME, title="DIPLOMA", document_number=number
    )


def _batch(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    directory: Path,
    *,
    passport_number: str = "00 0000001",
    diploma_number: str = "DIP-0000077",
) -> str:
    """Pasaport (Hazır'a belge) ve katalog dışı diploma (Unknown + aday tür) yükler ve gerçek boru
    hattından geçirir; parti kimliğini döner. İkinci parti başka numaralar almalı: aynı baytlar
    tekrar dosyasıdır (01.4.1) ve işlenmez."""
    passport, diploma = [_passport(passport_number)], [_diploma(diploma_number)]
    with session_factory() as session:
        if session.get(KnownDocumentType, "russian_passport") is None:
            import_catalog(session, load_seed_catalog())
            session.commit()
    response = client.post(
        "/api/uploads",
        files=[
            ("files", ("pasaport.pdf", make_document_pdf_bytes(passport), "application/pdf")),
            ("files", ("diploma.pdf", make_document_pdf_bytes(diploma), "application/pdf")),
        ],
    )
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    with session_factory() as session:
        process_upload(
            session,
            layout,
            session.get_one(Upload, upload_id),
            settings=SETTINGS,
            provider=recorded_provider(directory, passport, diploma),
        )
    return upload_id


@pytest.fixture
def batch(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> str:
    upload_id = _batch(client, session_factory, layout, tmp_path / "kayit")
    with session_factory() as session:
        assert session.get_one(Upload, upload_id).status == UploadStatus.DONE
        assert len(session.scalars(select(Document)).all()) == 1
        (item,) = session.scalars(select(QueueItem)).all()
        assert item.kind == QueueKind.UNKNOWN and item.resolved_at is None
    return upload_id


def _token(response_text: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', response_text)
    assert match is not None, response_text
    return match.group(1)


def _prepare(client: TestClient, upload_id: str) -> str:
    response = client.post(f"/uploads/{upload_id}/dismiss/prepare")
    assert response.status_code == 200, response.text
    return _token(response.text)


def _events(session_factory: sessionmaker[Session]) -> list[tuple[int, str]]:
    with session_factory() as session:
        return [(row.id, row.type) for row in session.scalars(select(Event).order_by(Event.id))]


def _state(session_factory: sessionmaker[Session], upload_id: str) -> tuple[object, ...]:
    """Partinin yoksaymayla değişebilecek bütün durumu."""
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        items = session.scalars(select(QueueItem).order_by(QueueItem.id)).all()
        return (
            upload.dismissed_at,
            upload.dismissed_by,
            [(item.resolved_at, item.resolved_by, item.resolution) for item in items],
        )


def _files(layout: DataLayout) -> dict[str, str]:
    """Veri dizinindeki her dosyanın SHA-256'sı (Inbox, sayfa görüntüleri, çıktılar, kuyruk
    kopyaları, `reason.json`)."""
    return {
        path.relative_to(layout.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(layout.root.rglob("*"))
        if path.is_file()
    }


def _tab_counters(html: str) -> dict[str, int]:
    """Kuyruk sekmelerinin başlığındaki bekleyen öğe sayaçları."""
    tabs = re.search(r'<nav class="tabs".*?</nav>', html, re.S)
    assert tabs is not None
    return {
        label: int(count)
        for label, count in re.findall(
            r'>(\w+) <span class="counter" title="Bekleyen öğe">(\d+)</span>', tabs.group(0)
        )
    }


def _queue_rows(html: str) -> list[int]:
    return [int(number) for number in re.findall(r'<td><a href="/queues/(\d+)">', html)]


def _dismiss_step(html: str) -> str | None:
    match = re.search(
        r'<details class="reanalyze dismiss" id="dismiss-step">.*?</details>', html, re.S
    )
    return match.group(0) if match else None


# --- düğme ---------------------------------------------------------------------------------------


def test_the_detail_page_offers_dismiss_next_to_the_other_actions_with_the_first_text(
    client: TestClient, batch: str
) -> None:
    page = client.get(f"/uploads/{batch}")

    step = _dismiss_step(page.text)
    assert step is not None
    assert "<summary>Taramayı yoksay</summary>" in step
    assert f'<p class="confirm-text">{FIRST_TEXT}</p>' in step
    assert CONFIRMATION_TEXTS[Operation.DISMISS].first == FIRST_TEXT
    # Doğrudan tetiklenmez: önce birinci onay, sonra hazırlık isteği; düğmede döner gösterge
    # (`.htmx-request`) HTMX isteği sürerken görünür, düğme kilitlenir.
    assert f'hx-post="/uploads/{batch}/dismiss/prepare"' in step
    assert 'hx-disabled-elt="this"' in step
    assert f'hx-post="/uploads/{batch}/dismiss"' not in page.text
    # Yeniden çalıştır ve yeniden analiz de yanında durur.
    assert 'id="rerun-button"' in page.text and 'id="reanalyze-step"' in page.text
    assert 'id="dismissed-notice"' not in page.text


def test_a_running_batch_offers_no_dismiss_and_its_prepare_is_409(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    content = make_document_pdf_bytes([_passport()])
    upload_id = client.post(
        "/api/uploads", files=[("files", ("a.pdf", content, "application/pdf"))]
    ).json()["upload_id"]
    before = _events(session_factory)

    page = client.get(f"/uploads/{upload_id}")
    prepared = client.post(f"/uploads/{upload_id}/dismiss/prepare")
    dismissed = client.post(f"/uploads/{upload_id}/dismiss", data={"confirmation": "x"})

    assert _dismiss_step(page.text) is None
    assert upload_page.BUSY_MESSAGE in page.text
    assert prepared.status_code == 409
    assert upload_page.DISMISS_BUSY_MESSAGE in prepared.text
    assert dismissed.status_code == 400  # belirteç önce denetlenir
    assert _events(session_factory) == before
    with session_factory() as session:
        assert session.get_one(Upload, upload_id).dismissed_at is None


def test_a_final_batch_without_a_plan_can_still_be_dismissed(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = make_document_pdf_bytes([_passport()])
    upload_id = client.post(
        "/api/uploads", files=[("files", ("a.pdf", content, "application/pdf"))]
    ).json()["upload_id"]
    with session_factory() as session:
        session.get_one(Upload, upload_id).status = UploadStatus.FAILED.value
        session.commit()

    page = client.get(f"/uploads/{upload_id}")
    assert upload_page.NO_PLAN_MESSAGE in page.text
    assert 'id="rerun-button"' not in page.text
    assert _dismiss_step(page.text) is not None

    token = _prepare(client, upload_id)
    response = client.post(f"/uploads/{upload_id}/dismiss", data={"confirmation": token})

    assert response.status_code == 200, response.text
    assert "Tarama yoksayıldı: 0 kuyruk öğesi kapandı; 0 belge yerinde kaldı." in response.text
    assert dismissal_subject(upload_id, None) == f"{upload_id}:none"


def test_an_unknown_batch_is_404(client: TestClient) -> None:
    assert client.post("/uploads/u_yoktur/dismiss/prepare").status_code == 404
    assert client.post("/uploads/u_yoktur/dismiss", data={"confirmation": "x"}).status_code == 404


def test_dismiss_endpoints_need_a_session(app: FastAPI, client: TestClient, batch: str) -> None:
    app.dependency_overrides.pop(get_current_user)

    for path in (f"/uploads/{batch}/dismiss/prepare", f"/uploads/{batch}/dismiss"):
        response = client.post(path, follow_redirects=False)
        assert response.status_code in (303, 401), path


# --- birinci onay: hiçbir şey değişmez (S16) -----------------------------------------------------


def test_prepare_gives_the_section_20_6_second_text_with_counts_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, batch: str
) -> None:
    events, state, files = _events(session_factory), _state(session_factory, batch), _files(layout)

    response = client.post(f"/uploads/{batch}/dismiss/prepare")

    assert response.status_code == 200
    expected = second_text(Operation.DISMISS, queue_items=1, documents=1)
    assert expected == (
        "Parti ve bekleyen 1 kuyruk öğesi listelerden kalkacaktır; üretilmiş 1 belge yerinde "
        "kalır. Son kararınız mı?"
    )
    assert f'<p class="confirm-text" role="alert">{expected}</p>' in response.text
    assert f'hx-post="/uploads/{batch}/dismiss"' in response.text
    assert "Evet, taramayı yoksay" in response.text
    assert _token(response.text)
    assert _events(session_factory) == events
    assert _state(session_factory, batch) == state
    assert _files(layout) == files


# --- belirteç: 400 ve hiçbir şey ------------------------------------------------------------------


def test_a_dismissal_without_a_token_is_400_and_does_nothing(
    client: TestClient, session_factory: sessionmaker[Session], batch: str
) -> None:
    events, state = _events(session_factory), _state(session_factory, batch)

    missing = client.post(f"/uploads/{batch}/dismiss")
    blank = client.post(f"/uploads/{batch}/dismiss", data={"confirmation": ""})
    garbage = client.post(f"/uploads/{batch}/dismiss", data={"confirmation": "x.y"})

    for response in (missing, blank, garbage):
        assert response.status_code == 400
        assert CONFIRMATION_REFUSED in unescape(response.text)
    assert _events(session_factory) == events
    assert _state(session_factory, batch) == state


def test_an_expired_token_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    session_factory: sessionmaker[Session],
    batch: str,
) -> None:
    token = _prepare(client, batch)
    state = _state(session_factory, batch)
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=5)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)

    response = client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token})

    assert response.status_code == 400
    assert _state(session_factory, batch) == state


def test_a_token_works_once(
    client: TestClient, session_factory: sessionmaker[Session], batch: str
) -> None:
    token = _prepare(client, batch)
    assert client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token}).status_code == 200
    events, state = _events(session_factory), _state(session_factory, batch)

    replay = client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token})

    assert replay.status_code == 400
    assert _events(session_factory) == events
    assert _state(session_factory, batch) == state


def test_a_token_is_bound_to_its_batch_its_plan_its_operation_and_its_session(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    batch: str,
) -> None:
    other = _batch(
        client,
        session_factory,
        layout,
        tmp_path / "ikinci",
        passport_number="00 0000002",
        diploma_number="DIP-0000078",
    )
    with session_factory() as session:
        plan_id = session.scalars(select(Plan.id).where(Plan.upload_id == batch)).one()
    other_batch = _prepare(client, other)
    other_session = issue_token(
        session_factory, Operation.DISMISS, dismissal_subject(batch, plan_id), cookie="baska"
    )
    other_operation = issue_token(
        session_factory, Operation.ARCHIVE, dismissal_subject(batch, plan_id)
    )
    stale_plan = _prepare(client, batch)
    with session_factory() as session:
        # Birinci onaydan sonra partiye yeni plan sürümü açıldı: onaylanan sayılar eskidi.
        session.add(Plan(upload_id=batch, version=2, json={}, plan_hash="2" * 64))
        session.commit()
    events, state = _events(session_factory), _state(session_factory, batch)

    for token in (other_batch, other_session, other_operation, stale_plan):
        response = client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token})
        assert response.status_code == 400
    assert _events(session_factory) == events
    assert _state(session_factory, batch) == state


# --- ikinci onay: yoksayma ------------------------------------------------------------------------


def test_a_confirmed_dismissal_closes_the_items_and_logs_the_user_in_one_step(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, batch: str
) -> None:
    token = _prepare(client, batch)
    events_before = _events(session_factory)
    files_before = _files(layout)
    before = utcnow()

    response = client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token})

    assert response.status_code == 200, response.text
    assert "Tarama yoksayıldı: 1 kuyruk öğesi kapandı; 1 belge yerinde kaldı." in response.text
    with session_factory() as session:
        upload = session.get_one(Upload, batch)
        assert upload.dismissed_by == USER
        assert upload.dismissed_at is not None and before <= upload.dismissed_at <= utcnow()
        assert upload.status == UploadStatus.DONE
        (item,) = session.scalars(select(QueueItem)).all()
        assert item.resolved_at == upload.dismissed_at
        assert item.resolved_by == USER
        assert item.resolution == QueueResolution.DISMISSED
        (document,) = session.scalars(select(Document)).all()
        assert document.status == DocumentStatus.ACTIVE
        document_id, item_id = document.id, item.id
        # Onay olayı, ardından işlemin kendi olayı; ikisi de kullanıcı adıyla (§20.6.1).
        new = session.scalars(
            select(Event).where(Event.id > events_before[-1][0]).order_by(Event.id)
        ).all()
        assert [event.type for event in new] == [
            EventType.USER_CONFIRMED,
            EventType.UPLOAD_DISMISSED,
        ]
        confirmed, dismissed = new
        assert confirmed.actor == dismissed.actor == USER
        assert confirmed.upload_id == dismissed.upload_id == batch
        assert confirmed.data_json is not None
        assert confirmed.data_json["operation"] == "dismiss"
        assert confirmed.data_json["target"]["upload_id"] == batch
        assert (
            confirmed.data_json["first_confirmed_at"] <= confirmed.data_json["second_confirmed_at"]
        )
        assert dismissed.data_json == {
            "queue_item_ids": [item_id],
            "active_document_ids": [document_id],
        }
    # Silme yok: önceki olaylar yerinde, dosya sistemi bayt bayt aynı (Inbox, sayfa görüntüleri,
    # Hazır'daki çıktı, Unknown kopyası ve reason.json).
    assert _events(session_factory)[: len(events_before)] == events_before
    assert _files(layout) == files_before
    assert any(path.startswith("Inbox/") for path in files_before)
    assert any(path.startswith("cache/pages/") for path in files_before)
    assert any(path.startswith("Unknown/") for path in files_before)


def test_the_dismissed_batch_leaves_the_lists_and_the_queues_but_opens_by_address(
    client: TestClient, session_factory: sessionmaker[Session], batch: str
) -> None:
    with session_factory() as session:
        item_id = session.scalars(select(QueueItem.id)).one()
    assert f'href="/uploads/{batch}"' in client.get("/uploads").text
    open_before = client.get("/queues?tab=unknown").text
    assert _queue_rows(open_before) == [item_id]
    assert _tab_counters(open_before)["Unknown"] == 1
    assert DIPLOMA_NAME in client.get("/document-types/candidate-types").text

    token = _prepare(client, batch)
    assert client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token}).status_code == 200

    # Yükleme listesi: varsayılan gizli, süzgeçte görünür ve işaretli.
    assert f'href="/uploads/{batch}"' not in client.get("/uploads").text
    only = client.get("/uploads?dismissed=only").text
    assert f'href="/uploads/{batch}"' in only and "Yoksayıldı" in only
    assert f'href="/uploads/{batch}"' in client.get("/uploads?dismissed=include").text
    # Kuyruklar: öğe ne bekleyenlerde ne çözülenlerde; sayaçlar düşer.
    for state in ("open", "resolved", "superseded"):
        listing = client.get(f"/queues?tab=unknown&state={state}").text
        assert _queue_rows(listing) == [], state
        assert _tab_counters(listing)["Unknown"] == 0, state
    # Aday tür: tek görülmesi yoksayılan partideydi, bekleyenlerden kalkar.
    assert DIPLOMA_NAME not in client.get("/document-types/candidate-types").text
    with session_factory() as session:
        candidate = session.scalars(select(CandidateDocumentType)).one()
        assert candidate.seen_count == 1  # kayıt değişmez, yalnız gösterim süzülür
    # Detay adresle açılır: bildirim var, işlem düğmesi yok.
    page = client.get(f"/uploads/{batch}")
    assert page.status_code == 200
    notice = re.search(
        r'<p class="notice" id="dismissed-notice" role="status">(.*?)</p>', page.text
    )
    assert notice is not None
    assert re.fullmatch(
        rf"Bu tarama \d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d UTC tarihinde {USER} tarafından yoksayıldı\.",
        notice.group(1),
    )
    assert 'id="rerun-button"' not in page.text
    assert 'id="reanalyze-step"' not in page.text
    assert _dismiss_step(page.text) is None
    assert DISMISSED_MESSAGE in page.text
    # Kuyruk öğesi de adresle açılır ve nasıl kapandığını söyler.
    assert "tarama yoksayıldı" in client.get(f"/queues/{item_id}").text
    assert "tarama yoksayıldı" in page.text


def test_queue_counters_drop_the_dismissed_batch_only(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    batch: str,
) -> None:
    kept = _batch(
        client,
        session_factory,
        layout,
        tmp_path / "ikinci",
        passport_number="00 0000002",
        diploma_number="DIP-0000078",
    )
    with session_factory() as session:
        kept_item = session.scalars(select(QueueItem.id).where(QueueItem.upload_id == kept)).one()

    token = _prepare(client, batch)
    assert client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token}).status_code == 200

    listing = client.get("/queues?tab=unknown").text
    assert _queue_rows(listing) == [kept_item]
    assert _tab_counters(listing) == {"Unknown": 1, "Unreadable": 0, "Unresolved": 0}
    rows = client.get("/uploads").text
    assert f'href="/uploads/{kept}"' in rows and f'href="/uploads/{batch}"' not in rows


def test_a_dismissed_batch_is_neither_rerun_nor_reanalyzed_nor_dismissed_again(
    client: TestClient, session_factory: sessionmaker[Session], batch: str
) -> None:
    token = _prepare(client, batch)
    assert client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token}).status_code == 200
    events, state = _events(session_factory), _state(session_factory, batch)

    responses = [
        client.post(f"/uploads/{batch}/rerun"),
        client.post(f"/uploads/{batch}/reanalyze/prepare"),
        client.post(f"/uploads/{batch}/dismiss/prepare"),
        client.post(f"/api/uploads/{batch}/rerun"),
        client.post(f"/api/uploads/{batch}/reanalyze"),
    ]

    for response in responses:
        assert response.status_code == 409, response.text
        assert DISMISSED_MESSAGE in unescape(response.text)
    assert _events(session_factory) == events
    assert _state(session_factory, batch) == state


def test_a_valid_token_on_an_already_dismissed_batch_is_409_and_stays_unused(
    client: TestClient, session_factory: sessionmaker[Session], batch: str
) -> None:
    first, second = _prepare(client, batch), _prepare(client, batch)
    assert client.post(f"/uploads/{batch}/dismiss", data={"confirmation": first}).status_code == 200
    events = _events(session_factory)

    response = client.post(f"/uploads/{batch}/dismiss", data={"confirmation": second})

    assert response.status_code == 409
    assert DISMISSED_MESSAGE in unescape(response.text)
    assert _events(session_factory) == events  # USER_CONFIRMED geri alındı


def test_the_same_file_is_still_detected_as_a_duplicate_after_dismissal(
    client: TestClient, session_factory: sessionmaker[Session], batch: str
) -> None:
    token = _prepare(client, batch)
    assert client.post(f"/uploads/{batch}/dismiss", data={"confirmation": token}).status_code == 200

    again = client.post(
        "/api/uploads",
        files=[("files", ("yine.pdf", make_document_pdf_bytes([_passport()]), "application/pdf"))],
    )

    status = client.get(f"/api/uploads/{again.json()['upload_id']}").json()
    assert [file["is_duplicate"] for file in status["files"]] == [True]
