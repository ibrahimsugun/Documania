"""10.7.1 — kuyruk ekranları: üç sekme, sayaçlar, öğe detayı ve sayfa görüntüleri.

Uçtan uca sınama gerçek boru hattından geçen bir partiyle yapılır (`process_upload`, kayıtlı yanıt
sağlayıcısı; canlı yapay zekâ çağrısı yok): bulanık numaralı sentetik pasaport Unreadable'a düşer,
sayfa görüntüsü gerçekten üretilir. Durum kuralları (bekleyen / çözülen / eski sürüm), sayfalama ve
bozuk kayıt biçimleri elle yazılan sentetik satırlarla sınanır. Gerçek kimlik belgesi kullanılmaz.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    Employee,
    Event,
    Page,
    Plan,
    QueueItem,
    QueueKind,
    Upload,
    UploadFile,
    utcnow,
)
from app.events import EventType
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout
from app.web.auth import get_current_user
from app.web.routers.queue import (
    CORRUPT_SOURCE,
    PAGE_SIZE,
    QUEUE_ITEM_NOT_FOUND,
    SUPERSEDED_NOTE,
    get_confirmed_actor,
)
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.web.test_queue import ACTOR, TARGET
from tests.web.test_queue import _queued_item as _pipeline_queued_item

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
PASSPORT = "russian_passport"
UPLOAD_ID = "u_kuyruk1"
UNREADABLE_REASON = "Okunamayan alanlar: document_number"
UNREADABLE_NOTES = (
    "Belge numarası ve MRZ bölgesi bulanık, karakterler seçilemiyor. Karşılanmayan kabul "
    "kriteri: MRZ iki satırı da okunabilir olmalı"
)


def _tab_counters(html: str) -> dict[str, int]:
    """Sekme başlığındaki sayaçlar: `{"Unknown": 2, ...}`."""
    tabs = re.search(r'<nav class="tabs".*?</nav>', html, re.S)
    assert tabs is not None
    return {
        label: int(count)
        for label, count in re.findall(
            r'>(\w+) <span class="counter" title="Bekleyen öğe">(\d+)</span>', tabs.group(0)
        )
    }


def _state_counts(html: str) -> dict[str, int]:
    states = re.search(r'<nav class="states".*?</nav>', html, re.S)
    assert states is not None
    return {
        label: int(count)
        for label, count in re.findall(r">([^<>]+?) \((\d+)\)</a>", states.group(0))
    }


def _row_ids(html: str) -> list[int]:
    """Listedeki öğe numaraları, sayfadaki sırayla."""
    return [int(number) for number in re.findall(r'<td><a href="/queues/(\d+)">', html)]


def _section(html: str, name: str) -> str:
    match = re.search(rf'<section id="{name}".*?</section>', html, re.S)
    assert match is not None, name
    return match.group(0)


# --- sentetik veri -----------------------------------------------------------------------------


def _upload(session: Session, upload_id: str = UPLOAD_ID) -> Upload:
    upload = Upload(id=upload_id, channel="web")
    session.add(upload)
    session.flush()
    return upload


def _plan(session: Session, upload: Upload, version: int) -> Plan:
    plan = Plan(upload_id=upload.id, version=version, json={}, plan_hash=f"{upload.id}-{version}")
    session.add(plan)
    session.flush()
    return plan


def _source_file(session: Session, upload: Upload, name: str, page_count: int = 2) -> UploadFile:
    upload_file = UploadFile(
        upload_id=upload.id,
        original_name=name,
        stored_path=f"Inbox/{upload.id}/{name}",
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        mime="application/pdf",
        page_count=page_count,
    )
    session.add(upload_file)
    session.flush()
    for index in range(page_count):
        session.add(
            Page(
                file_id=upload_file.id,
                index=index,
                image_path=f"cache/pages/{upload_file.id}-{index}.png",
            )
        )
    session.flush()
    return upload_file


def _payload(
    file_id: int,
    pages: list[int],
    *,
    slug: str | None = None,
    guess: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "document_type_slug": slug,
        "sources": [{"file_id": file_id, "pages": pages}],
        "employee_guess": guess or {"action": "none", "employee_id": None, "matched_by": None},
    }


def _queue_item(
    session: Session,
    upload: Upload,
    plan: Plan | None,
    kind: QueueKind,
    *,
    item_id: str = "i1",
    reason: str = "Sentetik gerekçe",
    payload: Any = None,
    resolved_by: str | None = None,
) -> QueueItem:
    row = QueueItem(
        upload_id=upload.id,
        plan_id=plan.id if plan is not None else None,
        plan_item_id=item_id,
        kind=kind.value,
        reason=reason,
        payload_json=payload,
        resolved_at=utcnow() if resolved_by is not None else None,
        resolved_by=resolved_by,
    )
    session.add(row)
    session.flush()
    return row


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


# --- sekmeler ve sayaçlar ----------------------------------------------------------------------


def test_three_tabs_with_zero_counters_when_nothing_is_queued(client: TestClient) -> None:
    response = client.get("/queues")

    assert response.status_code == 200
    html = response.text
    assert "<h1>Kuyruklar</h1>" in html
    assert _tab_counters(html) == {"Unknown": 0, "Unreadable": 0, "Unresolved": 0}
    # Kuyruklar menüsü etkin, ilk sekme (Unknown) açık.
    assert re.search(r'<a href="/queues" class="active" aria-current="page">Kuyruklar</a>', html)
    assert re.search(
        r'<a href="/queues\?tab=unknown" class="active" aria-current="page">Unknown', html
    )
    assert "Unknown kuyruğunda bekleyen öğe yok." in html
    assert "henüz hazır değil" not in html  # 10.1'in yer tutucusu değil, gerçek ekran


def test_counters_count_only_open_items_of_the_current_plan(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        first = _upload(session, "u_kuyruk1")
        old_plan, new_plan = _plan(session, first, 1), _plan(session, first, 2)
        second = _upload(session, "u_kuyruk2")
        only_plan = _plan(session, second, 1)
        # Unknown: iki bekleyen (biri başka partide), bir çözülen, iki eski sürüm (biri plansız).
        _queue_item(session, first, new_plan, QueueKind.UNKNOWN, item_id="i1")
        _queue_item(session, second, only_plan, QueueKind.UNKNOWN, item_id="i1")
        _queue_item(
            session, first, new_plan, QueueKind.UNKNOWN, item_id="i2", resolved_by="ik.ayse"
        )
        _queue_item(session, first, old_plan, QueueKind.UNKNOWN, item_id="i3")
        _queue_item(session, first, None, QueueKind.UNKNOWN, item_id="i4")
        # Unreadable: bir bekleyen; eski sürümde çözülmüş öğe çözülen sayılır (eski sürüm değil).
        _queue_item(session, first, new_plan, QueueKind.UNREADABLE, item_id="i5")
        _queue_item(
            session, first, old_plan, QueueKind.UNREADABLE, item_id="i6", resolved_by="ik.ayse"
        )
        session.commit()

    unknown = client.get("/queues?tab=unknown").text

    assert _tab_counters(unknown) == {"Unknown": 2, "Unreadable": 1, "Unresolved": 0}
    assert _state_counts(unknown) == {"Bekleyen": 2, "Çözülen": 1, "Eski sürüm": 2}
    unreadable = client.get("/queues?tab=unreadable").text
    assert _tab_counters(unreadable) == {"Unknown": 2, "Unreadable": 1, "Unresolved": 0}
    assert re.search(r"Bekleyen \(1\)", unreadable) and re.search(r"Çözülen \(1\)", unreadable)
    assert "Eski sürüm (0)" in unreadable


def test_tab_lists_only_its_own_kind_in_queue_order_and_filters_by_state(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        old_plan, plan = _plan(session, upload, 1), _plan(session, upload, 2)
        ids = {
            "open_first": _queue_item(session, upload, plan, QueueKind.UNRESOLVED, item_id="i1").id,
            "open_second": _queue_item(
                session, upload, plan, QueueKind.UNRESOLVED, item_id="i2"
            ).id,
            "resolved_old": _queue_item(
                session, upload, plan, QueueKind.UNRESOLVED, item_id="i3", resolved_by="ik.ayse"
            ).id,
            "resolved_new": _queue_item(
                session, upload, plan, QueueKind.UNRESOLVED, item_id="i4", resolved_by="ik.veli"
            ).id,
            "resolved_third": _queue_item(
                session, upload, plan, QueueKind.UNRESOLVED, item_id="i8", resolved_by="ik.veli"
            ).id,
            "stale_old": _queue_item(
                session, upload, old_plan, QueueKind.UNRESOLVED, item_id="i5"
            ).id,
            "stale_new": _queue_item(
                session, upload, old_plan, QueueKind.UNRESOLVED, item_id="i6"
            ).id,
            "other_kind": _queue_item(session, upload, plan, QueueKind.UNKNOWN, item_id="i7").id,
        }
        session.commit()

    opened = client.get("/queues?tab=unresolved").text
    resolved = client.get("/queues?tab=unresolved&state=resolved").text
    stale = client.get("/queues?tab=unresolved&state=superseded").text

    assert _row_ids(opened) == [
        ids["open_first"],
        ids["open_second"],
    ]  # kuyruk sırası: eskiden yeniye
    assert _row_ids(resolved) == [ids["resolved_third"], ids["resolved_new"], ids["resolved_old"]]
    assert _row_ids(stale) == [ids["stale_new"], ids["stale_old"]]
    # Sekme sayaçları hangi durum açık olursa olsun bekleyen öğeleri sayar.
    for page in (opened, resolved, stale):
        assert _tab_counters(page) == {"Unknown": 1, "Unreadable": 0, "Unresolved": 2}
    assert _state_counts(resolved) == {"Bekleyen": 2, "Çözülen": 3, "Eski sürüm": 2}
    assert ids["other_kind"] not in _row_ids(opened + resolved + stale)
    assert "<th>Çözüldü</th>" in resolved and "<th>Çözüldü</th>" not in opened
    assert "ik.veli" in resolved and "ik.ayse" in resolved
    assert re.search(r'class="active" aria-current="page">Unresolved', opened)
    assert re.search(
        r'<a href="/queues\?tab=unresolved&amp;state=resolved" class="active"', resolved
    )


def test_empty_state_names_the_queue_and_the_state(client: TestClient) -> None:
    html = client.get("/queues?tab=unreadable&state=resolved").text

    assert "Unreadable kuyruğunda çözülen öğe yok." in html


def test_invalid_tab_state_or_page_is_rejected(client: TestClient) -> None:
    assert client.get("/queues?tab=archive").status_code == 422
    assert client.get("/queues?tab=unknown&state=deleted").status_code == 422
    assert client.get("/queues?page=0").status_code == 422


def test_listing_is_paged_and_an_out_of_range_page_lands_on_the_last_one(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        plan = _plan(session, upload, 1)
        created = [
            _queue_item(session, upload, plan, QueueKind.UNKNOWN, item_id=f"i{number}").id
            for number in range(PAGE_SIZE + 2)
        ]
        session.commit()

    first = client.get("/queues?tab=unknown").text
    second = client.get("/queues?tab=unknown&page=2").text
    beyond = client.get("/queues?tab=unknown&page=99").text

    assert _row_ids(first) == created[:PAGE_SIZE]
    assert 'href="/queues?tab=unknown&amp;page=2" rel="next"' in first and 'rel="prev"' not in first
    assert _row_ids(second) == created[PAGE_SIZE:]
    assert 'href="/queues?tab=unknown" rel="prev"' in second and 'rel="next"' not in second
    assert "Sayfa 2 / 2" in second
    assert _row_ids(beyond) == created[PAGE_SIZE:]
    assert _tab_counters(first)["Unknown"] == PAGE_SIZE + 2  # sayaç sayfaya değil kuyruğa bakar


def test_row_shows_type_person_guess_sources_and_reason(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        plan = _plan(session, upload, 3)
        session.add(
            Employee(
                id="E0007", folder_name="Kayitli_Kisi_E0007", given_names="Kayitli", surname="Kisi"
            )
        )
        stored = _source_file(session, upload, "tarama.pdf", page_count=4)
        _queue_item(
            session,
            upload,
            plan,
            QueueKind.UNRESOLVED,
            item_id="i9",
            reason="Aynı türden iki ön yüz var; eşleştirme yapılmadı.",
            payload=_payload(
                stored.id,
                [0, 1, 3],
                slug=PASSPORT,
                guess={"action": "match", "employee_id": "E0007", "matched_by": "document_number"},
            ),
        )
        session.commit()

    html = client.get("/queues?tab=unresolved").text

    assert "<td>Russian Passport</td>" in html  # katalogdaki ad, slug değil
    assert "Eşleşti · E0007 — Kayitli Kisi (belge numarası)" in html
    assert "tarama.pdf · s. 1–2, 4" in html
    assert "Aynı türden iki ön yüz var; eşleştirme yapılmadı." in html
    assert f'<a href="/uploads/{UPLOAD_ID}">{UPLOAD_ID}</a>' in html
    assert "plan 3 · i9" in html


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"sources": "yok", "employee_guess": 7, "document_type_slug": 3},
        {"sources": [{"file_id": "x"}, 5, {"file_id": 999_999, "pages": [0]}]},
    ],
    ids=["null", "empty", "wrong-types", "broken-sources"],
)
def test_items_with_a_missing_or_corrupt_payload_do_not_break_the_screens(
    client: TestClient, session_factory: sessionmaker[Session], payload: Any
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        plan = _plan(session, upload, 1)
        item = _queue_item(session, upload, plan, QueueKind.UNKNOWN, payload=payload)
        item_id = item.id
        session.commit()

    listing = client.get("/queues?tab=unknown")
    detail = client.get(f"/queues/{item_id}")

    assert listing.status_code == 200 and detail.status_code == 200
    assert _row_ids(listing.text) == [item_id]
    assert "Belirlenmedi" in listing.text and "Belirlenmedi" in detail.text
    assert "Sentetik gerekçe" in detail.text


def test_unknown_type_slug_is_shown_as_written(
    client: TestClient, session_factory: sessionmaker[Session], seeded: None
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        plan = _plan(session, upload, 1)
        stored = _source_file(session, upload, "diploma.pdf", page_count=1)
        item = _queue_item(
            session,
            upload,
            plan,
            QueueKind.UNKNOWN,
            payload=_payload(stored.id, [0], slug="katalogda_yok"),
        )
        item_id = item.id
        session.commit()

    assert "<td>katalogda_yok</td>" in client.get("/queues?tab=unknown").text
    assert "<dd>katalogda_yok</dd>" in client.get(f"/queues/{item_id}").text


# --- öğe detayı --------------------------------------------------------------------------------


def _process_unreadable_passport(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> tuple[str, int]:
    """Bulanık numaralı pasaportu yükler ve işler; `(upload_id, kuyruk öğesi)` döner."""
    page = passport_page(
        PERSON_ORNEKOVA,
        document_number="00 0000001",
        expiry_date=date(2030, 1, 1),
        blurred={"document_number"},
        mrz_legible=False,
        notes=UNREADABLE_NOTES,
    )
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
    uploaded = client.post(
        "/api/uploads",
        files=[("files", ("pasaport.pdf", make_document_pdf_bytes([page]), "application/pdf"))],
    )
    assert uploaded.status_code == 201, uploaded.text
    upload_id: str = uploaded.json()["upload_id"]
    with session_factory() as session:
        process_upload(
            session,
            layout,
            session.get_one(Upload, upload_id),
            settings=SETTINGS,
            provider=recorded_provider(tmp_path / "kayit", [page]),
        )
    with session_factory() as session:
        return upload_id, session.scalars(select(QueueItem)).one().id


def test_item_detail_shows_reason_guess_sources_and_page_images_from_the_real_pipeline(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id, item_id = _process_unreadable_passport(client, session_factory, layout, tmp_path)
    with session_factory() as session:
        source_file = session.scalars(select(UploadFile)).one()
        page = session.scalars(select(Page)).one()
        file_id, page_id = source_file.id, page.id

    listing = client.get("/queues?tab=unreadable")
    assert _tab_counters(listing.text) == {"Unknown": 0, "Unreadable": 1, "Unresolved": 0}
    assert _row_ids(listing.text) == [item_id]
    assert UNREADABLE_REASON in listing.text and "pasaport.pdf · s. 1" in listing.text

    response = client.get(f"/queues/{item_id}")

    assert response.status_code == 200
    html = response.text
    assert f"<title>Kuyruk öğesi {item_id} · belgeee</title>" in html
    assert '<a href="/queues?tab=unreadable">← Unreadable kuyruğu</a>' in html
    assert re.search(r'<a href="/queues" class="active" aria-current="page">Kuyruklar</a>', html)
    assert "<dt>Durum</dt><dd>Bekleyen</dd>" in html
    assert "<dt>Belge türü</dt><dd>Russian Passport</dd>" in html
    assert UNREADABLE_REASON in html  # R7: gerekçe yazılı
    assert f'<a href="/uploads/{upload_id}">{upload_id}</a>' in html
    assert f'<a href="/uploads/{upload_id}#item-i1">plan öğesi i1</a>' in html
    # Kaynak dosya ve sayfa: dosya bölümüne bağlanır, sayfa görüntüsü sayfada ve açılabilir.
    sources = _section(html, "sources")
    assert f'<a href="/uploads/{upload_id}#file-{file_id}">pasaport.pdf</a>' in sources
    image_url = f"/uploads/{upload_id}/pages/{page_id}/image"
    assert f'<a href="{image_url}" target="_blank" rel="noopener">' in sources
    assert f'<img src="{image_url}"' in sources and "Sayfa 1" in sources
    served = client.get(image_url)
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/") and served.content
    # Kuyruğa alınma olayı öğenin izinde.
    timeline = _section(html, "timeline")
    assert EventType.QUEUED_UNREADABLE.value in timeline and "pasaport.pdf · s. 1" in timeline


def test_resolved_item_shows_who_resolved_it_and_links_to_the_output_history(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    item_id = _pipeline_queued_item(session_factory, layout)
    app.dependency_overrides[get_confirmed_actor] = lambda: ACTOR  # 10.8.1'in yerine
    assigned = client.post(f"/api/queue/{item_id}/assign", json={"employee_id": TARGET})
    assert assigned.status_code == 200, assigned.text
    document_id: int = assigned.json()["document_id"]

    detail = client.get(f"/queues/{item_id}").text
    listing = client.get("/queues?tab=unreadable&state=resolved").text

    assert "<dt>Durum</dt><dd>Çözülen</dd>" in detail
    assert f"· {ACTOR}" in detail
    assert f'<a href="/documents/{document_id}/history">çıktının geçmişi</a>' in detail
    assert '<a href="/queues?tab=unreadable&amp;state=resolved">← Unreadable kuyruğu</a>' in detail
    timeline = _section(detail, "timeline")
    assert EventType.QUEUED_UNREADABLE.value in timeline
    assert EventType.MANUAL_ASSIGN.value in timeline and ACTOR in timeline
    assert _row_ids(listing) == [item_id] and ACTOR in listing
    assert _tab_counters(client.get("/queues").text) == {
        "Unknown": 0,
        "Unreadable": 0,
        "Unresolved": 0,
    }
    with session_factory() as session:  # ekranlar okur: kuyruk kaydı ve çıktı aynı kalır
        assert session.get_one(QueueItem, item_id).resolved_by == ACTOR


def test_unknown_item_without_a_type_says_so(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    item_id = _pipeline_queued_item(session_factory, layout, unknown=True)

    html = client.get(f"/queues/{item_id}").text

    assert "<dt>Kuyruk</dt><dd>Unknown</dd>" in html
    assert "<dt>Belge türü</dt><dd>Belirlenmedi</dd>" in html


def test_superseded_item_says_it_cannot_be_resolved(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        old_plan, _new_plan = _plan(session, upload, 1), _plan(session, upload, 2)
        item = _queue_item(session, upload, old_plan, QueueKind.UNRESOLVED)
        item_id = item.id
        session.commit()

    html = client.get(f"/queues/{item_id}").text

    assert "<dt>Durum</dt><dd>Eski sürüm</dd>" in html
    assert SUPERSEDED_NOTE in html
    assert "plan sürüm 1" in html
    assert '<a href="/queues?tab=unresolved&amp;state=superseded">← Unresolved kuyruğu</a>' in html


def test_missing_item_is_a_404_page(client: TestClient) -> None:
    response = client.get("/queues/12345")

    assert response.status_code == 404
    assert QUEUE_ITEM_NOT_FOUND in response.text
    assert '<a href="/queues">← Kuyruklar</a>' in response.text


def test_item_without_source_records_says_so(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        item = _queue_item(
            session, upload, _plan(session, upload, 1), QueueKind.UNKNOWN, payload={}
        )
        item_id = item.id
        session.commit()

    html = client.get(f"/queues/{item_id}").text

    assert "Bu öğe için kaynak kaydı yok." in html
    assert "Bu öğe için olay yok." in html


def test_corrupt_source_reference_is_written_without_a_link(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        item = _queue_item(
            session,
            upload,
            _plan(session, upload, 1),
            QueueKind.UNKNOWN,
            payload={"sources": [{"file_id": "x", "pages": []}]},
        )
        item_id = item.id
        session.commit()

    assert CORRUPT_SOURCE in client.get("/queues").text
    assert "Bozuk köken kaydı" in client.get(f"/queues/{item_id}").text  # 10.6'nın ortak yazımı


def test_item_events_are_only_those_of_that_item(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        upload = _upload(session)
        plan = _plan(session, upload, 1)
        mine = _queue_item(session, upload, plan, QueueKind.UNKNOWN, item_id="i1")
        other = _queue_item(session, upload, plan, QueueKind.UNKNOWN, item_id="i2")
        for row, message in ((mine, "benim olayım"), (other, "başkasının olayı")):
            session.add(
                Event(
                    upload_id=upload.id,
                    type=EventType.QUEUED_UNKNOWN.value,
                    message=message,
                    data_json={"queue_item_id": row.id},
                )
            )
        session.add(
            Event(upload_id=upload.id, type=EventType.QUEUED_UNKNOWN.value, message="verisiz")
        )
        mine_id = mine.id
        session.commit()

    html = client.get(f"/queues/{mine_id}").text

    assert "benim olayım" in html
    assert "başkasının olayı" not in html and "verisiz" not in html


# --- sınırlar ----------------------------------------------------------------------------------


def test_queue_screens_are_read_only_except_the_assignment_and_profile_steps(
    app: FastAPI,
) -> None:
    # 10.7.1 yalnız gösterir; eylemler 10.7.2'nin iki onaylı ataması (`test_queue_assign.py`) ve
    # 10.7.3'ün iki onaylı profil oluşturmasıdır (`test_queue_new_profile.py`). Belge içeriğini
    # düzenleyen yol yoktur (K17).
    methods = {
        path: set(operations)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/queues")
    }

    assert methods == {
        "/queues": {"get"},
        "/queues/{queue_item_id}": {"get"},
        "/queues/{queue_item_id}/assign/employees": {"get"},
        "/queues/{queue_item_id}/assign/confirm": {"get"},
        "/queues/{queue_item_id}/assign/prepare": {"post"},
        "/queues/{queue_item_id}/assign": {"post"},
        "/queues/{queue_item_id}/profile/confirm": {"post"},
        "/queues/{queue_item_id}/profile/prepare": {"post"},
        "/queues/{queue_item_id}/profile": {"post"},
    }


def test_queue_screens_require_a_session(app: FastAPI) -> None:
    app.dependency_overrides.pop(get_current_user)  # oturumsuz istemci
    anonymous = TestClient(app)
    for path in ("/queues", "/queues?tab=unresolved", "/queues/1"):
        response = anonymous.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login?next="), path
