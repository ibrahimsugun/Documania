"""10.10.3 arayüz çevirisi I — çalışanlar, profil, yükleme, yüklemeler, belge geçmişi, erişim logu,
kullanıcılar ve hesap sayfaları İngilizce ve Sırpça (PLAN.md §D92 e, f, g, l; §D95; tm 154).

§20.6 onay metinleri (`confirm-text`) da taranır (10.10.4, tm 156): dil başına PRD'den birebir
gelirler.

Her sayfa hesabın dil tercihiyle (`PanelUser.language`) çizilir: başlık, tablo başlıkları,
düğmeler, boş durum ve hata metni seçili dilde görünür; Türkçe kalıntı taraması
(`tests/i18n/residue.py`) İngilizce ve Sırpça sayfada temizdir. Veri (çalışan adı, belge türü adı,
dosya adı) çevrilmez — msgid'le aynı yazılsa bile. Türkçe (`tr`) sayfalar bugünkü metinle aynıdır:
bunu bu bölümlerin mevcut testleri `PANEL_DEFAULT_LANGUAGE=tr` ile sınar.

Veri sentetiktir; parti gerçek boru hattından kayıtlı yanıt sağlayıcısıyla geçer, yapay zekâ canlı
çağrılmaz.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    KnownDocumentType,
    Upload,
)
from app.groups import add_item, assign_package, create_group
from app.i18n import ngettext, use_language
from app.i18n.tools import check
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout
from app.web.auth import SESSION_COOKIE, PanelUser, get_current_user
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    make_pdf_bytes,
    passport_page,
    recorded_provider,
)
from tests.i18n.residue import assert_no_turkish
from tests.web.conftest import SIGNED_IN

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
LANGUAGES = ("en", "sr")
PASSPORT = "russian_passport"
FILE_NAME = "Dmitry_Vasiliev-Passport.pdf"

Speak = Callable[[str], None]


@pytest.fixture
def speak(app: FastAPI) -> Speak:
    """Oturumdaki kullanıcının dil tercihini koyar (girişli istekte dil hesabın tercihidir)."""

    def choose(language: str) -> None:
        # 10.1.9: root her sayfayı (erişim logu dahil) açar; tarama her sayfayı çizer.
        user = PanelUser(SIGNED_IN.id, SIGNED_IN.username, "root", language=language)
        app.dependency_overrides[get_current_user] = lambda: user

    return choose


@pytest.fixture(autouse=True)
def _session_cookie(client: TestClient) -> None:
    """Onay belirteci oturum çerezine bağlıdır; oturum bağımlılığı geçersiz kılındığı için elle."""
    client.cookies.set(SESSION_COOKIE, "oturum-bir")


def _employee(
    session: Session, number: int, given: str, surname: str, **fields: object
) -> Employee:
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


def _document(session: Session, layout: DataLayout, employee: Employee, file_name: str) -> Document:
    path = layout.ensure_employee_tree(employee.folder_name) / "Hazir" / file_name
    path.write_bytes(make_pdf_bytes())
    document = Document(
        employee_id=employee.id,
        type_slug=PASSPORT,
        path=layout.relative(path),
        format="pdf",
        sequence_no=1,
        source_refs_json=[],
        status=DocumentStatus.ACTIVE.value,
    )
    session.add(document)
    session.flush()
    return document


@pytest.fixture
def world(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, object]:
    """Etkin bir çalışan (belge, isim yazımı, numara, iletişim, kaldırılmış numara, paket) ve pasif
    bir çalışan; adlar ve değerler Türkçe harf taşımaz."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        dmitry = _employee(
            session,
            1,
            "Dmitry",
            "Vasiliev",
            nationality="RUS",
            date_of_birth=date(1990, 5, 1),
        )
        _employee(session, 2, "Anna", "Petrova", status="inactive")
        document = _document(session, layout, dmitry, FILE_NAME)
        session.add_all(
            [
                EmployeeAlias(
                    employee_id=dmitry.id,
                    raw_name="Dmitry Vasiliev",
                    normalized_name="dmitry vasiliev",
                    script="latin",
                ),
                EmployeeIdentifier(
                    employee_id=dmitry.id,
                    kind=PASSPORT,
                    value="00 0000001",
                    source_document_id=document.id,
                ),
                EmployeeIdentifier(
                    employee_id=dmitry.id,
                    kind=PASSPORT,
                    value="00 0000009",
                    removed_at=datetime(2026, 9, 1, tzinfo=UTC),
                    removed_by="ik",
                    seen_after_removal_at=datetime(2026, 9, 2, tzinfo=UTC),
                ),
                EmployeeContact(
                    employee_id=dmitry.id, kind="phone", value="+381 11 000 0000", added_by="ik"
                ),
            ]
        )
        group = create_group(session, name="Work permit file", description=None, actor="ik")
        add_item(session, group.id, match_kind="label", file_label="Passport", actor="ik")
        add_item(session, group.id, match_kind="type", type_slug="work_permit", actor="ik")
        assign_package(session, dmitry.id, group.id, actor="ik")
        session.commit()
        alias_id = session.query(EmployeeAlias.id).scalar()
        return {"document": document.id, "alias": alias_id}


def _processed(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout, tmp: Path
) -> str:
    """Sentetik pasaportu yükler ve gerçek boru hattından geçirir (kayıtlı yanıt)."""
    page = passport_page(
        PERSON_ORNEKOVA, document_number="00 0000002", expiry_date=date(2030, 1, 1)
    )
    response = client.post(
        "/api/uploads",
        files=[("files", ("passport.pdf", make_document_pdf_bytes([page]), "application/pdf"))],
    )
    assert response.status_code == 201, response.text
    upload_id: str = response.json()["upload_id"]
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        provider = recorded_provider(tmp / "kayit", [page])
        process_upload(session, layout, upload, settings=SETTINGS, provider=provider)
    return upload_id


def _page(client: TestClient, path: str, status: int = 200) -> str:
    response = client.get(path)
    assert response.status_code == status, (path, response.status_code, response.text[:500])
    return response.text


# --- sayfa başına beklenen metinler ------------------------------------------------------------

# Yol → dil → sayfada bulunması gereken metinler (başlık, tablo başlığı, düğme, boş durum).
PAGES: dict[str, dict[str, tuple[str, ...]]] = {
    "/employees": {
        "en": (
            "<h1>Employees</h1>",
            "<th>Documents</th>",
            "With incomplete packages",
            "2 employees",
        ),
        "sr": ("<h1>Zaposleni</h1>", "<th>Broj dokumenata</th>", "Sa nepotpunim paketima"),
    },
    "/employees?q=zzzz": {
        "en": ("No employees match “zzzz”.",),
        "sr": ("Nema zaposlenih koji odgovaraju upitu “zzzz”.",),
    },
    "/employees/E0001": {
        "en": (
            "Edit profile",
            "Profile records",
            "Document packages",
            "Open — 1/2 required items",
            "Upload documents",
            "<dt>Phone</dt>",
            "Removed record",
            "A document number seen in a document matches a removed record",
            "Drag and drop files here",
        ),
        "sr": (
            "Uredi profil",
            "Zapisi profila",
            "Paketi dokumenata",
            "Otvoren — 1/2 obaveznih stavki",
            "Otpremi dokumente",
            "<dt>Telefon</dt>",
            "Uklonjen zapis",
        ),
    },
    "/employees/E0002": {
        "en": ("Inactive employee", "Reactivate"),
        "sr": ("Neaktivan zaposleni", "Ponovo aktiviraj"),
    },
    "/employees/E0001/fields": {
        "en": ("<h1>Edit profile</h1>", "ICAO code (e.g. RUS, SRB, D)", "Yes, continue", "Cancel"),
        "sr": ("<h1>Uredi profil</h1>", "ICAO kod (npr. RUS, SRB, D)", "Da, nastavi", "Odustani"),
    },
    "/employees/E0001/status/confirm?to=inactive": {
        "en": ("<h1>Deactivate employee</h1>", "Note (optional)", "← Back to profile"),
        "sr": ("<h1>Deaktiviraj zaposlenog</h1>", "Napomena (opciono)", "← Nazad na profil"),
    },
    "/employees/E0001/merge/employees?q=Anna": {
        "en": ("<h1>Merge with another record</h1>", "1 employee found", "Select", "(inactive)"),
        "sr": (
            "<h1>Spoji sa drugim zapisom</h1>",
            "Pronađen 1 zaposleni",
            "Izaberi",
            "(neaktivan)",
        ),
    },
    "/employees/E0001/merge/confirm?other=E0002": {
        "en": ("Record to keep", "Apply selection", "will move to the kept record"),
        "sr": ("Zapis koji ostaje", "Primeni izbor", "prelazi na zapis koji ostaje"),
    },
    "/employees/E0001/records/alias/{alias}/remove/confirm": {
        "en": ("<h1>Remove record</h1>", "<dt>Name spelling</dt>"),
        "sr": ("<h1>Ukloni zapis</h1>", "<dt>Zapis imena</dt>"),
    },
    "/documents/{document}/history": {
        "en": ("<h1>Document history</h1>", "Move to another employee", "Source files and pages"),
        "sr": (
            "<h1>Istorija dokumenta</h1>",
            "Premesti drugom zaposlenom",
            "Izvorne datoteke i strane",
        ),
    },
    "/documents/{document}/move/employees?q=Anna": {
        "en": ("1 employee found", "Select"),
        "sr": ("Pronađen 1 zaposleni", "Izaberi"),
    },
    "/documents/{document}/archive/confirm": {
        "en": ("<h1>Move the document to the archive</h1>", "Yes, continue"),
        "sr": ("<h1>Premesti dokument u arhivu</h1>", "Da, nastavi"),
    },
    "/access-log": {
        "en": ("<h1>Access log</h1>", "Last access", "1 employee"),
        "sr": ("<h1>Dnevnik pristupa</h1>", "Poslednji pristup"),
    },
    "/access-log/employees/E0001": {
        "en": ("Who viewed", "<th>Action</th>", "Opened", "1 access"),
        "sr": ("Ko je pregledao", "<th>Radnja</th>", "Otvorio", "1 pristup"),
    },
    "/upload": {
        "en": ("<h1>Upload</h1>", "Drag and drop files here", "(optional)"),
        "sr": ("<h1>Otpremi</h1>", "Prevucite i otpustite datoteke ovde", "(opciono)"),
    },
    "/uploads": {
        "en": ("<h1>Uploads</h1>", "Filter uploads", "1 upload", "Completed"),
        "sr": ("<h1>Otpremanja</h1>", "Filtriraj otpremanja", "1 otpremanje"),
    },
    "/uploads?status=nope": {
        "en": ("The status filter was not recognized; it was ignored.",),
        "sr": ("Filter statusa nije prepoznat; zanemaren je.",),
    },
    "/uploads?from=2099-01-01": {
        "en": ("No uploads match this filter.", "Clear filter"),
        "sr": ("Nijedno otpremanje ne odgovara ovom filteru.", "Obriši filter"),
    },
    "/uploads/{upload}": {
        "en": (
            "Batch",
            '<h2 id="pages-title">Pages</h2>',
            "Event timeline",
            "Re-analyze",
            "Version 1",
        ),
        "sr": (
            "Serija",
            '<h2 id="pages-title">Strane</h2>',
            "Vremenska linija događaja",
            "Verzija 1",
        ),
    },
    "/users": {
        "en": ("<h1>Users</h1>", "New user", "Create user", "<td>HR</td>", "My Telegram"),
        "sr": (
            "<h1>Korisnici</h1>",
            "Novi korisnik",
            "Napravi korisnika",
            "<td>HR</td>",
            "Moj Telegram",
        ),
    },
    "/account/telegram": {
        "en": ("<h1>My Telegram</h1>", "Your Telegram IDs", "Connect Telegram", "Add manually"),
        "sr": ("<h1>Moj Telegram</h1>", "Vaši Telegram ID-jevi", "Poveži Telegram", "Dodaj ručno"),
    },
    "/account/password": {
        "en": ("<h1>Change my password</h1>", "Current password", "Back to the Users page"),
        "sr": ("<h1>Promeni moju lozinku</h1>", "Trenutna lozinka", "Nazad na stranicu Korisnici"),
    },
}
# Bulunmayan kayıt: hata sayfası seçili dilde.
NOT_FOUND = {
    "/employees/E9999": {"en": "Employee not found.", "sr": "Zaposleni nije pronađen."},
    "/documents/9999/history": {"en": "Document not found.", "sr": "Dokument nije pronađen."},
    "/access-log/employees/E9999": {"en": "Employee not found.", "sr": "Zaposleni nije pronađen."},
    "/uploads/u_20990101_0001": {"en": "Batch not found.", "sr": "Serija nije pronađena."},
}


@pytest.fixture
def ready(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    world: dict[str, object],
    tmp_path: Path,
) -> dict[str, object]:
    """Dünya + işlenmiş bir parti + erişim logunda bir kayıt (belge açıldı)."""
    upload_id = _processed(client, session_factory, layout, tmp_path)
    opened = client.get(f"/employees/E0001/documents/{world['document']}/file")
    assert opened.status_code == 200
    return {**world, "upload": upload_id}


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_page_is_drawn_in_the_chosen_language_without_turkish_residue(
    client: TestClient, speak: Speak, ready: dict[str, object], language: str
) -> None:
    speak(language)
    for template, expected in PAGES.items():
        path = template.format(**ready)
        html = _page(client, path)
        for text in expected[language]:
            assert text in html, (path, language, text)
        assert_no_turkish(html, language)


@pytest.mark.parametrize("language", LANGUAGES)
def test_not_found_pages_speak_the_chosen_language(
    client: TestClient, speak: Speak, world: dict[str, object], language: str
) -> None:
    speak(language)
    for path, messages in NOT_FOUND.items():
        html = _page(client, path, 404)
        assert messages[language] in html, (path, language)
        assert_no_turkish(html, language)


ERRORS = {
    # Profil formu: üst hata ve alan sorunu (çekirdeğin kaynak metni gösterimde çevrilir).
    "fields": {
        "en": (
            "The profile fields are invalid; correct them and submit again.",
            "Surname: cannot be empty",
        ),
        "sr": (
            "Polja profila nisu ispravna; ispravite ih i pošaljite ponovo.",
            "Prezime: ne može biti prazno",
        ),
    },
    # İletişim formu: değer taşıyan sorun (`Translatable`, sınır değeriyle).
    "contact": {
        "en": ("The value can be at most 500 characters long.",),
        "sr": ("Vrednost može imati najviše 500 znakova.",),
    },
    # Paket notu sınırı (çekirdek `NOTE_TOO_LONG`).
    "package": {
        "en": ("The note can be at most 120 characters long.",),
        "sr": ("Napomena može imati najviše 120 znakova.",),
    },
    # Yükleme: dosya seçilmedi.
    "upload": {
        "en": ("No file was selected for upload.",),
        "sr": ("Nije izabrana nijedna datoteka za otpremanje.",),
    },
    # Kullanıcı formu: kısa kullanıcı adı (`app.web.auth`, sınır değeriyle).
    "user": {
        "en": ("The username must be at least 3 characters long.",),
        "sr": ("Korisničko ime je prekratko: najmanja dužina je 3.",),
    },
    # Hesap: tekrar eşleşmiyor.
    "password": {
        "en": ("The new password and its repetition do not match.",),
        "sr": ("Nova lozinka i njeno ponavljanje se ne poklapaju.",),
    },
}


@pytest.mark.parametrize("language", LANGUAGES)
def test_form_errors_speak_the_chosen_language(
    client: TestClient, speak: Speak, world: dict[str, object], language: str
) -> None:
    speak(language)
    responses = {
        "fields": client.post(
            "/employees/E0001/fields/prepare",
            data={"given_names": "Dmitry", "surname": "", "nationality": "RUS"},
        ),
        "contact": client.post(
            "/employees/E0001/contacts", data={"kind": "address", "value": "x" * 501}
        ),
        "package": client.post(
            "/employees/E0001/packages", data={"group_id": "1", "note": "n" * 121}
        ),
        "upload": client.post("/upload", data={}),
        "user": client.post("/users", data={"username": "ab", "password": "x" * 12, "role": "hr"}),
        "password": client.post(
            "/account/password",
            data={
                "current_password": "eski-parola",
                "new_password": "yeni-parola-1",
                "new_password_repeat": "yeni-parola-2",
            },
        ),
    }
    for name, response in responses.items():
        assert response.status_code >= 400, (name, response.status_code)
        for text in ERRORS[name][language]:
            assert text in response.text, (name, language, text)
        assert_no_turkish(response.text, language)


def test_serbian_counters_use_the_three_plural_forms() -> None:
    with use_language("sr"):
        forms = {
            count: ngettext("%(num)d çalışan", "%(num)d çalışan", count) % {"num": count}
            for count in (1, 2, 5, 21)
        }
        pages = {
            count: ngettext("%(num)d sayfa", "%(num)d sayfa", count) % {"num": count}
            for count in (1, 2, 5, 21)
        }
    assert forms == {1: "1 zaposleni", 2: "2 zaposlena", 5: "5 zaposlenih", 21: "21 zaposleni"}
    assert pages == {1: "1 strana", 2: "2 strane", 5: "5 strana", 21: "21 strana"}


def test_serbian_counter_on_the_employee_list(
    client: TestClient, speak: Speak, world: dict[str, object]
) -> None:
    speak("sr")
    html = _page(client, "/employees?status=all")
    assert "2 zaposlena" in html
    english = {1: "1 employee", 2: "2 employees"}
    speak("en")
    assert english[2] in _page(client, "/employees?status=all")


def test_data_is_not_translated_even_when_it_reads_like_a_message(
    client: TestClient,
    speak: Speak,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    """Çalışan adı ve belge türü adı veridir: msgid'le birebir aynı yazılsa da (`Kimlik ekle`,
    `Durum`) İngilizce sayfada olduğu gibi görünür (§D92 f)."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        employee = _employee(session, 1, "Kimlik", "ekle")
        _document(session, layout, employee, "Kimlik_ekle-Passport.pdf")
        session.get_one(KnownDocumentType, PASSPORT).name = "Durum"
        session.commit()
    speak("en")
    profile = _page(client, "/employees/E0001")
    assert "<h1>Kimlik ekle</h1>" in profile
    assert "<td>Durum</td>" in profile
    assert "<th>Status</th>" in profile
    listing = _page(client, "/employees")
    assert ">Kimlik ekle</a>" in listing


def test_the_catalog_is_complete_after_this_task() -> None:
    assert check() == []
