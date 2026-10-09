"""10.10.3 bütün panelin dil taraması (PLAN.md §D92 g, m; tm 155).

`app.routes`'taki her `GET` sayfa yolu (JSON API ve `/health` dışı) burada listelidir: HTML çizen
yol `PAGES`'te sentetik kayıtla doldurulmuş bir ya da birkaç adresle, dosya, görüntü ya da
yönlendirme döndüren yol `NOT_HTML`'de. Listede olmayan yeni bir yol testi kırmızı yapar — yeni
sayfa çevirisiz eklenemez. Her adres İngilizce ve Sırpça açılır: beklenen durum kodu (çoğu 200;
bulunamayan kayıt 404, atanamayan öğe 409) ve Türkçe kalıntı taraması (`tests/i18n/residue.py`)
temiz.

Veri sentetiktir ve Türkçe harf taşımaz (adlar, dosya adları, gerekçeler); parti gerçek boru
hattından kayıtlı yanıt sağlayıcısıyla geçer, yapay zekâ canlı çağrılmaz. Kayıtlı metin (kuyruk
gerekçesi, eğitim notu, olay mesajı) veridir ve `translate="no"` öğesindedir.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    CandidateDocumentType,
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    KnownDocumentType,
    QueueItem,
    Upload,
    UploadFile,
)
from app.groups import add_item, assign_package, create_group
from app.i18n import LANGUAGE_COOKIE, ngettext, translate, use_language
from app.i18n.tools import check
from app.main import create_app
from app.pipeline.orchestrate import process_upload
from app.pipeline.plan import create_plan, read_plan
from app.pipeline.queue_close import close_reason_label
from app.pipeline.route import route_queue_item
from app.storage import DataLayout, delete_document, remove_document_files
from app.training.map_import import SkippedRow, SkipReason
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user, require_api_user
from app.web.routers.training import get_training_provider_problem
from app.web.routers.upload_page import resolution_text
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    document_page,
    make_document_pdf_bytes,
    make_mrz_lines,
    make_pdf_bytes,
    make_text_pdf_bytes,
    recorded_provider,
    unknown_document_page,
)
from tests.i18n.residue import turkish_residue
from tests.pipeline.test_plan import CATALOG, MODEL, PERMIT
from tests.pipeline.test_plan import _page as plan_page
from tests.pipeline.test_plan import _pdf as plan_pdf
from tests.pipeline.test_plan import _person as plan_person
from tests.pipeline.test_plan import _upload as plan_upload
from tests.web.conftest import SIGNED_IN

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
LANGUAGES = ("en", "sr")
PASSPORT = "russian_passport"
FILE_NAME = "Dmitry_Vasiliev-Passport.pdf"
EXAMPLE = "specimen.pdf"

# `GET` yolu → (adres, beklenen durum) listesi. Adresler `world`'ün kimlikleriyle doldurulur.
PAGES: dict[str, tuple[tuple[str, int], ...]] = {
    "/login": (("/login", 200),),
    "/upload": (("/upload", 200),),
    "/upload/{upload_id}/progress": (
        ("/upload/{unknown_upload}/progress", 200),
        ("/upload/u_20990101_0001/progress", 404),
    ),
    "/uploads/{upload_id}": (
        ("/uploads/{unknown_upload}", 200),
        ("/uploads/{unreadable_upload}", 200),
        ("/uploads/u_20990101_0001", 404),
    ),
    "/uploads": (
        ("/uploads", 200),
        ("/uploads?status=nope", 200),
        ("/uploads?from=2099-01-01", 200),
        ("/uploads?dismissed=only", 200),
    ),
    "/employees": (
        ("/employees", 200),
        ("/employees?status=all", 200),
        ("/employees?q=zzzz", 200),
        ("/employees?packages=open", 200),
    ),
    "/employees/{employee_id}": (
        ("/employees/E0001", 200),
        ("/employees/E0002", 200),
        ("/employees/E9999", 404),
        ("/employees/E0009", 410),  # 10.5.13: kalıcı silinen çalışanın "silindi" sayfası
        ("/employees/E0009?notice=employee_deleted", 410),
    ),
    # 10.5.13 (tm 167): yalnız pasif çalışan silinir; etkin çalışan 409.
    "/employees/{employee_id}/delete/confirm": (
        ("/employees/E0002/delete/confirm", 200),
        ("/employees/E0001/delete/confirm", 409),
    ),
    "/employees/{employee_id}/fields": (("/employees/E0001/fields", 200),),
    "/employees/{employee_id}/status/confirm": (
        ("/employees/E0001/status/confirm?to=inactive", 200),
        ("/employees/E0002/status/confirm?to=active", 200),
    ),
    "/employees/{employee_id}/records/{kind}/{record_id}/remove/confirm": (
        ("/employees/E0001/records/alias/{alias}/remove/confirm", 200),
        ("/employees/E0001/records/identifier/{identifier}/remove/confirm", 200),
    ),
    "/employees/{employee_id}/merge/employees": (
        ("/employees/E0001/merge/employees?q=Anna", 200),
        ("/employees/E0001/merge/employees?q=zzzz", 200),
    ),
    "/employees/{employee_id}/merge/confirm": (
        ("/employees/E0001/merge/confirm?other=E0002", 200),
    ),
    "/documents/{document_id}/history": (
        ("/documents/{document}/history", 200),
        ("/documents/{archived}/history", 200),
        ("/documents/{deleted}/history", 200),  # 10.5.12: iskelet ve "kalıcı olarak silindi"
        ("/documents/9999/history", 404),
    ),
    "/documents/{document_id}/move/employees": (
        ("/documents/{document}/move/employees?q=Anna", 200),
    ),
    "/documents/{document_id}/move/confirm": (
        ("/documents/{document}/move/confirm?employee_id=E0002", 200),
    ),
    "/documents/{document_id}/archive/confirm": (("/documents/{document}/archive/confirm", 200),),
    "/documents/{document_id}/unarchive/confirm": (
        ("/documents/{archived}/unarchive/confirm", 200),
    ),
    # 10.5.12 (tm 166): etkin ve arşivdeki belge silinebilir.
    "/documents/{document_id}/delete/confirm": (
        ("/documents/{document}/delete/confirm", 200),
        ("/documents/{archived}/delete/confirm", 200),
    ),
    "/document-types": (
        ("/document-types", 200),
        ("/document-types?country=RU", 200),
        ("/document-types?country=general", 200),
        ("/document-types?archived=1", 200),
        ("/document-types?notice=created&slug=russian_passport", 200),
        ("/document-types?notice=bulk_archived&count=2&skipped=1", 200),
        ("/document-types?notice=none_selected", 200),
    ),
    "/document-types/new": (("/document-types/new", 200),),
    "/document-types/candidate-types": (
        ("/document-types/candidate-types", 200),
        ("/document-types/candidate-types?status=rejected", 200),
        ("/document-types/candidate-types?notice=rejected", 200),
    ),
    "/document-types/{slug}": (
        ("/document-types/russian_passport", 200),
        ("/document-types/profile_picture", 200),
        ("/document-types/profile_picture?notice=photo_rules", 200),
    ),
    "/document-types/{slug}/archive/confirm": (
        ("/document-types/russian_passport/archive/confirm", 200),
        ("/document-types/profile_picture/archive/confirm", 409),
    ),
    "/document-types/candidate-types/{candidate_id}": (
        ("/document-types/candidate-types/{candidate}", 200),
        ("/document-types/candidate-types/{candidate}?notice=restored", 200),
    ),
    "/document-groups": (
        ("/document-groups", 200),
        ("/document-groups?archived=1", 200),
    ),
    "/document-groups/new": (("/document-groups/new", 200),),
    "/document-groups/{group_id}": (
        ("/document-groups/{group}", 200),
        ("/document-groups/{group}?notice=created", 200),
        ("/document-groups/{archived_group}", 200),
    ),
    "/queues": (
        ("/queues", 200),
        ("/queues?tab=unreadable", 200),
        ("/queues?tab=unresolved", 200),
        ("/queues?tab=unknown&state=resolved", 200),
        ("/queues?tab=unknown&state=superseded", 200),
    ),
    "/queues/{queue_item_id}": (
        ("/queues/{unknown_item}", 200),
        ("/queues/{unresolved_item}", 200),
        ("/queues/{unreadable_item}", 200),
        ("/queues/{unresolved_item}?notice=reopened", 200),
        ("/queues/99999", 404),
    ),
    "/queues/{queue_item_id}/assign/employees": (
        ("/queues/{unreadable_item}/assign/employees?q=Dmitry", 200),
        ("/queues/{unreadable_item}/assign/employees?q=", 200),
        ("/queues/{unreadable_item}/assign/employees?q=zzzz", 200),
    ),
    "/queues/{queue_item_id}/assign/confirm": (
        ("/queues/{unreadable_item}/assign/confirm?employee_id=E0001", 200),
        ("/queues/{unknown_item}/assign/confirm?employee_id=E0001", 409),
    ),
    "/queues/{queue_item_id}/close/confirm": (("/queues/{unknown_item}/close/confirm", 200),),
    "/access-log": (("/access-log", 200),),
    "/access-log/employees/{employee_id}": (
        ("/access-log/employees/E0001", 200),
        ("/access-log/employees/E9999", 404),
    ),
    "/training": (
        ("/training", 200),
        ("/training?notice=uploaded", 200),
        ("/training?filter=mechanical", 200),
        ("/training?show=dismissed", 200),
        ("/training?archived=1", 200),
    ),
    "/training/items": (("/training/items", 200),),
    "/training/known": (
        ("/training/known", 200),
        ("/training/known?show=examples", 200),
        ("/training/known?show=ai", 200),
    ),
    "/training/known/{slug}": (
        ("/training/known/russian_passport", 200),
        ("/training/known/russian_passport?notice=moved", 200),
        ("/training/known/albanian_passport", 200),
    ),
    "/users": (("/users", 200),),
    "/account/password": (("/account/password", 200),),
    "/account/telegram": (("/account/telegram", 200),),
}
# HTML çizmeyen `GET` yolları: dosya, görüntü, yönlendirme ve makine arayüzü.
NOT_HTML = frozenset(
    {
        "/",
        "/health",
        "/uploads/{upload_id}/pages/{page_id}/image",
        "/employees/{employee_id}/documents/{document_id}/file",
        "/employees/{employee_id}/documents/{document_id}/download",
        "/employees/{employee_id}/photo",
        "/document-types/{slug}/examples/{name}",
        "/training/known/{slug}/examples/{name}",
    }
)

Speak = Callable[[str], None]


def page_routes(application: FastAPI) -> set[str]:
    """Uygulamanın JSON API dışındaki bütün `GET` yolları (içerilen yönlendiriciler dahil)."""
    paths: set[str] = set()
    for route in application.routes:
        contexts = (
            route.effective_route_contexts()
            if hasattr(route, "effective_route_contexts")
            else [route]
            if isinstance(route, APIRoute)
            else []
        )
        for context in contexts:
            calls = [dependency.call for dependency in context.dependant.dependencies]
            if "GET" in context.methods and require_api_user not in calls:
                paths.add(context.path)
    return paths


def test_every_get_page_route_is_swept_or_declared_not_html() -> None:
    routes = page_routes(create_app())

    assert routes == set(PAGES) | NOT_HTML
    assert not set(PAGES) & NOT_HTML


def test_a_new_html_route_without_a_sweep_entry_turns_the_list_red() -> None:
    application = create_app()
    application.add_api_route("/yeni-sayfa", lambda: "<p>Yeni sayfa</p>", methods=["GET"])

    assert page_routes(application) - (set(PAGES) | NOT_HTML) == {"/yeni-sayfa"}


@pytest.fixture
def speak(app: FastAPI) -> Speak:
    """Oturumdaki kullanıcının dil tercihini koyar (girişli istekte dil hesabın tercihidir)."""

    def choose(language: str) -> None:
        user = PanelUser(SIGNED_IN.id, SIGNED_IN.username, SIGNED_IN.role, language=language)
        app.dependency_overrides[get_current_user] = lambda: user

    return choose


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient, app: FastAPI) -> None:
    """Onay belirteci oturum çerezine bağlıdır; eğitim sekmesinin sağlayıcı notu kapalı."""
    client.cookies.set(SESSION_COOKIE, "oturum-bir")
    app.dependency_overrides[get_training_provider_problem] = lambda: None


def _employee(session: Session, number: int, given: str, surname: str, **fields: object) -> str:
    employee_id = f"E{number:04d}"
    session.add(
        Employee(
            id=employee_id,
            folder_name=f"{given}_{surname}_{employee_id}",
            given_names=given,
            surname=surname,
            **fields,
        )
    )
    session.flush()
    return employee_id


def _document(
    session: Session, layout: DataLayout, employee_id: str, name: str, status: DocumentStatus
) -> int:
    folder = session.get_one(Employee, employee_id).folder_name
    path = layout.ensure_employee_tree(folder) / "Hazir" / name
    path.write_bytes(make_pdf_bytes())
    document = Document(
        employee_id=employee_id,
        type_slug=PASSPORT,
        path=layout.relative(path),
        format="pdf",
        sequence_no=1,
        source_refs_json=[],
        status=status.value,
    )
    session.add(document)
    session.flush()
    return document.id


def _process(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    directory: Path,
    name: str,
    page: object,
) -> str:
    response = client.post(
        "/api/uploads",
        files=[("files", (name, make_document_pdf_bytes([page]), "application/pdf"))],
    )
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        provider = recorded_provider(directory, [page])
        process_upload(session, layout, upload, settings=SETTINGS, provider=provider)
    return upload_id


def _training_passport() -> bytes:
    """Metin katmanında geçerli MRZ taşıyan sentetik Rus pasaportu (mekanik tanınır)."""
    lines = make_mrz_lines(
        "TD3",
        document_code="P",
        issuing_state="RUS",
        surname="SPECIMEN",
        given_names="SAMPLE",
        document_number="000000001",
        nationality="RUS",
        date_of_birth=date(1990, 1, 1),
        sex="F",
        expiry_date=date(2030, 1, 1),
    )
    return make_text_pdf_bytes(["\n".join(("PASSPORT", *lines))])


@pytest.fixture
def world(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> dict[str, object]:
    """Panelin her sayfasını dolduran sentetik dünya: çalışanlar (etkin ve pasif), etkin ve
    arşivli belge, kayıtlar, grup ve paket, Unknown ve Unresolved kuyruk öğesi (aday türle),
    katalog türünün örneği ve bir eğitim çalıştırması."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        # Ülke adı veridir ve CLDR'den isteğin dilinde gelir; İngilizce adı "Türkiye" Türkçe harf
        # taşır. Sentetik dünyada bu ülkenin türü yok (§D92 g: veri bu harfleri taşımaz).
        session.get_one(KnownDocumentType, "turkish_passport").country = None
        dmitry = _employee(
            session, 1, "Dmitry", "Vasiliev", nationality="RUS", date_of_birth=date(1990, 5, 1)
        )
        _employee(session, 2, "Anna", "Petrova", status="inactive")
        # 10.5.13: kalıcı silinmiş çalışanın iskeleti (kişisel sütunlar boş).
        session.add(
            Employee(
                id="E0009",
                folder_name="deleted_E0009",
                given_names="",
                surname="",
                status="deleted",
                deleted_at=datetime(2026, 10, 9, 9, 0, tzinfo=UTC),
                deleted_by="ik",
            )
        )
        document = _document(session, layout, dmitry, FILE_NAME, DocumentStatus.ACTIVE)
        archived = _document(
            session, layout, dmitry, "Dmitry_Vasiliev-Passport_2.pdf", DocumentStatus.ARCHIVED
        )
        deleted = _document(
            session, layout, dmitry, "Dmitry_Vasiliev-Passport-3.pdf", DocumentStatus.ACTIVE
        )
        alias = EmployeeAlias(
            employee_id=dmitry,
            raw_name="Dmitry Vasiliev",
            normalized_name="dmitry vasiliev",
            script="latin",
        )
        identifier = EmployeeIdentifier(
            employee_id=dmitry, kind=PASSPORT, value="00 0000001", source_document_id=document
        )
        session.add_all(
            [
                alias,
                identifier,
                EmployeeIdentifier(
                    employee_id=dmitry,
                    kind=PASSPORT,
                    value="00 0000009",
                    removed_at=datetime(2026, 9, 1, tzinfo=UTC),
                    removed_by="ik",
                ),
                EmployeeContact(
                    employee_id=dmitry, kind="phone", value="+381 11 000 0000", added_by="ik"
                ),
            ]
        )
        group = create_group(session, name="Work permit file", description="Visa", actor="ik")
        add_item(session, group.id, match_kind="label", file_label="Passport", actor="ik")
        add_item(session, group.id, match_kind="type", type_slug="work_permit", actor="ik")
        assign_package(session, dmitry, group.id, actor="ik")
        old = create_group(session, name="Old file", description=None, actor="ik")
        session.flush()
        old_id = old.id
        group_id = group.id
        session.commit()
        alias_id, identifier_id = alias.id, identifier.id
    client.post(f"/document-groups/{old_id}/archive")

    unknown_upload = _process(
        client,
        session_factory,
        layout,
        tmp_path / "aday",
        "diploma.pdf",
        unknown_document_page(
            PERSON_PRUEBA,
            candidate_type_name="Peruvian Diploma",
            title="DIPLOMA",
            document_number="DIP-0000077",
        ),
    )
    unreadable_upload = _process(
        client,
        session_factory,
        layout,
        tmp_path / "pasaport",
        "permit.pdf",
        document_page(
            "work_permit",
            title="WORK PERMIT",
            person=PERSON_ORNEKOVA,
            document_number="AB12",
            shows=("surname", "given_names", "date_of_birth", "document_number"),
        ),
    )
    with session_factory() as session:
        # Onay bekleyen profil (§20.2.2 satır 7): numarası temiz olmayan çalışma izni, saklanmış
        # analiziyle planlanır ve Unresolved kuyruğuna alınır.
        upload = plan_upload(
            session, layout, plan_pdf(plan_page(PERMIT, person=plan_person(document_number="AB12")))
        )
        for row in session.scalars(select(UploadFile).where(UploadFile.upload_id == upload.id)):
            row.original_name = "permit-scan.pdf"
        plan = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
        (planned,) = read_plan(plan).items
        route_queue_item(session, layout, plan, planned)
        session.commit()
        items = {row.kind: row.id for row in session.scalars(select(QueueItem))}
        candidate = session.scalars(select(CandidateDocumentType.id)).one()

    stored = client.post(
        f"/document-types/{PASSPORT}/examples",
        files=[("files", (EXAMPLE, make_pdf_bytes(), "application/pdf"))],
    )
    assert stored.status_code == 200, stored.text
    trained = client.post(
        "/training",
        files=[("files", ("sample.pdf", _training_passport(), "application/pdf"))],
        data={"hint_slug": ""},
        follow_redirects=False,
    )
    assert trained.status_code in (200, 303), trained.text
    opened = client.get(f"/employees/{dmitry}/documents/{document}/file")
    assert opened.status_code == 200
    # 10.5.12: açılmış sonra kalıcı silinmiş belge — erişim logunda satırı "belge silindi" kalır.
    assert client.get(f"/employees/{dmitry}/documents/{deleted}/file").status_code == 200
    with session_factory() as session:
        removed = delete_document(session, layout, deleted, actor="ik")
        session.commit()
        remove_document_files(session, removed)
    return {
        "document": document,
        "archived": archived,
        "deleted": deleted,
        "alias": alias_id,
        "identifier": identifier_id,
        "group": group_id,
        "archived_group": old_id,
        "unknown_upload": unknown_upload,
        "unreadable_upload": unreadable_upload,
        "unknown_item": items["unknown"],
        "unreadable_item": items["unreadable"],
        "unresolved_item": items["unresolved"],
        "candidate": candidate,
    }


def _signed_out(app: FastAPI, client: TestClient, language: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: None
    client.cookies.set(LANGUAGE_COOKIE, language)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_panel_page_opens_in_the_chosen_language_without_turkish_residue(
    app: FastAPI,
    client: TestClient,
    speak: Speak,
    world: dict[str, object],
    language: str,
) -> None:
    failures: list[str] = []
    for route, addresses in PAGES.items():
        for template, expected in addresses:
            if route == "/login":
                _signed_out(app, client, language)
            else:
                speak(language)
            path = template.format(**world)
            response = client.get(path, follow_redirects=False)
            if response.status_code != expected:
                failures.append(f"{path}: {response.status_code} (beklenen {expected})")
                continue
            assert response.headers["content-type"].startswith("text/html"), path
            residue = turkish_residue(response.text, language)
            if residue:
                failures.append(f"{path}: {residue}")
    assert not failures, "\n".join(failures)


# --- 10.10-d sayfaları: başlık, düğme, durum adları -------------------------------------------

# Adres → dil → sayfada bulunması gereken metinler.
EXPECTED: dict[str, dict[str, tuple[str, ...]]] = {
    "/document-types": {
        "en": (
            "<h1>Document types</h1>",
            "New type",
            "Candidate types",
            "Archived types",
            "<th>File label</th>",
            "Deactivate",
            "Archive",
            "Edit",
            "Active",
        ),
        "sr": (
            "<h1>Tipovi dokumenata</h1>",
            "Novi tip",
            "Predloženi tipovi",
            "Arhivirani tipovi",
            "<th>Oznaka datoteke</th>",
            "Deaktiviraj",
            "Arhiviraj",
            "Uredi",
            "Aktivan",
        ),
    },
    "/document-types?notice=bulk_archived&count=2&skipped=1": {
        "en": ("2 types archived, 1 protected types skipped.",),
        "sr": ("Arhivirano tipova: 2; preskočeno zaštićenih tipova: 1.",),
    },
    "/document-types?notice=created&slug=russian_passport": {
        "en": ("Russian Passport: The type was created.",),
        "sr": ("Russian Passport: Tip je napravljen.",),
    },
    "/document-types/new": {
        "en": ("<h1>New document type</h1>", "File label", "Add criterion", "Save", "Cancel"),
        "sr": ("<h1>Novi tip dokumenta</h1>", "Oznaka datoteke", "Dodaj kriterijum", "Sačuvaj"),
    },
    "/document-types/russian_passport": {
        "en": ("<h1>Edit document type</h1>", "Example documents", "Upload examples", "Verified"),
        "sr": ("<h1>Uredi tip dokumenta</h1>", "Primeri dokumenata", "Otpremi primere"),
    },
    "/document-types/profile_picture": {
        "en": ("Photo rules", "Face visible", "Company decision", "Save rules", "Accepted photos"),
        "sr": ("Pravila za fotografiju", "Lice vidljivo", "Odluka firme", "Sačuvaj pravila"),
    },
    "/document-types/russian_passport/archive/confirm": {
        "en": (
            "You are about to archive the Russian Passport document type. Are you sure?",
            "Yes, continue",
        ),
        "sr": ("Upravo ćete arhivirati tip dokumenta Russian Passport. Da li ste sigurni?",),
    },
    "/document-types/candidate-types": {
        "en": ("<h1>Candidate types</h1>", "Pending (1)", "Rejected (0)", "Sightings"),
        "sr": ("<h1>Predloženi tipovi</h1>", "Na čekanju (1)", "Odbijeni (0)", "Viđenja"),
    },
    "/document-types/candidate-types/{candidate}": {
        "en": (
            "Candidate type:",
            "Awaiting approval",
            "Add to the standard types",
            "Reject the candidate",
            "Examine again",
        ),
        "sr": (
            "Predloženi tip:",
            "Čeka odobrenje",
            "Dodaj među standardne tipove",
            "Odbij predlog",
        ),
    },
    "/document-groups": {
        "en": ("<h1>Document groups</h1>", "New group", "<th>Open packages</th>"),
        "sr": ("<h1>Grupe dokumenata</h1>", "Nova grupa", "<th>Otvoreni paketi</th>"),
    },
    "/document-groups/{group}": {
        "en": ("Items", "Add an item by file label", "Required", "Archive the group"),
        "sr": ("Stavke", "Dodaj stavku prema oznaci datoteke", "Obavezno", "Arhiviraj grupu"),
    },
    "/queues": {
        "en": ("<h1>Queues</h1>", "Pending (1)", "Resolved (0)"),
        "sr": ("<h1>Redovi</h1>", "Na čekanju (1)", "Rešeno (0)"),
    },
    "/queues/{unknown_item}": {
        "en": ("Queue item", "Close the item", "Assign to an employee", "Not determined"),
        "sr": ("Stavka reda", "Zatvori stavku", "Dodeli zaposlenom", "Nije određeno"),
    },
    "/queues/{unresolved_item}": {
        "en": ("Create profile", "Send for confirmation"),
        "sr": ("Napravi profil", "Pošalji na potvrdu"),
    },
    "/queues/{unknown_item}/close/confirm": {
        "en": ("<h1>Close the queue item</h1>", "Not a document / junk page", "Other"),
        "sr": ("<h1>Zatvori stavku reda</h1>", "Nije dokument / otpadna strana", "Drugo"),
    },
    "/training": {
        "en": ("<h1>Training mode</h1>", "Upload for training", "Bulk scan with a map", "Runs"),
        "sr": ("<h1>Režim obuke</h1>", "Otpremi za obuku", "Skeniranje odjednom pomoću mape"),
    },
    "/training/known": {
        "en": ("Known documents", "With examples", "With AI decisions"),
        "sr": ("Poznati dokumenti", "Sa primerima", "Sa AI odlukama"),
    },
    "/training/known/russian_passport": {
        "en": ("Document type page", "Verified", "HR (manual)", "Move to another type"),
        "sr": ("Stranica tipa dokumenta", "Potvrđeno", "HR (ručno)", "Premesti u drugi tip"),
    },
}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_pages_of_this_task_show_titles_buttons_and_states_in_the_chosen_language(
    client: TestClient, speak: Speak, world: dict[str, object], language: str
) -> None:
    speak(language)
    for template, expected in EXPECTED.items():
        html = client.get(template.format(**world)).text
        for text in expected[language]:
            assert text in html, (template, language, text)


# Form ve adım hataları: çekirdeğin kaynak metni gösterimde çevrilir.
ERRORS = {
    "type": {
        "en": ("The type was not saved: correct the warnings under the fields.", "cannot be empty"),
        "sr": ("Tip nije sačuvan: ispravite upozorenja ispod polja.", "ne može biti prazno"),
    },
    "group": {
        "en": (
            "The group was not saved",
            "The group name must contain at least one letter or digit.",
        ),
        "sr": ("Grupa nije sačuvana", "Ime grupe mora sadržati bar jedno slovo ili cifru."),
    },
    "example": {
        "en": ("The examples were not uploaded", "No file was selected."),
        "sr": ("Primeri nisu otpremljeni", "Nije izabrana nijedna datoteka."),
    },
    "empty_example": {
        "en": ("The file &#39;blank.pdf&#39; is empty.",),
        "sr": ("Datoteka &#39;blank.pdf&#39; je prazna.",),
    },
    "photo": {
        "en": ("Minimum width:", "enter a pixel count between 1 and"),
        "sr": ("Minimalna širina:", "unesite broj piksela između 1 i"),
    },
    "training": {
        "en": ("Nothing was done:", "No file was selected for upload."),
        "sr": ("Ništa nije urađeno:", "Nije izabrana nijedna datoteka za otpremanje."),
    },
}


@pytest.mark.parametrize("language", LANGUAGES)
def test_form_errors_of_this_task_speak_the_chosen_language(
    client: TestClient, speak: Speak, world: dict[str, object], language: str
) -> None:
    speak(language)
    responses = {
        "type": client.post("/document-types", data={"slug": "new_type"}),
        "group": client.post("/document-groups", data={"name": "!!!", "description": ""}),
        "example": client.post(f"/document-types/{PASSPORT}/examples", data={}),
        "empty_example": client.post(
            f"/document-types/{PASSPORT}/examples",
            files=[("files", ("blank.pdf", b"", "application/pdf"))],
        ),
        "photo": client.post(
            "/document-types/profile_picture/photo-rules",
            data={"enabled": ["face_visible"], "min_width_px": "0", "min_height_px": "400"},
        ),
        "training": client.post("/training", data={"hint_slug": ""}),
    }
    for name, response in responses.items():
        assert response.status_code >= 400, (name, response.status_code)
        for text in ERRORS[name][language]:
            assert text in response.text, (name, language, text)
        assert turkish_residue(response.text, language) == [], name


def test_serbian_counters_of_this_task_use_the_three_plural_forms() -> None:
    with use_language("sr"):
        types = {n: ngettext("%(num)d tür", "%(num)d tür", n) % {"num": n} for n in (1, 3, 5, 21)}
        files = {n: ngettext("%(num)d dosya", "%(num)d dosya", n) % {"num": n} for n in (1, 2, 7)}
    assert types == {1: "1 tip", 3: "3 tipa", 5: "5 tipova", 21: "21 tip"}
    assert files == {1: "1 datoteka", 2: "2 datoteke", 7: "7 datoteka"}


def test_the_catalog_is_complete_after_this_task() -> None:
    assert check() == []


def test_close_reasons_and_skip_reasons_translate_when_shown() -> None:
    """Kapatma gerekçesi (çözülen öğenin satırı) ve harita atlama gerekçesi kaynak dilde saklanır,
    gösterimde çevrilir; tanınmayan kod olduğu gibi kalır."""
    detailed = SkippedRow(3, SkipReason.UNSAFE_PATH, "dest", "../x", "../x").label
    closed = QueueItem(
        resolved_at=datetime(2026, 10, 2, 9, 30, tzinfo=UTC),
        resolved_by="ik",
        resolution="closed",
        resolution_reason="other",
    )
    with use_language("en"):
        assert translate(resolution_text(closed)).endswith("ik · closed: Other")
        assert translate(close_reason_label("not_a_document")) == "Not a document / junk page"
        assert translate(close_reason_label("other")) == "Other"
        assert translate(detailed) == "unsafe path (../x)"
    with use_language("sr"):
        assert translate(close_reason_label("already_exists")) == "Već postoji"
    assert close_reason_label("other") == "Diğer"
    assert close_reason_label("eski_kod") == "eski_kod"
