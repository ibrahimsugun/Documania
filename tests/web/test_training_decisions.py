"""11.9.4 — Etiket kararı paneli: "AI kararı" örneğinde elle kontrol ikonu; Doğrula (tek ve toplu,
tek adım), Başka türe taşı ve Örneklerden çıkar (iki aşamalı onay, 10.8.1 belirteci; metinler
PLAN.md §D58'den birebir), katalog dışı işlemler olarak PRD §20.6'nın dışında
(`app.web.routers.training`, `app.training.decisions`).

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi ve yapay zekâ çağrısı yoktur
(CONVENTIONS §6). Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.db.models import (
    ConfirmationToken,
    Event,
    ExampleFileRecord,
    TrainingItem,
    TrainingMethod,
    TrainingRunKind,
)
from app.events import EventType
from app.storage import DataLayout
from app.storage.examples import check_example, list_examples, store_example
from app.training import create_run, load_known_types, place_example, stage_file
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, CONFIRMATION_TEXTS, Operation
from app.web.routers.training import (
    MANUAL_CHECK_TEXT,
    MOVE_FIRST_CONFIRMATION,
    MOVE_SECOND_CONFIRMATION,
    REMOVE_FIRST_CONFIRMATION,
    REMOVE_SECOND_CONFIRMATION,
    decision_subject,
)
from tests.fixtures.gen import make_portrait_image_bytes
from tests.training.invariants import assert_employee_data_untouched
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

LIMIT = 1024 * 1024
FROM_SLUG = "albanian_passport"
TO_SLUG = "afghan_passport"
PLAN = Path(__file__).resolve().parents[2] / "PLAN.md"
ICON = f'aria-label="{MANUAL_CHECK_TEXT}"'


@pytest.fixture(autouse=True)
def catalog(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture
def signed_client(client: TestClient) -> TestClient:
    # Onay belirteci oturum çerezine bağlıdır (10.8.1).
    client.cookies.set(SESSION_COOKIE, SESSION)
    return client


def _png(width: int) -> bytes:
    return make_portrait_image_bytes("PNG", (width, 300))


def _example(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    content: bytes,
    *,
    name: str = "ornek.png",
    slug: str = FROM_SLUG,
    method: TrainingMethod = TrainingMethod.AI,
) -> int:
    """Eğitimle yerleşmiş örnek (yapay zekâ yolunda "AI kararı" etiketli); kaydın kimliği."""
    with session_factory() as session:
        run = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")
        item = stage_file(session, layout, run, name, content, max_bytes=LIMIT)
        known = load_known_types(session)
        placement = place_example(session, layout, known, item, slug, method=method, note="not")
        session.commit()
        return placement.example.id


def _record(session_factory: sessionmaker[Session], example_id: int) -> ExampleFileRecord:
    with session_factory() as session:
        record = session.get_one(ExampleFileRecord, example_id)
        session.expunge(record)
        return record


def _events(session_factory: sessionmaker[Session], event_type: EventType) -> list[Event]:
    with session_factory() as session:
        rows = list(session.scalars(select(Event).where(Event.type == event_type.value)))
        for row in rows:
            session.expunge(row)
        return rows


def _files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _state(session_factory: sessionmaker[Session], layout: DataLayout) -> tuple[Any, ...]:
    """Kararın dokunabileceği her şey: dosyalar, örnek kayıtları, olay sayısı."""
    with session_factory() as session:
        records = [
            (r.id, r.type_slug, r.name, r.label, r.removed_at is None)
            for r in session.scalars(select(ExampleFileRecord).order_by(ExampleFileRecord.id))
        ]
        events = session.scalar(select(func.count()).select_from(Event))
    return _files(layout.root), records, events


def _token(page: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', page)
    assert match is not None, "belirteç yok"
    return match.group(1)


def _card(page: str, name: str) -> str:
    match = re.search(
        rf'<li class="thumb[^"]*"[^>]*>(?:(?!</li>).)*?{re.escape(name)}.*?</li>', page, re.S
    )
    assert match is not None, name
    return match.group(0)


# --- metinler ve §20.6 ------------------------------------------------------------------------


def _d58_texts() -> dict[str, tuple[str, str]]:
    text = PLAN.read_text(encoding="utf-8")
    block = text[text.index("- **D58 —") : text.index("- **D59 —")]
    flat = " ".join(block.split())
    found = {}
    for title in ("Eğitim örneğini başka türe taşı", "Eğitim örneğini örneklerden çıkar"):
        match = re.search(rf"{title} — birinci: `([^`]+)` · ikinci: `([^`]+)`", flat)
        assert match is not None, title
        found[title] = (match.group(1), match.group(2))
    return found


def test_the_confirmation_texts_are_plan_d58_verbatim() -> None:
    texts = _d58_texts()

    assert texts["Eğitim örneğini başka türe taşı"] == (
        MOVE_FIRST_CONFIRMATION,
        MOVE_SECOND_CONFIRMATION,
    )
    assert texts["Eğitim örneğini örneklerden çıkar"] == (
        REMOVE_FIRST_CONFIRMATION,
        REMOVE_SECOND_CONFIRMATION,
    )


def test_training_decisions_stay_outside_section_20_6() -> None:
    # §D58 a: K16 ve §20.6 değişmez; işlemler REANALYZE gibi tablo dışıdır.
    assert Operation.TRAINING_MOVE not in CONFIRMATION_TEXTS
    assert Operation.TRAINING_REMOVE not in CONFIRMATION_TEXTS
    assert len(CONFIRMATION_TEXTS) == 6


# --- ikon ve Doğrula -----------------------------------------------------------------------------


def test_the_type_page_shows_the_icon_and_the_decisions_only_where_they_apply(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    ai_id = _example(session_factory, layout, _png(200), name="ai.png")
    mechanical_id = _example(
        session_factory, layout, _png(210), name="mekanik.png", method=TrainingMethod.MECHANICAL
    )
    hand = _png(220)
    store_example(
        layout, FROM_SLUG, "elle.png", hand, check_example("elle.png", hand, max_bytes=LIMIT)
    )

    page = client.get(f"/training/known/{FROM_SLUG}").text

    ai, mechanical, manual = (_card(page, name) for name in ("ai.png", "mekanik.png", "elle.png"))
    assert ICON in ai and "needs-check" in ai
    assert f'action="/training/examples/{ai_id}/move/confirm"' in ai
    assert f'action="/training/examples/{ai_id}/remove/confirm"' in ai
    assert f'value="{ai_id}" form="verify-selected"' in ai and ">Doğrula</button>" in ai
    # Etiketsiz (mekanik) örnek taşınabilir/çıkarılabilir ama doğrulanacak bir şey yok.
    assert ICON not in mechanical and ">Doğrula</button>" not in mechanical
    assert f'action="/training/examples/{mechanical_id}/remove/confirm"' in mechanical
    # Kaydı olmayan örnek karar almaz.
    assert "/training/examples/" not in manual
    assert 'id="verify-selected"' in page and "Seçilenleri doğrula" in page


def test_verifying_one_example_removes_its_icon_and_logs_the_user(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    example_id = _example(session_factory, layout, _png(200))
    files = _files(layout.root)

    response = client.post(
        "/training/examples/verify",
        data={"example_ids": [example_id], "next": f"/training/known/{FROM_SLUG}"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/training/known/{FROM_SLUG}?notice=verified"
    assert _record(session_factory, example_id).label == "verified"
    assert _files(layout.root) == files  # tek adım; dosya işlemi değil
    (event,) = _events(session_factory, EventType.TRAINING_LABEL_VERIFIED)
    assert event.actor == SIGNED_IN.username
    assert event.data_json is not None and event.data_json["example_file_id"] == example_id
    assert _events(session_factory, EventType.USER_CONFIRMED) == []
    page = client.get(response.headers["location"]).text
    assert "örnekleri doğrulandı" in page
    assert ICON not in _card(page, "ornek.png") and "Doğrulandı" in _card(page, "ornek.png")


def test_bulk_verification_from_the_results_table(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    first = _example(session_factory, layout, _png(200), name="a.png")
    second = _example(session_factory, layout, _png(210), name="b.png")
    mechanical = _example(
        session_factory, layout, _png(220), name="c.png", method=TrainingMethod.MECHANICAL
    )
    page = client.get("/training").text
    assert page.count(ICON) == 2 and 'id="verify-results"' in page
    assert f'value="{first}" form="verify-results"' in page

    response = client.post(
        "/training/examples/verify",
        data={"example_ids": [first, second, mechanical], "next": "/training?filter=ai"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/training?filter=ai&notice=verified"
    labels = [_record(session_factory, key).label for key in (first, second, mechanical)]
    assert labels == ["verified", "verified", None]
    assert len(_events(session_factory, EventType.TRAINING_LABEL_VERIFIED)) == 2
    after = client.get(response.headers["location"]).text
    assert "Bu süzgece uyan dosya yok." in after  # "AI kararı" süzgecinden çıktılar
    assert ICON not in client.get("/training").text


@pytest.mark.parametrize(
    "next_url", ["https://kotu.example/x", "//kotu.example", "/training\\..", None]
)
def test_verification_without_a_selection_changes_nothing_and_never_leaves_the_tab(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    next_url: str | None,
) -> None:
    example_id = _example(session_factory, layout, _png(200))
    before = _state(session_factory, layout)
    data: dict[str, Any] = {} if next_url is None else {"next": next_url}

    response = client.post("/training/examples/verify", data=data, follow_redirects=False)

    assert response.headers["location"] == "/training?notice=verify_none"
    assert _state(session_factory, layout) == before
    assert _record(session_factory, example_id).label == "ai_decision"


# --- Başka türe taşı -----------------------------------------------------------------------------


def test_moving_takes_two_confirmations_and_then_moves_the_file(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = _png(200)
    example_id = _example(session_factory, layout, content)
    before = _state(session_factory, layout)
    base = f"/training/examples/{example_id}/move"

    first = signed_client.post(f"{base}/confirm", data={"slug": TO_SLUG})

    assert first.status_code == 200
    assert (
        "ornek.png örneğini Albanian Passport türünden Afghan Passport türüne taşımak "
        "üzeresiniz. Emin misiniz?"
    ) in html.unescape(first.text)
    assert f'action="{base}/prepare"' in first.text and 'name="confirmation"' not in first.text
    assert _state(session_factory, layout) == before

    second = signed_client.post(f"{base}/prepare", data={"slug": TO_SLUG})

    assert second.status_code == 200
    assert (
        "Örnek artık Afghan Passport türünün örneklerinde durur ve o türün açıklama üretimini "
        "etkiler. Son kararınız mı?"
    ) in html.unescape(second.text)
    token = _token(second.text)
    assert _state(session_factory, layout)[:2] == before[:2]  # yalnız belirteç yazıldı

    done = signed_client.post(
        base, data={"slug": TO_SLUG, "confirmation": token}, follow_redirects=False
    )

    assert done.status_code == 303
    assert done.headers["location"] == f"/training/known/{TO_SLUG}?notice=moved"
    assert [e.name for e in list_examples(layout, FROM_SLUG)] == []
    assert (layout.type_examples_dir(TO_SLUG) / "ornek.png").read_bytes() == content
    record = _record(session_factory, example_id)
    assert (record.type_slug, record.name, record.label) == (TO_SLUG, "ornek.png", "verified")
    (confirmed,) = _events(session_factory, EventType.USER_CONFIRMED)
    assert confirmed.actor == SIGNED_IN.username
    assert confirmed.data_json is not None
    assert confirmed.data_json["operation"] == "training_move"
    assert confirmed.data_json["target"] == {
        "example_file_id": example_id,
        "from_slug": FROM_SLUG,
        "to_slug": TO_SLUG,
    }
    (moved,) = _events(session_factory, EventType.TRAINING_EXAMPLE_MOVED)
    assert moved.actor == SIGNED_IN.username
    with session_factory() as session:
        item = session.scalar(select(TrainingItem))
        assert item is not None and item.result_slug == TO_SLUG
        assert_employee_data_untouched(session, layout)
    page = signed_client.get(done.headers["location"]).text
    assert "Örnek bu türe taşındı" in page and ICON not in page
    # Aynı belirteç ikinci kez geçmez; örnek artık o türde.
    again = signed_client.post(base, data={"slug": TO_SLUG, "confirmation": token})
    assert again.status_code in (400, 409)
    assert len(_events(session_factory, EventType.TRAINING_EXAMPLE_MOVED)) == 1


@pytest.mark.parametrize("case", ["missing", "unknown", "other_target", "other_operation"])
def test_a_move_without_its_own_token_does_nothing(
    signed_client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    case: str,
) -> None:
    example_id = _example(session_factory, layout, _png(200))
    with session_factory() as session:
        record = session.get_one(ExampleFileRecord, example_id)
        other_target = decision_subject(record, "turkish_passport")
        removal_target = decision_subject(record)
    token = {
        "missing": None,
        "unknown": "uydurma-belirtec",
        "other_target": issue_token(session_factory, Operation.TRAINING_MOVE, other_target),
        "other_operation": issue_token(session_factory, Operation.TRAINING_REMOVE, removal_target),
    }[case]
    before = _state(session_factory, layout)
    data = {"slug": TO_SLUG} | ({"confirmation": token} if token else {})

    response = signed_client.post(f"/training/examples/{example_id}/move", data=data)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in html.unescape(response.text)
    assert _state(session_factory, layout) == before


def test_a_token_prepared_for_one_target_does_not_move_to_another(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    example_id = _example(session_factory, layout, _png(200))
    base = f"/training/examples/{example_id}/move"
    token = _token(signed_client.post(f"{base}/prepare", data={"slug": TO_SLUG}).text)
    before = _state(session_factory, layout)

    response = signed_client.post(base, data={"slug": "turkish_passport", "confirmation": token})

    assert response.status_code == 400
    assert _state(session_factory, layout) == before


def test_a_move_into_a_taken_name_gets_the_next_suffix(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    other = _png(300)
    store_example(
        layout, TO_SLUG, "ornek.png", other, check_example("o.png", other, max_bytes=LIMIT)
    )
    example_id = _example(session_factory, layout, _png(200))
    base = f"/training/examples/{example_id}/move"
    token = _token(signed_client.post(f"{base}/prepare", data={"slug": TO_SLUG}).text)

    signed_client.post(base, data={"slug": TO_SLUG, "confirmation": token})

    assert _record(session_factory, example_id).name == "ornek-2.png"
    assert (layout.type_examples_dir(TO_SLUG) / "ornek.png").read_bytes() == other


@pytest.mark.parametrize(
    ("slug", "status_code", "message"),
    [
        ("bilinmeyen_tur", 422, "bilinen türlerden biri değil"),
        (FROM_SLUG, 409, "zaten bu türde"),
    ],
)
def test_an_impossible_move_is_refused_at_every_step(
    signed_client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    slug: str,
    status_code: int,
    message: str,
) -> None:
    example_id = _example(session_factory, layout, _png(200))
    before = _state(session_factory, layout)
    base = f"/training/examples/{example_id}/move"

    for url in (f"{base}/confirm", f"{base}/prepare", base):
        response = signed_client.post(url, data={"slug": slug, "confirmation": "x"})
        assert response.status_code == status_code, url
        assert message in html.unescape(response.text)
        assert f'href="/training/known/{FROM_SLUG}"' in response.text
    assert _state(session_factory, layout) == before
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ConfirmationToken)) == 0


def test_an_unknown_example_is_404(signed_client: TestClient) -> None:
    for url in ("/training/examples/999/move/confirm", "/training/examples/999/remove/prepare"):
        response = signed_client.post(url, data={"slug": TO_SLUG})
        assert response.status_code == 404
        assert "Eğitim örneği bulunamadı." in response.text


# --- Örneklerden çıkar ---------------------------------------------------------------------------


def test_removing_takes_two_confirmations_and_archives_without_deleting(
    signed_client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    content = _png(200)
    example_id = _example(session_factory, layout, content)
    before = _state(session_factory, layout)
    base = f"/training/examples/{example_id}/remove"

    first = signed_client.post(f"{base}/confirm")

    assert first.status_code == 200
    assert (
        "ornek.png örneğini Albanian Passport örneklerinden çıkarmak üzeresiniz. Emin misiniz?"
        in html.unescape(first.text)
    )
    assert _state(session_factory, layout) == before
    second = signed_client.post(f"{base}/prepare")
    assert (
        "Dosya silinmez, eğitim arşivine taşınır ve bu türün açıklama üretimine artık girmez. "
        "Son kararınız mı?"
    ) in html.unescape(second.text)
    assert signed_client.post(base).status_code == 400  # belirteçsiz
    assert _state(session_factory, layout)[:2] == before[:2]

    done = signed_client.post(
        base, data={"confirmation": _token(second.text)}, follow_redirects=False
    )

    assert done.status_code == 303
    assert done.headers["location"] == f"/training/known/{FROM_SLUG}?notice=removed"
    archived = layout.root / f"KnownDocuments/_egitim/cikarilan/{FROM_SLUG}/ornek.png"
    assert archived.read_bytes() == content
    assert list_examples(layout, FROM_SLUG) == []
    assert len(_files(layout.root)) == len(before[0])  # hiçbir dosya silinmedi
    record = _record(session_factory, example_id)
    assert record.removed_by == SIGNED_IN.username and record.removed_at is not None
    (confirmed,) = _events(session_factory, EventType.USER_CONFIRMED)
    assert confirmed.data_json is not None and confirmed.data_json["operation"] == "training_remove"
    (removed,) = _events(session_factory, EventType.TRAINING_EXAMPLE_REMOVED)
    assert removed.actor == SIGNED_IN.username
    page = signed_client.get(done.headers["location"]).text
    assert "eğitim arşivine taşındı" in page and "ornek.png" not in page
    results = signed_client.get("/training").text
    assert "Örneklerden çıkarıldı" in results and ICON not in results
    # Bilinen belgeler sayımı çıkarılanı saymaz.
    known = signed_client.get("/training/known?show=ai").text
    assert f'id="type-{FROM_SLUG}"' not in known
