"""10.10.4 — onay metinleri üç dilde: iki aşamalı onay metinleri (§20.6) kullanıcının dilinde
görünür; İngilizce ve Sırpça karşılıklar PRD §20.6.3'ten birebir gelir, belirteç akışı ve
`USER_CONFIRMED` olayı dilden bağımsızdır (PLAN.md §D92 h, §D96; tm 156).

Üç katman: (1) taşıma akışı baştan sona (birinci ve ikinci metin, belirteçsiz ret, tüketilen
belirteç, olay); (2) çalışan ve belge akışlarının birinci ve ikinci adım sayfaları; (3) kuyruk ve
aday tür onay adımı şablonları — onay metni ile çevresindeki düğme ve etiketler. Bütün sayfalar
Türkçe kalıntı taramasından (`tests/i18n/residue.py`) geçer; onay paragrafı da taranır. Metin
PRD'den birebirdir: beklenen değer `first_text`/`second_text`'ten gelir, onların PRD ile eşitliği
`test_confirm.py`'dedir. Veri sentetiktir, gerçek kimlik belgesi yoktur.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.catalog import import_catalog, load_seed_catalog
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    Event,
)
from app.events import EventType
from app.i18n import translate, use_language
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    CONFIRMATION_TEXTS_BY_LANGUAGE,
    Operation,
    first_text,
    second_text,
)
from app.web.templating import render_page
from tests.fixtures.gen import make_pdf_bytes
from tests.i18n.residue import assert_no_turkish
from tests.web.conftest import SESSION, SIGNED_IN

LANGUAGES = ("en", "sr", "tr")
FOREIGN = ("en", "sr")  # Türkçe kalıntı taraması yalnız bunlarda anlamlıdır
PASSPORT = "russian_passport"
CONFIRM_TEXT = re.compile(r'<p class="confirm-text"[^>]*>(.*?)</p>', re.S)
TOKEN = re.compile(r'name="confirmation" value="([^"]+)"')


@pytest.fixture
def speak(app: FastAPI):
    """Oturumdaki kullanıcının dil tercihini koyar (girişli istekte dil hesabın tercihidir)."""

    def choose(language: str) -> None:
        user = PanelUser(SIGNED_IN.id, SIGNED_IN.username, SIGNED_IN.role, language=language)
        app.dependency_overrides[get_current_user] = lambda: user

    return choose


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    """Onay belirteci oturum çerezine bağlıdır; oturum bağımlılığı geçersiz kılındığı için elle."""
    client.cookies.set(SESSION_COOKIE, SESSION)


def _employee(session: Session, number: int, given: str, surname: str, **fields: Any) -> Employee:
    employee_id = f"E{number:04d}"
    employee = Employee(
        id=employee_id,
        folder_name=f"{given}_{surname}_{employee_id}",
        given_names=given,
        surname=surname,
        **fields,
    )
    session.add(employee)
    session.flush()
    return employee


@pytest.fixture
def world(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, int]:
    """Etkin iki çalışan (E0001 belgeli ve isim yazımlı, E0002) ve pasif bir çalışan (E0003);
    adlar Türkçe harf taşımaz."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        dmitry = _employee(session, 1, "Dmitry", "Vasiliev", nationality="RUS")
        _employee(session, 2, "Anna", "Petrova")
        _employee(session, 3, "Boris", "Ivanov", status="inactive")
        path = layout.ensure_employee_tree(dmitry.folder_name) / "Hazir" / "Dmitry_Vasiliev.pdf"
        path.write_bytes(make_pdf_bytes())
        document = Document(
            employee_id=dmitry.id,
            type_slug=PASSPORT,
            path=layout.relative(path),
            format="pdf",
            sequence_no=1,
            source_refs_json=[],
            status=DocumentStatus.ACTIVE.value,
        )
        session.add(document)
        session.add(
            EmployeeAlias(
                employee_id=dmitry.id,
                raw_name="Dmitry Vasiliev",
                normalized_name="dmitry vasiliev",
                script="latin",
            )
        )
        session.flush()
        alias_id = session.query(EmployeeAlias.id).scalar()
        layout.ensure_employee_tree("Anna_Petrova_E0002")
        session.commit()
        return {"document": document.id, "alias": alias_id}


def _confirm_texts(html: str) -> list[str]:
    """Sayfadaki onay paragraflarının görünen metni (kaçışlar açılmış)."""
    return [" ".join(unescape(text).split()) for text in CONFIRM_TEXT.findall(html)]


def _token(html: str) -> str:
    match = TOKEN.search(html)
    assert match is not None, html
    return match.group(1)


def _events(session_factory: sessionmaker[Session], event_type: EventType) -> list[Event]:
    with session_factory() as session:
        return list(session.scalars(select(Event).where(Event.type == event_type.value)))


# --- 1. taşıma akışı baştan sona ---------------------------------------------------------------


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_move_flow_shows_both_texts_in_the_chosen_language_and_keeps_the_token_flow(
    client: TestClient,
    speak: Any,
    session_factory: sessionmaker[Session],
    world: dict[str, int],
    language: str,
) -> None:
    speak(language)
    document = world["document"]
    first = first_text(Operation.MOVE, language=language)
    second = second_text(Operation.MOVE, language=language)

    step_one = client.get(f"/documents/{document}/move/confirm", params={"employee_id": "E0002"})
    assert step_one.status_code == 200
    assert _confirm_texts(step_one.text) == [first]

    prepared = client.post(f"/documents/{document}/move/prepare", data={"employee_id": "E0002"})
    assert prepared.status_code == 200
    assert _confirm_texts(prepared.text) == [second]
    token = _token(prepared.text)
    if language in FOREIGN:
        assert_no_turkish(step_one.text, language)
        assert_no_turkish(prepared.text, language)

    # Belirteçsiz istek reddedilir, hiçbir şey değişmez; ret metni seçili dildedir.
    refused = client.post(f"/documents/{document}/move", data={"employee_id": "E0002"})
    assert refused.status_code == 400
    with use_language(language):
        assert translate(CONFIRMATION_REFUSED) in unescape(refused.text)
    with session_factory() as session:
        assert session.get_one(Document, document).employee_id == "E0001"
    assert _events(session_factory, EventType.USER_CONFIRMED) == []

    moved = client.post(
        f"/documents/{document}/move", data={"employee_id": "E0002", "confirmation": token}
    )
    assert moved.status_code == 200, moved.text
    with session_factory() as session:
        assert session.get_one(Document, document).employee_id == "E0002"
    replay = client.post(
        f"/documents/{document}/move", data={"employee_id": "E0001", "confirmation": token}
    )
    assert replay.status_code == 400  # belirteç tüketildi (başka hedefe de bağlı değil)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_confirmation_event_does_not_depend_on_the_language(
    client: TestClient,
    speak: Any,
    session_factory: sessionmaker[Session],
    world: dict[str, int],
    language: str,
) -> None:
    speak(language)
    document = world["document"]
    token = _token(
        client.post(f"/documents/{document}/move/prepare", data={"employee_id": "E0002"}).text
    )
    assert (
        client.post(
            f"/documents/{document}/move", data={"employee_id": "E0002", "confirmation": token}
        ).status_code
        == 200
    )

    (event,) = _events(session_factory, EventType.USER_CONFIRMED)
    data = event.data_json
    assert data is not None
    assert set(data) == {"operation", "target", "first_confirmed_at", "second_confirmed_at"}
    assert data["operation"] == "move"
    assert data["target"] == {"document_id": document, "employee_id": "E0002"}
    assert event.actor == SIGNED_IN.username
    for stamp in ("first_confirmed_at", "second_confirmed_at"):
        assert datetime.fromisoformat(data[stamp]).tzinfo in (None, UTC)
    # Olay metin taşımaz: hiçbir dilin onay cümlesi olayda yoktur.
    dumped = json.dumps(data, ensure_ascii=False)
    for texts in CONFIRMATION_TEXTS_BY_LANGUAGE.values():
        for pair in texts.values():
            assert pair.first not in dumped and pair.second not in dumped


# --- 2. çalışan ve belge akışlarının adım sayfaları ----------------------------------------------

# (kimlik, yöntem, yol, form, işlem, adım, yer tutucu değerleri); `{alias}` ve `{document}`
# dünyadan gelir.
STEPS = [
    ("edit-1", "get", "/employees/E0001/fields", None, Operation.EDIT_EMPLOYEE, "first", {}),
    (
        "edit-2",
        "post",
        "/employees/E0001/fields/prepare",
        {"given_names": "Dmitry", "surname": "Vasilev", "nationality": "RUS"},
        Operation.EDIT_EMPLOYEE,
        "second",
        {"count": 1},
    ),
    (
        "deactivate-1",
        "get",
        "/employees/E0001/status/confirm?to=inactive",
        None,
        Operation.DEACTIVATE_EMPLOYEE,
        "first",
        {"name": "Dmitry Vasiliev"},
    ),
    (
        "deactivate-2",
        "post",
        "/employees/E0001/status/prepare",
        {"to": "inactive", "reason": ""},
        Operation.DEACTIVATE_EMPLOYEE,
        "second",
        {},
    ),
    (
        "reactivate-1",
        "get",
        "/employees/E0003/status/confirm?to=active",
        None,
        Operation.REACTIVATE_EMPLOYEE,
        "first",
        {"name": "Boris Ivanov"},
    ),
    (
        "reactivate-2",
        "post",
        "/employees/E0003/status/prepare",
        {"to": "active", "reason": ""},
        Operation.REACTIVATE_EMPLOYEE,
        "second",
        {},
    ),
    (
        "remove-1",
        "get",
        "/employees/E0001/records/alias/{alias}/remove/confirm",
        None,
        Operation.REMOVE_PROFILE_RECORD,
        "first",
        {},
    ),
    (
        "remove-2",
        "post",
        "/employees/E0001/records/alias/{alias}/remove/prepare",
        None,
        Operation.REMOVE_PROFILE_RECORD,
        "second",
        {},
    ),
    (
        "merge-1",
        "get",
        "/employees/E0001/merge/confirm?other=E0002",
        None,
        Operation.MERGE_EMPLOYEES,
        "first",
        {"merged_name": "Anna Petrova", "kept_name": "Dmitry Vasiliev"},
    ),
    (
        "merge-2",
        "post",
        "/employees/E0001/merge/prepare",
        {"other": "E0002", "keep": "E0001"},
        Operation.MERGE_EMPLOYEES,
        "second",
        {"count": 0},
    ),
    (
        "archive-1",
        "get",
        "/documents/{document}/archive/confirm",
        None,
        Operation.ARCHIVE,
        "first",
        {},
    ),
    (
        "archive-2",
        "post",
        "/documents/{document}/archive/prepare",
        None,
        Operation.ARCHIVE,
        "second",
        {},
    ),
]


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("step", STEPS, ids=[step[0] for step in STEPS])
def test_every_employee_and_document_step_shows_the_text_of_the_chosen_language(
    client: TestClient,
    speak: Any,
    world: dict[str, int],
    language: str,
    step: tuple[str, str, str, dict[str, str] | None, Operation, str, dict[str, Any]],
) -> None:
    _, method, path, form, operation, which, values = step
    speak(language)
    url = path.format(**world)

    response = client.get(url) if method == "get" else client.post(url, data=form or {})

    assert response.status_code == 200, (url, response.text[:400])
    build = first_text if which == "first" else second_text
    expected = build(operation, language=language, **values)
    assert _confirm_texts(response.text) == [expected]
    if language in FOREIGN:
        assert_no_turkish(response.text, language)


def test_the_two_languages_really_differ_from_the_source_on_the_same_step(
    client: TestClient, speak: Any, world: dict[str, int]
) -> None:
    pages = {}
    for language in LANGUAGES:
        speak(language)
        pages[language] = _confirm_texts(
            client.get(f"/documents/{world['document']}/archive/confirm").text
        )
    assert len({tuple(texts) for texts in pages.values()}) == 3
    assert pages["en"][0].startswith("You are about to move this document to the archive")
    assert pages["sr"][0].startswith("Upravo ćete premestiti ovaj dokument u arhivu")
    assert pages["tr"][0].startswith("Bu belgeyi arşive taşımak üzeresiniz")


# --- 3. kuyruk ve aday tür onay adımı şablonları -----------------------------------------------


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


def _render(name: str, **context: Any) -> str:
    response = render_page(_request(), name, user=None, **context)
    return response.body.decode("utf-8")


ASSIGNEE = SimpleNamespace(id="E0002", name="Anna Petrova")
SUMMARY_ROWS = [
    SimpleNamespace(label="Given names", value="Anna", edited=True),
    SimpleNamespace(label="Surname", value="Petrova", edited=False),
]
CLOSE_STEP = SimpleNamespace(
    kind_label="Unknown",
    state_label="Open",
    upload_id="u_20990101_0001",
    type_name=None,
    reason="x",
)
CLOSE_CHOICES = [SimpleNamespace(value="duplicate", label="Duplicate", checked=True)]
CANDIDATE_FORM = {
    "slug": "work_permit",
    "name": "Work permit",
    "file_label": "Work_Permit",
    "country": "",
    "description": "Permit",
    "expected_file_types": [],
    "pages_min": "1",
    "pages_max": "2",
    "sides": "single",
    "front_back_layouts": [],
    "direct": False,
    "analyze": False,
    "required_fields": "",
    "allowed_conversions": [],
    "output_format": "pdf",
    "acceptance_criteria": [],
    "prompt_description": "",
}


def _step_pages(language: str) -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """Şablon → (çizilen sayfa, beklenen onay metni, çevre metinde bulunması gerekenler)."""
    en = language == "en"
    first = lambda op, **v: first_text(op, language=language, **v)  # noqa: E731
    second = lambda op, **v: second_text(op, language=language, **v)  # noqa: E731
    yes_continue = "Yes, continue" if en else "Da, nastavi"
    cancel = "Cancel" if en else "Odustani"
    selected = (
        "Selected employee: Anna Petrova (E0002)"
        if en
        else "Izabrani zaposleni: Anna Petrova (E0002)"
    )
    pages = {
        "assign-1": (
            _render(
                "queue_assign.html",
                queue_item_id=7,
                assignee=ASSIGNEE,
                first_confirmation=first(Operation.ASSIGN, name=ASSIGNEE.name),
            ),
            first(Operation.ASSIGN, name=ASSIGNEE.name),
            (selected, yes_continue, cancel),
        ),
        "assign-2": (
            _render(
                "queue_assign.html",
                queue_item_id=7,
                assignee=ASSIGNEE,
                second_confirmation=second(Operation.ASSIGN),
                confirmation="belirtec",
            ),
            second(Operation.ASSIGN),
            (selected, "Yes, assign" if en else "Da, dodeli", cancel),
        ),
        "profile-1": (
            _render(
                "queue_new_profile.html",
                queue_item_id=7,
                rows=SUMMARY_ROWS,
                hidden={"given_names": "Anna"},
                first_confirmation=first(Operation.APPROVE_PROFILE, name="Anna Petrova"),
            ),
            first(Operation.APPROVE_PROFILE, name="Anna Petrova"),
            ("corrected" if en else "ispravljeno", yes_continue, cancel),
        ),
        "profile-2": (
            _render(
                "queue_new_profile.html",
                queue_item_id=7,
                rows=SUMMARY_ROWS,
                hidden={"given_names": "Anna"},
                second_confirmation=second(Operation.APPROVE_PROFILE),
                confirmation="belirtec",
            ),
            second(Operation.APPROVE_PROFILE),
            ("Yes, create the profile" if en else "Da, kreiraj profil", cancel),
        ),
        "close-1": (
            _render(
                "queue_close_step.html",
                title="Close",
                queue_item_id=7,
                step=CLOSE_STEP,
                choices=CLOSE_CHOICES,
                note="",
                note_limit=200,
                first_confirmation=first(Operation.CLOSE_QUEUE_ITEM),
            ),
            first(Operation.CLOSE_QUEUE_ITEM),
            (
                "Queue item 7" if en else "Stavka reda 7",
                "Not determined" if en else "Nije određeno",
                yes_continue,
                cancel,
            ),
        ),
        "close-2": (
            _render(
                "queue_close_step.html",
                title="Close",
                queue_item_id=7,
                step=CLOSE_STEP,
                close_reason_label="Duplicate",
                close_reason="duplicate",
                note="",
                second_confirmation=second(Operation.CLOSE_QUEUE_ITEM),
                confirmation="belirtec",
            ),
            second(Operation.CLOSE_QUEUE_ITEM),
            (
                "Reason for closing: Duplicate" if en else "Razlog zatvaranja: Duplicate",
                "Yes, close" if en else "Da, zatvori",
                cancel,
            ),
        ),
        "type-1": (
            _render(
                "catalog_candidate_step.html",
                candidate_id=3,
                candidate_name="Work permit",
                step="approve",
                rows=[("Name", "Work permit")],
                form=CANDIDATE_FORM,
                first_confirmation=first(Operation.APPROVE_TYPE, type_name="Work permit"),
            ),
            first(Operation.APPROVE_TYPE, type_name="Work permit"),
            (
                "Add to the standard types: Work permit"
                if en
                else "Dodaj među standardne tipove: Work permit",
                yes_continue,
                cancel,
            ),
        ),
        "type-2": (
            _render(
                "catalog_candidate_step.html",
                candidate_id=3,
                candidate_name="Work permit",
                step="approve",
                rows=[("Name", "Work permit")],
                form=CANDIDATE_FORM,
                second_confirmation=second(Operation.APPROVE_TYPE),
                confirmation="belirtec",
            ),
            second(Operation.APPROVE_TYPE),
            ("Yes, add the type" if en else "Da, dodaj tip", cancel),
        ),
    }
    return pages


@pytest.mark.parametrize("language", FOREIGN)
def test_the_queue_and_candidate_type_steps_carry_the_text_and_their_own_controls_translated(
    language: str,
) -> None:
    with use_language(language):
        for name, (html, expected, around) in _step_pages(language).items():
            assert _confirm_texts(html) == [expected], name
            visible = unescape(html)
            for text in around:
                assert text in visible, (name, text)
            assert_no_turkish(html, language)


@pytest.mark.parametrize("language", FOREIGN)
def test_the_refusal_shows_in_the_chosen_language_on_every_confirmation_step_template(
    language: str,
) -> None:
    contexts = {
        "queue_assign.html": {"queue_item_id": 7, "error": CONFIRMATION_REFUSED},
        "queue_new_profile.html": {"queue_item_id": 7, "error": CONFIRMATION_REFUSED},
        "queue_close_step.html": {
            "title": "Close",
            "queue_item_id": 7,
            "step": None,
            "error": CONFIRMATION_REFUSED,
        },
        "catalog_candidate_step.html": {
            "candidate_id": 3,
            "error": CONFIRMATION_REFUSED,
        },
    }
    with use_language(language):
        expected = translate(CONFIRMATION_REFUSED)
        for name, context in contexts.items():
            html = _render(name, **context)
            assert expected in unescape(html), name
            assert CONFIRMATION_REFUSED not in unescape(html), name
