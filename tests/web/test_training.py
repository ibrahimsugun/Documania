"""11.9.1 — Eğitim modu sekmesi: yükleme ve beklenen tür, çalıştırma ve öğe tablosu, süzgeçler, "AI
kararı" satırında elle kontrol ikonu, Bilinen belgeler görünümü ve katalog dışı türün örnek dosyası,
"Türe yerleştir" (PLAN.md §C86 "Sekme", `app.web.routers.training`).

Veri sentetiktir (`tests/fixtures/gen.py`: kurgusal kişi `ORNEKOVA TEST`, sentetik PDF ve
görüntüler); gerçek kimlik belgesi ve canlı yapay zekâ çağrısı yoktur (CONVENTIONS §6). Sağlayıcı
durumu bağımlılıkla verilir; sekme sağlayıcıyı çağırmaz.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
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
from app.storage import DataLayout, sha256_bytes
from app.storage.examples import list_examples, store_example
from app.storage.filetype import FileKind
from app.training import (
    create_run,
    leave_unplaced,
    load_known_types,
    place_example,
    stage_and_recognize,
)
from app.web.auth import get_current_user
from app.web.routers.training import (
    MANUAL_CHECK_TEXT,
    NO_FILE_MESSAGE,
    NOT_MANUALLY_PLACEABLE,
    UNKNOWN_HINT_MESSAGE,
    UNKNOWN_TYPE_MESSAGE,
    get_training_provider_problem,
)
from tests.fixtures.gen import (
    make_half_filled_image_bytes,
    make_mrz_lines,
    make_text_pdf_bytes,
)
from tests.training.invariants import assert_employee_data_untouched
from tests.web.conftest import SIGNED_IN

LIMIT = 1024 * 1024
SURNAME, GIVEN, NUMBER = "ORNEKOVA", "TEST", "U00000001"
PERSONAL_VALUES = (SURNAME, GIVEN, NUMBER, "900101", "1990-01-01")
PROVIDER_PROBLEM = "AI_PROVIDER=anthropic için ANTHROPIC_API_KEY tanımlı olmalı."
ICON = f'aria-label="{MANUAL_CHECK_TEXT}"'


def _passport_pdf(state: str = "TUR") -> bytes:
    """Metin katmanında geçerli TD3 MRZ taşıyan tek sayfalık sentetik pasaport PDF'i."""
    lines = make_mrz_lines(
        "TD3",
        document_code="P",
        issuing_state=state,
        surname=SURNAME,
        given_names=GIVEN,
        document_number=NUMBER,
        nationality=state,
        date_of_birth=date(1990, 1, 1),
        sex="F",
        expiry_date=date(2030, 1, 1),
    )
    return make_text_pdf_bytes(["\n".join(("PASAPORT", *lines))])


def _image(width: int = 200) -> bytes:
    """Mekanik tanınmayan JPEG (metin katmanı yok); genişlik içeriği ayırır."""
    return make_half_filled_image_bytes("JPEG", (width, 100))


@pytest.fixture(autouse=True)
def catalog(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture(autouse=True)
def provider_ready(app: FastAPI) -> None:
    """Varsayılan: sağlayıcı ayarlı (bilgi notu yok). Ayarsız durum testte ayrıca verilir."""
    app.dependency_overrides[get_training_provider_problem] = lambda: None


def _upload(
    client: TestClient, files: list[tuple[str, bytes]], *, hint: str = ""
) -> Any:  # httpx.Response
    return client.post(
        "/training",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
        data={"hint_slug": hint},
        follow_redirects=False,
    )


def _items(session_factory: sessionmaker[Session]) -> list[TrainingItem]:
    with session_factory() as session:
        return list(session.scalars(select(TrainingItem).order_by(TrainingItem.id)))


def _count(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def _row(html: str, item_id: int) -> str:
    match = re.search(rf'<tr id="item-{item_id}".*?</tr>', html, re.S)
    assert match is not None, item_id
    return match.group(0)


def _row_ids(html: str) -> list[int]:
    return [int(value) for value in re.findall(r'<tr id="item-(\d+)"', html)]


# --- sayfa ve menü ----------------------------------------------------------------------------


def test_the_training_tab_opens_from_the_menu_with_its_upload_form(client: TestClient) -> None:
    page = client.get("/training")

    assert page.status_code == 200
    assert "<title>Eğitim modu · belgeee</title>" in page.text
    assert '<a href="/training" class="active" aria-current="page">Eğitim modu</a>' in page.text
    assert 'method="post" action="/training" enctype="multipart/form-data"' in page.text
    assert 'name="files" type="file" multiple accept=".pdf,.jpg,.jpeg,.png"' in page.text
    # "Beklenen tür" bilinen türlerin hepsini sunar: katalog ve hazır önerilen türler.
    assert '<option value="turkish_passport">' in page.text
    assert '<option value="albanian_passport">' in page.text
    assert 'href="/training/known"' in page.text
    assert "Henüz eğitim yüklemesi yok." in page.text
    assert "hx-trigger" not in page.text  # bekleyen öğe yok, yoklama yok


def test_the_training_tab_requires_a_session(
    app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    for path in ("/training", "/training/items", "/training/known", "/training/known/x"):
        response = anonymous.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login"), path
    response = anonymous.post("/training", follow_redirects=False)
    assert response.status_code == 303
    assert _count(session_factory, TrainingRun) == 0


def test_the_page_says_when_the_ai_provider_is_not_configured(
    app: FastAPI, client: TestClient
) -> None:
    app.dependency_overrides[get_training_provider_problem] = lambda: PROVIDER_PROBLEM

    page = client.get("/training")

    assert "Yapay zekâ sağlayıcısı ayarlı değil" in page.text
    assert PROVIDER_PROBLEM in page.text


def test_the_provider_check_reports_a_missing_key_without_calling_the_provider() -> None:
    settings = Settings(_env_file=None, database_url="sqlite://", anthropic_api_key=None)

    assert "ANTHROPIC_API_KEY" in (get_training_provider_problem(settings) or "")
    assert (
        get_training_provider_problem(
            Settings(_env_file=None, database_url="sqlite://", anthropic_api_key="test-anahtari")
        )
        is None
    )


# --- yükleme ----------------------------------------------------------------------------------


def test_upload_places_a_mechanically_recognized_passport_at_once(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    response = _upload(client, [("pasaport.pdf", _passport_pdf())])

    assert response.status_code == 303
    assert response.headers["location"] == "/training?run=1&notice=uploaded"
    (item,) = _items(session_factory)
    assert (item.status, item.result_slug, item.method) == (
        "placed",
        "turkish_passport",
        "mechanical",
    )
    assert [example.name for example in list_examples(layout, "turkish_passport")] == [
        "pasaport.pdf"
    ]
    with session_factory() as session:
        run = session.get_one(TrainingRun, 1)
        assert (run.kind, run.created_by, run.status) == ("upload", SIGNED_IN.username, "done")

    page = client.get(response.headers["location"])
    row = _row(page.text, item.id)
    assert "pasaport.pdf" in row
    assert "Turkish Passport" in row
    assert "Mekanik" in row and "Yerleşti" in row
    assert "Mekanik: PDF metin katmanında MRZ" in row
    assert ICON not in row  # mekanik yerleşen örnek etiketsiz
    assert "Yükleme alındı ve mekanik tanıma bitti." in page.text
    for value in PERSONAL_VALUES:
        assert value not in page.text
    with session_factory() as session:
        assert_employee_data_untouched(session, layout)


def test_an_unrecognized_file_waits_for_the_ai_and_the_results_poll(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    response = _upload(client, [("belge.jpg", _image())])

    (item,) = _items(session_factory)
    assert item.status == TrainingItemStatus.AI_PENDING
    assert list_examples(layout, "turkish_passport") == []
    page = client.get(response.headers["location"])
    row = _row(page.text, item.id)
    assert "Yapay zekâ incelemesi bekliyor" in row
    assert 'hx-get="/training/items?run=1"' in page.text
    assert 'hx-trigger="every 3s"' in page.text
    assert "1 dosya sistemin kararını bekliyor" in page.text

    fragment = client.get("/training/items?run=1")
    assert fragment.status_code == 200
    assert '<section id="training-results"' in fragment.text
    assert 'hx-trigger="every 3s"' in fragment.text
    assert "<html" not in fragment.text  # parça, sayfa değil

    # Yapay zekâ kararı verince (burada elle) yoklama durur.
    with session_factory() as session:
        pending = session.get_one(TrainingItem, item.id)
        leave_unplaced(
            session,
            pending,
            TrainingItemStatus.UNPLACED,
            note="Yapay zekâ önerisi: Library Card; bilinen türe inmedi",
            method=TrainingMethod.AI,
        )
        session.commit()
    fragment = client.get("/training/items?run=1")
    assert "hx-trigger" not in fragment.text
    assert "Yerleştirilemedi" in _row(fragment.text, item.id)


def test_the_expected_type_is_used_as_the_hint(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # MRZ'siz tek sayfalık PDF: beklenen türün yapı kuralları (PDF, 1 sayfa) tutar.
    content = make_text_pdf_bytes(["PASAPORT"])

    response = _upload(client, [("kapak.pdf", content)], hint="turkish_passport")

    assert response.status_code == 303
    (item,) = _items(session_factory)
    assert (item.hint_slug, item.status, item.result_slug) == (
        "turkish_passport",
        "placed",
        "turkish_passport",
    )
    assert (item.note or "").startswith("Mekanik: beklenen tür → `turkish_passport`")
    page = client.get(response.headers["location"])
    assert 'href="/training/known/turkish_passport">Turkish Passport</a>' in _row(
        page.text, item.id
    )


def test_a_hint_conflicting_with_the_mrz_goes_to_the_ai(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(client, [("pasaport.pdf", _passport_pdf("TUR"))], hint="serbian_passport")

    (item,) = _items(session_factory)
    assert item.status == TrainingItemStatus.AI_PENDING


def test_several_files_make_one_run_with_one_item_each(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _upload(
        client,
        [("pasaport.pdf", _passport_pdf()), ("a.jpg", _image(200)), ("b.jpg", _image(220))],
    )

    items = _items(session_factory)
    assert [item.status for item in items] == ["placed", "ai_pending", "ai_pending"]
    assert {item.run_id for item in items} == {1}
    with session_factory() as session:
        assert session.get_one(TrainingRun, 1).counts_json == {"placed": 1, "ai_pending": 2}


def test_an_unknown_expected_type_writes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    response = _upload(client, [("pasaport.pdf", _passport_pdf())], hint="yok_boyle_tur")

    assert response.status_code == 400
    assert UNKNOWN_HINT_MESSAGE in response.text
    assert _count(session_factory, TrainingRun) == 0
    assert not layout.training.exists() or not any(layout.training.rglob("*.*"))


@pytest.mark.parametrize("name", ["a:b.pdf", "belge.pdf.", "ad<>.jpg"])
def test_a_name_the_upload_page_refuses_writes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], name: str
) -> None:
    response = _upload(client, [("iyi.pdf", _passport_pdf()), (name, _image())])

    assert response.status_code == 400
    assert "Geçersiz dosya adı" in response.text
    assert _count(session_factory, TrainingRun) == 0
    assert _count(session_factory, TrainingItem) == 0


def test_no_file_is_refused(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    response = client.post(
        "/training",
        files=[("files", ("", b"", "application/octet-stream"))],
        data={"hint_slug": ""},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert NO_FILE_MESSAGE in response.text
    assert _count(session_factory, TrainingRun) == 0


def test_oversized_and_unsupported_files_become_failed_items(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://", max_upload_file_size_bytes=1024
    )
    big = _image(1200)
    assert len(big) > 1024

    response = _upload(client, [("buyuk.jpg", big), ("not.txt", b"duz metin"), ("bos.pdf", b"")])

    assert response.status_code == 303
    items = _items(session_factory)
    assert [item.status for item in items] == ["failed", "failed", "failed"]
    assert "sınırını aşıyor" in (items[0].note or "")
    assert "yalnız PDF, JPEG ve PNG" in (items[1].note or "")
    assert "boş" in (items[2].note or "")
    assert [item.staged_path for item in items] == [None, None, None]
    page = client.get("/training?filter=failed")
    assert _row_ids(page.text) == [item.id for item in reversed(items)]
    assert "Hatalı" in _row(page.text, items[0].id)


def test_upload_reads_each_file_only_one_byte_past_the_limit(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from starlette.datastructures import UploadFile as StarletteUploadFile

    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://", max_upload_file_size_bytes=1024
    )
    sizes: list[int] = []
    original = StarletteUploadFile.read

    async def read(self: StarletteUploadFile, size: int = -1) -> bytes:
        sizes.append(size)
        return await original(self, size)

    monkeypatch.setattr(StarletteUploadFile, "read", read)

    _upload(client, [("buyuk.jpg", _image(1200))])

    assert sizes == [1025]


# --- süzgeçler ve elle kontrol ikonu ----------------------------------------------------------


@pytest.fixture
def states(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, int]:
    """Her süzgece bir öğe: mekanik, AI kararı, yerleştirilemedi, çelişki, hatalı, bekleyen."""
    with session_factory() as session:
        known = load_known_types(session)
        run = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")

        def stage(name: str, content: bytes, hint: str | None = None) -> TrainingItem:
            return stage_and_recognize(
                session,
                layout,
                known,
                run,
                name,
                content,
                max_bytes=LIMIT,
                inventory=None,
                hint_slug=hint,
            )

        mechanical = stage("pasaport.pdf", _passport_pdf())
        ai = stage("arnavut.jpg", _image(200))
        place_example(
            session,
            layout,
            known,
            ai,
            "albanian_passport",
            method=TrainingMethod.AI,
            note="AI kararı: `albanian_passport` (tür eşleşmesi, model sahte-model)",
        )
        unplaced = stage("kart.jpg", _image(210))
        leave_unplaced(
            session,
            unplaced,
            TrainingItemStatus.UNPLACED,
            note="Yapay zekâ önerisi: Library Card; bilinen türe inmedi",
            method=TrainingMethod.AI,
        )
        conflict = stage("ehliyet.jpg", _image(220))
        # Beklenen tür yapı kuralıyla mekanik tanınırdı; çelişki yapay zekânın sonucudur.
        conflict.hint_slug = "serbian_driving_license"
        leave_unplaced(
            session,
            conflict,
            TrainingItemStatus.CONFLICT,
            note="Beklenen `serbian_driving_license`, yapay zekâ `serbian_passport`",
            method=TrainingMethod.AI,
            slug="serbian_passport",
        )
        failed = stage("not.txt", b"duz metin")
        pending = stage("bekleyen.jpg", _image(230))
        session.commit()
        return {
            "mechanical": mechanical.id,
            "ai": ai.id,
            "unplaced": unplaced.id,
            "conflict": conflict.id,
            "failed": failed.id,
            "pending": pending.id,
        }


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("ai", ["ai"]),
        ("unplaced", ["unplaced"]),
        ("conflict", ["conflict"]),
        ("mechanical", ["mechanical"]),
        ("failed", ["failed"]),
    ],
)
def test_each_filter_lists_only_its_items(
    client: TestClient, states: dict[str, int], key: str, expected: list[str]
) -> None:
    page = client.get(f"/training?filter={key}")

    assert page.status_code == 200
    assert _row_ids(page.text) == [states[name] for name in expected]
    assert f'<a href="/training?filter={key}" class="active" aria-current="page">' in page.text


def test_the_unfiltered_table_lists_every_item_newest_first(
    client: TestClient, states: dict[str, int]
) -> None:
    page = client.get("/training")

    assert _row_ids(page.text) == sorted(states.values(), reverse=True)
    assert "6 dosya" in page.text
    assert 'hx-get="/training/items"' in page.text  # bekleyen öğe var


def test_the_ai_decision_row_carries_the_manual_check_icon(
    client: TestClient, states: dict[str, int]
) -> None:
    page = client.get("/training")

    ai_row = _row(page.text, states["ai"])
    assert "AI kararı" in ai_row
    assert ICON in ai_row and "⚠" in ai_row
    assert f'<span class="manual-check-text">{MANUAL_CHECK_TEXT}</span>' in ai_row
    assert "needs-check" in ai_row
    assert 'href="/training/known/albanian_passport">Albanian Passport</a>' in ai_row
    for name in ("mechanical", "unplaced", "conflict", "failed", "pending"):
        assert ICON not in _row(page.text, states[name]), name


def test_only_unplaced_and_conflict_rows_offer_place_into_type(
    client: TestClient, states: dict[str, int]
) -> None:
    page = client.get("/training")

    for name, offered in (
        ("unplaced", True),
        ("conflict", True),
        ("ai", False),
        ("mechanical", False),
        ("failed", False),
        ("pending", False),
    ):
        action = f'action="/training/items/{states[name]}/place"'
        assert (action in _row(page.text, states[name])) is offered, name
    assert '<datalist id="known-type-options">' in page.text
    conflict = _row(page.text, states["conflict"])
    assert "Çelişki" in conflict and "Serbian Driving License" in conflict


def test_a_run_link_narrows_the_table_to_that_run(
    client: TestClient, states: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    _upload(client, [("yeni.jpg", _image(300))])

    page = client.get("/training?run=2")
    (new_item,) = [item for item in _items(session_factory) if item.run_id == 2]
    assert _row_ids(page.text) == [new_item.id]
    assert 'aria-current="true"' in page.text
    assert "çalıştırma #2" in page.text
    # Bilinmeyen ve bozuk parametre sayfayı düşürmez.
    assert client.get("/training?run=abc&filter=nope").status_code == 200
    assert _row_ids(client.get("/training?run=999").text) == []


# --- türe yerleştir ---------------------------------------------------------------------------


def test_place_into_type_puts_the_unplaced_item_there_as_verified(
    client: TestClient,
    states: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    item_id = states["unplaced"]

    response = client.post(
        f"/training/items/{item_id}/place",
        data={"slug": "serbian_residence_card"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/training?run=1&notice=placed#item-{item_id}"
    with session_factory() as session:
        item = session.get_one(TrainingItem, item_id)
        assert (item.status, item.result_slug, item.method, item.decided_by) == (
            "placed",
            "serbian_residence_card",
            "manual",
            SIGNED_IN.username,
        )
        assert (item.note or "").startswith(
            "Elle yerleştirildi → `serbian_residence_card`; önceki not: Yapay zekâ önerisi"
        )
        record = session.scalars(
            select(ExampleFileRecord).where(ExampleFileRecord.training_item_id == item_id)
        ).one()
        assert (record.type_slug, record.method, record.label) == (
            "serbian_residence_card",
            "manual",
            "verified",
        )
        event = session.scalars(
            select(Event)
            .where(Event.type == EventType.TRAINING_EXAMPLE_PLACED.value)
            .order_by(Event.id.desc())
        ).first()
        assert event is not None and event.actor == SIGNED_IN.username
        assert event.data_json["training_item_id"] == item_id
        assert_employee_data_untouched(session, layout)
    assert [example.name for example in list_examples(layout, "serbian_residence_card")] == [
        "kart.jpg"
    ]
    page = client.get(response.headers["location"])
    row = _row(page.text, item_id)
    assert "Doğrulandı" in row and "İK (elle)" in row and ICON not in row
    assert "Öğe seçilen türe yerleşti" in page.text


def test_place_into_type_also_resolves_a_conflict(
    client: TestClient, states: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        f"/training/items/{states['conflict']}/place",
        data={"slug": "serbian_driving_license"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with session_factory() as session:
        item = session.get_one(TrainingItem, states["conflict"])
        assert (item.status, item.result_slug) == ("placed", "serbian_driving_license")


def test_place_into_type_keeps_the_duplicate_rule(
    client: TestClient,
    states: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    # Aynı içerik başka türde zaten örnekse öğe yerleşmez, çelişki olarak bekler.
    content = _image(240)
    with session_factory() as session:
        run = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")
        item = stage_and_recognize(
            session,
            layout,
            load_known_types(session),
            run,
            "tekrar.jpg",
            content,
            max_bytes=LIMIT,
            inventory=None,
        )
        leave_unplaced(
            session, item, TrainingItemStatus.UNPLACED, note="bilinmiyor", method=TrainingMethod.AI
        )
        # Öğe beklerken aynı içerik başka türe örnek olarak kaydedilmiş.
        session.add(
            ExampleFileRecord(
                type_slug="albanian_passport",
                name="baska.jpg",
                sha256=sha256_bytes(content),
                method="legacy",
            )
        )
        session.commit()
        item_id = item.id

    response = client.post(
        f"/training/items/{item_id}/place",
        data={"slug": "serbian_residence_card"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "notice=conflict" in response.headers["location"]
    assert list_examples(layout, "serbian_residence_card") == []
    with session_factory() as session:
        item = session.get_one(TrainingItem, item_id)
        assert item.status == "conflict"
        assert "başka türde örnek: albanian_passport" in (item.note or "")
    page = client.get(response.headers["location"])
    assert "Öğe yerleşmedi: aynı içerik başka bir türde örnek." in page.text


@pytest.mark.parametrize("name", ["ai", "mechanical", "failed", "pending"])
def test_place_into_type_refuses_items_not_waiting_for_hr(
    client: TestClient,
    states: dict[str, int],
    session_factory: sessionmaker[Session],
    name: str,
) -> None:
    item_id = states[name]
    with session_factory() as session:
        before = session.get_one(TrainingItem, item_id).status

    response = client.post(
        f"/training/items/{item_id}/place",
        data={"slug": "turkish_passport"},
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert NOT_MANUALLY_PLACEABLE in response.text
    with session_factory() as session:
        assert session.get_one(TrainingItem, item_id).status == before


@pytest.mark.parametrize("slug", ["", "yok_boyle_tur", "../turkish_passport"])
def test_place_into_type_refuses_an_unknown_type(
    client: TestClient,
    states: dict[str, int],
    session_factory: sessionmaker[Session],
    slug: str,
) -> None:
    response = client.post(
        f"/training/items/{states['unplaced']}/place", data={"slug": slug}, follow_redirects=False
    )

    assert response.status_code == 422
    assert UNKNOWN_TYPE_MESSAGE in response.text
    with session_factory() as session:
        assert session.get_one(TrainingItem, states["unplaced"]).status == "unplaced"


def test_place_into_type_of_a_missing_item_is_404(client: TestClient) -> None:
    response = client.post("/training/items/999/place", data={"slug": "turkish_passport"})

    assert response.status_code == 404


def test_place_into_type_when_the_training_copy_is_gone_changes_nothing(
    client: TestClient,
    states: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    with session_factory() as session:
        staged = layout.resolve(session.get_one(TrainingItem, states["unplaced"]).staged_path)
    staged.unlink()

    response = client.post(
        f"/training/items/{states['unplaced']}/place",
        data={"slug": "serbian_residence_card"},
        follow_redirects=False,
    )

    assert response.status_code == 409
    with session_factory() as session:
        assert session.get_one(TrainingItem, states["unplaced"]).status == "unplaced"
    assert list_examples(layout, "serbian_residence_card") == []


# --- bilinen belgeler -------------------------------------------------------------------------


def test_known_documents_list_catalog_and_suggested_types_with_counts(
    client: TestClient, states: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        total = len(load_known_types(session))

    page = client.get("/training/known")

    assert page.status_code == 200
    assert '<a href="/training/known" class="active" aria-current="page">' in page.text
    assert len(re.findall(r'<tr id="type-', page.text)) == total
    assert f"{total} tür" in page.text
    albanian = re.search(r'<tr id="type-albanian_passport">.*?</tr>', page.text, re.S).group(0)
    assert "Önerilen" in albanian and "ALB" in albanian
    cells = re.findall(r'<td class="num">(.*?)</td>', albanian, re.S)
    assert cells[0] == "1" and cells[2] == "0"
    assert cells[1].startswith("1 ") and ICON in cells[1]
    turkish = re.search(r'<tr id="type-turkish_passport">.*?</tr>', page.text, re.S).group(0)
    assert "Katalog" in turkish
    assert re.findall(r'<td class="num">(.*?)</td>', turkish, re.S) == ["1", "0", "0"]


@pytest.mark.parametrize(
    ("show", "expected"),
    [("examples", {"albanian_passport", "turkish_passport"}), ("ai", {"albanian_passport"})],
)
def test_known_documents_filters(
    client: TestClient, states: dict[str, int], show: str, expected: set[str]
) -> None:
    page = client.get(f"/training/known?show={show}")

    assert set(re.findall(r'<tr id="type-([a-z0-9_]+)">', page.text)) == expected


def test_a_suggested_type_detail_lists_its_examples_with_the_icon_and_image(
    client: TestClient, states: dict[str, int], layout: DataLayout
) -> None:
    page = client.get("/training/known/albanian_passport")

    assert page.status_code == 200
    assert "<h1>Albanian Passport</h1>" in page.text
    assert "Önerilen" in page.text
    assert "/document-types/albanian_passport" not in page.text  # katalogda değil
    url = "/training/known/albanian_passport/examples/arnavut.jpg"
    assert f'<img src="{url}"' in page.text
    assert "AI kararı" in page.text and ICON in page.text
    assert "AI kararı: `albanian_passport`" in page.text

    image = client.get(url)
    assert image.status_code == 200
    assert image.headers["x-content-type-options"] == "nosniff"
    assert image.content == _image(200)
    # Mevcut katalog uç noktası katalog dışı türde 404 verir; yeni uç nokta bu yüzden var.
    assert client.get("/document-types/albanian_passport/examples/arnavut.jpg").status_code == 404


def test_a_catalog_type_detail_links_its_type_page_and_shows_unlabeled_examples(
    client: TestClient, states: dict[str, int]
) -> None:
    page = client.get("/training/known/turkish_passport")

    assert 'href="/document-types/turkish_passport"' in page.text
    assert "pasaport.pdf" in page.text and "Mekanik" in page.text
    assert '<span class="no-image">PDF</span>' in page.text
    assert ICON not in page.text


def test_an_example_placed_before_training_is_listed_without_a_record(
    client: TestClient, layout: DataLayout
) -> None:
    content = _image(250)
    store_example(layout, "albanian_passport", "elle.jpg", content, FileKind.JPEG)

    page = client.get("/training/known/albanian_passport")

    assert "elle.jpg" in page.text
    assert ICON not in page.text
    response = client.get("/training/known/albanian_passport/examples/elle.jpg")
    assert sha256_bytes(response.content) == sha256_bytes(content)


@pytest.mark.parametrize(
    "path",
    [
        "/training/known/yok_boyle_tur",
        "/training/known/yok_boyle_tur/examples/arnavut.jpg",
        "/training/known/albanian_passport/examples/yok.jpg",
        "/training/known/albanian_passport/examples/..%2F..%2Fcatalog.yaml",
        "/training/known/albanian_passport/examples/..%5C..%5Ccatalog.yaml",
        "/training/known/..%2Fturkish_passport/examples/pasaport.pdf",
    ],
)
def test_unknown_types_and_escaping_names_are_404(
    client: TestClient, states: dict[str, int], path: str
) -> None:
    assert client.get(path).status_code == 404


def test_the_example_file_route_refuses_writes(client: TestClient, states: dict[str, int]) -> None:
    url = "/training/known/albanian_passport/examples/arnavut.jpg"

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, url, content=b"yeni icerik").status_code == 405, method
