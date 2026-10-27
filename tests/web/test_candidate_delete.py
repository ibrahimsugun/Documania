"""11.1.9 — reddedilen aday türü kalıcı silme (PLAN.md §D134 a, b, d, e).

Aday kayıtları doğrudan yazılır (boru hattı gerekmez): yükleme, dosya ve sayfa satırı adayın
görülmesini taşır ve silmeden sonra yerinde kalır. Onay iki aşamalıdır; belirteçsiz, başka adaya
ya da eskimiş görülme sayısına ait belirteçle gelen istek hiçbir şey silmez.

Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import re
from html import unescape

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    CandidateDocumentType,
    Event,
    Page,
    Upload,
    UploadFile,
    record_candidate_type_sighting,
)
from app.events import EventType
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user
from app.web.confirm import Operation
from tests.web.conftest import SIGNED_IN, issue_token
from tests.web.flash import flashed

BASE = "/document-types/candidate-types"
UPLOAD = "u_20261027_0001"
FIRST = "Peruvian Diploma aday türünü kalıcı olarak silmek üzeresiniz. Emin misiniz?"
SECOND = (
    "Aday kaydı ve 2 görülme kaydı silinecek; sayfalar, yüklemeler ve belgeler değişmez. Bu işlem "
    "geri alınamaz. Son kararınız mı?"
)


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "oturum-bir")


@pytest.fixture
def candidates(session_factory: sessionmaker[Session]) -> dict[str, int]:
    """Üç aday: reddedilen (iki görülme), bekleyen, onaylanmış."""
    with session_factory() as session:
        session.add(Upload(id=UPLOAD, channel="web"))
        session.flush()
        file = UploadFile(
            upload_id=UPLOAD,
            original_name="scan.pdf",
            stored_path=f"Inbox/{UPLOAD}/scan.pdf",
            sha256="0" * 64,
            mime="application/pdf",
        )
        session.add(file)
        session.flush()
        pages = [Page(file_id=file.id, index=index) for index in range(3)]
        session.add_all(pages)
        session.flush()
        ids: dict[str, int] = {}
        for key, name, page_ids, status in (
            ("rejected", "Peruvian Diploma", (pages[0].id, pages[1].id), "rejected"),
            ("pending", "Chilean Permit", (pages[2].id,), "pending"),
            ("approved", "Bolivian Card", (pages[2].id,), "approved"),
        ):
            for page_id in page_ids:
                sighting = record_candidate_type_sighting(
                    session, proposed_name=name, upload_id=UPLOAD, page_id=page_id
                )
            sighting.candidate_type.status = status
            ids[key] = sighting.candidate_type.id
        session.commit()
    return ids


def _events(session_factory: sessionmaker[Session], *types: EventType) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event).where(Event.type.in_([t.value for t in types])).order_by(Event.id)
            )
        )


def _count(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match, html
    return match.group(1)


def test_the_rejected_list_has_a_delete_button_next_to_restore(
    client: TestClient, candidates: dict[str, int]
) -> None:
    page = client.get(f"{BASE}?status=rejected").text

    restore = f'action="{BASE}/{candidates["rejected"]}/restore"'
    delete = f'method="get" action="{BASE}/{candidates["rejected"]}/delete/confirm"'
    assert restore in page and delete in page
    assert page.index(restore) < page.index(delete)
    assert '<button type="submit" class="danger">Sil</button>' in page


def test_deleting_a_rejected_candidate_takes_two_confirmations_and_keeps_pages_and_uploads(
    client: TestClient, session_factory: sessionmaker[Session], candidates: dict[str, int]
) -> None:
    target = f"{BASE}/{candidates['rejected']}/delete"

    first = client.get(f"{target}/confirm")
    assert first.status_code == 200
    assert FIRST in unescape(first.text)
    assert "<dd>2</dd>" in first.text
    assert f'action="{target}/prepare"' in first.text
    assert _events(session_factory, EventType.USER_CONFIRMED) == []

    second = client.post(f"{target}/prepare")
    assert second.status_code == 200
    assert SECOND in unescape(second.text)
    assert 'class="danger">Evet, kalıcı sil</button>' in second.text

    done = client.post(target, data={"confirmation": _token(second.text)}, follow_redirects=False)

    assert done.status_code == 303
    assert done.headers["location"] == f"{BASE}?status=rejected"
    assert flashed(done) == ("catalog.candidate_deleted", {})
    listing = client.get(done.headers["location"]).text
    assert "<strong>Reddedilenler (0)</strong>" in listing
    assert "Peruvian Diploma" not in listing
    with session_factory() as session:
        assert session.get(CandidateDocumentType, candidates["rejected"]) is None
    assert _count(session_factory, CandidateDocumentType) == 2
    assert (_count(session_factory, Upload), _count(session_factory, Page)) == (1, 3)
    confirmed, deleted = _events(
        session_factory, EventType.USER_CONFIRMED, EventType.CANDIDATE_TYPE_DELETED
    )
    assert confirmed.data_json["operation"] == "candidate_delete"
    assert (deleted.actor, deleted.data_json) == (
        SIGNED_IN.username,
        {
            "candidate_type_id": candidates["rejected"],
            "candidate_type_name": "Peruvian Diploma",
            "seen_count": 2,
        },
    )
    # Aynı ad yeniden önerilirse yeni aday doğar.
    with session_factory() as session:
        reborn = record_candidate_type_sighting(
            session, proposed_name="Peruvian Diploma", upload_id=UPLOAD, page_id=1
        )
        assert reborn.created and reborn.candidate_type.status == "pending"


@pytest.mark.parametrize("key", ["pending", "approved"])
def test_a_pending_or_approved_candidate_is_not_deleted(
    client: TestClient,
    session_factory: sessionmaker[Session],
    candidates: dict[str, int],
    key: str,
) -> None:
    target = f"{BASE}/{candidates[key]}/delete"
    token = issue_token(
        session_factory, Operation.CANDIDATE_DELETE, f"candidate-types:{candidates[key]}:delete:1"
    )

    assert client.get(f"{target}/confirm").status_code == 409
    assert client.post(f"{target}/prepare").status_code == 409
    refused = client.post(target, data={"confirmation": token})

    assert refused.status_code == 409
    assert "Yalnız reddedilen aday tür silinir" in refused.text
    assert client.get(f"{BASE}/9999/delete/confirm").status_code == 404
    assert _count(session_factory, CandidateDocumentType) == 3
    assert _events(session_factory, EventType.CANDIDATE_TYPE_DELETED) == []


def test_a_missing_foreign_or_stale_token_deletes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], candidates: dict[str, int]
) -> None:
    rejected = candidates["rejected"]
    target = f"{BASE}/{rejected}/delete"
    other = issue_token(
        session_factory,
        Operation.CANDIDATE_DELETE,
        f"candidate-types:{candidates['pending']}:delete:1",
    )
    stale = issue_token(
        session_factory, Operation.CANDIDATE_DELETE, f"candidate-types:{rejected}:delete:1"
    )

    assert client.post(target).status_code == 400
    assert client.post(target, data={"confirmation": other}).status_code == 400
    assert client.post(target, data={"confirmation": stale}).status_code == 400
    with session_factory() as session:
        assert session.get(CandidateDocumentType, rejected) is not None
    assert _events(session_factory, EventType.CANDIDATE_TYPE_DELETED) == []


def test_a_read_only_user_sees_no_delete_button_and_is_refused(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    candidates: dict[str, int],
) -> None:
    app.dependency_overrides[get_current_user] = lambda: PanelUser(
        id=SIGNED_IN.id, username=SIGNED_IN.username, role="user"
    )
    target = f"{BASE}/{candidates['rejected']}/delete"

    page = client.get(f"{BASE}?status=rejected").text

    assert "Peruvian Diploma" in page
    assert "/delete/confirm" not in page
    assert client.get(f"{target}/confirm").status_code == 403
    assert client.post(f"{target}/prepare").status_code == 403
    assert client.post(target, data={"confirmation": "x"}).status_code == 403
    assert _count(session_factory, CandidateDocumentType) == 3
