"""09.3 — PRD §9 kabul senaryosu S20 uçtan uca: eğitim modunda pasaport yükleniyor, ikinci dosya
hiçbir türe uymuyor (11.9.1; PLAN.md §C86).

Senaryo panelin gerçek yolundan geçer: dosyalar Eğitim modu sekmesinden (`POST /training`) yüklenir,
mekanik tanıma istek içinde biter; mekanik tanınmayan dosyayı işçinin boş-zaman işi
(`TrainingClassificationJob`) yapay zekâya sorar ve sonuç sekmede görünür. Beklenen: pasaport
örneklere girer (mekanik ya da "AI kararı" etiketli), ikincisi "Yerleştirilemedi"de bekler; çalışan,
kuyruk öğesi, yükleme partisi ve çıktı belgesi oluşmaz. Yapay zekâ canlı çağrılmaz (kayıtlı yanıt);
dosyalar ve kişiler sentetiktir, gerçek kimlik belgesi yoktur (CONVENTIONS §6).
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.recording_provider import RecordingProvider
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
from app.db.models import Base, ExampleFileRecord, TrainingItem, TrainingRun
from app.db.session import create_db_engine, create_session_factory, get_session
from app.main import create_app
from app.storage import DataLayout, prepare_data_dir
from app.storage.examples import list_examples
from app.training.classification import TrainingClassificationJob
from app.web.auth import get_current_user
from app.web.routers.training import MANUAL_CHECK_TEXT, get_training_provider_problem
from app.web.routers.uploads import get_layout
from app.worker import IdleContext
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    make_mrz_lines,
    make_page_image_bytes,
    make_text_pdf_bytes,
    passport_page,
    unknown_document_page,
)
from tests.training.invariants import assert_employee_data_untouched
from tests.web.conftest import SIGNED_IN

ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "training_classifications" / "s20"
SETTINGS = Settings(_env_file=None, database_url="sqlite://", worker_max_attempts=3)
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "PRUEBA", "Prueba", "00 0000001", "1990-01-01")
ICON = f'aria-label="{MANUAL_CHECK_TEXT}"'


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'scenario-s20.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    with create_session_factory(db_engine)() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def client(engine: Engine, layout: DataLayout) -> Iterator[TestClient]:
    application = create_app()
    factory = create_session_factory(engine)

    def _override_get_session() -> Iterator[Session]:
        with factory() as db_session:
            yield db_session

    application.dependency_overrides[get_session] = _override_get_session
    application.dependency_overrides[get_layout] = lambda: layout
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    application.dependency_overrides[get_current_user] = lambda: SIGNED_IN
    application.dependency_overrides[get_training_provider_problem] = lambda: None
    yield TestClient(application)
    application.dependency_overrides.clear()


def _card() -> bytes:
    """Hiçbir bilinen türe uymayan sentetik kart (kütüphane üyelik kartı) görüntüsü."""
    return make_page_image_bytes(
        unknown_document_page(
            PERSON_PRUEBA, candidate_type_name="Library Card", title="LIBRARY CARD"
        )
    )


def _passport_pdf() -> bytes:
    """Metin katmanında geçerli TD3 MRZ taşıyan sentetik Türk pasaportu PDF'i."""
    lines = make_mrz_lines(
        "TD3",
        document_code="P",
        issuing_state="TUR",
        surname="ORNEKOVA",
        given_names="TEST",
        document_number="U00000001",
        nationality="TUR",
        date_of_birth=date(1990, 1, 1),
        sex="F",
        expiry_date=date(2030, 1, 1),
    )
    return make_text_pdf_bytes(["\n".join(("PASAPORT", *lines))])


def _upload(client: TestClient, *files: tuple[str, bytes]) -> str:
    response = client.post(
        "/training",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
        data={"hint_slug": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"]


def _work(engine: Engine, layout: DataLayout, provider: RecordingProvider) -> int:
    """İşçinin boş-zaman işini iş kalmayana kadar koşar; koşulan birim sayısı."""
    context = IdleContext(create_session_factory(engine), layout, SETTINGS, provider)
    job = TrainingClassificationJob()
    units = 0
    while job.run_one(context):
        units += 1
    return units


def _items(engine: Engine) -> dict[str, TrainingItem]:
    with create_session_factory(engine)() as session:
        return {item.original_name: item for item in session.scalars(select(TrainingItem))}


def _row(html: str, item_id: int) -> str:
    match = re.search(rf'<tr id="item-{item_id}".*?</tr>', html, re.S)
    assert match is not None, item_id
    return match.group(0)


def _assert_nothing_on_the_employee_side(engine: Engine, layout: DataLayout) -> None:
    with create_session_factory(engine)() as session:
        assert_employee_data_untouched(session, layout)


def test_s20_mechanical_passport_is_placed_and_the_unfitting_file_waits_unplaced(
    client: TestClient, engine: Engine, layout: DataLayout, tmp_path: Path
) -> None:
    location = _upload(client, ("pasaport.pdf", _passport_pdf()), ("kart.jpg", _card()))

    items = _items(engine)
    passport, card = items["pasaport.pdf"], items["kart.jpg"]
    assert (passport.status, passport.method, passport.result_slug) == (
        "placed",
        "mechanical",
        "turkish_passport",
    )
    assert card.status == "ai_pending"
    assert [example.name for example in list_examples(layout, "turkish_passport")] == [
        "pasaport.pdf"
    ]
    waiting = client.get(location)
    assert "Yapay zekâ incelemesi bekliyor" in _row(waiting.text, card.id)
    assert 'hx-trigger="every 3s"' in waiting.text

    # Kayıtlı yanıt: kart hiçbir bilinen türe inmez (S20'nin ikinci yanıtı).
    recordings = tmp_path / "kart-yaniti"
    recordings.mkdir()
    shutil.copy(RECORDINGS / "1.json", recordings / "0.json")
    provider = RecordingProvider.from_directory(recordings)
    assert _work(engine, layout, provider) == 1
    assert len(provider.training_requests) == 1
    assert provider.requests == []  # sayfa analizi yok

    card = _items(engine)["kart.jpg"]
    assert card.status == "unplaced"
    unplaced = client.get("/training?filter=unplaced")
    row = _row(unplaced.text, card.id)
    assert "Yerleştirilemedi" in row
    assert "Yapay zekâ önerisi: Library Membership Card" in row
    assert f'action="/training/items/{card.id}/place"' in row
    assert f'<tr id="item-{passport.id}"' not in unplaced.text
    done = client.get(location)
    assert "hx-trigger" not in done.text
    assert "Mekanik" in _row(done.text, passport.id)
    with create_session_factory(engine)() as session:
        run = session.get_one(TrainingRun, card.run_id)
        assert (run.status, run.counts_json) == ("done", {"placed": 1, "unplaced": 1})
    _assert_nothing_on_the_employee_side(engine, layout)
    for text in (done.text, unplaced.text):
        for value in PERSONAL_VALUES:
            assert value not in text


def test_s20_ai_path_places_the_passport_with_the_ai_decision_label(
    client: TestClient, engine: Engine, layout: DataLayout
) -> None:
    # Metin katmanı olmayan pasaport görüntüsü mekanik tanınmaz: yapay zekâ onu "AI kararı"
    # etiketiyle yerleştirir; kart yine "Yerleştirilemedi"de bekler.
    passport = make_page_image_bytes(
        passport_page(PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1))
    )
    location = _upload(client, ("pasaport.jpg", passport), ("kart.jpg", _card()))
    assert {item.status for item in _items(engine).values()} == {"ai_pending"}

    provider = RecordingProvider.from_directory(RECORDINGS)
    assert _work(engine, layout, provider) == 2

    items = _items(engine)
    placed, card = items["pasaport.jpg"], items["kart.jpg"]
    assert (placed.status, placed.method, placed.result_slug) == (
        "placed",
        "ai",
        "russian_passport",
    )
    assert card.status == "unplaced"
    with create_session_factory(engine)() as session:
        (example,) = session.scalars(select(ExampleFileRecord)).all()
        assert (example.type_slug, example.label) == ("russian_passport", "ai_decision")
    page = client.get(location)
    passport_row = _row(page.text, placed.id)
    assert "AI kararı" in passport_row and ICON in passport_row and "⚠" in passport_row
    assert "Yerleştirilemedi" in _row(page.text, card.id)
    assert [placed.id] == [
        int(value)
        for value in re.findall(r'<tr id="item-(\d+)"', client.get("/training?filter=ai").text)
    ]
    known = client.get("/training/known/russian_passport")
    assert "pasaport.jpg" in known.text and ICON in known.text
    _assert_nothing_on_the_employee_side(engine, layout)
    for value in PERSONAL_VALUES:
        assert value not in page.text
