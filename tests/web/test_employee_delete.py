"""10.5.13 — profilden pasif çalışanı kalıcı silme: bağlantı yalnız pasif profilde; iki onay
verilmeden hiçbir şey silinmez, ikinci onay belge sayısını (`<N>`) söyler ve belirteç o sayıya
bağlıdır; silinen çalışanın adresleri "silindi" sayfası (410) döner, liste, arama ve birleştirme
onu göstermez (K16, R11, §20.6, §20.6.1, §D110; kabul senaryosu S16 kalıbı).

Veriler sentetiktir; gerçek kimlik belgesi kullanılmaz. Onay belirteci oturum çerezine bağlıdır;
oturum bağımlılığı testte geçersiz kılındığı için çerez elle konur.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeStatus,
    Event,
    KnownDocumentType,
    Plan,
    Upload,
    UploadFile,
)
from app.matching.names import normalize_name
from app.storage import DataLayout, copy_to_received
from app.web.auth import SESSION_COOKIE
from app.web.confirm import CONFIRMATION_REFUSED, Operation
from app.web.routers.employees import EMPLOYEE_DELETION_CHANGED, employee_deletion_subject
from tests.web.conftest import SESSION, SIGNED_IN, issue_token

GONE, GONE_FOLDER = "E0001", "Zorana_Testovic_E0001"
OTHER, OTHER_FOLDER = "E0002", "Milan_Probic_E0002"
TYPE_SLUG = "test_passport"
# §20.6 "Çalışanı kalıcı sil" (§D110 i) — birebir.
DELETE_FIRST = (
    "Zorana Testovic çalışanını bütün belgeleriyle kalıcı olarak silmek üzeresiniz. Emin misiniz?"
)
DELETE_SECOND = (
    "Çalışanın klasörü, belgeleri ({n}) ve kişisel bilgileri silinecek, yalnız E numarası "
    "kalacaktır; bu işlem geri alınamaz. Son kararınız mı?"
)


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


def _document(
    session: Session, layout: DataLayout, employee_id: str, folder: str, upload_id: str
) -> int:
    content = f"%PDF sentetik tarama {upload_id}".encode()
    session.add(Upload(id=upload_id, channel="web", status="done"))
    plan = Plan(upload_id=upload_id, version=1, json={}, plan_hash=upload_id)
    session.add(plan)
    directory = layout.upload_inbox_dir(upload_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "tarama.pdf").write_bytes(content)
    source = UploadFile(
        upload_id=upload_id,
        original_name="tarama.pdf",
        stored_path=layout.relative(directory / "tarama.pdf"),
        sha256=hashlib.sha256(content).hexdigest(),
        mime="application/pdf",
        page_count=1,
    )
    session.add(source)
    session.flush()
    path = layout.ready_dir(folder) / f"{folder}-Passport.pdf"
    path.write_bytes(b"%PDF cikti")
    document = Document(
        employee_id=employee_id,
        type_slug=TYPE_SLUG,
        path=layout.relative(path),
        format="pdf",
        plan_id=plan.id,
        source_refs_json=[{"file_id": source.id, "pages": [0]}],
        status=DocumentStatus.ACTIVE.value,
    )
    session.add(document)
    session.flush()
    copy_to_received(layout, folder, layout.resolve(source.stored_path), sha256=source.sha256)
    return document.id


@pytest.fixture
def world(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, int]:
    """E0001 pasif (bir belge, bir yazım), E0002 etkin (bir belge)."""
    with session_factory() as session:
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
        for employee_id, folder, given, surname, state in (
            (GONE, GONE_FOLDER, "Zorana", "Testovic", EmployeeStatus.INACTIVE),
            (OTHER, OTHER_FOLDER, "Milan", "Probic", EmployeeStatus.ACTIVE),
        ):
            session.add(
                Employee(
                    id=employee_id,
                    folder_name=folder,
                    given_names=given,
                    surname=surname,
                    status=state.value,
                )
            )
            session.add(
                EmployeeAlias(
                    employee_id=employee_id,
                    raw_name=f"{given} {surname}",
                    normalized_name=normalize_name(f"{given} {surname}"),
                    script="latin",
                )
            )
            layout.ensure_employee_tree(folder)
        session.flush()
        gone = _document(session, layout, GONE, GONE_FOLDER, "u_bir")
        other = _document(session, layout, OTHER, OTHER_FOLDER, "u_iki")
        session.commit()
    return {"gone": gone, "other": other}


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _events(session_factory: sessionmaker[Session], *types: str) -> list[Event]:
    with session_factory() as session:
        return list(session.scalars(select(Event).where(Event.type.in_(types)).order_by(Event.id)))


def _status(session_factory: sessionmaker[Session], employee_id: str) -> str:
    with session_factory() as session:
        return session.get_one(Employee, employee_id).status


# --- profil ve onay adımları --------------------------------------------------------------------


def test_only_the_inactive_profile_offers_permanent_deletion(
    client: TestClient, world: dict[str, int]
) -> None:
    inactive = client.get(f"/employees/{GONE}").text
    active = client.get(f"/employees/{OTHER}").text

    assert f'href="/employees/{GONE}/delete/confirm" class="employee-delete"' in inactive
    assert '/delete/confirm" class="employee-delete"' not in active


def test_the_first_step_shows_the_section_20_6_text_and_changes_nothing(
    client: TestClient, world: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    page = client.get(f"/employees/{GONE}/delete/confirm")

    assert page.status_code == 200
    assert DELETE_FIRST in page.text
    assert f'action="/employees/{GONE}/delete/prepare"' in page.text
    assert _status(session_factory, GONE) == EmployeeStatus.INACTIVE.value


@pytest.mark.parametrize(
    ("employee_id", "code"), [(OTHER, 409), ("E0404", 404)], ids=["active", "unknown"]
)
def test_an_active_or_unknown_employee_is_refused(
    client: TestClient, world: dict[str, int], employee_id: str, code: int
) -> None:
    assert client.get(f"/employees/{employee_id}/delete/confirm").status_code == code
    assert client.post(f"/employees/{employee_id}/delete/prepare").status_code == code
    refused = client.post(
        f"/employees/{employee_id}/delete", data={"confirmation": "x", "documents": "1"}
    )
    assert refused.status_code == code


def test_one_confirmation_changes_nothing(
    client: TestClient,
    world: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    prepared = client.post(f"/employees/{GONE}/delete/prepare")

    assert prepared.status_code == 200
    assert DELETE_SECOND.format(n=1) in prepared.text
    assert 'name="documents" value="1"' in prepared.text
    assert _status(session_factory, GONE) == EmployeeStatus.INACTIVE.value
    assert layout.employee_dir(GONE_FOLDER).is_dir()
    # Token'sız son adım da hiçbir şey değiştirmez.
    refused = client.post(f"/employees/{GONE}/delete", data={"documents": "1"})
    assert refused.status_code == 400 and CONFIRMATION_REFUSED in refused.text
    assert _status(session_factory, GONE) == EmployeeStatus.INACTIVE.value
    assert _events(session_factory, "EMPLOYEE_DELETED") == []


def test_a_token_for_another_count_is_refused(
    client: TestClient, world: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    token = _token(client.post(f"/employees/{GONE}/delete/prepare").text)

    refused = client.post(
        f"/employees/{GONE}/delete", data={"confirmation": token, "documents": "0"}
    )

    assert refused.status_code == 400
    assert _status(session_factory, GONE) == EmployeeStatus.INACTIVE.value


def test_a_changed_document_count_is_409_and_deletes_nothing(
    client: TestClient,
    world: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    token = _token(client.post(f"/employees/{GONE}/delete/prepare").text)
    with session_factory() as session:
        _document(session, layout, GONE, GONE_FOLDER, "u_uc")
        session.commit()

    refused = client.post(
        f"/employees/{GONE}/delete", data={"confirmation": token, "documents": "1"}
    )

    assert refused.status_code == 409
    assert EMPLOYEE_DELETION_CHANGED in refused.text
    assert _status(session_factory, GONE) == EmployeeStatus.INACTIVE.value
    assert layout.employee_dir(GONE_FOLDER).is_dir()


def test_two_confirmations_delete_the_employee(
    client: TestClient,
    world: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    token = _token(client.post(f"/employees/{GONE}/delete/prepare").text)

    deleted = client.post(
        f"/employees/{GONE}/delete",
        data={"confirmation": token, "documents": "1"},
        follow_redirects=False,
    )

    assert deleted.status_code == 303
    assert deleted.headers["location"] == f"/employees/{GONE}?notice=employee_deleted"
    assert _status(session_factory, GONE) == EmployeeStatus.DELETED.value
    assert not layout.employee_dir(GONE_FOLDER).exists()
    confirmed, event = _events(session_factory, "USER_CONFIRMED", "EMPLOYEE_DELETED")
    assert confirmed.data_json["operation"] == Operation.DELETE_EMPLOYEE.value
    assert (event.type, event.actor) == ("EMPLOYEE_DELETED", SIGNED_IN.username)
    # Belirteç tek kullanımlıktır: ikinci gönderim "silindi" sayfasıdır, bir şey değişmez.
    again = client.post(f"/employees/{GONE}/delete", data={"confirmation": token, "documents": "1"})
    assert again.status_code == 410
    assert len(_events(session_factory, "EMPLOYEE_DELETED")) == 1


def test_a_token_of_another_operation_or_employee_is_refused(
    client: TestClient, world: dict[str, int], session_factory: sessionmaker[Session]
) -> None:
    # §20.6.1: belirteç işleme ve hedefe bağlıdır; belgeyi silme belirteci ya da başka çalışanın
    # belirteci çalışanı silmez.
    for operation, subject in (
        (Operation.DELETE_DOCUMENT, employee_deletion_subject(GONE, 1)),
        (Operation.DELETE_EMPLOYEE, employee_deletion_subject(OTHER, 1)),
    ):
        token = issue_token(session_factory, operation, subject)
        refused = client.post(
            f"/employees/{GONE}/delete", data={"confirmation": token, "documents": "1"}
        )
        assert refused.status_code == 400
    assert _status(session_factory, GONE) == EmployeeStatus.INACTIVE.value


# --- silindi sayfası ve görünürlük ----------------------------------------------------------------


def _delete(client: TestClient) -> None:
    token = _token(client.post(f"/employees/{GONE}/delete/prepare").text)
    client.post(f"/employees/{GONE}/delete", data={"confirmation": token, "documents": "1"})


def test_every_address_of_a_deleted_employee_is_the_deleted_page(
    client: TestClient, world: dict[str, int]
) -> None:
    _delete(client)

    profile = client.get(f"/employees/{GONE}?notice=employee_deleted")
    assert profile.status_code == 410
    assert "kalıcı olarak silindi" in profile.text and SIGNED_IN.username in profile.text
    assert "Zorana" not in profile.text and "Testovic" not in profile.text
    for path in (
        f"/employees/{GONE}/fields",
        f"/employees/{GONE}/status/confirm?to=active",
        f"/employees/{GONE}/delete/confirm",
        f"/employees/{GONE}/merge/employees?q=Milan",
        f"/employees/{GONE}/photo",
        f"/employees/{GONE}/documents/{world['gone']}/file",
    ):
        assert client.get(path).status_code == 410, path
    assert (
        client.post(f"/employees/{GONE}/status/prepare", data={"to": "active"}).status_code == 410
    )


def test_lists_searches_and_merge_do_not_show_a_deleted_employee(
    client: TestClient, world: dict[str, int]
) -> None:
    _delete(client)

    for path in ("/employees?status=all", "/employees?status=inactive", "/employees?q=Zorana"):
        assert f"/employees/{GONE}" not in client.get(path).text, path
    assert f"/employees/{OTHER}" in client.get("/employees?status=all").text
    search = client.get(f"/employees/{OTHER}/merge/employees?q=Zorana")
    assert GONE not in search.text
    assert client.get(f"/employees/{OTHER}/merge/confirm?other={GONE}").status_code == 404
    moves = client.get(f"/documents/{world['other']}/move/employees?q=Zorana")
    assert GONE not in moves.text


def test_a_failed_file_removal_is_reported(
    client: TestClient,
    world: dict[str, int],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(client.post(f"/employees/{GONE}/delete/prepare").text)
    original_unlink = Path.unlink

    def locked(path: Path, missing_ok: bool = False) -> None:
        if path.name == "tarama.pdf":
            raise PermissionError("kilitli")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", locked)

    deleted = client.post(
        f"/employees/{GONE}/delete",
        data={"confirmation": token, "documents": "1"},
        follow_redirects=False,
    )

    assert deleted.headers["location"] == f"/employees/{GONE}?notice=employee_deleted_partial"
    (event,) = _events(session_factory, "EMPLOYEE_DELETED")
    assert event.data_json["files_failed"] >= 1
    assert _status(session_factory, GONE) == EmployeeStatus.DELETED.value
