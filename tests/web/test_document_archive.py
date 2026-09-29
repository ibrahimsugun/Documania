"""08.4.1, 10.5.10 — profilden arşive taşıma ve arşivden geri alma: iki onay verilmeden işlem
gerçekleşmez, belge silinmez, geri alınan belge `Hazir/`'a K8 adıyla döner; olaylar kullanıcı
adıyla loglanır (K16, §20.6, §20.6.1, §20.6.2, §D61; kabul senaryosu S16).

Belgeler sentetiktir (bayt dizgesi); gerçek kimlik belgesi kullanılmaz. Onay belirteci oturum
çerezine bağlıdır; oturum bağımlılığı testte geçersiz kılındığı için çerez elle konur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeStatus,
    Event,
    KnownDocumentType,
)
from app.events import EventType
from app.storage import DataLayout, archive_document
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, Operation
from app.web.routers.documents import (
    DOCUMENT_FILE_MISSING,
    DOCUMENT_NOT_FOUND,
    OWNER_MERGED,
    document_subject,
)
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

OWNER, FOLDER = "E0001", "Test_Kisi_E0001"
TYPE_SLUG = "test_passport"
READY_NAME = "Test_Kisi-Passport.pdf"
CONTENT = b"%PDF-1.4 sentetik belge"
# §20.6 "Belgeyi arşive taşı" ve "Belgeyi arşivden geri al" (§D61) — birebir.
ARCHIVE_FIRST = "Bu belgeyi arşive taşımak üzeresiniz. Emin misiniz?"
ARCHIVE_SECOND = "Belge çalışanın Hazır klasöründen çıkacaktır. Son kararınız mı?"
UNARCHIVE_FIRST = "Bu belgeyi arşivden geri almak üzeresiniz. Emin misiniz?"
UNARCHIVE_SECOND = "Belge çalışanın Hazır klasörüne dönecektir. Son kararınız mı?"


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


@dataclass(frozen=True)
class Docs:
    active: int
    superseded: int
    archived: int


def _document(
    session: Session,
    layout: DataLayout,
    name: str,
    *,
    status: DocumentStatus = DocumentStatus.ACTIVE,
    sequence_no: int = 1,
) -> Document:
    path = layout.ready_dir(FOLDER) / name
    path.write_bytes(CONTENT + name.encode())
    document = Document(
        employee_id=OWNER,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format="pdf",
        source_refs_json=[],
        status=status.value,
        sequence_no=sequence_no,
    )
    session.add(document)
    session.flush()
    return document


@pytest.fixture
def docs(session_factory: sessionmaker[Session], layout: DataLayout) -> Docs:
    """Bir etkin, bir eski sürüm ve bir arşivdeki belge (E0001)."""
    layout.ensure_employee_tree(FOLDER)
    with session_factory() as session:
        session.add(Employee(id=OWNER, folder_name=FOLDER, given_names="Test", surname="Kisi"))
        session.add(
            KnownDocumentType(
                slug=TYPE_SLUG,
                name="Test Passport",
                file_label="Passport",
                sides="single",
                direct=True,
                analyze=True,
                output_format="keep",
            )
        )
        session.flush()
        active = _document(session, layout, READY_NAME)
        superseded = _document(
            session, layout, "Test_Kisi-Passport-eski.pdf", status=DocumentStatus.SUPERSEDED
        )
        archived = _document(session, layout, "Test_Kisi-Passport-2.pdf", sequence_no=2)
        archive_document(session, layout, archived.id, actor="kurulum", today=date(2026, 3, 5))
        session.commit()
        return Docs(active.id, superseded.id, archived.id)


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _state(session_factory: sessionmaker[Session], document_id: int) -> tuple[str, str, int]:
    with session_factory() as session:
        document = session.get_one(Document, document_id)
        return document.status, document.path, document.sequence_no


def _events(session_factory: sessionmaker[Session], *types: EventType) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event).where(Event.type.in_([t.value for t in types])).order_by(Event.id)
            )
        )


def _documents_section(client: TestClient) -> str:
    page = client.get(f"/employees/{OWNER}").text
    return page.split('<section class="profile-documents">', 1)[1].split("</section>", 1)[0]


# --- profil belge listesi -------------------------------------------------------------------------


def test_the_profile_offers_archive_or_unarchive_by_status(client: TestClient, docs: Docs) -> None:
    section = _documents_section(client)

    assert f'href="/documents/{docs.active}/archive/confirm"' in section
    assert f'href="/documents/{docs.archived}/unarchive/confirm"' in section
    assert f"/documents/{docs.active}/unarchive/" not in section
    assert f"/documents/{docs.archived}/archive/" not in section
    # K18: eski sürüm ne arşivlenir ne geri alınır.
    assert f"/documents/{docs.superseded}/archive/" not in section
    assert f"/documents/{docs.superseded}/unarchive/" not in section
    assert section.count("Arşive taşı<") == 1
    assert section.count("Arşivden geri al<") == 1


def test_a_merged_profile_offers_neither(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.get_one(Employee, OWNER).status = EmployeeStatus.MERGED.value
        session.commit()

    section = _documents_section(client)

    assert "/archive/confirm" not in section
    assert "/unarchive/confirm" not in section


# --- arşive taşı --------------------------------------------------------------------------------


def test_archive_needs_both_confirmations_and_logs_the_user(
    client: TestClient,
    docs: Docs,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    before = _state(session_factory, docs.active)

    first = client.get(f"/documents/{docs.active}/archive/confirm")
    assert first.status_code == 200
    assert ARCHIVE_FIRST in first.text
    assert READY_NAME in first.text
    assert f'action="/documents/{docs.active}/archive/prepare"' in first.text

    prepared = client.post(f"/documents/{docs.active}/archive/prepare")
    assert prepared.status_code == 200
    assert ARCHIVE_SECOND in prepared.text
    token = _token(prepared.text)
    # S16: yalnız birinci onay (hazırlık) hiçbir şeyi değiştirmez.
    assert _state(session_factory, docs.active) == before
    assert (layout.ready_dir(FOLDER) / READY_NAME).exists()

    done = client.post(
        f"/documents/{docs.active}/archive", data={"confirmation": token}, follow_redirects=False
    )

    assert done.status_code == 303
    assert done.headers["location"] == f"/employees/{OWNER}?notice=document_archived#documents"
    status, path, _ = _state(session_factory, docs.active)
    assert status == DocumentStatus.ARCHIVED.value
    assert path.startswith("Archive/")
    assert layout.resolve(path).read_bytes() == CONTENT + READY_NAME.encode()
    assert not (layout.ready_dir(FOLDER) / READY_NAME).exists()
    confirmed, archived = _events(session_factory, EventType.USER_CONFIRMED, EventType.ARCHIVED)[
        -2:
    ]
    assert (confirmed.type, archived.type) == ("USER_CONFIRMED", "ARCHIVED")
    assert confirmed.actor == archived.actor == SIGNED_IN.username
    assert confirmed.data_json["operation"] == Operation.ARCHIVE.value
    assert confirmed.data_json["target"] == {"document_id": docs.active}
    assert confirmed.data_json["first_confirmed_at"] and confirmed.data_json["second_confirmed_at"]
    assert "Belge arşive taşındı" in client.get(done.headers["location"]).text

    # Aynı belirteç ikinci kez kullanılamaz.
    again = client.post(f"/documents/{docs.active}/archive", data={"confirmation": token})
    assert again.status_code == 409  # belge artık arşivde


def test_archive_without_a_token_changes_nothing(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session]
) -> None:
    before = _state(session_factory, docs.active)

    response = client.post(f"/documents/{docs.active}/archive")

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    assert f'href="/documents/{docs.active}/archive/confirm"' in response.text
    assert _state(session_factory, docs.active) == before
    assert _events(session_factory, EventType.USER_CONFIRMED) == []


def test_archive_refuses_a_document_that_is_not_active(client: TestClient, docs: Docs) -> None:
    for document_id in (docs.superseded, docs.archived):
        for response in (
            client.get(f"/documents/{document_id}/archive/confirm"),
            client.post(f"/documents/{document_id}/archive/prepare"),
            client.post(f"/documents/{document_id}/archive", data={"confirmation": "x"}),
        ):
            assert response.status_code == 409
            assert "Yalnız etkin belge arşive taşınır" in response.text


# --- arşivden geri al ---------------------------------------------------------------------------


def test_unarchive_needs_both_confirmations_and_returns_the_file_to_hazir(
    client: TestClient,
    docs: Docs,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    before = _state(session_factory, docs.archived)
    archived_path = layout.resolve(before[1])

    first = client.get(f"/documents/{docs.archived}/unarchive/confirm")
    assert first.status_code == 200
    assert UNARCHIVE_FIRST in first.text
    assert "Arşivlendi" in first.text

    prepared = client.post(f"/documents/{docs.archived}/unarchive/prepare")
    assert prepared.status_code == 200
    assert UNARCHIVE_SECOND in prepared.text
    token = _token(prepared.text)
    assert _state(session_factory, docs.archived) == before  # S16
    assert archived_path.exists()

    done = client.post(
        f"/documents/{docs.archived}/unarchive",
        data={"confirmation": token},
        follow_redirects=False,
    )

    assert done.status_code == 303
    assert done.headers["location"] == f"/employees/{OWNER}?notice=document_unarchived#documents"
    status, path, sequence_no = _state(session_factory, docs.archived)
    assert status == DocumentStatus.ACTIVE.value
    # Kendi eki (-2) boştu; belge ona döner.
    assert layout.resolve(path) == layout.ready_dir(FOLDER) / "Test_Kisi-Passport-2.pdf"
    assert sequence_no == 2
    assert layout.resolve(path).read_bytes() == CONTENT + b"Test_Kisi-Passport-2.pdf"
    assert not archived_path.exists()
    confirmed, restored = _events(session_factory, EventType.USER_CONFIRMED, EventType.UNARCHIVED)[
        -2:
    ]
    assert (confirmed.type, restored.type) == ("USER_CONFIRMED", "UNARCHIVED")
    assert confirmed.actor == restored.actor == SIGNED_IN.username
    assert confirmed.data_json["operation"] == Operation.UNARCHIVE.value
    assert restored.data_json["from"] == before[1]
    assert restored.data_json["to"] == path
    profile = client.get(done.headers["location"]).text
    assert "Belge arşivden geri alındı" in profile
    assert layout.profile_path(FOLDER).read_text(encoding="utf-8").count("| active |") == 2

    again = client.post(f"/documents/{docs.archived}/unarchive", data={"confirmation": token})
    assert again.status_code == 409
    assert "Yalnız arşivdeki belge geri alınır" in again.text


def test_unarchive_refuses_a_bad_expired_or_foreign_token(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session]
) -> None:
    before = _state(session_factory, docs.archived)
    foreign = [
        # Başka işlemin (arşive taşı) belirteci.
        issue_token(session_factory, Operation.ARCHIVE, document_subject(docs.archived)),
        # Başka belgenin belirteci.
        issue_token(session_factory, Operation.UNARCHIVE, document_subject(docs.active)),
        # Başka oturumun belirteci.
        issue_token(
            session_factory, Operation.UNARCHIVE, document_subject(docs.archived), cookie="baska"
        ),
        "uydurma-belirtec",
    ]

    for token in foreign:
        response = client.post(
            f"/documents/{docs.archived}/unarchive", data={"confirmation": token}
        )
        assert response.status_code == 400
        assert CONFIRMATION_REFUSED in response.text

    assert _state(session_factory, docs.archived) == before
    assert _events(session_factory, EventType.USER_CONFIRMED, EventType.UNARCHIVED) == []


def test_unarchive_refuses_a_document_that_is_not_archived(client: TestClient, docs: Docs) -> None:
    for document_id in (docs.active, docs.superseded):
        for response in (
            client.get(f"/documents/{document_id}/unarchive/confirm"),
            client.post(f"/documents/{document_id}/unarchive/prepare"),
            client.post(f"/documents/{document_id}/unarchive", data={"confirmation": "x"}),
        ):
            assert response.status_code == 409
            assert "Yalnız arşivdeki belge geri alınır" in response.text


def test_unarchive_refuses_a_merged_owner_and_a_missing_file(
    client: TestClient,
    docs: Docs,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    with session_factory() as session:
        session.get_one(Employee, OWNER).status = EmployeeStatus.MERGED.value
        session.commit()
    merged = client.post(f"/documents/{docs.archived}/unarchive/prepare")
    assert merged.status_code == 409
    assert OWNER_MERGED in merged.text

    with session_factory() as session:
        session.get_one(Employee, OWNER).status = EmployeeStatus.ACTIVE.value
        session.commit()
    layout.resolve(_state(session_factory, docs.archived)[1]).unlink()
    missing = client.get(f"/documents/{docs.archived}/unarchive/confirm")
    assert missing.status_code == 409
    assert DOCUMENT_FILE_MISSING in missing.text


def test_unknown_document_is_404_in_both_flows(client: TestClient, docs: Docs) -> None:
    for action in ("archive", "unarchive"):
        for response in (
            client.get(f"/documents/9999/{action}/confirm"),
            client.post(f"/documents/9999/{action}/prepare"),
            client.post(f"/documents/9999/{action}", data={"confirmation": "x"}),
        ):
            assert response.status_code == 404
            assert DOCUMENT_NOT_FOUND in response.text


def test_prepare_without_a_session_cookie_issues_no_token(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session]
) -> None:
    client.cookies.clear()

    response = client.post(f"/documents/{docs.archived}/unarchive/prepare")

    assert response.status_code == 400
    assert 'name="confirmation"' not in response.text
    assert _state(session_factory, docs.archived)[0] == DocumentStatus.ARCHIVED.value


def test_archive_then_unarchive_round_trip_keeps_the_content(
    client: TestClient,
    docs: Docs,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    original = (layout.ready_dir(FOLDER) / READY_NAME).read_bytes()

    token = _token(client.post(f"/documents/{docs.active}/archive/prepare").text)
    assert (
        client.post(f"/documents/{docs.active}/archive", data={"confirmation": token}).status_code
        == 200
    )  # yönlendirme izlenir: profil
    token = _token(client.post(f"/documents/{docs.active}/unarchive/prepare").text)
    assert (
        client.post(f"/documents/{docs.active}/unarchive", data={"confirmation": token}).status_code
        == 200
    )

    status, path, sequence_no = _state(session_factory, docs.active)
    assert (status, sequence_no) == (DocumentStatus.ACTIVE.value, 1)
    assert Path(path).name == READY_NAME
    assert layout.resolve(path).read_bytes() == original
