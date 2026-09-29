"""11.9.6 — eğitim sekmesinde temizlik: öğeyi yoksay / geri al (tek adım, not `<input>`),
yoksayılanlar görünümü (`?show=dismissed`), çalıştırmayı arşivle / geri al ve arşivli çalıştırmanın
listeden ve üst sayaçlardan düşmesi (`?archived=1`), olaylar (PLAN.md §C92-c, §D61-b;
`app.web.routers.training`).

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi ve canlı yapay zekâ çağrısı
yoktur. Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.db.models import (
    Event,
    ExampleFileRecord,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
)
from app.events import EventType
from app.storage import DataLayout
from app.training import create_run, leave_unplaced, load_known_types, place_example, stage_file
from app.training.cleanup import DISMISSED_NOTE, NOT_DISMISSABLE, NOT_DISMISSED, NOTE_TOO_LONG
from app.web.routers.training import get_training_provider_problem
from tests.fixtures.gen import make_half_filled_image_bytes
from tests.training.invariants import assert_employee_data_untouched
from tests.web.conftest import SIGNED_IN

LIMIT = 1024 * 1024


def _image(width: int) -> bytes:
    return make_half_filled_image_bytes("JPEG", (width, 100))


@pytest.fixture(autouse=True)
def catalog(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture(autouse=True)
def provider_ready(app: FastAPI) -> None:
    app.dependency_overrides[get_training_provider_problem] = lambda: None


@pytest.fixture
def items(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, int]:
    """İki çalıştırma: #1'de yerleşen, yerleştirilemedi, çelişki, inceleme ve bekleyen öğe; #2'de
    bir yerleştirilemedi öğe."""
    with session_factory() as session:
        known = load_known_types(session)
        first = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")
        width = iter(range(200, 400, 10))

        def waiting(run: TrainingRun, status: TrainingItemStatus) -> TrainingItem:
            item = stage_file(
                session, layout, run, "bekleyen.jpg", _image(next(width)), max_bytes=LIMIT
            )
            if status is not TrainingItemStatus.QUEUED:
                leave_unplaced(
                    session,
                    item,
                    status,
                    note="bilinen türe inmedi",
                    method=TrainingMethod.AI,
                    slug="serbian_passport" if status is TrainingItemStatus.CONFLICT else None,
                )
            return item

        placed = stage_file(session, layout, first, "yer.jpg", _image(390), max_bytes=LIMIT)
        place_example(
            session, layout, known, placed, "albanian_passport", method=TrainingMethod.MANUAL
        )
        unplaced = waiting(first, TrainingItemStatus.UNPLACED)
        conflict = waiting(first, TrainingItemStatus.CONFLICT)
        review = waiting(first, TrainingItemStatus.REVIEW)
        pending = waiting(first, TrainingItemStatus.QUEUED)
        second = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")
        other = waiting(second, TrainingItemStatus.UNPLACED)
        session.commit()
        return {
            "run1": first.id,
            "run2": second.id,
            "placed": placed.id,
            "unplaced": unplaced.id,
            "conflict": conflict.id,
            "review": review.id,
            "pending": pending.id,
            "other": other.id,
        }


def _row_ids(html: str) -> list[int]:
    return [int(value) for value in re.findall(r'<tr id="item-(\d+)"', html)]


def _row(html: str, item_id: int) -> str:
    match = re.search(rf'<tr id="item-{item_id}".*?</tr>', html, re.S)
    assert match is not None, item_id
    return match.group(0)


def _run_rows(html: str) -> list[int]:
    table = html.split('class="items training-runs"', 1)
    if len(table) < 2:
        return []
    body = table[1].split("</table>", 1)[0]
    return [int(value) for value in re.findall(r'<a href="[^"]*">#(\d+)</a>', body)]


def _item(session_factory: sessionmaker[Session], item_id: int) -> TrainingItem:
    with session_factory() as session:
        item = session.get(TrainingItem, item_id)
        assert item is not None
        session.expunge(item)
        return item


def _events(session_factory: sessionmaker[Session], event_type: EventType) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(select(Event).where(Event.type == event_type.value).order_by(Event.id))
        )


def _dismiss(client: TestClient, item_id: int, **data: str) -> Any:
    return client.post(f"/training/items/{item_id}/dismiss", data=data, follow_redirects=False)


# --- öğeyi yoksay -----------------------------------------------------------------------------


def test_rows_waiting_for_hr_offer_dismiss_with_a_note_input(
    client: TestClient, items: dict[str, int]
) -> None:
    page = client.get("/training").text

    for name, offered in (
        ("unplaced", True),
        ("conflict", True),
        ("review", True),
        ("placed", False),
        ("pending", False),
    ):
        row = _row(page, items[name])
        assert (f'action="/training/items/{items[name]}/dismiss"' in row) is offered, name
    row = _row(page, items["unplaced"])
    assert 'name="note" maxlength="200"' in row
    assert '<input type="hidden" name="next" value="/training">' in row
    assert "<textarea" not in page


@pytest.mark.parametrize("name", ["unplaced", "conflict", "review"])
def test_dismissing_hides_the_item_counts_it_and_logs_the_user(
    client: TestClient,
    items: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    name: str,
) -> None:
    response = _dismiss(client, items[name], note="çöp tarama", next="/training?filter=" + name)

    assert response.status_code == 303
    assert response.headers["location"] == f"/training?filter={name}&notice=dismissed"
    item = _item(session_factory, items[name])
    assert item.status == TrainingItemStatus.DISMISSED
    assert item.note is not None and item.note.endswith(f"{DISMISSED_NOTE}: çöp tarama")
    assert item.decided_by == SIGNED_IN.username
    (event,) = _events(session_factory, EventType.TRAINING_ITEM_DISMISSED)
    assert event.actor == SIGNED_IN.username
    assert event.data_json is not None
    assert event.data_json["training_item_id"] == items[name]
    assert event.data_json["previous_status"] == name

    page = client.get(f"/training?filter={name}&notice=dismissed")
    assert items[name] not in _row_ids(page.text)
    assert "Öğe yoksayıldı" in page.text
    everything = client.get("/training").text
    assert items[name] not in _row_ids(everything)
    assert "Yoksayılanlar (1)" in everything
    assert "1 yoksayılan" in everything  # çalıştırmanın sayacı
    # S20: yoksaymak da çalışan, kuyruk ya da parti açmaz.
    with session_factory() as session:
        assert_employee_data_untouched(session, layout)


def test_the_dismissed_view_lists_only_dismissed_items_with_restore(
    client: TestClient, items: dict[str, int]
) -> None:
    _dismiss(client, items["unplaced"])
    _dismiss(client, items["conflict"])

    for path in ("/training?show=dismissed", "/training/items?show=dismissed"):
        page = client.get(path).text
        assert _row_ids(page) == [items["conflict"], items["unplaced"]], path
        row = _row(page, items["unplaced"])
        assert "Yoksayıldı" in row
        assert f'action="/training/items/{items["unplaced"]}/restore"' in row
        assert "/dismiss" not in row and "/place" not in row
    page = client.get("/training?show=dismissed").text
    assert (
        '<a href="/training?show=dismissed" class="active" aria-current="page">'
        "Yoksayılanlar (2)</a>"
    ) in page
    assert '<a href="/training" class="active" aria-current="page">Tümü</a>' not in page
    assert "2 dosya" in page
    # Bilinmeyen `show` değeri varsayılan görünümdür.
    assert items["unplaced"] not in _row_ids(client.get("/training?show=nope").text)


def test_the_dismissed_view_is_empty_when_nothing_is_dismissed(
    client: TestClient, items: dict[str, int]
) -> None:
    page = client.get("/training?show=dismissed").text

    assert _row_ids(page) == []
    assert "Yoksayılan dosya yok." in page
    assert "Yoksayılanlar (0)" in page


@pytest.mark.parametrize("name", ["placed", "pending"])
def test_items_not_waiting_for_hr_are_not_dismissed(
    client: TestClient, items: dict[str, int], session_factory: sessionmaker[Session], name: str
) -> None:
    before = _item(session_factory, items[name])

    response = _dismiss(client, items[name])

    assert response.status_code == 409
    assert NOT_DISMISSABLE in response.text
    after = _item(session_factory, items[name])
    assert (after.status, after.note) == (before.status, before.note)
    assert _events(session_factory, EventType.TRAINING_ITEM_DISMISSED) == []


def test_a_note_longer_than_200_is_refused(
    client: TestClient, items: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    response = _dismiss(client, items["unplaced"], note="x" * 201)

    assert response.status_code == 422
    assert NOTE_TOO_LONG in response.text
    assert _item(session_factory, items["unplaced"]).status == TrainingItemStatus.UNPLACED


def test_dismiss_and_restore_of_a_missing_item_are_404(client: TestClient) -> None:
    assert _dismiss(client, 999).status_code == 404
    assert client.post("/training/items/999/restore").status_code == 404


def test_an_unsafe_next_falls_back_to_the_training_tab(
    client: TestClient, items: dict[str, int]
) -> None:
    response = _dismiss(client, items["unplaced"], next="https://example.org/training")

    assert response.headers["location"] == "/training?notice=dismissed"


# --- geri al ----------------------------------------------------------------------------------


def test_restoring_brings_the_item_back_as_unplaced(
    client: TestClient, items: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    _dismiss(client, items["conflict"])

    response = client.post(
        f"/training/items/{items['conflict']}/restore",
        data={"next": "/training?show=dismissed"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/training?show=dismissed&notice=restored"
    assert _item(session_factory, items["conflict"]).status == TrainingItemStatus.UNPLACED
    (event,) = _events(session_factory, EventType.TRAINING_ITEM_RESTORED)
    assert event.actor == SIGNED_IN.username
    page = client.get("/training?filter=unplaced").text
    assert items["conflict"] in _row_ids(page)
    assert f'action="/training/items/{items["conflict"]}/place"' in page


def test_restoring_an_item_that_is_not_dismissed_is_refused(
    client: TestClient, items: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    response = client.post(f"/training/items/{items['unplaced']}/restore")

    assert response.status_code == 409
    assert NOT_DISMISSED in response.text
    assert _events(session_factory, EventType.TRAINING_ITEM_RESTORED) == []


# --- çalıştırmayı arşivle ---------------------------------------------------------------------


def test_each_run_offers_archive_and_the_archived_view_offers_restore(
    client: TestClient, items: dict[str, int]
) -> None:
    page = client.get("/training").text

    assert _run_rows(page) == [items["run2"], items["run1"]]
    for run in ("run1", "run2"):
        assert f'action="/training/runs/{items[run]}/archive"' in page
    assert '<a href="/training?archived=1">arşivlenenler</a>' in page
    assert "Arşivlenen çalıştırma yok." in client.get("/training?archived=1").text


def test_archiving_a_run_drops_it_from_the_list_and_the_counters(
    client: TestClient,
    items: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    with session_factory() as session:
        before = [
            (i.id, i.status, i.note)
            for i in session.scalars(select(TrainingItem).order_by(TrainingItem.id))
        ]
        examples = [(e.id, e.name) for e in session.scalars(select(ExampleFileRecord))]
    assert 'hx-get="/training/items"' in client.get("/training").text  # bekleyen öğe var

    response = client.post(f"/training/runs/{items['run1']}/archive", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/training?notice=run_archived"
    page = client.get("/training?notice=run_archived").text
    assert _run_rows(page) == [items["run2"]]
    assert _row_ids(page) == [items["other"]]
    assert "1 dosya" in page
    # Bekleyen öğe arşivli çalıştırmada: üst sayaç ve yoklama da onu saymaz.
    assert "hx-get=" not in page
    assert "Çalıştırma arşivlendi" in page
    assert _row_ids(client.get("/training?filter=unplaced").text) == [items["other"]]
    with session_factory() as session:
        after = [
            (i.id, i.status, i.note)
            for i in session.scalars(select(TrainingItem).order_by(TrainingItem.id))
        ]
        assert after == before
        assert [(e.id, e.name) for e in session.scalars(select(ExampleFileRecord))] == examples
        assert_employee_data_untouched(session, layout)
    (event,) = _events(session_factory, EventType.TRAINING_RUN_ARCHIVED)
    assert event.actor == SIGNED_IN.username
    assert event.data_json == {"run_id": items["run1"], "restored": False}

    archived = client.get("/training?archived=1").text
    assert "Arşivlenen çalıştırmalar" in archived
    assert _run_rows(archived) == [items["run1"]]
    assert f'action="/training/runs/{items["run1"]}/restore"' in archived
    assert items["unplaced"] in _row_ids(archived) and items["other"] not in _row_ids(archived)
    assert f'href="/training?run={items["run1"]}&amp;archived=1"' in archived
    # Seçili arşivli çalıştırma öğelerini gösterir.
    selected = client.get(f"/training?run={items['run1']}").text
    assert items["unplaced"] in _row_ids(selected)


def test_restoring_a_run_brings_it_back(
    client: TestClient, items: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    client.post(f"/training/runs/{items['run1']}/archive")

    response = client.post(f"/training/runs/{items['run1']}/restore", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/training?notice=run_restored"
    page = client.get("/training").text
    assert _run_rows(page) == [items["run2"], items["run1"]]
    assert items["unplaced"] in _row_ids(page)
    events = _events(session_factory, EventType.TRAINING_RUN_ARCHIVED)
    assert [e.data_json for e in events] == [
        {"run_id": items["run1"], "restored": False},
        {"run_id": items["run1"], "restored": True},
    ]


def test_run_archive_refusals(
    client: TestClient, items: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    not_archived = client.post(f"/training/runs/{items['run1']}/restore")
    client.post(f"/training/runs/{items['run1']}/archive")
    twice = client.post(f"/training/runs/{items['run1']}/archive")

    assert not_archived.status_code == 409
    assert "arşivde değil" in not_archived.text
    assert twice.status_code == 409
    assert "zaten arşivde" in twice.text
    assert client.post("/training/runs/999/archive").status_code == 404
    assert client.post("/training/runs/999/restore").status_code == 404
    assert len(_events(session_factory, EventType.TRAINING_RUN_ARCHIVED)) == 1


def test_cleanup_routes_refuse_get(client: TestClient, items: dict[str, int]) -> None:
    for path in (
        f"/training/items/{items['unplaced']}/dismiss",
        f"/training/items/{items['unplaced']}/restore",
        f"/training/runs/{items['run1']}/archive",
        f"/training/runs/{items['run1']}/restore",
    ):
        assert client.get(path).status_code == 405, path
