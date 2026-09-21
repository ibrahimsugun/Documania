"""11.5.1–11.5.4 — aday tür akışı panelde: liste (ad, görülme sayısı, örnek sayfalar), iki aşamalı
onayla kataloğa ekleme, onaydan sonra ilişkili Unknown öğelerinin toplu yeniden analizi ve ret.

Partiler gerçek boru hattından geçer (`process_upload`, kayıtlı yanıt sağlayıcısı): aday tür kaydı,
Unknown kuyruk öğeleri ve sayfa görüntüleri gerçek adımların ürünüdür. Yapay zekâ canlı çağrılmaz,
belgeler sentetiktir (CONVENTIONS §6). Onayın sunucu tarafı sınanır (§20.6.2): yalnız birinci
onayla, belirteçsiz, süresi geçmiş, başka kayda ya da adaya ait belirteçle gelen istek hiçbir şey
değiştirmez.

Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.web.confirm as confirm
from app.ai.provider import ProviderConfigError
from app.ai.recording_provider import RecordingProvider
from app.catalog import (
    CandidateDecidedError,
    CatalogEntry,
    FrontBackLayout,
    PageRange,
    create_type,
    export_catalog,
    import_catalog,
    load_seed_catalog,
)
from app.config import Settings
from app.db.models import (
    CandidateDocumentType,
    ConfirmationToken,
    Event,
    KnownDocumentType,
    Plan,
    QueueItem,
    Upload,
    UploadStatus,
    utcnow,
)
from app.events import EventType
from app.pipeline.execute import PlanItemReferenceError
from app.pipeline.orchestrate import PlanExecutor, plan_executor, process_upload
from app.pipeline.plan import Route, read_plan
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE
from app.web.routers import catalog as catalog_router
from app.web.routers.catalog import SLUG_TAKEN as SLUG_TAKEN_TEXT
from app.web.routers.upload_page import get_reanalysis_provider
from app.web.routers.uploads import get_plan_executor
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    PERSON_SIDOROV,
    SyntheticPage,
    SyntheticPerson,
    document_page,
    make_document_pdf_bytes,
    recorded_provider,
    unknown_document_page,
)
from tests.web.conftest import SIGNED_IN, issue_token

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
BASE = "/document-types/candidate-types"
DIPLOMA = "peruvian_diploma"
DIPLOMA_NAME = "Peruvian Diploma"
DIPLOMA_FIELDS = ("surname", "given_names", "document_number")
PERMIT_NAME = "Chilean Permit"
FIRST_NUMBER = "DIP-0000077"
SECOND_NUMBER = "DIP-0000078"
# §20.6 "Yeni belge türünü onayla" — birebir.
FIRST_TEXT = (
    "Peruvian Diploma belge türünü standart türler arasına eklemek üzeresiniz. Emin misiniz?"
)
SECOND_TEXT = "Bu işlem bundan sonraki tüm belge analizlerini etkileyecektir. Son kararınız mı?"
# Şablon kesme işaretini kaçışlar.
SLUG_TAKEN = SLUG_TAKEN_TEXT.replace("'", "&#39;")
BATCH_SECOND_TEXT = (
    "Bu işlem her partiye yeni bir plan sürümü açacak; önceki sürümlerin çıktıları "
    "&#34;eski sürüm&#34; olarak işaretlenecektir. Son kararınız mı?"
)


def _unknown(person: SyntheticPerson, number: str, name: str = DIPLOMA_NAME) -> SyntheticPage:
    return unknown_document_page(
        person, candidate_type_name=name, title="DIPLOMA", document_number=number
    )


def _known(person: SyntheticPerson, number: str) -> SyntheticPage:
    """Onaydan sonra aynı sayfanın kataloğun türüyle okunuşu."""
    return document_page(
        DIPLOMA,
        title="DIPLOMA",
        person=person,
        document_number=number,
        shows=("surname", "given_names", "date_of_birth", "document_number"),
        language="es",
        script="latin",
        required_fields=DIPLOMA_FIELDS,
    )


def _form(**overrides: Any) -> dict[str, Any]:
    """Onay formunun gönderdiği alanlar; `None` verilen alan hiç gönderilmez (işaretsiz kutu)."""
    data: dict[str, Any] = {
        "slug": DIPLOMA,
        "name": DIPLOMA_NAME,
        "file_label": "Diploma",
        "country": "pe",
        "description": "",
        "expected_file_types": ["pdf", "jpeg", "png"],
        "pages_min": "1",
        "pages_max": "1",
        "sides": "single",
        "analyze": "on",
        "required_fields": "surname, given_names, document_number",
        "allowed_conversions": ["wrap_image"],
        "output_format": "pdf",
        "acceptance_criteria": ["Mühür görünür", ""],
        "prompt_description": 'Peru\'da verilmiş diploma; sağ üstte "DIP" numarası.',
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


EXPECTED_ENTRY = CatalogEntry.model_validate(
    {
        "slug": DIPLOMA,
        "name": DIPLOMA_NAME,
        "file_label": "Diploma",
        "country": "PE",
        "expected_file_types": ["pdf", "jpeg", "png"],
        "expected_pages": {"min": 1, "max": 1},
        "sides": "single",
        "direct": False,
        "analyze": True,
        "required_fields": list(DIPLOMA_FIELDS),
        "allowed_conversions": ["wrap_image"],
        "output_format": "pdf",
        "acceptance_criteria": ["Mühür görünür"],
        "prompt_description": 'Peru\'da verilmiş diploma; sağ üstte "DIP" numarası.',
    }
)


def _hidden(html: str) -> dict[str, list[str]]:
    """Adım sayfasının gizli alanları: bir sonraki adıma tarayıcının göndereceği değerler."""
    fields: dict[str, list[str]] = {}
    for name, value in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', html):
        fields.setdefault(name, []).append(unescape(value))
    return fields


@dataclass(frozen=True, slots=True)
class Seen:
    """Üç parti: iki Peru diploması (aynı aday tür) ve bir Şili izni (başka aday tür)."""

    first: str
    second: str
    permit_upload: str
    diploma: int
    permit: int


def _process(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    directory: Path,
    pages: list[SyntheticPage],
    name: str,
) -> str:
    response = client.post(
        "/api/uploads",
        files=[("files", (name, make_document_pdf_bytes(pages), "application/octet-stream"))],
    )
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        process_upload(
            session, layout, upload, settings=SETTINGS, provider=recorded_provider(directory, pages)
        )
    return upload_id


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    """Onay belirteci oturum çerezinden türetilir; oturum bağımlılığı geçersiz kılındığı için çerez
    testte elle konur."""
    client.cookies.set(SESSION_COOKIE, "oturum-bir")


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


@pytest.fixture
def seen(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    seeded: None,
) -> Seen:
    first = _process(
        client,
        session_factory,
        layout,
        tmp_path / "bir",
        [_unknown(PERSON_PRUEBA, FIRST_NUMBER)],
        "diploma-bir.pdf",
    )
    second = _process(
        client,
        session_factory,
        layout,
        tmp_path / "iki",
        [_unknown(PERSON_SIDOROV, SECOND_NUMBER)],
        "diploma-iki.pdf",
    )
    permit = _process(
        client,
        session_factory,
        layout,
        tmp_path / "uc",
        [_unknown(PERSON_ORNEKOVA, "CL-0000001", PERMIT_NAME)],
        "izin.pdf",
    )
    with session_factory() as session:
        ids = {row.proposed_name: row.id for row in session.scalars(select(CandidateDocumentType))}
    return Seen(first, second, permit, ids[DIPLOMA_NAME], ids[PERMIT_NAME])


@pytest.fixture
def reanalysis_provider(app: FastAPI, tmp_path: Path) -> Iterator[RecordingProvider]:
    """Toplu yeniden analizin sağlayıcısı: iki diplomanın katalog türüyle kayıtlı yanıtları, parti
    sırasıyla."""
    recorded = recorded_provider(
        tmp_path / "yeniden",
        [_known(PERSON_PRUEBA, FIRST_NUMBER)],
        [_known(PERSON_SIDOROV, SECOND_NUMBER)],
    )
    app.dependency_overrides[get_reanalysis_provider] = lambda: recorded
    yield recorded


def _candidate(session_factory: sessionmaker[Session], candidate_id: int) -> CandidateDocumentType:
    with session_factory() as session:
        row = session.get_one(CandidateDocumentType, candidate_id)
        session.expunge(row)
    return row


def _events(session_factory: sessionmaker[Session], *types: EventType) -> list[Event]:
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(Event)
                .where(Event.type.in_([each.value for each in types]))
                .order_by(Event.id)
            )
        )
        session.expunge_all()
    return rows


def _count(session_factory: sessionmaker[Session], model: type[Any]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def _plans(session_factory: sessionmaker[Session], upload_id: str) -> list[Plan]:
    with session_factory() as session:
        rows = list(
            session.scalars(select(Plan).where(Plan.upload_id == upload_id).order_by(Plan.version))
        )
        session.expunge_all()
    return rows


def _diploma_type(session_factory: sessionmaker[Session]) -> KnownDocumentType | None:
    with session_factory() as session:
        return session.get(KnownDocumentType, DIPLOMA)


def _unchanged(session_factory: sessionmaker[Session], seen: Seen) -> None:
    """Hiçbir şey yazılmadı: tür katalogda yok, aday bekliyor, karar olayı yok."""
    assert _diploma_type(session_factory) is None
    assert _candidate(session_factory, seen.diploma).status == "pending"
    assert (
        _events(
            session_factory,
            EventType.USER_CONFIRMED,
            EventType.TYPE_APPROVED,
            EventType.TYPE_REJECTED,
        )
        == []
    )


def _confirmed(client: TestClient, candidate_id: int, data: dict[str, Any]) -> Any:
    """Birinci onay adımı (hiçbir şey değişmez)."""
    response = client.post(f"{BASE}/{candidate_id}/approve/confirm", data=data)
    assert response.status_code == 200, response.text
    return response


def _prepared(client: TestClient, candidate_id: int, data: dict[str, Any]) -> dict[str, list[str]]:
    """Birinci ve ikinci onay adımları; ikinci adımın gizli alanları (belirteç dahil)."""
    first = _confirmed(client, candidate_id, data)
    second = client.post(f"{BASE}/{candidate_id}/approve/prepare", data=_hidden(first.text))
    assert second.status_code == 200, second.text
    return _hidden(second.text)


def _approve(client: TestClient, candidate_id: int, data: dict[str, Any] | None = None) -> None:
    fields = _prepared(client, candidate_id, data or _form())
    response = client.post(f"{BASE}/{candidate_id}/approve", data=fields, follow_redirects=False)
    assert response.status_code == 303, response.text


def _batch_token(client: TestClient, candidate_id: int) -> str:
    response = client.post(f"{BASE}/{candidate_id}/reanalyze/prepare")
    assert response.status_code == 200, response.text
    return _hidden(response.text)["confirmation"][0]


def _open_unknown(session_factory: sessionmaker[Session], upload_id: str) -> list[QueueItem]:
    with session_factory() as session:
        plan = session.scalars(
            select(Plan).where(Plan.upload_id == upload_id).order_by(Plan.version.desc())
        ).first()
        rows = list(
            session.scalars(
                select(QueueItem).where(
                    QueueItem.upload_id == upload_id,
                    QueueItem.kind == "unknown",
                    QueueItem.resolved_at.is_(None),
                    QueueItem.plan_id == (plan.id if plan is not None else None),
                )
            )
        )
        session.expunge_all()
    return rows


# --- 11.5.1: liste --------------------------------------------------------------------------------


def test_candidates_are_listed_with_their_name_seen_count_and_sample_pages(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    page = client.get(BASE)

    assert page.status_code == 200
    assert "<title>Aday türler · belgeee</title>" in page.text
    html = page.text
    diploma_row = html[html.index(f'href="{BASE}/{seen.diploma}"') :]
    permit_row = html[html.index(f'href="{BASE}/{seen.permit}"') :]
    # Görülme sayısına göre: iki kez görülen diploma önce.
    assert html.index(f'href="{BASE}/{seen.diploma}"') < html.index(f'href="{BASE}/{seen.permit}"')
    assert diploma_row.index(DIPLOMA_NAME) < diploma_row.index('<td class="seen-count">2</td>')
    assert '<td class="seen-count">1</td>' in permit_row
    with session_factory() as session:
        pages = {
            row.proposed_name: row.sample_page_ids
            for row in session.scalars(select(CandidateDocumentType))
        }
    uploads = {seen.first: pages[DIPLOMA_NAME][0], seen.second: pages[DIPLOMA_NAME][1]}
    for upload_id, page_id in uploads.items():
        assert f'<img src="/uploads/{upload_id}/pages/{page_id}/image"' in html
        image = client.get(f"/uploads/{upload_id}/pages/{page_id}/image")
        assert image.status_code == 200
        assert image.headers["content-type"].startswith("image/")
    assert "diploma-bir.pdf</a> · s. 1" in html
    assert f'<img src="/uploads/{seen.permit_upload}/pages/{pages[PERMIT_NAME][0]}/image"' in html
    assert "Onaylanan, Unknown öğesi bekleyen adaylar" not in html


def test_the_catalog_page_links_to_the_candidates_with_the_pending_count(
    client: TestClient, seen: Seen
) -> None:
    page = client.get("/document-types")

    assert f'<a href="{BASE}">Aday türler</a>' in page.text
    assert "(2 onay bekliyor)" in page.text


def test_without_candidates_the_list_says_so(client: TestClient, seeded: None) -> None:
    page = client.get(BASE)

    assert page.status_code == 200
    assert "Onay bekleyen aday tür yok." in page.text
    assert "(0 onay bekliyor)" in client.get("/document-types").text


def test_candidate_page_shows_samples_related_unknown_items_and_a_prefilled_form(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    page = client.get(f"{BASE}/{seen.diploma}")

    assert page.status_code == 200
    assert "<h1>Aday tür: Peruvian Diploma</h1>" in page.text
    assert "Onay bekliyor" in page.text
    for upload_id in (seen.first, seen.second):
        (item,) = _open_unknown(session_factory, upload_id)
        assert f'<a href="/queues/{item.id}">Öğe {item.id}</a>' in page.text
        assert f'<img src="/uploads/{upload_id}/pages/' in page.text
    (permit_item,) = _open_unknown(session_factory, seen.permit_upload)
    assert f'href="/queues/{permit_item.id}"' not in page.text
    assert "diploma-iki.pdf · s. 1" in page.text
    # Tür formu adayın adıyla açılır; yapı İK'nındır.
    assert 'name="slug" value="peruvian_diploma"' in page.text
    assert 'name="name" value="Peruvian Diploma"' in page.text
    assert 'name="file_label" value="Peruvian Diploma"' in page.text
    assert f'action="{BASE}/{seen.diploma}/approve/confirm"' in page.text
    assert f'action="{BASE}/{seen.diploma}/reject"' in page.text
    assert "/reanalyze/prepare" not in page.text


def test_an_unknown_candidate_is_404(client: TestClient, seeded: None) -> None:
    assert client.get(f"{BASE}/404").status_code == 404
    for action in ("approve/confirm", "approve/prepare", "approve"):
        response = client.post(f"{BASE}/404/{action}", data=_form())
        assert response.status_code == 404, action
        assert "Aday tür bulunamadı." in response.text
    for action in ("reject", "reanalyze/prepare", "reanalyze"):
        assert client.post(f"{BASE}/404/{action}").status_code == 404, action


# --- 11.5.2: onay ---------------------------------------------------------------------------------


def test_approval_takes_two_confirmations_and_puts_the_type_in_the_catalog(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    first = _confirmed(client, seen.diploma, _form())

    assert f'<p class="confirm-text" role="alert">{FIRST_TEXT}</p>' in first.text
    assert "<dt>Ülke</dt><dd>PE</dd>" in first.text
    assert "<dt>Kabul kriterleri</dt><dd>Mühür görünür</dd>" in first.text
    assert f'action="{BASE}/{seen.diploma}/approve/prepare"' in first.text
    assert "confirmation" not in _hidden(first.text)
    _unchanged(session_factory, seen)
    assert _count(session_factory, ConfirmationToken) == 0

    second = client.post(f"{BASE}/{seen.diploma}/approve/prepare", data=_hidden(first.text))

    assert second.status_code == 200
    assert f'<p class="confirm-text" role="alert">{SECOND_TEXT}</p>' in second.text
    assert f'action="{BASE}/{seen.diploma}/approve"' in second.text
    _unchanged(session_factory, seen)

    done = client.post(
        f"{BASE}/{seen.diploma}/approve", data=_hidden(second.text), follow_redirects=False
    )

    assert done.status_code == 303
    assert done.headers["location"] == f"{BASE}/{seen.diploma}?notice=approved"
    with session_factory() as session:
        assert export_catalog(session).get(DIPLOMA) == EXPECTED_ENTRY
    assert _candidate(session_factory, seen.diploma).status == "approved"
    confirmed, approved = _events(
        session_factory, EventType.USER_CONFIRMED, EventType.TYPE_APPROVED
    )
    assert (confirmed.type, confirmed.actor) == (EventType.USER_CONFIRMED, SIGNED_IN.username)
    assert confirmed.data_json is not None
    assert confirmed.data_json["operation"] == "approve_type"
    assert confirmed.data_json["target"] == {
        "candidate_type_id": seen.diploma,
        "document_type_slug": DIPLOMA,
    }
    first_at = datetime.fromisoformat(confirmed.data_json["first_confirmed_at"])
    assert first_at <= datetime.fromisoformat(confirmed.data_json["second_confirmed_at"])
    assert (approved.type, approved.actor) == (EventType.TYPE_APPROVED, SIGNED_IN.username)
    assert approved.data_json == {
        "candidate_type_id": seen.diploma,
        "candidate_type_name": DIPLOMA_NAME,
        "document_type_slug": DIPLOMA,
    }

    detail = client.get(done.headers["location"])
    assert "Aday tür standart türler arasına eklendi" in detail.text
    assert f'<a href="/document-types/{DIPLOMA}"><code>{DIPLOMA}</code></a>' in detail.text
    assert "/approve/confirm" not in detail.text
    assert "/reject" not in detail.text
    listing = client.get(BASE).text
    assert f'<td><a href="{BASE}/{seen.diploma}">' not in listing
    assert f"{DIPLOMA_NAME}</a> — 2 bekleyen Unknown öğesi" in listing
    assert "(1 onay bekliyor)" in client.get("/document-types").text


def test_a_front_back_candidate_keeps_its_layouts_through_both_confirmations(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    # 04.1.2, 11.1.2: onay formunda seçilen düzen gizli alanla adımlar arasında taşınır; sayfa
    # aralığı (formda 1–1 yazsa da) düzenlerden türer.
    data = _form(sides="front_back", front_back_layouts=["separate", "combined"])

    first = _confirmed(client, seen.diploma, data)

    assert (
        "<dt>Kabul edilen düzenler</dt><dd>Ön ve arka ayrı sayfalarda, İki yüz tek sayfada</dd>"
        in first.text
    )
    assert "<dt>Beklenen sayfa sayısı</dt><dd>1 – 2</dd>" in first.text
    assert _hidden(first.text)["front_back_layouts"] == ["separate", "combined"]
    _approve(client, seen.diploma, data)

    with session_factory() as session:
        entry = export_catalog(session).get(DIPLOMA)
    assert entry is not None
    assert entry.front_back_layouts == (FrontBackLayout.SEPARATE, FrontBackLayout.COMBINED)
    assert entry.expected_pages == PageRange(min=1, max=2)


def test_the_first_confirmation_or_a_missing_token_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    first = _confirmed(client, seen.diploma, _form())

    missing = client.post(f"{BASE}/{seen.diploma}/approve", data=_hidden(first.text))
    blank = client.post(
        f"{BASE}/{seen.diploma}/approve", data={**_hidden(first.text), "confirmation": ""}
    )
    garbage = client.post(
        f"{BASE}/{seen.diploma}/approve", data={**_hidden(first.text), "confirmation": "x.y"}
    )

    for response in (missing, blank, garbage):
        assert response.status_code == 400
        assert "Onay geçersiz" in response.text
    _unchanged(session_factory, seen)


def test_the_token_is_single_use_and_bound_to_the_entry_and_the_candidate(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    fields = _prepared(client, seen.diploma, _form())

    renamed = client.post(
        f"{BASE}/{seen.diploma}/approve", data={**fields, "name": ["Diploma of Peru"]}
    )
    elsewhere = client.post(f"{BASE}/{seen.permit}/approve", data=fields)

    assert renamed.status_code == 400
    assert elsewhere.status_code == 400
    _unchanged(session_factory, seen)

    done = client.post(f"{BASE}/{seen.diploma}/approve", data=fields, follow_redirects=False)
    replay = client.post(f"{BASE}/{seen.diploma}/approve", data=fields)

    assert done.status_code == 303
    assert replay.status_code == 409
    assert "Bu aday tür onaylanmış; yeniden karara bağlanamaz." in replay.text
    assert len(_events(session_factory, EventType.TYPE_APPROVED)) == 1


def test_a_token_of_another_operation_or_an_expired_one_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    session_factory: sessionmaker[Session],
    seen: Seen,
) -> None:
    fields = _prepared(client, seen.diploma, _form())
    subject = catalog_router.approval_subject(seen.diploma, EXPECTED_ENTRY)
    other = issue_token(session_factory, confirm.Operation.REANALYZE, subject)

    wrong_operation = client.post(
        f"{BASE}/{seen.diploma}/approve", data={**fields, "confirmation": [other]}
    )
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=5)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)
    expired = client.post(f"{BASE}/{seen.diploma}/approve", data=fields)

    assert wrong_operation.status_code == 400
    assert expired.status_code == 400
    _unchanged(session_factory, seen)


def test_an_invalid_form_is_redrawn_with_its_values_at_every_step(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    data = _form(direct="on", name="Diploma of Peru")

    for action in ("approve/confirm", "approve/prepare", "approve"):
        response = client.post(f"{BASE}/{seen.diploma}/{action}", data=data)

        assert response.status_code == 422, action
        assert "Tür eklenmedi: alanların altındaki uyarıları düzeltin." in response.text
        assert "Direkt Belge (direct: true) türünde allowed_conversions boş olmalı" in response.text
        assert 'name="name" value="Diploma of Peru"' in response.text
        assert 'name="direct" checked' in response.text
    _unchanged(session_factory, seen)
    assert _count(session_factory, ConfirmationToken) == 0


def test_a_slug_already_in_the_catalog_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    response = client.post(
        f"{BASE}/{seen.diploma}/approve/confirm", data=_form(slug="russian_passport")
    )

    assert response.status_code == 409
    assert SLUG_TAKEN in response.text
    assert 'name="slug" value="russian_passport"' in response.text
    _unchanged(session_factory, seen)


def test_a_slug_taken_after_the_second_confirmation_keeps_the_token(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    fields = _prepared(client, seen.diploma, _form())
    with session_factory() as session:
        create_type(session, EXPECTED_ENTRY.model_copy(update={"name": "Başka tür"}))
        session.commit()

    response = client.post(f"{BASE}/{seen.diploma}/approve", data=fields)

    assert response.status_code == 409
    assert SLUG_TAKEN in response.text
    assert _candidate(session_factory, seen.diploma).status == "pending"
    with session_factory() as session:
        (token,) = session.scalars(select(ConfirmationToken)).all()
        assert token.consumed_at is None
        assert session.get_one(KnownDocumentType, DIPLOMA).name == "Başka tür"
    assert _events(session_factory, EventType.USER_CONFIRMED, EventType.TYPE_APPROVED) == []


def test_a_decision_lost_to_a_concurrent_one_is_409_and_keeps_the_token(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    session_factory: sessionmaker[Session],
    seen: Seen,
) -> None:
    fields = _prepared(client, seen.diploma, _form())

    def lost(_session: Session, candidate_id: int, *_args: object, **_kwargs: object) -> None:
        raise CandidateDecidedError(candidate_id, "rejected")

    monkeypatch.setattr(catalog_router, "approve_candidate_type", lost)

    response = client.post(f"{BASE}/{seen.diploma}/approve", data=fields)

    assert response.status_code == 409
    assert "Bu aday tür reddedilmiş; yeniden karara bağlanamaz." in response.text
    _unchanged(session_factory, seen)
    with session_factory() as session:
        (token,) = session.scalars(select(ConfirmationToken)).all()
        assert token.consumed_at is None


def test_prepare_needs_a_session_cookie(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    first = _confirmed(client, seen.diploma, _form())
    client.cookies.clear()

    response = client.post(f"{BASE}/{seen.diploma}/approve/prepare", data=_hidden(first.text))

    assert response.status_code == 400
    assert "Oturum çerezi yok." in response.text
    assert "confirmation" not in _hidden(response.text)
    _unchanged(session_factory, seen)


# --- 11.5.4: ret ----------------------------------------------------------------------------------


def test_a_rejected_candidate_never_returns_to_the_list(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    seen: Seen,
) -> None:
    catalog_before = _count(session_factory, KnownDocumentType)

    response = client.post(f"{BASE}/{seen.diploma}/reject", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"{BASE}?notice=rejected"
    listing = client.get(response.headers["location"]).text
    assert "Aday tür reddedildi; bir daha listeye düşmez." in listing
    assert DIPLOMA_NAME not in listing
    assert PERMIT_NAME in listing
    (event,) = _events(session_factory, EventType.TYPE_REJECTED)
    assert event.actor == SIGNED_IN.username
    assert event.data_json == {
        "candidate_type_id": seen.diploma,
        "candidate_type_name": DIPLOMA_NAME,
    }
    assert _count(session_factory, KnownDocumentType) == catalog_before
    # Belgeler Unknown kuyruğunda kalır; hiçbir şey taşınmaz.
    assert len(_open_unknown(session_factory, seen.first)) == 1
    detail = client.get(f"{BASE}/{seen.diploma}").text
    assert "Reddedildi" in detail
    assert "Bu aday reddedildi; bir daha listeye düşmez." in detail
    assert "/approve/confirm" not in detail

    # Aynı tür yeniden önerilir: görülme sayılır, aday listeye geri düşmez.
    _process(
        client,
        session_factory,
        layout,
        tmp_path / "dort",
        [_unknown(PERSON_PRUEBA, "DIP-0000079", "PERUVIAN diploma")],
        "diploma-uc.pdf",
    )

    candidate = _candidate(session_factory, seen.diploma)
    assert (candidate.status, candidate.seen_count) == ("rejected", 3)
    assert DIPLOMA_NAME not in client.get(BASE).text
    assert "(1 onay bekliyor)" in client.get("/document-types").text


def test_a_decided_candidate_is_neither_approved_nor_rejected_again(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    assert client.post(f"{BASE}/{seen.diploma}/reject", follow_redirects=False).status_code == 303

    again = client.post(f"{BASE}/{seen.diploma}/reject")
    for action in ("approve/confirm", "approve/prepare", "approve"):
        response = client.post(f"{BASE}/{seen.diploma}/{action}", data=_form())
        assert response.status_code == 409, action
        assert "Bu aday tür reddedilmiş; yeniden karara bağlanamaz." in response.text

    assert again.status_code == 409
    assert len(_events(session_factory, EventType.TYPE_REJECTED)) == 1
    assert _diploma_type(session_factory) is None


# --- 11.5.3: toplu yeniden analiz ----------------------------------------------------------------


def test_after_approval_related_unknown_items_are_reanalyzed_together(
    client: TestClient,
    session_factory: sessionmaker[Session],
    seen: Seen,
    reanalysis_provider: RecordingProvider,
) -> None:
    before = {
        upload_id: _plans(session_factory, upload_id) for upload_id in (seen.first, seen.second)
    }
    _approve(client, seen.diploma)
    detail = client.get(f"{BASE}/{seen.diploma}").text
    assert "Bu 2 partiyi yeniden analiz etmek üzeresiniz. Emin misiniz?" in detail
    assert f'action="{BASE}/{seen.diploma}/reanalyze/prepare"' in detail

    prepared = client.post(f"{BASE}/{seen.diploma}/reanalyze/prepare")

    assert prepared.status_code == 200
    assert f'<p class="confirm-text" role="alert">{BATCH_SECOND_TEXT}</p>' in prepared.text
    for upload_id in (seen.first, seen.second):
        assert f'<a href="/uploads/{upload_id}">{upload_id}</a></td><td>1</td>' in prepared.text
    assert len(reanalysis_provider.requests) == 0

    done = client.post(
        f"{BASE}/{seen.diploma}/reanalyze",
        data={"confirmation": _hidden(prepared.text)["confirmation"]},
    )

    assert done.status_code == 200, done.text
    assert "2 parti yeniden analiz edildi." in done.text
    assert "Bu aday türle bekleyen Unknown öğesi kalmadı." in done.text
    assert len(reanalysis_provider.requests) == 2
    for upload_id in (seen.first, seen.second):
        old, new = _plans(session_factory, upload_id)
        assert old.id == before[upload_id][0].id
        assert new.version == 2
        (item,) = read_plan(new).items
        assert item.document_type_slug == DIPLOMA
        assert item.route is not Route.UNKNOWN
        assert _open_unknown(session_factory, upload_id) == []
        assert (
            f'<a href="/uploads/{upload_id}">{upload_id}</a></td><td>1</td><td>2</td>' in done.text
        )
    assert len(_plans(session_factory, seen.permit_upload)) == 1
    confirmations = _events(session_factory, EventType.USER_CONFIRMED)
    batch = confirmations[-1]
    assert batch.actor == SIGNED_IN.username
    assert batch.data_json is not None
    assert batch.data_json["operation"] == "reanalyze"
    assert batch.data_json["target"] == {
        "candidate_type_id": seen.diploma,
        "uploads": [
            {"upload_id": seen.first, "plan_id": before[seen.first][0].id},
            {"upload_id": seen.second, "plan_id": before[seen.second][0].id},
        ],
    }
    reanalyzed = _events(session_factory, EventType.PLAN_REANALYZED)
    assert sorted(event.upload_id or "" for event in reanalyzed) == [seen.first, seen.second]
    after = client.get(f"{BASE}/{seen.diploma}").text
    assert "Yeniden analiz edilecek bekleyen Unknown öğesi yok." in after
    assert "Onaylanan, Unknown öğesi bekleyen adaylar" not in client.get(BASE).text


def test_batch_reanalysis_needs_an_approved_candidate_and_a_matching_token(
    client: TestClient,
    session_factory: sessionmaker[Session],
    seen: Seen,
    reanalysis_provider: RecordingProvider,
) -> None:
    for action in ("reanalyze/prepare", "reanalyze"):
        response = client.post(f"{BASE}/{seen.diploma}/{action}")
        assert response.status_code == 409, action
        assert "Toplu yeniden analiz yalnız onaylanmış aday türde yapılır." in response.text
    _approve(client, seen.diploma)
    token = _batch_token(client, seen.diploma)

    missing = client.post(f"{BASE}/{seen.diploma}/reanalyze")
    other_candidate = client.post(f"{BASE}/{seen.permit}/reanalyze", data={"confirmation": token})
    # Hazırlıktan sonra parti kümesi değişti: ikinci partinin öğesi çözüldü.
    with session_factory() as session:
        (item,) = session.scalars(
            select(QueueItem).where(QueueItem.upload_id == seen.second, QueueItem.kind == "unknown")
        ).all()
        item.resolved_at = utcnow()
        item.resolved_by = "baska-kullanici"
        session.commit()
    changed = client.post(f"{BASE}/{seen.diploma}/reanalyze", data={"confirmation": token})

    assert missing.status_code == 400
    assert other_candidate.status_code == 409  # onaylanmamış aday
    assert changed.status_code == 400
    assert "Onay geçersiz" in changed.text
    assert len(reanalysis_provider.requests) == 0
    assert [len(_plans(session_factory, u)) for u in (seen.first, seen.second)] == [1, 1]

    token = _batch_token(client, seen.diploma)
    done = client.post(f"{BASE}/{seen.diploma}/reanalyze", data={"confirmation": token})
    replay = client.post(f"{BASE}/{seen.diploma}/reanalyze", data={"confirmation": token})

    assert done.status_code == 200
    assert "1 parti yeniden analiz edildi." in done.text
    assert replay.status_code == 409
    assert "Bu aday türle ilişkili bekleyen Unknown öğesi yok" in replay.text
    assert [len(_plans(session_factory, u)) for u in (seen.first, seen.second)] == [2, 1]


def test_batch_reanalysis_is_all_or_nothing(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    seen: Seen,
    reanalysis_provider: RecordingProvider,
) -> None:
    _approve(client, seen.diploma)
    token = _batch_token(client, seen.diploma)
    real = plan_executor(SETTINGS)
    calls: list[str] = []

    def failing_on_second() -> PlanExecutor:
        def execute(session: Session, layout: DataLayout, plan: Plan, document: Any) -> None:
            calls.append(plan.upload_id)
            if len(calls) == 2:
                raise PlanItemReferenceError("Plan öğesi bulunamadı.")
            real(session, layout, plan, document)

        return execute

    app.dependency_overrides[get_plan_executor] = failing_on_second
    confirmed_before = len(_events(session_factory, EventType.USER_CONFIRMED))

    response = client.post(f"{BASE}/{seen.diploma}/reanalyze", data={"confirmation": token})

    assert response.status_code == 409
    assert "Plan öğesi bulunamadı." in response.text
    assert calls == [seen.first, seen.second]
    # İlk partinin yeniden analizi de geri alındı; belirteç tüketilmedi, onay olayı yok.
    assert [len(_plans(session_factory, u)) for u in (seen.first, seen.second)] == [1, 1]
    assert len(_events(session_factory, EventType.USER_CONFIRMED)) == confirmed_before
    assert _events(session_factory, EventType.PLAN_REANALYZED) == []
    with session_factory() as session:
        batch = session.scalars(
            select(ConfirmationToken).where(ConfirmationToken.operation == "reanalyze")
        ).one()
        assert batch.consumed_at is None


def test_batch_reanalysis_without_a_provider_is_503_and_does_nothing(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    _approve(client, seen.diploma)
    token = _batch_token(client, seen.diploma)
    app.dependency_overrides[get_reanalysis_provider] = lambda: ProviderConfigError("kurulamaz")

    response = client.post(f"{BASE}/{seen.diploma}/reanalyze", data={"confirmation": token})

    assert response.status_code == 503
    assert "kurulamaz" in response.text
    assert [len(_plans(session_factory, u)) for u in (seen.first, seen.second)] == [1, 1]


def test_a_busy_upload_blocks_the_batch(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    _approve(client, seen.diploma)
    with session_factory() as session:
        session.get_one(Upload, seen.second).status = UploadStatus.EXECUTING.value
        session.commit()

    detail = client.get(f"{BASE}/{seen.diploma}").text
    response = client.post(f"{BASE}/{seen.diploma}/reanalyze/prepare")

    busy = f"{seen.second}: Parti hâlâ işleniyor"
    assert busy in detail
    assert "/reanalyze/prepare" not in detail
    assert response.status_code == 409
    assert busy in response.text


def test_an_item_without_a_readable_first_page_is_not_related(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    with session_factory() as session:
        for payload in ({"sources": []}, {"sources": [{"file_id": "x"}]}, None):
            (item,) = session.scalars(
                select(QueueItem).where(QueueItem.upload_id == seen.second)
            ).all()
            item.payload_json = payload
            session.commit()
            page = client.get(f"{BASE}/{seen.diploma}").text
            assert f'href="/queues/{item.id}"' not in page
    _approve(client, seen.diploma)

    assert (
        "Bu 1 partiyi yeniden analiz etmek üzeresiniz." in client.get(f"{BASE}/{seen.diploma}").text
    )


def test_batch_prepare_needs_a_session_cookie(
    client: TestClient, session_factory: sessionmaker[Session], seen: Seen
) -> None:
    _approve(client, seen.diploma)
    client.cookies.clear()

    response = client.post(f"{BASE}/{seen.diploma}/reanalyze/prepare")

    assert response.status_code == 400
    assert "Oturum çerezi yok." in response.text
    assert "confirmation" not in _hidden(response.text)
