"""10.7.3 — kuyruktan profil oluşturma: önerilen profil düzenlenip onaylanabilir; belge içeriği
düzenlenemez (K7, K16, K17, §20.6, §20.6.1, §20.6.2).

Onay bekleyen profil öğesi gerçek planlayıcıdan (06.1) ve kuyruğa yönlendirmeden (08.1) geçer
(`_pending_items`: numarası temiz olmayan sentetik çalışma izni, §20.2.2 satır 7); sayfa analizleri
saklanmış sentetik yanıtlardır, yapay zekâ sağlayıcısı çağrılmaz. Onay belirteci 10.8.1'in tek
kullanımlık belirtecidir ve oturum çerezine bağlıdır; oturum bağımlılığı testte geçersiz kılındığı
için çerez elle konur. Gerçek kimlik belgesi kullanılmaz.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

import app.web.confirm as confirm
import app.web.routers.queue as queue_module
from app.catalog import import_catalog
from app.db.models import (
    Document,
    Employee,
    EmployeeAlias,
    Event,
    Page,
    QueueItem,
    utcnow,
)
from app.events import EventType
from app.matching.match import ProfileFields
from app.matching.names import normalize_name
from app.pipeline.plan import create_plan, read_plan
from app.pipeline.route import QueueItemNotFoundError, route_queue_item
from app.storage import DataLayout, sha256_file
from app.web.auth import SESSION_COOKIE, get_current_user
from app.web.confirm import CONFIRMATION_REFUSED, Operation, first_text, second_text
from app.web.routers.queue import (
    NOT_PENDING_NOTE,
    PROFILE_RESOLVED_NOTE,
    QUEUE_ITEM_NOT_FOUND,
    SUPERSEDED_NOTE,
    assignment_subject,
    profile_subject,
)
from tests.pipeline.test_plan import (
    BORN,
    CATALOG,
    GIVEN,
    MODEL,
    PERMIT,
    SURNAME,
    _page,
    _pdf,
    _person,
)
from tests.pipeline.test_plan import _upload as _upload_with_analyses
from tests.web.conftest import SESSION, SIGNED_IN, issue_token
from tests.web.test_queue import _queued_item, _refuse_provider

# §20.2.3 koşul 2: normalize hâli 5 karakterden kısa numara temiz değildir → satır 7.
SHORT_NUMBER = "AB12"
NEW = "E0001"
EDITED_SURNAME = "ORNEKOVIC"
EDITED_FOLDER = "Test_Ornekovic_E0001"
# Formun öneriyle dolan değerleri ve İK'nın düzelttiği hâli.
PROPOSAL = {
    "given_names": GIVEN,
    "surname": SURNAME,
    "other_names": "",
    "original_script_name": "",
    "date_of_birth": BORN,
    "nationality": "RUS",
}
EDITED = {**PROPOSAL, "surname": EDITED_SURNAME, "date_of_birth": "1990-02-01"}
# §20.6 — birebir; `<Ad Soyad>` onaylanan ad-soyadla dolar.
FIRST_TEXT = (
    f"{GIVEN} {EDITED_SURNAME} için yeni bir çalışan profili oluşturmak üzeresiniz. Emin misiniz?"
)
SECOND_TEXT = "Bu işlem sistemde kalıcı bir çalışan kaydı oluşturacaktır. Son kararınız mı?"
PERSONAL_VALUES = (GIVEN, SURNAME, EDITED_SURNAME, "Ornekov", BORN, "1990-02-01", SHORT_NUMBER)


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)


def _pending_items(
    session_factory: sessionmaker[Session], layout: DataLayout, count: int = 1
) -> list[int]:
    """Her dosyası bir onay bekleyen profil öğesi olan parti (aynı kişinin numarasız belgeleri ayrı
    önerilerdir, C29); commit edilir, kuyruk kayıtlarının kimlikleri döner."""
    with session_factory() as session:
        import_catalog(session, CATALOG)
        page = _page(PERMIT, person=_person(document_number=SHORT_NUMBER))
        upload = _upload_with_analyses(session, layout, *(_pdf(page) for _ in range(count)))
        plan = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
        items = read_plan(plan).items
        assert [item.employee.action.value for item in items] == ["pending"] * count
        ids = [route_queue_item(session, layout, plan, item).queue_item.id for item in items]
        session.commit()
        return ids


@pytest.fixture
def item_id(session_factory: sessionmaker[Session], layout: DataLayout) -> int:
    (queue_item_id,) = _pending_items(session_factory, layout)
    return queue_item_id


def _register(session_factory: sessionmaker[Session], *, name: str, born: date) -> None:
    """`name` yazımlı, `born` doğumlu kayıtlı çalışan (E0042)."""
    with session_factory() as session:
        employee = Employee(
            id="E0042",
            folder_name="Kayitli_Kisi_E0042",
            given_names="Kayitli",
            surname="Kisi",
            date_of_birth=born,
        )
        session.add(employee)
        session.add(
            EmployeeAlias(employee=employee, raw_name=name, normalized_name=normalize_name(name))
        )
        session.commit()


def _token(html: str) -> str:
    match = re.search(r'name="confirmation" value="([^"]+)"', html)
    assert match is not None, html
    return match.group(1)


def _confirm(client: TestClient, queue_item_id: int, values: dict[str, str]) -> Any:
    return client.post(f"/queues/{queue_item_id}/profile/confirm", data=values)


def _prepare(client: TestClient, queue_item_id: int, values: dict[str, str] = EDITED) -> str:
    response = client.post(f"/queues/{queue_item_id}/profile/prepare", data=values)
    assert response.status_code == 200, response.text
    return _token(response.text)


def _create(
    client: TestClient,
    queue_item_id: int,
    token: str | None,
    values: dict[str, str] = EDITED,
    **extra: str,
) -> Any:  # TestClient yanıtı
    data = {**values, **extra}
    if token is not None:
        data["confirmation"] = token
    return client.post(f"/queues/{queue_item_id}/profile", data=data)


def _count(session: Session, event_type: EventType) -> int:
    return session.scalar(select(func.count()).where(Event.type == event_type.value)) or 0


def _unchanged(
    session_factory: sessionmaker[Session], queue_item_id: int, *, employees: int = 0
) -> None:
    """Hiçbir şey olmadı: öğe çözülmedi, çalışan açılmadı, çıktı ve onay olayı yazılmadı."""
    with session_factory() as session:
        queue_item = session.get_one(QueueItem, queue_item_id)
        assert (queue_item.resolved_at, queue_item.resolved_by) == (None, None)
        assert session.scalar(select(func.count()).select_from(Employee)) == employees
        assert session.scalars(select(Document)).all() == []
        for event_type in (
            EventType.USER_CONFIRMED,
            EventType.EMPLOYEE_CREATED,
            EventType.MANUAL_APPROVE,
        ):
            assert _count(session, event_type) == 0


def _section(html: str, section_id: str) -> str:
    match = re.search(rf'<section id="{section_id}".*?</section>', html, re.S)
    assert match is not None, html
    return match.group(0)


def _edit_form(html: str) -> str:
    match = re.search(r'<form class="profile-edit".*?</form>', html, re.S)
    assert match is not None, html
    return match.group(0)


def _hidden(html: str) -> dict[str, str]:
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', html))


# --- öğe detayındaki profil bölümü ----------------------------------------------------------------


def test_pending_item_offers_the_proposed_profile_as_an_editable_form(
    client: TestClient, item_id: int
) -> None:
    html = client.get(f"/queues/{item_id}").text

    section = _section(html, "new-profile")
    assert "Profil oluştur" in section
    form = _edit_form(section)
    assert f'hx-post="/queues/{item_id}/profile/confirm"' in form
    # Form yalnız çalışan kaydının altı alanını taşır, öneriyle dolu (K17: belge içeriği yok).
    inputs = re.findall(
        r'<input type="([^"]+)" id="profile-[^"]+" name="([^"]+)"\s+value="([^"]*)"', form
    )
    assert inputs == [
        ("text", "given_names", GIVEN),
        ("text", "surname", SURNAME),
        ("text", "other_names", ""),
        ("text", "original_script_name", ""),
        ("date", "date_of_birth", BORN),
        ("text", "nationality", "RUS"),
    ]
    assert form.count("<input") == 6
    assert "<textarea" not in form and "<select" not in form
    assert '<div id="profile-step"' in section
    # Onay bekleyen profil kayıtlı bir çalışana da atanabilir (10.7.2).
    assert '<section id="assign"' in html


def test_items_that_propose_no_profile_have_no_profile_section(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # Zorunlu alanı okunamayan belge (Unreadable) profil önerisi değildir.
    queue_item_id = _queued_item(session_factory, layout)

    html = client.get(f"/queues/{queue_item_id}").text

    assert '<section id="new-profile"' not in html
    assert "/profile/" not in html


def test_superseded_pending_item_has_no_profile_section(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, item_id: int
) -> None:
    with session_factory() as session:
        upload = session.get_one(QueueItem, item_id).upload
        create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)  # K18: sürüm 2
        session.commit()

    html = client.get(f"/queues/{item_id}").text

    assert SUPERSEDED_NOTE in html
    assert '<section id="new-profile"' not in html


def test_pending_item_whose_person_is_now_registered_says_why_it_cannot_be_approved(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    # Öneriden sonra kişi kayıtlı: satır 7 artık uymuyor, form yok — belge çalışana atanır.
    _register(session_factory, name=f"{GIVEN} {SURNAME}", born=date.fromisoformat(BORN))

    section = _section(client.get(f"/queues/{item_id}").text, "new-profile")

    assert "eşleştirme hükmü name_dob" in section
    assert "profile-edit" not in section


# --- iki aşamalı onay -----------------------------------------------------------------------------


def test_first_confirmation_shows_the_edited_profile_verbatim_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    response = _confirm(client, item_id, EDITED)

    assert response.status_code == 200, response.text
    html = response.text
    assert FIRST_TEXT == first_text(Operation.APPROVE_PROFILE, name=f"{GIVEN} {EDITED_SURNAME}")
    assert f'<p class="confirm-text" role="alert">{FIRST_TEXT}</p>' in html
    assert f'hx-post="/queues/{item_id}/profile/prepare"' in html
    # Onaylanacak değerler ve öneriden farklı olanlar gösterilir; formun değerleri taşınır.
    assert f'<dd>{EDITED_SURNAME} <span class="edited">düzeltildi</span></dd>' in html
    assert '<dd>01.02.1990 <span class="edited">düzeltildi</span></dd>' in html
    assert f"<dd>{GIVEN}</dd>" in html and "<dd>—</dd>" in html
    assert html.count("düzeltildi") == 2
    assert _hidden(html) == EDITED
    assert 'name="confirmation"' not in html  # belirteç birinci onaydan sonra gelir
    _unchanged(session_factory, item_id)


def test_first_confirmation_of_the_unchanged_proposal_says_so(
    client: TestClient, item_id: int
) -> None:
    html = _confirm(client, item_id, PROPOSAL).text

    assert f"{GIVEN} {SURNAME} için yeni bir çalışan profili oluşturmak üzeresiniz." in html
    assert "Önerilen profil değiştirilmeden onaylanacak." in html
    assert "düzeltildi" not in html


def test_form_values_are_trimmed_and_the_nationality_is_upper_cased(
    client: TestClient, item_id: int
) -> None:
    values = {**EDITED, "surname": f"  {EDITED_SURNAME} ", "nationality": " srb "}

    html = _confirm(client, item_id, values).text

    assert _hidden(html) == {**EDITED, "nationality": "SRB"}


def test_invalid_fields_are_listed_at_every_step_and_change_nothing(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    values = {**EDITED, "given_names": " ", "date_of_birth": "01.02.1990", "nationality": "RUS1"}
    token = issue_token(
        session_factory, Operation.APPROVE_PROFILE, profile_subject(item_id, _fields(EDITED))
    )

    responses = [
        _confirm(client, item_id, values),
        client.post(f"/queues/{item_id}/profile/prepare", data=values),
        _create(client, item_id, token, values),
    ]

    for response in responses:
        assert response.status_code == 422, response.text
        html = response.text
        assert "Profil alanları geçersiz; düzeltip yeniden gönderin." in html
        assert "<li>Ad: boş olamaz</li>" in html
        assert "<li>Doğum tarihi: YYYY-AA-GG biçiminde bir tarih olmalı</li>" in html
        assert "<li>Vatandaşlık: ICAO uyruk kodu olmalı (1–3 büyük harf, ör. RUS, D)</li>" in html
        assert 'name="confirmation"' not in html
    _unchanged(session_factory, item_id)


def test_first_confirmation_gives_the_second_one_with_a_token_and_changes_nothing(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    response = client.post(f"/queues/{item_id}/profile/prepare", data=EDITED)

    assert response.status_code == 200
    html = response.text
    assert SECOND_TEXT == second_text(Operation.APPROVE_PROFILE)
    assert f'<p class="confirm-text" role="alert">{SECOND_TEXT}</p>' in html
    assert f'hx-post="/queues/{item_id}/profile"' in html
    hidden = _hidden(html)
    assert hidden.pop("confirmation") == _token(html)
    assert hidden == EDITED
    _unchanged(session_factory, item_id)


def test_confirmed_edited_profile_opens_the_employee_and_binds_the_unchanged_document(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    item_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 10.7.3 kabul kriteri: önerilen profil düzenlenip onaylanır; belge içeriği değişmez.
    with session_factory() as session:
        analyses = [copy.deepcopy(page.analysis_json) for page in session.scalars(select(Page))]
    token = _prepare(client, item_id)
    _refuse_provider(monkeypatch)  # K9: onay yapay zekâya sorulmaz

    response = _create(client, item_id, token)

    assert response.status_code == 200, response.text
    with session_factory() as session:
        queue_item = session.get_one(QueueItem, item_id)
        (upload_file,) = queue_item.upload.files
        employee = session.get_one(Employee, NEW)
        (document,) = session.scalars(select(Document)).all()
        # Çalışan düzeltilmiş profille açıldı (K7, K8).
        assert (
            employee.folder_name,
            employee.given_names,
            employee.surname,
            employee.date_of_birth,
            employee.nationality,
        ) == (EDITED_FOLDER, GIVEN, EDITED_SURNAME, date(1990, 2, 1), "RUS")
        # Belge ona bağlandı; içerik kaynağın baytlarıdır, yalnız adı çalışanın adından (K8, K11).
        output = layout.resolve(document.path)
        assert output == layout.ready_dir(EDITED_FOLDER) / "Test_Ornekovic-Work-Permit.pdf"
        assert sha256_file(output) == upload_file.sha256
        assert (document.employee_id, document.type_slug, document.source_refs_json) == (
            NEW,
            PERMIT,
            [{"file_id": upload_file.id, "pages": [0]}],
        )
        assert [page.analysis_json for page in session.scalars(select(Page))] == analyses
        assert queue_item.resolved_by == SIGNED_IN.username

        events = list(
            session.scalars(
                select(Event)
                .where(Event.upload_id == queue_item.upload_id)
                .order_by(Event.ts, Event.id)
            )
        )
        types = [event.type for event in events]
        assert (
            types.index(EventType.USER_CONFIRMED)
            < types.index(EventType.EMPLOYEE_CREATED)
            < types.index(EventType.MANUAL_APPROVE)
        )
        confirmed = next(e for e in events if e.type == EventType.USER_CONFIRMED)
        created = next(e for e in events if e.type == EventType.EMPLOYEE_CREATED)
        manual = next(e for e in events if e.type == EventType.MANUAL_APPROVE)
        # §20.6.1 / §20.6.2: kullanıcı adı, işlem, hedef ve iki onayın zamanı.
        assert confirmed.actor == created.actor == manual.actor == SIGNED_IN.username
        data = confirmed.data_json
        assert data is not None
        assert data["operation"] == "approve_profile"
        assert data["target"] == {"queue_item_id": item_id}
        first = datetime.fromisoformat(data["first_confirmed_at"])
        second = datetime.fromisoformat(data["second_confirmed_at"])
        assert first <= second <= utcnow()
        assert created.data_json == {
            "action": "pending",
            "document_type_slug": PERMIT,
            "edited_fields": ["surname", "date_of_birth"],
        }
        assert (manual.document_id, manual.employee_id) == (document.id, NEW)
        # Olaylar kişisel değer taşımaz (CONVENTIONS §6).
        logged = json.dumps(
            [[e.data_json, e.message] for e in (confirmed, created, manual)], ensure_ascii=False
        )
        for value in PERSONAL_VALUES:
            assert value not in logged
    html = response.text
    link = f'<a href="/employees/{NEW}">{GIVEN} {EDITED_SURNAME} ({NEW})</a>'
    assert f"Çalışan profili oluşturuldu: {link}" in html
    assert "Belge Test_Ornekovic-Work-Permit.pdf olarak çalışanın Hazır klasörüne yazıldı." in html
    assert f'<a href="/documents/{document.id}/history">Çıktının geçmişi</a>' in html
    assert '<div id="profile-form" hx-swap-oob="true"></div>' in html


def test_after_approval_the_item_is_resolved_and_the_profile_is_there(
    client: TestClient, item_id: int
) -> None:
    assert _create(client, item_id, _prepare(client, item_id)).status_code == 200

    detail = client.get(f"/queues/{item_id}").text
    profile = client.get(f"/employees/{NEW}")

    assert "<dt>Durum</dt><dd>Çözülen</dd>" in detail
    assert '<section id="new-profile"' not in detail
    timeline = _section(detail, "timeline")
    assert EventType.USER_CONFIRMED.value in timeline
    assert EventType.MANUAL_APPROVE.value in timeline and SIGNED_IN.username in timeline
    assert profile.status_code == 200
    assert f"<dt>Soyad</dt><dd>{EDITED_SURNAME}</dd>" in profile.text


def test_unchanged_proposal_is_approved_as_proposed(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    response = _create(client, item_id, _prepare(client, item_id, PROPOSAL), PROPOSAL)

    assert response.status_code == 200, response.text
    with session_factory() as session:
        employee = session.get_one(Employee, NEW)
        assert (employee.folder_name, employee.surname) == ("Test_Ornekova_E0001", SURNAME)
        (created,) = session.scalars(
            select(Event).where(Event.type == EventType.EMPLOYEE_CREATED)
        ).all()
        assert created.data_json == {"action": "pending", "document_type_slug": PERMIT}


def test_document_content_cannot_be_sent_with_the_profile(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, item_id: int
) -> None:
    # K17: akış yalnız çalışan alanlarını okur; tür, sayfa ya da okuma gönderilse de yok sayılır.
    token = _prepare(client, item_id)

    response = _create(
        client,
        item_id,
        token,
        document_type_slug="profile_picture",
        pages="1",
        surname_on_document=EDITED_SURNAME,
    )

    assert response.status_code == 200, response.text
    with session_factory() as session:
        (document,) = session.scalars(select(Document)).all()
        (upload_file,) = session.get_one(QueueItem, item_id).upload.files
        assert document.type_slug == PERMIT
        assert document.source_refs_json == [{"file_id": upload_file.id, "pages": [0]}]
        assert sha256_file(layout.resolve(document.path)) == upload_file.sha256


# --- belirteç kuralları (§20.6.1 adım 4–5, §20.6.2) -----------------------------------------------


def _fields(values: dict[str, str]) -> ProfileFields:
    return ProfileFields(
        given_names=values["given_names"],
        surname=values["surname"],
        other_names=values["other_names"] or None,
        original_script_name=values["original_script_name"] or None,
        date_of_birth=date.fromisoformat(values["date_of_birth"]),
        nationality=values["nationality"] or None,
    )


@pytest.mark.parametrize("token", [None, "", "abc", "123.deadbeef"], ids=repr)
def test_approval_without_a_valid_token_changes_nothing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    item_id: int,
    token: str | None,
) -> None:
    # S16: yalnız birinci onayla (ya da hiç onaysız) gelen istek hiçbir değişiklik yapmaz.
    response = _create(client, item_id, token)

    assert response.status_code == 400
    assert CONFIRMATION_REFUSED in response.text
    _unchanged(session_factory, item_id)
    assert list(layout.employees.iterdir()) == []


def test_a_token_is_bound_to_the_confirmed_values(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    # İkinci onaydan sonra değiştirilen alan onaylanmamıştır: belirteç geçmez.
    token = _prepare(client, item_id, EDITED)

    for values in (PROPOSAL, {**EDITED, "nationality": "SRB"}, {**EDITED, "other_names": "X"}):
        response = _create(client, item_id, token, values)
        assert response.status_code == 400, values
    _unchanged(session_factory, item_id)
    assert _create(client, item_id, token).status_code == 200


def test_a_token_is_bound_to_its_item_its_operation_and_its_session(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    item_id, other_item = _pending_items(session_factory, layout, count=2)
    token = _prepare(client, item_id)
    # Aynı oturumun atama belirteci (10.7.2) ve aynı hedefe başka işlem belirteci profil
    # onayında geçmez.
    foreign = issue_token(session_factory, Operation.ASSIGN, assignment_subject(item_id, "E0042"))
    same_target = issue_token(
        session_factory, Operation.ASSIGN, profile_subject(item_id, _fields(EDITED))
    )

    wrong_item = _create(client, other_item, token)
    other_operation = _create(client, item_id, foreign)
    other_operation_same_target = _create(client, item_id, same_target)
    client.cookies.set(SESSION_COOKIE, "oturum-iki")
    other_session = _create(client, item_id, token)

    for response in (wrong_item, other_operation, other_operation_same_target, other_session):
        assert response.status_code == 400, response.text
    _unchanged(session_factory, item_id)
    _unchanged(session_factory, other_item)


def test_the_same_token_twice_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    token = _prepare(client, item_id)
    assert _create(client, item_id, token).status_code == 200

    replay = _create(client, item_id, token)

    assert replay.status_code == 409
    assert PROFILE_RESOLVED_NOTE in replay.text
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Employee)) == 1
        assert len(session.scalars(select(Document)).all()) == 1
        assert _count(session, EventType.USER_CONFIRMED) == 1
        assert _count(session, EventType.MANUAL_APPROVE) == 1


def test_an_expired_token_is_refused(
    client: TestClient,
    session_factory: sessionmaker[Session],
    item_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _prepare(client, item_id)
    later = utcnow() + confirm.CONFIRMATION_TTL + timedelta(seconds=5)
    monkeypatch.setattr(confirm, "utcnow", lambda: later)

    response = _create(client, item_id, token)

    assert response.status_code == 400
    _unchanged(session_factory, item_id)


def test_prepare_needs_a_session_cookie(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    client.cookies.clear()

    response = client.post(f"/queues/{item_id}/profile/prepare", data=EDITED)

    assert response.status_code == 400
    assert "Oturum çerezi yok." in response.text
    _unchanged(session_factory, item_id)


def test_a_failed_approval_does_not_keep_the_confirmation_event(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, item_id: int
) -> None:
    # Onay olayı ve onay tek işlemdedir: Inbox'taki orijinal değişmişse (K10) onay düşer,
    # `USER_CONFIRMED` de geri alınır, çalışan açılmaz.
    token = _prepare(client, item_id)
    with session_factory() as session:
        (upload_file,) = session.get_one(QueueItem, item_id).upload.files
        layout.resolve(upload_file.stored_path).write_bytes(b"degistirildi")

    response = _create(client, item_id, token)

    assert response.status_code == 409
    _unchanged(session_factory, item_id)


# --- düzeltme ikinci çalışan açtırmaz; onaylanamayan öğe, bilinmeyen kayıt -----------------------


def test_edited_profile_matching_a_registered_employee_is_refused_at_every_step(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    # Belgenin kişisi kimseye uymuyor (satır 7) ama düzeltilen ad-soyad + doğum tarihi kayıtlı
    # çalışana uyuyor: ikinci çalışan açılmaz (belge o çalışana atanır, 10.7.2).
    _register(session_factory, name="KAYITLI KISI", born=date(1985, 5, 5))
    values = {
        **PROPOSAL,
        "given_names": "KAYITLI",
        "surname": "KISI",
        "date_of_birth": "1985-05-05",
    }
    token = issue_token(
        session_factory, Operation.APPROVE_PROFILE, profile_subject(item_id, _fields(values))
    )

    responses = [
        _confirm(client, item_id, values),
        client.post(f"/queues/{item_id}/profile/prepare", data=values),
        _create(client, item_id, token, values),
    ]

    for response in responses:
        assert response.status_code == 409, response.text
        assert "onaylanan profil kayıtlı çalışanla eşleşiyor" in response.text
        assert "eşleştirme hükmü name_dob (E0042)" in response.text
    _unchanged(session_factory, item_id, employees=1)


def _steps(
    client: TestClient, session_factory: sessionmaker[Session], queue_item_id: int
) -> list[Any]:
    token = issue_token(
        session_factory, Operation.APPROVE_PROFILE, profile_subject(queue_item_id, _fields(EDITED))
    )
    return [
        _confirm(client, queue_item_id, EDITED),
        client.post(f"/queues/{queue_item_id}/profile/prepare", data=EDITED),
        _create(client, queue_item_id, token),
    ]


def test_every_step_refuses_an_item_that_proposes_no_profile(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    queue_item_id = _queued_item(session_factory, layout)  # Unreadable, satır 7 değil

    for response in _steps(client, session_factory, queue_item_id):
        assert response.status_code == 409
        assert NOT_PENDING_NOTE in response.text
    _unchanged(session_factory, queue_item_id, employees=1)


def test_every_step_refuses_a_superseded_item(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, item_id: int
) -> None:
    with session_factory() as session:
        upload = session.get_one(QueueItem, item_id).upload
        create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
        session.commit()

    for response in _steps(client, session_factory, item_id):
        assert response.status_code == 409
        assert SUPERSEDED_NOTE in response.text
    _unchanged(session_factory, item_id)


def test_every_step_reports_a_missing_item(
    client: TestClient, session_factory: sessionmaker[Session], item_id: int
) -> None:
    for response in _steps(client, session_factory, item_id + 100):
        assert response.status_code == 404
        assert QUEUE_ITEM_NOT_FOUND in response.text
    _unchanged(session_factory, item_id)


def test_profile_steps_require_a_session(app: FastAPI, item_id: int) -> None:
    app.dependency_overrides.pop(get_current_user)  # oturumsuz istemci
    anonymous = TestClient(app)
    for path in (
        f"/queues/{item_id}/profile/confirm",
        f"/queues/{item_id}/profile/prepare",
        f"/queues/{item_id}/profile",
    ):
        response = anonymous.post(path, data=EDITED, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login?next="), path


def test_an_item_vanishing_between_the_checks_is_reported_as_missing(
    client: TestClient,
    session_factory: sessionmaker[Session],
    item_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Öğe ön denetimle onay arasında bulunamazsa (yarış) adım 404 verir, hiçbir şey yazılmaz.
    def _missing(*args: object, **kwargs: object) -> object:
        raise QueueItemNotFoundError(f"Kuyruk öğesi bulunamadı: {item_id}")

    token = _prepare(client, item_id)
    monkeypatch.setattr(queue_module, "approve_queued_profile", _missing)
    approval = _create(client, item_id, token)
    monkeypatch.setattr(queue_module, "review_queued_profile", _missing)
    review = _confirm(client, item_id, EDITED)

    for response in (approval, review):
        assert response.status_code == 404, response.text
    assert QUEUE_ITEM_NOT_FOUND in review.text
    _unchanged(session_factory, item_id)


# --- 05.2.2: Latin yazımı belgede olmayan öneri ---------------------------------------------------

ARABIC_GIVEN, ARABIC_SURNAME = "محمد", "علي"
LATIN_PROFILE = {
    **PROPOSAL,
    "given_names": "Muhammad",
    "surname": "Ali",
    "original_script_name": f"{ARABIC_GIVEN} {ARABIC_SURNAME}",
}


@pytest.fixture
def arabic_item_id(session_factory: sessionmaker[Session], layout: DataLayout) -> int:
    """Arap yazımlı adın onay bekleyen profili: Latin yazım belgede yok, numara temiz."""
    with session_factory() as session:
        import_catalog(session, CATALOG)
        person = _person(surname=ARABIC_SURNAME, given_names=ARABIC_GIVEN)
        page = _page(PERMIT, person=person, language="ar", script="arabic")
        upload = _upload_with_analyses(session, layout, _pdf(page))
        plan = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
        (item,) = read_plan(plan).items
        assert item.employee.action.value == "pending"
        queue_item_id = route_queue_item(session, layout, plan, item).queue_item.id
        session.commit()
        return queue_item_id


def test_proposal_without_latin_spelling_leaves_the_latin_name_to_hr(
    client: TestClient, arabic_item_id: int
) -> None:
    html = client.get(f"/queues/{arabic_item_id}").text

    assert "Latin yazım belgede yok" in html
    form = _edit_form(_section(html, "new-profile"))
    inputs = re.findall(
        r'<input type="([^"]+)" id="profile-[^"]+" name="([^"]+)"\s+value="([^"]*)"', form
    )
    assert inputs[:4] == [
        ("text", "given_names", ""),
        ("text", "surname", ""),
        ("text", "other_names", ""),
        ("text", "original_script_name", f"{ARABIC_GIVEN} {ARABIC_SURNAME}"),
    ]
    assert "Latin harfleriyle" in form


def test_non_latin_names_are_refused_at_every_step(
    client: TestClient, session_factory: sessionmaker[Session], arabic_item_id: int
) -> None:
    values = {**LATIN_PROFILE, "given_names": ARABIC_GIVEN, "surname": ARABIC_SURNAME}
    token = issue_token(
        session_factory,
        Operation.APPROVE_PROFILE,
        profile_subject(arabic_item_id, _fields(values)),
    )

    responses = [
        _confirm(client, arabic_item_id, values),
        client.post(f"/queues/{arabic_item_id}/profile/prepare", data=values),
        _create(client, arabic_item_id, token, values),
    ]

    for response in responses:
        assert response.status_code == 422, response.text
        latin_only = "Latin harfleriyle yazılmalı; Latin olmayan yazım Orijinal yazım alanına"
        assert f"<li>Ad: {latin_only}</li>" in response.text
        assert f"<li>Soyad: {latin_only}</li>" in response.text
    _unchanged(session_factory, arabic_item_id)


def test_latin_name_written_by_hr_opens_the_employee(
    client: TestClient, session_factory: sessionmaker[Session], arabic_item_id: int
) -> None:
    token = _prepare(client, arabic_item_id, LATIN_PROFILE)

    response = _create(client, arabic_item_id, token, LATIN_PROFILE)

    assert response.status_code == 200, response.text
    with session_factory() as session:
        employee = session.get_one(Employee, NEW)
        assert (
            employee.given_names,
            employee.surname,
            employee.original_script_name,
            employee.folder_name,
        ) == ("Muhammad", "Ali", f"{ARABIC_GIVEN} {ARABIC_SURNAME}", "Muhammad_Ali_E0001")
