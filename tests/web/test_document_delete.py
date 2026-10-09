"""10.5.12 — profilden belgeyi kalıcı silme: iki onay verilmeden hiçbir şey silinmez, ikinci onay
`<N>`/`<M>` sayılarını söyler ve belirteç o sayılara bağlıdır, sayılar onaydan sonra değişirse
409; silinen belge listelerden, dosya adresinden ve bottan kalkar, geçmişi ve erişim logu satırı
kalır (K16, R11, §20.6, §20.6.1, §20.6.2, §D110; kabul senaryosu S16 kalıbı).

Veriler sentetiktir (bayt dizgesi); gerçek kimlik belgesi kullanılmaz. Onay belirteci oturum
çerezine bağlıdır; oturum bağımlılığı testte geçersiz kılındığı için çerez elle konur.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
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
    Plan,
    Upload,
    UploadFile,
)
from app.events import EventType
from app.storage import DataLayout, archive_document, copy_to_received
from app.telegram.intent import find_documents
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, Operation
from app.web.routers.documents import DELETION_CHANGED, deletion_subject
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

OWNER, FOLDER = "E0001", "Test_Kisi_E0001"
TYPE_SLUG = "test_passport"
READY_NAME = "Test_Kisi-Passport.pdf"
# §20.6 "Belgeyi kalıcı sil" (§D110 i) — birebir.
DELETE_FIRST = "Bu belgeyi kalıcı olarak silmek üzeresiniz. Emin misiniz?"
DELETE_SECOND = (
    "Belge dosyası ve kopyaları ({n}) diskten silinecek, başka belgelere de kaynak olan dosyalar "
    "({m}) kalacaktır; bu işlem geri alınamaz. Son kararınız mı?"
)


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


@dataclass(frozen=True)
class Docs:
    active: int
    superseded: int
    archived: int
    source: int
    upload_id: str


def _upload_file(session: Session, layout: DataLayout, upload_id: str) -> UploadFile:
    content = f"%PDF sentetik tarama {upload_id}".encode()
    session.add(Upload(id=upload_id, channel="web", status="done"))
    session.add(Plan(upload_id=upload_id, version=1, json={}, plan_hash=upload_id))
    directory = layout.upload_inbox_dir(upload_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "tarama.pdf").write_bytes(content)
    upload_file = UploadFile(
        upload_id=upload_id,
        original_name="tarama.pdf",
        stored_path=layout.relative(directory / "tarama.pdf"),
        sha256=hashlib.sha256(content).hexdigest(),
        mime="application/pdf",
        page_count=2,
    )
    session.add(upload_file)
    session.flush()
    return upload_file


def _document(
    session: Session,
    layout: DataLayout,
    name: str,
    source: UploadFile,
    pages: list[int],
    *,
    status: DocumentStatus = DocumentStatus.ACTIVE,
) -> Document:
    path = layout.ready_dir(FOLDER) / name
    path.write_bytes(b"%PDF cikti " + name.encode())
    plan_id = session.scalars(select(Plan.id).where(Plan.upload_id == source.upload_id)).one()
    document = Document(
        employee_id=OWNER,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format="pdf",
        plan_id=plan_id,
        source_refs_json=[{"file_id": source.id, "pages": pages}],
        status=status.value,
    )
    session.add(document)
    session.flush()
    copy_to_received(layout, FOLDER, layout.resolve(source.stored_path), sha256=source.sha256)
    return document


@pytest.fixture
def docs(session_factory: sessionmaker[Session], layout: DataLayout) -> Docs:
    """E0001: tek kaynaklı etkin belge, ayrı partiden eski sürüm ve arşivdeki belge."""
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
        source = _upload_file(session, layout, "u_etkin")
        active = _document(session, layout, READY_NAME, source, [0])
        older = _upload_file(session, layout, "u_eski")
        superseded = _document(
            session,
            layout,
            "Test_Kisi-Passport-eski.pdf",
            older,
            [0],
            status=DocumentStatus.SUPERSEDED,
        )
        archived = _document(session, layout, "Test_Kisi-Passport-2.pdf", older, [1])
        archive_document(session, layout, archived.id, actor="kurulum")
        session.commit()
        return Docs(active.id, superseded.id, archived.id, source.id, source.upload_id)


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _counts(html: str) -> dict[str, str]:
    return dict(re.findall(r'name="(files_deleted|files_kept)" value="(\d+)"', html))


def _document_row(session_factory: sessionmaker[Session], document_id: int) -> Document:
    with session_factory() as session:
        document = session.get_one(Document, document_id)
        session.expunge(document)
        return document


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


def _prepare(client: TestClient, document_id: int) -> tuple[str, dict[str, str]]:
    prepared = client.post(f"/documents/{document_id}/delete/prepare")
    assert prepared.status_code == 200, prepared.text
    return _token(prepared.text), _counts(prepared.text)


# --- profil belge listesi -------------------------------------------------------------------------


def test_the_profile_offers_permanent_deletion_for_active_and_archived_documents(
    client: TestClient, docs: Docs
) -> None:
    section = _documents_section(client)

    assert f'href="/documents/{docs.active}/delete/confirm" class="document-delete"' in section
    assert f'href="/documents/{docs.archived}/delete/confirm" class="document-delete"' in section
    # K18: eski sürüm silinmez.
    assert f"/documents/{docs.superseded}/delete/" not in section
    assert section.count("Kalıcı sil<") == 2


def test_a_merged_profile_offers_no_deletion(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.get_one(Employee, OWNER).status = EmployeeStatus.MERGED.value
        session.commit()

    assert "/delete/confirm" not in _documents_section(client)
    assert client.get(f"/documents/{docs.active}/delete/confirm").status_code == 409


# --- iki aşamalı onay -----------------------------------------------------------------------------


def test_deletion_needs_both_confirmations_and_logs_the_user(
    client: TestClient,
    docs: Docs,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    ready = layout.ready_dir(FOLDER) / READY_NAME
    inbox = layout.upload_inbox_dir(docs.upload_id) / "tarama.pdf"

    first = client.get(f"/documents/{docs.active}/delete/confirm")
    assert first.status_code == 200
    assert DELETE_FIRST in first.text
    assert READY_NAME in first.text
    assert f'action="/documents/{docs.active}/delete/prepare"' in first.text

    prepared = client.post(f"/documents/{docs.active}/delete/prepare")
    assert prepared.status_code == 200
    # Tek kaynaklı belge: belge dosyası, Alinan kopyası ve Inbox orijinali gider; kalan yok.
    assert DELETE_SECOND.format(n=3, m=0) in prepared.text
    assert _counts(prepared.text) == {"files_deleted": "3", "files_kept": "0"}
    assert 'class="danger"' in prepared.text
    token = _token(prepared.text)
    # S16: yalnız birinci onay (hazırlık) hiçbir şeyi değiştirmez.
    assert _document_row(session_factory, docs.active).status == "active"
    assert ready.exists() and inbox.exists()

    done = client.post(
        f"/documents/{docs.active}/delete",
        data={"confirmation": token, "files_deleted": "3", "files_kept": "0"},
        follow_redirects=False,
    )

    assert done.status_code == 303
    assert done.headers["location"] == f"/employees/{OWNER}?notice=document_deleted#documents"
    row = _document_row(session_factory, docs.active)
    assert (row.status, row.path, row.deleted_by) == ("deleted", None, SIGNED_IN.username)
    assert not ready.exists() and not inbox.exists()
    confirmed, deleted = _events(
        session_factory, EventType.USER_CONFIRMED, EventType.DOCUMENT_DELETED
    )
    assert (confirmed.actor, deleted.actor) == (SIGNED_IN.username, SIGNED_IN.username)
    assert confirmed.data_json is not None
    assert confirmed.data_json["operation"] == "delete_document"
    assert confirmed.data_json["target"] == {"document_id": docs.active}
    assert confirmed.data_json["first_confirmed_at"] <= confirmed.data_json["second_confirmed_at"]
    assert deleted.data_json is not None
    assert (deleted.data_json["files_deleted"], deleted.data_json["files_kept"]) == (3, 0)

    profile = client.get(f"/employees/{OWNER}").text
    assert (
        "Belge kalıcı olarak silindi; dosyaları diskten kaldırıldı."
        in client.get(f"/employees/{OWNER}?notice=document_deleted").text
    )
    section = profile.split('<section class="profile-documents">', 1)[1].split("</section>")[0]
    assert READY_NAME not in section and f"/documents/{docs.active}/" not in section


def test_the_archived_document_reports_the_shared_original_it_keeps(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # Arşivdeki belgenin kaynağı eski sürümün de kaynağı: orijinal ve Alinan kalır (<M> = 2).
    token, counts = _prepare(client, docs.archived)
    assert counts == {"files_deleted": "1", "files_kept": "2"}
    archived = layout.resolve(_document_row(session_factory, docs.archived).path or "")

    done = client.post(
        f"/documents/{docs.archived}/delete",
        data={"confirmation": token, **counts},
        follow_redirects=False,
    )

    assert done.status_code == 303
    assert not archived.exists()
    assert (layout.upload_inbox_dir("u_eski") / "tarama.pdf").exists()
    deleted = _events(session_factory, EventType.DOCUMENT_DELETED)[0]
    assert deleted.data_json is not None and deleted.data_json["previous_status"] == "archived"


def test_without_a_token_or_with_other_counts_nothing_is_deleted(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    missing = client.post(
        f"/documents/{docs.active}/delete", data={"files_deleted": "3", "files_kept": "0"}
    )
    assert missing.status_code == 400
    assert CONFIRMATION_REFUSED in missing.text
    assert f'href="/documents/{docs.active}/delete/confirm"' in missing.text

    token, _ = _prepare(client, docs.active)
    # Kullanıcının görmediği sayılarla gelen istek belirteçten geçmez.
    tampered = client.post(
        f"/documents/{docs.active}/delete",
        data={"confirmation": token, "files_deleted": "1", "files_kept": "0"},
    )
    assert tampered.status_code == 400
    without_counts = client.post(f"/documents/{docs.active}/delete", data={"confirmation": token})
    assert without_counts.status_code == 400

    assert _document_row(session_factory, docs.active).status == "active"
    assert (layout.ready_dir(FOLDER) / READY_NAME).exists()
    assert _events(session_factory, EventType.USER_CONFIRMED, EventType.DOCUMENT_DELETED) == []


def test_a_token_for_another_operation_or_document_is_refused(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session]
) -> None:
    subject = deletion_subject(docs.active, 3, 0)
    for operation, target in (
        (Operation.ARCHIVE, subject),
        (Operation.DELETE_DOCUMENT, deletion_subject(docs.archived, 3, 0)),
    ):
        token = issue_token(session_factory, operation, target)
        refused = client.post(
            f"/documents/{docs.active}/delete",
            data={"confirmation": token, "files_deleted": "3", "files_kept": "0"},
        )
        assert refused.status_code == 400

    assert _document_row(session_factory, docs.active).status == "active"


def test_the_same_token_cannot_delete_twice(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session]
) -> None:
    token, counts = _prepare(client, docs.active)
    data = {"confirmation": token, **counts}
    assert client.post(f"/documents/{docs.active}/delete", data=data).status_code == 200

    again = client.post(f"/documents/{docs.active}/delete", data=data, follow_redirects=False)

    assert again.status_code == 409  # artık silinmiş: profil akışına girmez
    assert len(_events(session_factory, EventType.DOCUMENT_DELETED)) == 1


def test_changed_counts_after_the_second_confirmation_stop_with_409(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    token, counts = _prepare(client, docs.active)
    assert counts == {"files_deleted": "3", "files_kept": "0"}
    # Onaydan sonra aynı kaynaktan ikinci bir belge yazıldı: orijinal artık kalacak.
    with session_factory() as session:
        source = session.get_one(UploadFile, docs.source)
        _document(session, layout, "Test_Kisi-Passport-3.pdf", source, [1])
        session.commit()

    changed = client.post(
        f"/documents/{docs.active}/delete", data={"confirmation": token, **counts}
    )

    assert changed.status_code == 409
    assert DELETION_CHANGED in changed.text
    assert f'href="/documents/{docs.active}/delete/confirm"' in changed.text
    assert _document_row(session_factory, docs.active).status == "active"
    assert (layout.ready_dir(FOLDER) / READY_NAME).exists()
    assert _events(session_factory, EventType.USER_CONFIRMED, EventType.DOCUMENT_DELETED) == []
    # Onay yeniden başlatılınca yeni sayılar görünür.
    _, again = _prepare(client, docs.active)
    assert again == {"files_deleted": "1", "files_kept": "2"}


@pytest.mark.parametrize("step", ["confirm", "prepare"])
def test_superseded_deleted_and_missing_documents_are_refused(
    client: TestClient, docs: Docs, step: str
) -> None:
    def call(document_id: int) -> int:
        url = f"/documents/{document_id}/delete/{step}"
        response = client.get(url) if step == "confirm" else client.post(url)
        return response.status_code

    assert call(docs.superseded) == 409
    assert call(9999) == 404


# --- silinen belgenin izleri ----------------------------------------------------------------------


def _delete(client: TestClient, document_id: int) -> None:
    token, counts = _prepare(client, document_id)
    done = client.post(
        f"/documents/{document_id}/delete",
        data={"confirmation": token, **counts},
        follow_redirects=False,
    )
    assert done.status_code == 303, done.text


def test_the_file_address_answers_404_and_the_history_says_deleted(
    client: TestClient, docs: Docs
) -> None:
    file_url = f"/employees/{OWNER}/documents/{docs.active}"
    assert client.get(f"{file_url}/file").status_code == 200

    _delete(client, docs.active)

    assert client.get(f"{file_url}/file").status_code == 404
    assert client.get(f"{file_url}/download").status_code == 404
    history = client.get(f"/documents/{docs.active}/history")
    assert history.status_code == 200
    assert "Kalıcı olarak silindi: " in history.text and SIGNED_IN.username in history.text
    assert "Silindi" in history.text and READY_NAME not in history.text


def test_the_access_log_keeps_the_row_and_says_the_document_was_deleted(
    client: TestClient, docs: Docs
) -> None:
    assert client.get(f"/employees/{OWNER}/documents/{docs.active}/file").status_code == 200

    _delete(client, docs.active)

    page = client.get(f"/access-log/employees/{OWNER}")
    assert page.status_code == 200
    assert "belge silindi" in page.text and READY_NAME not in page.text


def test_the_bot_no_longer_finds_the_document(
    client: TestClient, docs: Docs, session_factory: sessionmaker[Session]
) -> None:
    _delete(client, docs.active)

    with session_factory() as session:
        found = [document.id for document in find_documents(session, OWNER, [TYPE_SLUG])]
    assert docs.active not in found


def test_a_file_that_cannot_be_removed_says_so_on_the_profile(
    client: TestClient,
    docs: Docs,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inbox = layout.upload_inbox_dir(docs.upload_id) / "tarama.pdf"
    original_unlink = Path.unlink

    def locked(path: Path, missing_ok: bool = False) -> None:
        if path == inbox:
            raise PermissionError("açık dosya")
        original_unlink(path, missing_ok=missing_ok)

    token, counts = _prepare(client, docs.active)
    monkeypatch.setattr(Path, "unlink", locked)
    done = client.post(
        f"/documents/{docs.active}/delete",
        data={"confirmation": token, **counts},
        follow_redirects=False,
    )

    assert done.status_code == 303
    assert "notice=document_deleted_partial" in done.headers["location"]
    assert _document_row(session_factory, docs.active).status == "deleted"
    (deleted,) = _events(session_factory, EventType.DOCUMENT_DELETED)
    assert deleted.data_json is not None and deleted.data_json["files_failed"] == 1
    page = client.get(f"/employees/{OWNER}?notice=document_deleted_partial").text
    assert "bazı dosyaları diskten kaldırılamadı" in page
