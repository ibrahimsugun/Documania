"""10.3.1, 10.3.2 — yükleme detay sayfası (sayfa küçük resimleri, plan öğeleri, çıktılar, olay zaman
çizelgesi) ve yeniden çalıştır / yeniden analiz işlemleri.

Parti gerçek boru hattından geçer (`process_upload`, kayıtlı yanıt sağlayıcısı): sayfa yalnız
işlenmiş bir partinin verisini gösterir. Yapay zekâ canlı çağrılmaz. Yeniden analizin iki aşamalı
onayı sunucuda sınanır: yalnız birinci onayla, belirteçsiz, süresi geçmiş, başka partiye ya da başka
oturuma ait belirteçle gelen istek hiçbir şey değiştirmez (§20.6.2).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.web.confirm as confirm
from app.ai import PROVIDER_FACTORIES
from app.ai.provider import ProviderConfigError
from app.ai.recording_provider import RecordingProvider
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    Page,
    Plan,
    Upload,
    UploadStatus,
    utcnow,
)
from app.events import EventType
from app.pipeline.execute import PlanItemReferenceError
from app.pipeline.orchestrate import PlanExecutor, process_upload
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE, get_current_user
from app.web.routers import upload_page
from app.web.routers.upload_page import (
    CONFIRMATION_REFUSED,
    REANALYZE_FIRST_CONFIRMATION,
    REANALYZE_SECOND_CONFIRMATION,
    _employee_label,
    _page_ranges,
    get_reanalysis_provider,
)
from app.web.routers.uploads import get_plan_executor
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    SyntheticPage,
    blank_page,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
PASSPORT_NUMBER = "00 0000001"


def _passport(**options: object) -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA,
        document_number=PASSPORT_NUMBER,
        expiry_date=date(2030, 1, 1),
        **options,  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    """Onay belirteci oturum çerezinden türetilir; oturum bağımlılığı geçersiz kılındığı için çerez
    testte elle konur."""
    client.cookies.set(SESSION_COOKIE, "oturum-bir")


@pytest.fixture
def reanalysis_provider(app: FastAPI, tmp_path: Path) -> Iterator[RecordingProvider]:
    """Yeniden analizin sağlayıcısı: aynı pasaport sayfasının kayıtlı yanıtı."""
    recorded = recorded_provider(tmp_path / "yeniden", [_passport()])
    app.dependency_overrides[get_reanalysis_provider] = lambda: recorded
    yield recorded


def _processed(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    pages: list[SyntheticPage] | None = None,
    name: str = "pasaport.pdf",
) -> str:
    """Sentetik dosyayı yükler ve gerçek boru hattından geçirir; parti kimliğini döner."""
    pages = pages if pages is not None else [_passport()]
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
    response = client.post(
        "/api/uploads",
        files=[("files", (name, make_document_pdf_bytes(pages), "application/octet-stream"))],
    )
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    provider = recorded_provider(tmp_path / "kayit", pages)
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        process_upload(session, layout, upload, settings=SETTINGS, provider=provider)
    return upload_id


def _event_types(session_factory: sessionmaker[Session], upload_id: str) -> list[str]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event.type).where(Event.upload_id == upload_id).order_by(Event.ts, Event.id)
            )
        )


def _count(session_factory: sessionmaker[Session], model: type[Plan] | type[Document]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def _token(response_text: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', response_text)
    assert match is not None, response_text
    return match.group(1)


def _prepare_token(client: TestClient, upload_id: str) -> str:
    response = client.post(f"/uploads/{upload_id}/reanalyze/prepare")
    assert response.status_code == 200, response.text
    return _token(response.text)


# --- yardımcılar -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pages", "text"),
    [
        ((), "tüm dosya"),
        ((0,), "s. 1"),
        ((0, 1, 2), "s. 1–3"),
        ((0, 1, 2, 4), "s. 1–3, 5"),
        ((1, 3, 4), "s. 2, 4–5"),
    ],
)
def test_page_ranges_are_one_based_and_collapse_consecutive_pages(
    pages: tuple[int, ...], text: str
) -> None:
    assert _page_ranges(pages) == text


# --- 10.3.1: detay sayfası ---------------------------------------------------------------------


def test_detail_page_shows_thumbnails_plan_outputs_and_timeline_on_one_page(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)

    page = client.get(f"/uploads/{upload_id}")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert f"<title>Parti {upload_id} · belgeee</title>" in page.text
    assert f"<h1>Parti {upload_id}</h1>" in page.text
    assert "Tamamlandı" in page.text
    assert re.search(
        r'<a href="/uploads" class="active" aria-current="page">Yüklemeler</a>', page.text
    )
    # Dört bölüm aynı sayfada.
    for section in ("pages", "plan", "outputs", "timeline"):
        assert f'<section id="{section}"' in page.text
    # Sayfa küçük resmi: sayfanın görüntü adresi.
    with session_factory() as session:
        page_id = session.scalars(select(Page)).one().id
        item = session.scalars(select(Plan)).one().json["items"][0]
    assert f'<img src="/uploads/{upload_id}/pages/{page_id}/image"' in page.text
    assert "Sayfa 1" in page.text
    assert "pasaport.pdf" in page.text
    # Plan öğesi: kimlik, tür, kaynak, işlem, hedef ad, çalışan, rota ve doğrulamalar.
    plan_html = re.search(r'<section id="plan".*?</section>', page.text, re.S)
    assert plan_html is not None
    for expected in (
        "Sürüm 1",
        'id="item-i1"',
        "russian_passport",
        "pasaport.pdf · s. 1",
        f">{item['operation']}<",
        item["target_name"],
        "Ornekova",
        "Yeni çalışan · E0001",
        "Hazır",
        "✓ required_fields",
    ):
        assert expected in plan_html.group(0), expected
    # Çıktı: belge satırı, yolu ve kaynağı.
    outputs_html = re.search(r'<section id="outputs".*?</section>', page.text, re.S)
    assert outputs_html is not None
    for expected in ("E0001 — ", "russian_passport", "Hazir", "Etkin", "Sürüm 1"):
        assert expected in outputs_html.group(0), expected
    # Olay zaman çizelgesi: olaylar oluş sırasıyla.
    timeline = re.search(r'<section id="timeline".*?</section>', page.text, re.S)
    assert timeline is not None
    order = [
        timeline.group(0).index(event_type)
        for event_type in (
            EventType.FILE_UPLOADED,
            EventType.PAGE_ANALYZED,
            EventType.PLAN_CREATED,
            EventType.OUTPUT_SAVED,
        )
    ]
    assert order == sorted(order)


def test_detail_page_of_an_unknown_upload_is_404_with_a_message(client: TestClient) -> None:
    page = client.get("/uploads/u_yoktur")

    assert page.status_code == 404
    assert "Parti bulunamadı." in page.text
    assert 'role="alert"' in page.text


def test_detail_page_and_its_actions_need_a_session(app: FastAPI, client: TestClient) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app, follow_redirects=False)

    for method, path in (
        ("get", "/uploads/u_1"),
        ("get", "/uploads/u_1/pages/1/image"),
        ("post", "/uploads/u_1/rerun"),
        ("post", "/uploads/u_1/reanalyze/prepare"),
        ("post", "/uploads/u_1/reanalyze"),
    ):
        response = getattr(anonymous, method)(path)
        assert response.status_code in (303, 401), (method, path)


def test_detail_page_marks_blank_pages_and_the_plan_item_owning_each_page(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path, [_passport(), blank_page()])

    page = client.get(f"/uploads/{upload_id}")

    thumbs = re.findall(r'<li class="thumb">.*?</li>', page.text, re.S)
    assert len(thumbs) == 2
    assert "Sayfa 1" in thumbs[0] and ">i1<" in thumbs[0]
    assert "Sayfa 2" in thumbs[1] and ">Boş<" in thumbs[1]


def test_unreadable_item_shows_its_queue_row_and_reason(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    blurred = _passport(blurred={"document_number"}, mrz_legible=False)
    upload_id = _processed(client, session_factory, layout, tmp_path, [blurred])

    page = client.get(f"/uploads/{upload_id}")

    queue_html = re.search(r'<table class="queue">.*?</table>', page.text, re.S)
    assert queue_html is not None
    assert "Unreadable" in queue_html.group(0)
    assert "Okunamayan alanlar: document_number" in queue_html.group(0)
    assert "Bekliyor" in queue_html.group(0)
    plan_html = re.search(r'<section id="plan".*?</section>', page.text, re.S)
    assert plan_html is not None
    assert "Unreadable kuyruğu" in plan_html.group(0)
    assert "✗ required_fields" in plan_html.group(0)
    assert "Bu partiden henüz belge çıktısı yok." in page.text


def test_unprocessed_upload_shows_files_without_plan_and_offers_no_action(
    client: TestClient,
) -> None:
    content = make_document_pdf_bytes([_passport()])
    response = client.post("/api/uploads", files=[("files", ("a.pdf", content, "application/pdf"))])
    upload_id = response.json()["upload_id"]
    again = client.post("/api/uploads", files=[("files", ("b.pdf", content, "application/pdf"))])

    first = client.get(f"/uploads/{upload_id}")
    second = client.get(f"/uploads/{again.json()['upload_id']}")

    assert first.status_code == 200
    assert "Bu parti için henüz plan yok." in first.text
    assert "Bu parti için olay yok." not in first.text  # FILE_UPLOADED yazıldı
    assert "Sayfa görüntüsü yok" in first.text
    assert "Daha önce yüklenmiş" not in first.text
    assert "Daha önce yüklenmiş" in second.text
    assert "Tekrar dosya" in second.text
    for page in (first, second):
        assert upload_page.BUSY_MESSAGE in page.text
        assert 'id="rerun-button"' not in page.text
        assert 'id="reanalyze-step"' not in page.text


def test_tampered_plan_does_not_break_the_page_and_shows_the_reason(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    with session_factory() as session:
        plan = session.scalars(select(Plan)).one()
        plan.plan_hash = "0" * 64
        session.commit()

    page = client.get(f"/uploads/{upload_id}")

    assert page.status_code == 200
    assert "kaydıyla uyuşmuyor" in page.text
    assert 'id="item-i1"' not in page.text


def test_final_upload_without_a_plan_says_so_and_offers_no_action(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    content = make_document_pdf_bytes([_passport()])
    upload_id = client.post(
        "/api/uploads", files=[("files", ("a.pdf", content, "application/pdf"))]
    ).json()["upload_id"]
    with session_factory() as session:
        session.get_one(Upload, upload_id).status = UploadStatus.FAILED.value
        session.commit()

    page = client.get(f"/uploads/{upload_id}")

    assert "İşlenemedi" in page.text
    assert upload_page.NO_PLAN_MESSAGE in page.text
    assert 'id="rerun-button"' not in page.text
    assert 'id="reanalyze-step"' not in page.text


def test_an_employee_missing_from_the_registry_is_shown_by_its_number() -> None:
    assert _employee_label({}, "E0009") == "E0009"


def test_detail_page_lists_the_context_employee(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(
            Employee(id="E0007", folder_name="Ada_Ornek_E0007", given_names="Ada", surname="Ornek")
        )
        session.commit()
    response = client.post(
        "/api/uploads",
        data={"context_employee_id": "E0007"},
        files=[("files", ("a.pdf", make_document_pdf_bytes([_passport()]), "application/pdf"))],
    )

    page = client.get(f"/uploads/{response.json()['upload_id']}")

    assert "Bağlam çalışanı" in page.text
    assert "E0007 — Ada Ornek" in page.text


# --- 10.3.1: sayfa görüntüsü -------------------------------------------------------------------


def test_page_image_is_the_analysis_copy_and_only_served_for_its_own_upload(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    with session_factory() as session:
        page = session.scalars(select(Page)).one()
        stored = layout.resolve(page.image_path or "").read_bytes()
        page_id = page.id

    image = client.get(f"/uploads/{upload_id}/pages/{page_id}/image")

    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert image.content == stored
    other = client.get(f"/uploads/u_baska/pages/{page_id}/image")
    assert other.status_code == 404
    assert client.get(f"/uploads/{upload_id}/pages/99999/image").status_code == 404


@pytest.mark.parametrize("image_path", [None, "../disari.jpg", "cache/pages/9999/yok.jpg"])
def test_page_image_is_404_when_the_image_is_missing_or_escapes_the_data_dir(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    image_path: str | None,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    with session_factory() as session:
        page = session.scalars(select(Page)).one()
        page.image_path = image_path
        page_id = page.id
        session.commit()

    response = client.get(f"/uploads/{upload_id}/pages/{page_id}/image")

    assert response.status_code == 404
    assert "Sayfa görüntüsü bulunamadı." in response.text


# --- 10.3.2: yeniden çalıştır ------------------------------------------------------------------


def test_detail_page_offers_both_actions_and_the_first_confirmation(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)

    page = client.get(f"/uploads/{upload_id}")

    assert f'hx-post="/uploads/{upload_id}/rerun"' in page.text
    # Yeniden analiz doğrudan tetiklenmez: önce birinci onay metni, sonra hazırlık isteği.
    assert f'hx-post="/uploads/{upload_id}/reanalyze/prepare"' in page.text
    assert f'hx-post="/uploads/{upload_id}/reanalyze"' not in page.text
    assert f'<p class="confirm-text">{REANALYZE_FIRST_CONFIRMATION}</p>' in page.text
    assert 'id="action-result"' in page.text
    # 4xx/5xx işlem yanıtı da görünsün.
    assert "hx-on::before-swap" in page.text


def test_rerun_reapplies_the_current_plan_without_analysis_or_new_outputs(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    app.dependency_overrides[get_reanalysis_provider] = lambda: ProviderConfigError("kurulamaz")
    before = _event_types(session_factory, upload_id)

    response = client.post(f"/uploads/{upload_id}/rerun")

    assert response.status_code == 200
    assert "Plan (sürüm 1) yeniden uygulandı." in response.text
    assert _count(session_factory, Plan) == 1
    assert _count(session_factory, Document) == 1
    after = _event_types(session_factory, upload_id)
    assert after[: len(before)] == before
    assert EventType.PLAN_RERUN in after[len(before) :]
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        assert upload.status == UploadStatus.DONE


def test_rerun_of_a_failed_executor_is_409_and_changes_nothing(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)

    def _failing_executor() -> PlanExecutor:
        def _execute(*_args: object) -> None:
            raise PlanItemReferenceError("Plan öğesi bulunamadı.")

        return _execute

    app.dependency_overrides[get_plan_executor] = _failing_executor
    before = _event_types(session_factory, upload_id)

    response = client.post(f"/uploads/{upload_id}/rerun")

    assert response.status_code == 409
    assert "Plan öğesi bulunamadı." in response.text
    assert _event_types(session_factory, upload_id) == before


def test_rerun_is_refused_for_unknown_running_and_planless_uploads(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    unknown = client.post("/uploads/u_yoktur/rerun")
    received = client.post(
        "/api/uploads",
        files=[("files", ("a.pdf", make_document_pdf_bytes([_passport()]), "application/pdf"))],
    ).json()["upload_id"]
    running = client.post(f"/uploads/{received}/rerun")
    with session_factory() as session:
        session.get_one(Upload, received).status = UploadStatus.FAILED.value
        session.commit()
    planless = client.post(f"/uploads/{received}/rerun")

    assert unknown.status_code == 404 and upload_page.UPLOAD_NOT_FOUND in unknown.text
    assert running.status_code == 409 and upload_page.BUSY_MESSAGE in running.text
    assert planless.status_code == 409 and upload_page.NO_PLAN_MESSAGE in planless.text
    assert _event_types(session_factory, received) == [EventType.FILE_UPLOADED]


# --- 10.3.2: yeniden analiz — iki aşamalı onay -------------------------------------------------


def test_prepare_returns_the_second_confirmation_and_a_token_without_changing_anything(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    reanalysis_provider: RecordingProvider,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    before = _event_types(session_factory, upload_id)

    response = client.post(f"/uploads/{upload_id}/reanalyze/prepare")

    assert response.status_code == 200
    assert REANALYZE_SECOND_CONFIRMATION.replace('"', "&#34;") in response.text
    assert f'hx-post="/uploads/{upload_id}/reanalyze"' in response.text
    assert _token(response.text)
    # Yalnız birinci onayla hiçbir değişiklik yapılmaz (S16).
    assert _count(session_factory, Plan) == 1
    assert _event_types(session_factory, upload_id) == before
    assert len(reanalysis_provider.requests) == 0


def test_reanalysis_without_a_token_is_400_and_does_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    reanalysis_provider: RecordingProvider,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    before = _event_types(session_factory, upload_id)

    missing = client.post(f"/uploads/{upload_id}/reanalyze")
    blank = client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": ""})
    garbage = client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": "x.y"})
    shaped = client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": "1.deadbeef"})

    for response in (missing, blank, garbage, shaped):
        assert response.status_code == 400
        assert CONFIRMATION_REFUSED in response.text
    assert _count(session_factory, Plan) == 1
    assert _event_types(session_factory, upload_id) == before
    assert len(reanalysis_provider.requests) == 0


def test_confirmed_reanalysis_opens_a_new_plan_version_and_marks_old_outputs_superseded(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    reanalysis_provider: RecordingProvider,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    token = _prepare_token(client, upload_id)
    with session_factory() as session:
        old_document = session.scalars(select(Document)).one()
        old_path = layout.resolve(old_document.path)
        old_bytes = old_path.read_bytes()
        old_id = old_document.id

    response = client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": token})

    assert response.status_code == 200
    assert "yeni plan sürümü 2 (önceki: 1); 1 çıktı" in response.text
    assert len(reanalysis_provider.requests) > 0
    with session_factory() as session:
        assert sorted(plan.version for plan in session.scalars(select(Plan))) == [1, 2]
        # K18: eski çıktı silinmez ve yeniden adlandırılmaz, yalnız "eski sürüm" işaretlenir.
        old = session.get_one(Document, old_id)
        assert old.status == DocumentStatus.SUPERSEDED
        assert layout.resolve(old.path).read_bytes() == old_bytes
        assert old.path == old_document.path
    types = _event_types(session_factory, upload_id)
    assert types.index(EventType.USER_CONFIRMED) < types.index(EventType.PLAN_REANALYZED)
    # Onay olayı: kullanıcı adı, işlem, hedef ve iki onayın zamanı (§20.6.1).
    with session_factory() as session:
        confirmed = session.scalars(
            select(Event).where(Event.type == EventType.USER_CONFIRMED)
        ).one()
        assert confirmed.actor == "test-yonetici"
        data = confirmed.data_json
        assert data is not None
        assert data["operation"] == "reanalyze"
        assert data["target"]["upload_id"] == upload_id
        first = datetime.fromisoformat(data["first_confirmed_at"])
        second = datetime.fromisoformat(data["second_confirmed_at"])
        assert first <= second <= utcnow()
    # Detay sayfası iki sürümü de gösterir: eski çıktı "Eski sürüm", plan "1 eski sürüm var".
    page = client.get(f"/uploads/{upload_id}")
    assert "Sürüm 2 · 1 eski sürüm var" in page.text
    assert re.search(r'<tr id="output-\d+" class="output-superseded">', page.text)
    assert "Eski sürüm" in page.text


def test_a_token_works_once(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    reanalysis_provider: RecordingProvider,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    token = _prepare_token(client, upload_id)
    assert (
        client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": token}).status_code
        == 200
    )
    calls = len(reanalysis_provider.requests)
    events = _event_types(session_factory, upload_id)

    replay = client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": token})

    assert replay.status_code == 400
    assert _count(session_factory, Plan) == 2
    assert len(reanalysis_provider.requests) == calls
    assert _event_types(session_factory, upload_id) == events


def test_an_expired_token_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    reanalysis_provider: RecordingProvider,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    token = _prepare_token(client, upload_id)
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=5)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)

    response = client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": token})

    assert response.status_code == 400
    assert _count(session_factory, Plan) == 1
    assert len(reanalysis_provider.requests) == 0


def test_a_token_is_bound_to_its_upload_and_its_session(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    reanalysis_provider: RecordingProvider,
) -> None:
    first = _processed(client, session_factory, layout, tmp_path, name="bir.pdf")
    other_passport = passport_page(
        PERSON_ORNEKOVA, document_number="00 0000002", expiry_date=date(2031, 1, 1)
    )
    second = _processed(
        client, session_factory, layout, tmp_path / "ikinci", [other_passport], name="iki.pdf"
    )
    token = _prepare_token(client, first)

    other_upload = client.post(f"/uploads/{second}/reanalyze", data={"confirmation": token})
    client.cookies.set(SESSION_COOKIE, "oturum-iki")
    other_session = client.post(f"/uploads/{first}/reanalyze", data={"confirmation": token})

    assert other_upload.status_code == 400
    assert other_session.status_code == 400
    assert _count(session_factory, Plan) == 2  # yalnız iki partinin ilk planları
    assert len(reanalysis_provider.requests) == 0


def test_prepare_needs_a_session_cookie(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    client.cookies.clear()

    response = client.post(f"/uploads/{upload_id}/reanalyze/prepare")

    assert response.status_code == 400
    assert "Oturum çerezi yok." in response.text
    assert "confirmation" not in response.text


def test_reanalysis_without_a_provider_is_503_and_changes_nothing(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    token = _prepare_token(client, upload_id)
    app.dependency_overrides[get_reanalysis_provider] = lambda: ProviderConfigError(
        "ANTHROPIC_API_KEY eksik"
    )
    before = _event_types(session_factory, upload_id)

    response = client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": token})

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY eksik" in response.text
    assert _count(session_factory, Plan) == 1
    assert _event_types(session_factory, upload_id) == before


def test_a_failed_reanalysis_rolls_back_including_the_confirmation_event(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    reanalysis_provider: RecordingProvider,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)
    token = _prepare_token(client, upload_id)

    def _failing_executor() -> PlanExecutor:
        def _execute(*_args: object) -> None:
            raise PlanItemReferenceError("Plan öğesi bulunamadı.")

        return _execute

    app.dependency_overrides[get_plan_executor] = _failing_executor
    before = _event_types(session_factory, upload_id)

    response = client.post(f"/uploads/{upload_id}/reanalyze", data={"confirmation": token})

    assert response.status_code == 409
    assert "Plan öğesi bulunamadı." in response.text
    assert _count(session_factory, Plan) == 1
    assert _event_types(session_factory, upload_id) == before


def test_reanalysis_is_refused_for_unknown_running_and_planless_uploads(
    client: TestClient,
    session_factory: sessionmaker[Session],
    reanalysis_provider: RecordingProvider,
) -> None:
    received = client.post(
        "/api/uploads",
        files=[("files", ("a.pdf", make_document_pdf_bytes([_passport()]), "application/pdf"))],
    ).json()["upload_id"]

    unknown = client.post("/uploads/u_yoktur/reanalyze/prepare")
    running = client.post(f"/uploads/{received}/reanalyze/prepare")
    running_final = client.post(f"/uploads/{received}/reanalyze", data={"confirmation": "1.x"})
    with session_factory() as session:
        session.get_one(Upload, received).status = UploadStatus.FAILED.value
        session.commit()
    planless = client.post(f"/uploads/{received}/reanalyze/prepare")

    assert unknown.status_code == 404
    assert running.status_code == 409 and upload_page.BUSY_MESSAGE in running.text
    assert running_final.status_code == 409
    assert planless.status_code == 409 and upload_page.NO_PLAN_MESSAGE in planless.text
    assert _count(session_factory, Plan) == 0
    assert len(reanalysis_provider.requests) == 0


# --- 10.2 ile bağlantı -------------------------------------------------------------------------


def test_progress_view_links_to_the_detail_page(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    upload_id = _processed(client, session_factory, layout, tmp_path)

    progress = client.get(f"/upload/{upload_id}/progress")

    assert f'<a href="/uploads/{upload_id}">Parti ayrıntısını aç</a>' in progress.text


# --- yeniden analizin sağlayıcısı --------------------------------------------------------------


def test_reanalysis_provider_is_built_from_the_settings_or_reports_why_it_cannot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded = recorded_provider(tmp_path / "kayit", [_passport()])
    monkeypatch.setitem(PROVIDER_FACTORIES, "kayitli", lambda settings: recorded)
    configured = Settings(_env_file=None, database_url="sqlite://", ai_provider="kayitli")
    unconfigured = Settings(
        _env_file=None, database_url="sqlite://", ai_provider="anthropic", anthropic_api_key=None
    )

    assert get_reanalysis_provider(configured) is recorded
    assert isinstance(get_reanalysis_provider(unconfigured), ProviderConfigError)
