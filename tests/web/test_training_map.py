"""11.9.5 — Harita yükle ve toplu tarama paneli: "Harita yükle" önizlemesi (yazma yok), iki aşamalı
"Toplu taramayı başlat" (metinler PLAN.md §D58'den birebir, 10.8.1 belirteci), çalıştırma + öğeler +
olay + saklanan harita, işçide ilerleme (HTMX yoklaması) ve "İnceleme gerekli" öğenin "Türe
yerleştir"i (`app.web.routers.training`, `app.training.map_import`, `app.training.map_scan`).

Haritalar testte kurulan sentetik CSV'lerdir; dosyalar sentetik görüntülerdir
(`tests/fixtures/gen.py`); gerçek kimlik belgesi ve yapay zekâ çağrısı yoktur (CONVENTIONS §6).
Yalnız `TestClient`.
"""

from __future__ import annotations

import base64
import html
import re
import zlib
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
from app.db.models import (
    ConfirmationToken,
    Event,
    ExampleFileRecord,
    TrainingItem,
    TrainingRun,
)
from app.events import EventType
from app.storage import DataLayout, sha256_bytes
from app.storage.examples import list_examples
from app.training.map_import import NO_PATH_COLUMN, NOT_UTF8
from app.training.map_scan import TrainingMapJob
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, CONFIRMATION_TEXTS, Operation
from app.web.routers.training import (
    MAP_DATA_INVALID,
    MAP_EMPTY,
    MAP_FIRST_CONFIRMATION,
    MAP_NOT_CSV,
    MAP_SAVE_FAILED,
    MAP_SECOND_CONFIRMATION,
    NO_MAP_MESSAGE,
    get_training_provider_problem,
    pack_map,
)
from app.worker import IdleContext
from tests.fixtures.gen import make_half_filled_image_bytes
from tests.training.invariants import assert_employee_data_untouched
from tests.web.conftest import SESSION, SIGNED_IN, issue_token
from tests.web.test_confirm import PRD_OPERATIONS

PLAN = Path(__file__).resolve().parents[2] / "PLAN.md"
PASSPORT = "turkish_passport"
IN_PLACE = f"KnownDocuments/examples/{PASSPORT}"
SETTINGS = Settings(_env_file=None, database_url="sqlite://")


@pytest.fixture(autouse=True)
def catalog(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture(autouse=True)
def provider_ready(app: FastAPI) -> None:
    app.dependency_overrides[get_training_provider_problem] = lambda: None


@pytest.fixture
def signed_client(client: TestClient) -> TestClient:
    # Onay belirteci oturum çerezine bağlıdır (10.8.1).
    client.cookies.set(SESSION_COOKIE, SESSION)
    return client


def _jpeg(width: int = 200) -> bytes:
    return make_half_filled_image_bytes("JPEG", (width, 100))


def _put(layout: DataLayout, relative: str, content: bytes) -> Path:
    path = layout.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _map(*rows: str) -> bytes:
    return ("﻿slug;role;dest;path;sha256\r\n" + "".join(f"{row}\r\n" for row in rows)).encode()


def _fixture_map(layout: DataLayout) -> bytes:
    """Yerindeki bir örnek (mekanik), türü belirsiz bir dosya (yapay zekâ gerekebilir), bir
    referans satırı ve bulunamayan bir dosya."""
    _put(layout, f"{IN_PLACE}/a.jpg", _jpeg(201))
    _put(layout, "gelen/b.jpg", _jpeg(202))
    return _map(
        f"{PASSPORT};example;{IN_PLACE}/a.jpg;;",
        "bilinmeyen_tur;example;;gelen\\b.jpg;",
        f"{PASSPORT};reference;{IN_PLACE}/a.jpg;;",
        ";;;gelen/yok.jpg;",
    )


def _upload_map(client: TestClient, content: bytes, name: str = "harita.csv") -> Any:
    return client.post("/training/maps", files={"map": (name, content, "text/csv")})


def _hidden(page: str, name: str) -> str:
    match = re.search(rf'name="{name}" value="([^"]*)"', page)
    assert match is not None, name
    return html.unescape(match.group(1))


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _state(session_factory: sessionmaker[Session], layout: DataLayout) -> tuple[Any, ...]:
    """Adımların dokunabileceği her şey: dosyalar, çalıştırma, öğe, örnek kaydı, olay, belirteç."""
    with session_factory() as session:
        counts = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (TrainingRun, TrainingItem, ExampleFileRecord, Event, ConfirmationToken)
        )
    return _files(layout.root), counts


def _events(session_factory: sessionmaker[Session], event_type: EventType) -> list[Event]:
    with session_factory() as session:
        rows = list(session.scalars(select(Event).where(Event.type == event_type.value)))
        for row in rows:
            session.expunge(row)
        return rows


def _scan(session_factory: sessionmaker[Session], layout: DataLayout, units: int = 0) -> int:
    """İşçinin harita işini koşar (`units` verilirse en çok o kadar birim); koşulan birim sayısı."""
    context = IdleContext(session_factory, layout, SETTINGS, None)  # type: ignore[arg-type]
    job, done = TrainingMapJob(), 0
    while (not units or done < units) and job.run_one(context):
        done += 1
    return done


def _start(client: TestClient, content: bytes, name: str = "harita.csv") -> Any:
    data = {"map_name": name, "map_data": pack_map(content)}
    prepared = client.post("/training/maps/prepare", data=data)
    assert prepared.status_code == 200
    return client.post(
        "/training/maps/start",
        data=data | {"confirmation": _hidden(prepared.text, "confirmation")},
        follow_redirects=False,
    )


# --- metinler ve §20.6 ------------------------------------------------------------------------


def test_the_map_confirmation_texts_are_plan_d58_verbatim() -> None:
    text = PLAN.read_text(encoding="utf-8")
    flat = " ".join(text[text.index("- **D58 —") : text.index("- **D59 —")].split())
    match = re.search(r"Toplu taramayı başlat — birinci: `([^`]+)` · ikinci: `([^`]+)`", flat)

    assert match is not None
    assert (match.group(1), match.group(2)) == (MAP_FIRST_CONFIRMATION, MAP_SECOND_CONFIRMATION)
    # §D58 a: K16 ve §20.6 değişmez; işlem REANALYZE gibi tablo dışıdır.
    assert Operation.TRAINING_MAP not in CONFIRMATION_TEXTS
    # Tabloda yalnız §20.6'nın işlemleri var (K16 işlemleriyle büyür, §D61; eğitim işlemi yok).
    assert set(CONFIRMATION_TEXTS) == set(PRD_OPERATIONS.values())


# --- harita yükle ve önizleme ---------------------------------------------------------------


def test_the_training_tab_offers_the_map_upload(client: TestClient) -> None:
    page = client.get("/training")

    assert page.status_code == 200
    assert 'method="post" action="/training/maps" enctype="multipart/form-data"' in page.text
    assert 'name="map" type="file"' in page.text
    assert "Harita yükle" in page.text


def test_uploading_a_map_shows_the_preview_and_writes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = _fixture_map(layout)
    before = _state(session_factory, layout)

    page = _upload_map(client, content)

    assert page.status_code == 200
    text = html.unescape(page.text)
    for key, value in (
        ("rows", 4),
        ("files", 2),
        ("skipped", 2),
        ("registered", 0),
        ("mechanical", 1),
        ("ai", 1),
    ):
        assert re.search(rf'<dd id="map-{key}">{value}\b', text), key
    assert "referans — örnek değil" in text and "dosya yok" in text
    assert "gelen/yok.jpg" in text  # atlanan satırın yolu
    assert 'method="post" action="/training/maps/confirm"' in page.text
    assert _hidden(page.text, "map_name") == "harita.csv"
    assert zlib.decompress(base64.urlsafe_b64decode(_hidden(page.text, "map_data"))) == content
    assert _state(session_factory, layout) == before


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("harita.txt", b"slug,path\nx,a.jpg\n", MAP_NOT_CSV),
        ("harita.csv", "slug,path\nç,ş.jpg\n".encode("cp1254"), NOT_UTF8),
        ("harita.csv", b"slug,note\nx,a.jpg\n", NO_PATH_COLUMN),
    ],
)
def test_an_unreadable_map_is_refused_on_the_training_page(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    name: str,
    content: bytes,
    message: str,
) -> None:
    before = _state(session_factory, layout)

    page = _upload_map(client, content, name)

    assert page.status_code == 400
    assert message in html.unescape(page.text)
    assert "İşlem yapılmadı" in page.text
    assert _state(session_factory, layout) == before


def test_a_missing_or_oversized_map_is_refused(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    missing = client.post("/training/maps", files={"map": ("", b"", "text/csv")})
    assert missing.status_code == 400 and NO_MAP_MESSAGE in missing.text

    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://", training_map_max_bytes=64
    )
    too_big = _upload_map(client, _map(*(f"x;;;{index}.jpg;" for index in range(20))))
    assert too_big.status_code == 400 and "MB sınırını aşıyor" in too_big.text

    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://", training_map_max_rows=2
    )
    too_long = _upload_map(client, _map(*(f"x;;;{index}.jpg;" for index in range(3))))
    assert too_long.status_code == 400 and "2 satır sınırını aşıyor" in too_long.text
    assert _state(session_factory, layout)[1] == (0, 0, 0, 0, 0)


def test_a_map_without_any_file_cannot_be_started(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = _map(";;;gelen/yok.jpg;")

    page = _upload_map(signed_client, content)

    assert page.status_code == 200
    assert "Haritada taranacak dosya yok; tarama başlatılamaz." in html.unescape(page.text)
    assert 'action="/training/maps/confirm"' not in page.text
    data = {"map_name": "harita.csv", "map_data": pack_map(content)}
    for step in ("confirm", "prepare"):
        refused = signed_client.post(f"/training/maps/{step}", data=data)
        assert refused.status_code == 400 and MAP_EMPTY in refused.text
    assert _state(session_factory, layout)[1] == (0, 0, 0, 0, 0)


# --- iki aşamalı başlatma --------------------------------------------------------------------


def test_starting_takes_two_confirmations_then_queues_the_scan(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = _fixture_map(layout)
    data = {"map_name": "harita.csv", "map_data": pack_map(content)}
    before = _state(session_factory, layout)

    first = signed_client.post("/training/maps/confirm", data=data)

    assert first.status_code == 200
    assert "harita.csv haritasındaki 2 dosyayı taramak üzeresiniz. Emin misiniz?" in html.unescape(
        first.text
    )
    assert 'action="/training/maps/prepare"' in first.text
    assert 'name="confirmation"' not in first.text
    assert _state(session_factory, layout) == before

    second = signed_client.post("/training/maps/prepare", data=data)

    assert second.status_code == 200
    assert "En çok 1 dosya yapay zekâya gönderilebilir. Son kararınız mı?" in html.unescape(
        second.text
    )
    assert 'action="/training/maps/start"' in second.text
    token = _hidden(second.text, "confirmation")
    files, counts = _state(session_factory, layout)
    assert files == before[0] and counts == (0, 0, 0, 0, 1)  # yalnız belirteç yazıldı

    done = signed_client.post(
        "/training/maps/start", data=data | {"confirmation": token}, follow_redirects=False
    )

    assert done.status_code == 303
    with session_factory() as session:
        run = session.scalars(select(TrainingRun)).one()
        items = list(session.scalars(select(TrainingItem).order_by(TrainingItem.id)))
        assert (run.kind, run.map_name, run.created_by, run.status) == (
            "map",
            "harita.csv",
            SIGNED_IN.username,
            "running",
        )
        assert [(i.row_number, i.original_name, i.status) for i in items] == [
            (2, "a.jpg", "queued"),
            (3, "b.jpg", "queued"),
        ]
        assert_employee_data_untouched(session, layout)
    assert done.headers["location"] == f"/training?run={run.id}&notice=map_started"
    assert (layout.training_maps / f"{run.id}.csv").read_bytes() == content
    (confirmed,) = _events(session_factory, EventType.USER_CONFIRMED)
    assert confirmed.actor == SIGNED_IN.username
    assert confirmed.data_json is not None
    assert confirmed.data_json["operation"] == "training_map"
    assert confirmed.data_json["target"] == {"run_id": run.id, "files": 2, "ai_possible": 1}
    (started,) = _events(session_factory, EventType.TRAINING_MAP_STARTED)
    assert started.actor == SIGNED_IN.username
    assert started.data_json is not None
    assert (started.data_json["run_id"], started.data_json["files"]) == (run.id, 2)
    assert started.data_json["skipped"] == {"reference": 1, "missing": 1}
    page = signed_client.get(done.headers["location"])
    assert "Toplu tarama başladı" in page.text
    assert "harita.csv" in page.text
    # Aynı belirteç ikinci kez geçmez.
    again = signed_client.post("/training/maps/start", data=data | {"confirmation": token})
    assert again.status_code == 400 and CONFIRMATION_REFUSED in html.unescape(again.text)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TrainingRun)) == 1


@pytest.mark.parametrize("case", ["missing", "unknown", "other_map", "other_operation"])
def test_a_start_without_its_own_token_does_nothing(
    signed_client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    case: str,
) -> None:
    content = _fixture_map(layout)
    data = {"map_name": "harita.csv", "map_data": pack_map(content)}
    token: str | None = None
    if case == "unknown":
        token = "tanimsiz-belirtec"
    elif case == "other_map":
        other = {"map_name": "baska.csv", "map_data": pack_map(content)}
        token = _hidden(
            signed_client.post("/training/maps/prepare", data=other).text, "confirmation"
        )
    elif case == "other_operation":
        prepared = signed_client.post("/training/maps/prepare", data=data)
        subject_token = _hidden(prepared.text, "confirmation")
        assert subject_token
        with session_factory() as session:
            target = session.scalars(select(ConfirmationToken.target)).one()
        token = issue_token(session_factory, Operation.TRAINING_MOVE, target)
    before = _state(session_factory, layout)
    form = data | ({"confirmation": token} if token else {})

    refused = signed_client.post("/training/maps/start", data=form)

    assert refused.status_code == 400
    assert CONFIRMATION_REFUSED in html.unescape(refused.text)
    assert _state(session_factory, layout) == before


def test_a_token_does_not_start_a_changed_map_or_changed_counts(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = _fixture_map(layout)
    data = {"map_name": "harita.csv", "map_data": pack_map(content)}
    token = _hidden(signed_client.post("/training/maps/prepare", data=data).text, "confirmation")

    tampered = data | {
        "map_data": pack_map(content + b";;;gelen/b.jpg;\r\n"),
        "confirmation": token,
    }
    assert signed_client.post("/training/maps/start", data=tampered).status_code == 400
    _put(layout, "gelen/yok.jpg", _jpeg(203))  # dosya sayısı değişti: onay metni artık başka
    changed = signed_client.post("/training/maps/start", data=data | {"confirmation": token})

    assert changed.status_code == 400
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TrainingRun)) == 0
    assert not layout.training_maps.exists() or _files(layout.training_maps) == []


@pytest.mark.parametrize(
    "map_data",
    ["bozuk veri!", pack_map(b"x")[:-4] + "AAAA", pack_map(b"slug,path\n") + "QUJD"],
)
def test_a_step_with_unreadable_map_data_does_nothing(
    signed_client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    map_data: str,
) -> None:
    before = _state(session_factory, layout)

    for step in ("confirm", "prepare", "start"):
        refused = signed_client.post(
            f"/training/maps/{step}", data={"map_name": "harita.csv", "map_data": map_data}
        )
        assert refused.status_code == 400
        assert MAP_DATA_INVALID in html.unescape(refused.text)
    assert _state(session_factory, layout) == before


def test_a_step_refuses_an_expanding_map_beyond_the_limit(
    signed_client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://", training_map_max_bytes=1024
    )
    bomb = pack_map(b"slug,path\n" + b"a" * 1024 * 1024)
    assert len(bomb) < 4096  # sıkıştırılmışı küçük, açılmışı büyük

    refused = signed_client.post(
        "/training/maps/confirm", data={"map_name": "harita.csv", "map_data": bomb}
    )

    assert refused.status_code == 400 and "MB sınırını aşıyor" in refused.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 0


def test_the_hidden_map_name_is_checked_again(
    signed_client: TestClient, layout: DataLayout
) -> None:
    content = _fixture_map(layout)

    refused = signed_client.post(
        "/training/maps/confirm",
        data={"map_name": "../harita.exe", "map_data": pack_map(content)},
    )

    assert refused.status_code == 400 and MAP_NOT_CSV in refused.text


# --- ilerleme ve inceleme -------------------------------------------------------------------


def test_progress_is_polled_while_the_worker_scans_the_map(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = _map(
        f"{PASSPORT};;{IN_PLACE}/a.jpg;;",
        f"{PASSPORT};;{IN_PLACE}/b.jpg;;",
    )
    _put(layout, f"{IN_PLACE}/a.jpg", _jpeg(201))
    _put(layout, f"{IN_PLACE}/b.jpg", _jpeg(202))
    location = _start(signed_client, content).headers["location"]

    waiting = signed_client.get(location)
    assert 'hx-trigger="every 3s"' in waiting.text
    assert '<progress max="2" value="0">' in waiting.text and "0/2 işlendi" in waiting.text
    assert "2 sırada" in waiting.text

    assert _scan(session_factory, layout, units=1) == 1
    halfway = signed_client.get(location.replace("/training?", "/training/items?"))
    assert "1/2 işlendi" in halfway.text and 'hx-trigger="every 3s"' in halfway.text

    assert _scan(session_factory, layout) == 1
    done = signed_client.get(location)
    assert "hx-trigger" not in done.text and "<progress" not in done.text
    assert "2 yerleşti" in done.text
    assert [example.name for example in list_examples(layout, PASSPORT)] == ["a.jpg", "b.jpg"]


def test_a_review_item_waits_under_its_filter_and_is_placed_in_place(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = _jpeg(201)
    _put(layout, f"{IN_PLACE}/a.jpg", content)
    _start(signed_client, _map(f"{PASSPORT};;{IN_PLACE}/a.jpg;;{'0' * 64}"))
    _scan(session_factory, layout)
    with session_factory() as session:
        item = session.scalars(select(TrainingItem)).one()
        assert item.status == "review"

    listed = signed_client.get("/training?filter=review")
    row = re.search(rf'<tr id="item-{item.id}".*?</tr>', listed.text, re.S)
    assert row is not None
    assert "İnceleme gerekli" in row.group(0)
    assert "haritadaki SHA-256 dosyayla tutmuyor" in row.group(0)
    assert f'action="/training/items/{item.id}/place"' in row.group(0)

    placed = signed_client.post(
        f"/training/items/{item.id}/place", data={"slug": PASSPORT}, follow_redirects=False
    )

    assert placed.status_code == 303
    with session_factory() as session:
        record = session.scalars(select(ExampleFileRecord)).one()
        assert (record.type_slug, record.name, record.method, record.label) == (
            PASSPORT,
            "a.jpg",
            "manual",
            "verified",
        )
        assert record.sha256 == sha256_bytes(content)
        assert session.get_one(TrainingItem, item.id).status == "placed"
    assert [example.name for example in list_examples(layout, PASSPORT)] == ["a.jpg"]  # kopya yok
    assert not (layout.training / "gelen").exists()


def test_a_failed_map_save_starts_nothing_and_keeps_the_token(
    signed_client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = _fixture_map(layout)
    data = {"map_name": "harita.csv", "map_data": pack_map(content)}
    token = _hidden(signed_client.post("/training/maps/prepare", data=data).text, "confirmation")

    def full_disk(*args: object, **kwargs: object) -> None:
        raise OSError("disk dolu")

    monkeypatch.setattr("app.training.map_import.write_unique", full_disk)
    failed = signed_client.post("/training/maps/start", data=data | {"confirmation": token})

    assert failed.status_code == 409 and MAP_SAVE_FAILED in failed.text
    with session_factory() as session:
        for model in (TrainingRun, TrainingItem, Event):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    monkeypatch.undo()
    # İşlem geri alındı: belirteç tüketilmedi, aynı onayla yeniden denenebilir.
    retried = signed_client.post(
        "/training/maps/start", data=data | {"confirmation": token}, follow_redirects=False
    )
    assert retried.status_code == 303


def test_a_step_without_the_map_is_refused(signed_client: TestClient) -> None:
    for step in ("confirm", "prepare", "start"):
        refused = signed_client.post(f"/training/maps/{step}", data={"map_name": "harita.csv"})
        assert refused.status_code == 400 and MAP_DATA_INVALID in html.unescape(refused.text)
