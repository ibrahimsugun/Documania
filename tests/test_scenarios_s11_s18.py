"""09.3.4 — PRD §9 kabul senaryoları S11–S15 ve S18 uçtan uca.

S1–S10 (`tests/test_scenarios_s01_s05.py`, `tests/test_scenarios_s06_s10.py`) gibi her senaryo
gerçek yoldan geçer: parti yükleme uç noktasıyla açılır, `process_upload` ile render → analiz →
plan → uygulama adımlarından geçer; yeniden analiz (S14) ve yeniden çalıştırma (S18) partinin uç
noktalarıyla (`POST /api/uploads/{id}/reanalyze`, `/rerun`) yapılır. Dosyalar ve sağlayıcının
kayıtlı yanıtları `tests/fixtures/gen.py`'nin sentetik sayfa tanımlarından üretilir; yapay zekâ
canlı çağrılmaz, gerçek kimlik belgesi yoktur (CONVENTIONS §6). Ortam (geçici veritabanı, veri
dizini, yükleme uç noktası) ve yardımcılar S1–S5'inkilerdir.

**S14 onayı.** Aday türün onay ekranı ve iki aşamalı onayı 11.5.2'dir (Faz 1); onayın sonucu
kabul kriterinde yazılıdır: "Onay sonrası tür katalogda". Faz 0'da tür kataloğa İK'nın katalog
eşitlemesiyle (00.6.3) girer; test onayı bu sonucuyla kurar — `peruvian_diploma` güncel kataloğa
(`import_catalog`, veritabanı) eklenir — ve partiyi gerçek yeniden analiz uç noktasından geçirir.

**S15 profil sayfası.** Profil sayfasından yükleme (10.5.3) yüklemenin bağlam çalışanıyla
yapılmasıdır; panel ekranı Faz 1'dir, bağlam yükleme uç noktasının `context_employee_id`
alanıyla verilir.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.recording_provider import RecordingProvider
from app.catalog import export_catalog, import_catalog, validate_catalog
from app.db.models import (
    CandidateDocumentType,
    CandidateTypeStatus,
    Employee,
    EmployeeIdentifier,
    Page,
    Plan,
    QueueItem,
    Upload,
)
from app.events import EventType
from app.matching.match import NAME_ONLY_REASON, EmployeeAction, MatchedBy
from app.matching.match import normalize_document_number as normalized
from app.pipeline.plan import Operation, Route, read_plan
from app.storage import DataLayout
from app.web.routers.uploads import get_analysis_provider
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    PERSON_SIDOROV,
    PERSON_TESTOVA_SHCHELKINA,
    SyntheticPage,
    SyntheticPerson,
    blank_page,
    document_page,
    driving_license_pages,
    make_document_pdf_bytes,
    make_docx_bytes,
    make_legacy_doc_bytes,
    passport_page,
    profile_picture_page,
    recorded_provider,
    residence_card_pages,
    unknown_document_page,
)
from tests.test_scenarios_s01_s05 import (
    ORNEKOVA_FOLDER,
    ORNEKOVA_PERSONAL,
    PASSPORT_NUMBER,
    PASSPORT_OUTPUT,
    PHOTO_OUTPUT,
    SIDOROV_FOLDER,
    SIDOROV_PERSONAL,
    _assert_no_personal_values,
    _events,
    _items,
    _names,
    _outputs,
    _process,
    _register_employee,
    _upload,
)
from tests.test_scenarios_s06_s10 import _count, _event_types, _reason_file

PASSPORT = "russian_passport"
LICENSE_NUMBER = "000123456"
RESIDENCE_NUMBER = "AB1234567"
LICENSE_OUTPUT = "Ivan_Sidorov-Driving-License.pdf"
RESIDENCE_OUTPUT = "Ivan_Sidorov-Residence-Card.pdf"

# S13: Kiril isimli belge; Latin alanlar ve MRZ ICAO yazımıyla (kayıtlı yanıt `s13_cyrillic_name`).
CYRILLIC_NUMBER = "00 0000013"
CYRILLIC_ORIGINAL = "Тестова-Щёлкина Юлья"
CYRILLIC_FOLDER = "Iulia_Testova_Shchelkina_E0001"
CYRILLIC_OUTPUT = "Iulia_Testova_Shchelkina-Passport.pdf"
CYRILLIC_PERSONAL = (
    "TESTOVA",
    "Testova",
    "Тестова",
    "IULIA",
    "Iulia",
    "Юлья",
    "0000013",
    "1992-03-15",
)

# S14: katalog dışı tür (Peru diploması, kayıtlı yanıt `s14_peruvian_diploma`).
DIPLOMA = "peruvian_diploma"
DIPLOMA_NAME = "Peruvian Diploma"
DIPLOMA_NUMBER = "DIP-0000077"
DIPLOMA_FIELDS = ("surname", "given_names", "document_number")
DIPLOMA_ENTRY: dict[str, Any] = {
    "slug": DIPLOMA,
    "name": DIPLOMA_NAME,
    "file_label": "Diploma",
    "country": "PE",
    "description": "Peru'da verilmiş diploma.",
    "expected_file_types": ["pdf", "jpeg", "png"],
    "expected_pages": {"min": 1, "max": 1},
    "sides": "single",
    "direct": False,
    "analyze": True,
    "required_fields": list(DIPLOMA_FIELDS),
    "allowed_conversions": ["wrap_image"],
    "output_format": "pdf",
    "acceptance_criteria": [],
    "prompt_description": "İspanyolca diploma; sahibinin adı, soyadı ve diploma numarası yazılı.",
    "photo_rules": None,
    "active": True,
}
PRUEBA_FOLDER = "Ana_Prueba_E0001"
DIPLOMA_OUTPUT = "Ana_Prueba-Diploma.pdf"
PRUEBA_PERSONAL = ("PRUEBA", "Prueba", "1995-03-15", "0000077")
UNKNOWN_REASON = (
    "Bilinmeyen belge türü (04.6.1): bu adayın (dosya 1, sayfa 1) türü katalogda yok; önerilen "
    f'aday tür: "{DIPLOMA_NAME}". Belge katalogdaki bir türe zorla atanmaz.'
)

# S15: Word eki (K2).
ATTACHMENT = "attachment"
ATTACHMENT_REASON = (
    "Word/Excel eki (04.7.1): parti bir çalışan bağlamıyla yüklenmedi, sahibi belirlenemedi; "
    "belge analiz edilmez, dönüştürülmez, gerekçesiyle kuyruğa alınır."
)

# Ortam fikstürleri (geçici veritabanı, veri dizini, yükleme uç noktası) S1–S5'inkilerdir; pytest
# onları bu modüldeki adlarından bulur.
engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client


# --- yardımcılar ------------------------------------------------------------------------------


def _passport(person: SyntheticPerson = PERSON_ORNEKOVA) -> SyntheticPage:
    return passport_page(person, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1))


def _register_sidorov(session: Session, layout: DataLayout) -> Employee:
    return _register_employee(
        session,
        layout,
        PERSON_SIDOROV,
        [("serbian_driving_license", LICENSE_NUMBER), ("serbian_residence_card", RESIDENCE_NUMBER)],
    )


def _upload_in_context(
    client: TestClient, session: Session, employee_id: str, *files: tuple[str, bytes]
) -> Upload:
    """Profil sayfasından yükleme (10.5.3): parti bağlam çalışanıyla açılır."""
    response = client.post(
        "/api/uploads",
        data={"context_employee_id": employee_id},
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )
    assert response.status_code == 201, response.text
    upload = session.get_one(Upload, response.json()["upload_id"])
    assert upload.context_employee_id == employee_id
    return upload


def _use_provider(client: TestClient, provider: RecordingProvider) -> None:
    """Uç noktaların sağlayıcısı (`get_analysis_provider`) kayıtlı yanıt sağlayıcısıdır."""
    application = client.app
    assert isinstance(application, FastAPI)
    application.dependency_overrides[get_analysis_provider] = lambda: provider


def _identifiers(session: Session, employee_id: str) -> list[tuple[str, str]]:
    query = (
        select(EmployeeIdentifier.kind, EmployeeIdentifier.value)
        .where(EmployeeIdentifier.employee_id == employee_id)
        .order_by(EmployeeIdentifier.id)
    )
    return [(kind, value) for kind, value in session.execute(query)]


def _profile(layout: DataLayout, folder_name: str) -> tuple[dict[str, Any], str]:
    """`profil.md`'nin YAML ön bloğu ve gövdesi."""
    text = layout.profile_path(folder_name).read_text(encoding="utf-8")
    _, front_matter, body = text.split("---\n", 2)
    data: dict[str, Any] = yaml.safe_load(front_matter)
    return data, body


def _document_row(body: str, name: str) -> list[str]:
    """Profilin belge tablosunda dosya adı `name` olan satırın hücreleri."""
    (row,) = [line for line in body.splitlines() if f"| {name} |" in line]
    return [cell.strip() for cell in row.strip("|").split("|")]


def _queue_rows(session: Session, upload: Upload) -> list[QueueItem]:
    query = select(QueueItem).where(QueueItem.upload_id == upload.id).order_by(QueueItem.id)
    return list(session.scalars(query))


def _plans(session: Session, upload: Upload) -> list[Plan]:
    query = select(Plan).where(Plan.upload_id == upload.id).order_by(Plan.version)
    return list(session.scalars(query))


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --- S11: temiz pasaport numarası, kayıtlı çalışan yok --------------------------------------------


@pytest.mark.parametrize(
    "someone_else", [False, True], ids=["kayitli-calisan-yok", "baska-kayitli-calisan-var"]
)
def test_s11_clean_passport_number_without_a_registered_employee_opens_a_new_employee(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path, someone_else: bool
) -> None:
    # Başka bir kayıtlı çalışan eşleşmeyi etkilemez; yeni çalışan bir sonraki E numarasını alır.
    other = _register_sidorov(session, layout) if someone_else else None
    employee_id = "E0002" if someone_else else "E0001"
    folder_name = ORNEKOVA_FOLDER.replace("E0001", employee_id)
    passport = _passport()
    content = make_document_pdf_bytes([passport])
    upload = _upload(client, session, ("pasaport.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [passport])

    _process(session, layout, upload, provider)

    # §20.2.2 satır 6: eşleşme yok, numara temiz → `create`; belge yeni çalışanın Hazir'ına.
    (item,) = _items(session, upload)
    assert (item.route, item.operation, item.document_type_slug, item.target_name) == (
        Route.READY,
        Operation.PASSTHROUGH,
        PASSPORT,
        PASSPORT_OUTPUT,
    )
    assert (item.employee.action, item.employee.employee_id, item.employee.matched_by) == (
        EmployeeAction.CREATE,
        employee_id,
        None,
    )

    # Yeni çalışan: E numarası, K8 klasörü, belgeden okunan kimlik ve temiz numarası.
    employee = session.get_one(Employee, employee_id)
    assert (employee.folder_name, employee.given_names, employee.surname) == (
        folder_name,
        PERSON_ORNEKOVA.given_names,
        PERSON_ORNEKOVA.surname,
    )
    assert (employee.date_of_birth, employee.nationality, employee.original_script_name) == (
        PERSON_ORNEKOVA.date_of_birth,
        "RUS",
        PERSON_ORNEKOVA.original_script_name,
    )
    assert _identifiers(session, employee_id) == [(PASSPORT, normalized(PASSPORT_NUMBER))]
    assert _count(session, Employee) == 1 + int(someone_else)

    # Klasör, profil.md ve Hazir'daki belge (Direkt Belge olduğu gibi); Alinan'da orijinali.
    folder = layout.employee_dir(folder_name)
    assert _names(layout.employees) == sorted(
        [folder_name, *([other.folder_name] if other is not None else [])]
    )
    assert _names(folder) == ["Alinan", "Hazir", "profil.md"]
    assert _names(folder / "Hazir") == [PASSPORT_OUTPUT]
    assert (folder / "Hazir" / PASSPORT_OUTPUT).read_bytes() == content
    assert _names(folder / "Alinan") == ["pasaport.pdf"]
    assert (folder / "Alinan" / "pasaport.pdf").read_bytes() == content
    (output,) = _outputs(session)
    assert (output.employee_id, output.type_slug, output.status) == (
        employee_id,
        PASSPORT,
        "active",
    )
    assert layout.resolve(output.path) == folder / "Hazir" / PASSPORT_OUTPUT

    profile, body = _profile(layout, folder_name)
    assert (profile["employee_id"], profile["folder_name"]) == (employee_id, folder_name)
    assert (profile["given_names"], profile["surname"]) == ("TEST", "ORNEKOVA")
    assert profile["document_numbers"] == [{"kind": PASSPORT, "value": normalized(PASSPORT_NUMBER)}]
    assert _document_row(body, PASSPORT_OUTPUT)[:3] == [
        "Russian Passport",
        PASSPORT_OUTPUT,
        "active",
    ]
    if other is not None:
        other_folder = layout.employee_dir(other.folder_name)
        assert (_names(other_folder / "Hazir"), _names(other_folder / "Alinan")) == ([], [])

    events = _events(session, upload)
    types = _event_types(events)
    assert EventType.PERSON_MATCHED not in types
    (created,) = [row for row in events if row.type == EventType.EMPLOYEE_CREATED]
    (saved,) = [row for row in events if row.type == EventType.OUTPUT_SAVED]
    assert types.index(EventType.EMPLOYEE_CREATED) < types.index(EventType.OUTPUT_SAVED)
    assert (created.employee_id, saved.employee_id, saved.document_id) == (
        employee_id,
        employee_id,
        output.id,
    )
    assert _queue_rows(session, upload) == []
    _assert_no_personal_values(events, ORNEKOVA_PERSONAL)


# --- S12: aynı isimli iki çalışan ---------------------------------------------------------------

OTHER_BIRTH_DATE = date(1980, 1, 1)
S12_AMBIGUOUS_REASON = (
    "Belirsiz eşleşme: ad-soyad ve doğum tarihi birden fazla çalışana uyuyor (E0001, E0002). "
    "Çalışan otomatik eşleştirilmez."
)
S12_NAME_ONLY_REASON = (
    f"{NAME_ONLY_REASON}. İsmi eşleşen çalışanlar: E0001, E0002. Yalnız isim eşleşmesi otomatik "
    "eşleştirme sayılmaz (R8)."
)


@pytest.mark.parametrize(
    ("birth_dates", "matched"),
    [
        pytest.param(
            (PERSON_ORNEKOVA.date_of_birth, OTHER_BIRTH_DATE), "E0001", id="ilkine-uyuyor"
        ),
        pytest.param(
            (OTHER_BIRTH_DATE, PERSON_ORNEKOVA.date_of_birth), "E0002", id="ikincisine-uyuyor"
        ),
    ],
)
def test_s12_namesake_whose_birth_date_matches_gets_the_document(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    birth_dates: tuple[date, date],
    matched: str,
) -> None:
    # İki kayıtlı çalışan aynı isimle, belge numarası kayıtsız: yalnız doğum tarihi ayırır.
    employees = [
        _register_employee(session, layout, replace(PERSON_ORNEKOVA, date_of_birth=born), ())
        for born in birth_dates
    ]
    assert [employee.id for employee in employees] == ["E0001", "E0002"]
    passport = _passport()
    content = make_document_pdf_bytes([passport])
    upload = _upload(client, session, ("pasaport.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [passport])

    _process(session, layout, upload, provider)

    # §20.2.2 satır 3: ad-soyad + doğum tarihi tek çalışana uyuyor → o çalışanın Hazir'ı.
    (item,) = _items(session, upload)
    assert (item.route, item.operation, item.target_name) == (
        Route.READY,
        Operation.PASSTHROUGH,
        PASSPORT_OUTPUT,
    )
    assert (item.employee.action, item.employee.employee_id, item.employee.matched_by) == (
        EmployeeAction.MATCH,
        matched,
        MatchedBy.NAME_DOB,
    )
    for employee in employees:
        hazir = layout.ready_dir(employee.folder_name)
        if employee.id == matched:
            assert _names(hazir) == [PASSPORT_OUTPUT]
            assert (hazir / PASSPORT_OUTPUT).read_bytes() == content
            # 05.7.2: eşleşen çalışana belgenin temiz numarası eklenir, ötekine hiçbir şey.
            assert _identifiers(session, employee.id) == [(PASSPORT, normalized(PASSPORT_NUMBER))]
        else:
            assert _names(hazir) == []
            assert _identifiers(session, employee.id) == []
    (output,) = _outputs(session)
    assert output.employee_id == matched
    assert _count(session, Employee) == 2
    assert _queue_rows(session, upload) == []

    events = _events(session, upload)
    (person,) = [row for row in events if row.type == EventType.PERSON_MATCHED]
    assert person.employee_id == matched
    assert EventType.EMPLOYEE_CREATED not in _event_types(events)
    _assert_no_personal_values(events, (*ORNEKOVA_PERSONAL, "1980-01-01"))


@pytest.mark.parametrize(
    ("birth_dates", "reason", "event_type", "rule"),
    [
        pytest.param(
            (PERSON_ORNEKOVA.date_of_birth, PERSON_ORNEKOVA.date_of_birth),
            S12_AMBIGUOUS_REASON,
            EventType.PERSON_AMBIGUOUS,
            "name_dob_ambiguous",
            id="ikisine-uyuyor",
        ),
        pytest.param(
            (OTHER_BIRTH_DATE, date(1970, 7, 7)),
            S12_NAME_ONLY_REASON,
            EventType.PERSON_NOT_MATCHED,
            "name_only",
            id="hicbirine-uymuyor",
        ),
    ],
)
def test_s12_namesakes_both_or_neither_matching_the_birth_date_go_to_unresolved(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    birth_dates: tuple[date, date],
    reason: str,
    event_type: EventType,
    rule: str,
) -> None:
    employees = [
        _register_employee(session, layout, replace(PERSON_ORNEKOVA, date_of_birth=born), ())
        for born in birth_dates
    ]
    passport = _passport()
    content = make_document_pdf_bytes([passport])
    upload = _upload(client, session, ("pasaport.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [passport])

    _process(session, layout, upload, provider)

    # Satır 4 (ikisine uyuyor) / satır 5 (yalnız isim): Unresolved; numara temiz olsa da satır 6'ya
    # inilmez — yeni çalışan açılmaz, iki çalışana da hiçbir şey eklenmez.
    (item,) = _items(session, upload)
    assert (item.route, item.operation, item.target_name, item.route_reason) == (
        Route.UNRESOLVED,
        None,
        None,
        reason,
    )
    assert (item.employee.action, item.employee.employee_id) == (EmployeeAction.NONE, None)
    (queued,) = _queue_rows(session, upload)
    assert (queued.kind, queued.reason) == ("unresolved", reason)
    directory = layout.queue_dir("unresolved", upload.id)
    assert _names(directory) == ["pasaport.pdf", "reason.json"]
    assert (directory / "pasaport.pdf").read_bytes() == content
    (entry,) = _reason_file(layout, "unresolved", upload)["items"]
    assert entry["reason"] == reason

    assert _count(session, Employee) == 2
    assert _outputs(session) == []
    for employee in employees:
        folder = layout.employee_dir(employee.folder_name)
        assert (_names(folder / "Hazir"), _names(folder / "Alinan")) == ([], [])
        assert _identifiers(session, employee.id) == []

    events = _events(session, upload)
    types = _event_types(events)
    for forbidden in (EventType.PERSON_MATCHED, EventType.EMPLOYEE_CREATED, EventType.OUTPUT_SAVED):
        assert forbidden not in types
    (verdict,) = [row for row in events if row.type == event_type]
    assert verdict.employee_id is None
    assert verdict.data_json is not None
    assert (verdict.data_json["rule"], verdict.data_json["employee_ids"]) == (
        rule,
        ["E0001", "E0002"],
    )
    assert types[-1] is EventType.QUEUED_UNRESOLVED
    _assert_no_personal_values(events, (*ORNEKOVA_PERSONAL, "1980-01-01", "1970-07-07"))


# --- S13: Kiril isimli belge ----------------------------------------------------------------------


def test_s13_cyrillic_name_gives_a_latin_file_name_and_keeps_the_original_in_the_profile(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    passport = passport_page(
        PERSON_TESTOVA_SHCHELKINA, document_number=CYRILLIC_NUMBER, expiry_date=date(2032, 3, 15)
    )
    content = make_document_pdf_bytes([passport])
    upload = _upload(client, session, ("pasport.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [passport])

    _process(session, layout, upload, provider)

    # Klasör ve dosya adı Latin (K8, 05.2.1): Kiril harf yok, ASCII.
    (item,) = _items(session, upload)
    assert (item.route, item.employee.action, item.target_name) == (
        Route.READY,
        EmployeeAction.CREATE,
        CYRILLIC_OUTPUT,
    )
    assert _names(layout.employees) == [CYRILLIC_FOLDER]
    folder = layout.employee_dir(CYRILLIC_FOLDER)
    assert _names(folder / "Hazir") == [CYRILLIC_OUTPUT]
    assert (folder / "Hazir" / CYRILLIC_OUTPUT).read_bytes() == content
    (output,) = _outputs(session)
    assert output.path.isascii() and output.path.endswith(f"/Hazir/{CYRILLIC_OUTPUT}")

    # Çalışan belgedeki Latin yazımla, orijinal yazım ayrıca saklanır.
    employee = session.get_one(Employee, "E0001")
    assert (employee.given_names, employee.surname, employee.original_script_name) == (
        "IULIA",
        "TESTOVA-SHCHELKINA",
        CYRILLIC_ORIGINAL,
    )

    # Profil: Latin ad ve orijinal yazım birlikte (09.1.2) — ön blokta ve kimlik tablosunda.
    profile, body = _profile(layout, CYRILLIC_FOLDER)
    assert (profile["given_names"], profile["surname"], profile["original_script_name"]) == (
        "IULIA",
        "TESTOVA-SHCHELKINA",
        CYRILLIC_ORIGINAL,
    )
    assert "# IULIA TESTOVA-SHCHELKINA\n" in body
    assert "| Ad | IULIA |" in body and "| Soyad | TESTOVA-SHCHELKINA |" in body
    assert f"| Orijinal yazım | {CYRILLIC_ORIGINAL} |" in body
    assert _document_row(body, CYRILLIC_OUTPUT)[:3] == [
        "Russian Passport",
        CYRILLIC_OUTPUT,
        "active",
    ]

    events = _events(session, upload)
    assert EventType.EMPLOYEE_CREATED in _event_types(events)
    _assert_no_personal_values(events, CYRILLIC_PERSONAL)


# --- S14: katalogda olmayan tür -------------------------------------------------------------------


def _diploma(slug: str | None) -> SyntheticPage:
    """Peru diploması: katalog dışıyken aday türle (`slug` boş), onaydan sonra kataloğun türüyle
    okunur. Sayfaya yazılan iki durumda da aynıdır."""
    if slug is None:
        return unknown_document_page(
            PERSON_PRUEBA,
            candidate_type_name=DIPLOMA_NAME,
            title="DIPLOMA",
            document_number=DIPLOMA_NUMBER,
        )
    return document_page(
        slug,
        title="DIPLOMA",
        person=PERSON_PRUEBA,
        document_number=DIPLOMA_NUMBER,
        shows=("surname", "given_names", "date_of_birth", "document_number"),
        language="es",
        script="latin",
        required_fields=DIPLOMA_FIELDS,
    )


def _approve_diploma_type(session: Session) -> None:
    """Onayın sonucu (11.5.2): tür güncel katalogda. Tohum türleri olduğu gibi kalır."""
    entries = [entry.model_dump(mode="json") for entry in export_catalog(session)]
    result = import_catalog(session, validate_catalog([*entries, DIPLOMA_ENTRY]))
    assert result.created == (DIPLOMA,)
    session.commit()


def test_s14_catalog_less_type_goes_to_unknown_then_to_hazir_after_approval_and_reanalysis(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee = _register_employee(session, layout, PERSON_PRUEBA, ())
    assert employee.folder_name == PRUEBA_FOLDER
    unknown = _diploma(None)
    content = make_document_pdf_bytes([unknown])
    assert make_document_pdf_bytes([_diploma(DIPLOMA)]) == content  # aynı fiziksel sayfa
    upload = _upload(client, session, ("diploma.pdf", content))

    _process(session, layout, upload, recorded_provider(tmp_path / "ilk", [unknown]))

    # 1) Unknown + aday tür: türe zorla atanmaz, çalışana yerleşmez (R7); aday tür kaydı açılır.
    (first_plan,) = _plans(session, upload)
    (item,) = read_plan(first_plan).items
    assert (item.route, item.document_type_slug, item.operation, item.target_name) == (
        Route.UNKNOWN,
        None,
        None,
        None,
    )
    assert item.route_reason == UNKNOWN_REASON
    (queued,) = _queue_rows(session, upload)
    assert (queued.kind, queued.plan_id, queued.plan_item_id) == ("unknown", first_plan.id, "i1")
    unknown_dir = layout.queue_dir("unknown", upload.id)
    assert _names(unknown_dir) == ["diploma.pdf", "reason.json"]
    assert (unknown_dir / "diploma.pdf").read_bytes() == content
    (entry,) = _reason_file(layout, "unknown", upload)["items"]
    assert (entry["reason"], entry["document_type_slug"]) == (UNKNOWN_REASON, None)

    (candidate,) = session.scalars(select(CandidateDocumentType)).all()
    (page,) = session.scalars(select(Page).where(Page.file_id == upload.files[0].id)).all()
    assert (candidate.proposed_name, candidate.status, candidate.seen_count) == (
        DIPLOMA_NAME,
        CandidateTypeStatus.PENDING.value,
        1,
    )
    assert (candidate.first_seen_upload_id, candidate.sample_page_ids) == (upload.id, [page.id])
    assert _outputs(session) == []
    hazir = layout.ready_dir(PRUEBA_FOLDER)
    assert _names(hazir) == []
    events = _events(session, upload)
    types = _event_types(events)
    assert EventType.DOC_TYPE_DETERMINED not in types
    (proposed,) = [row for row in events if row.type == EventType.CANDIDATE_TYPE_PROPOSED]
    assert proposed.data_json is not None
    assert (proposed.data_json["candidate_type_id"], proposed.data_json["candidate_type_name"]) == (
        candidate.id,
        DIPLOMA_NAME,
    )
    assert types[-1] is EventType.QUEUED_UNKNOWN

    # 2) Onay: tür katalogda. 3) Yeniden analiz: aynı sayfa güncel katalogla yeniden okunur.
    _approve_diploma_type(session)
    approved = _diploma(DIPLOMA)
    provider = recorded_provider(tmp_path / "yeniden", [approved])
    _use_provider(client, provider)
    response = client.post(f"/api/uploads/{upload.id}/reanalyze")
    assert response.status_code == 200, response.text
    session.expire_all()

    assert [request.page_index for request in provider.requests] == [0]
    old_plan, new_plan = _plans(session, upload)
    assert (old_plan.id, new_plan.version) == (first_plan.id, 2)
    assert response.json()["previous_plan_id"] == first_plan.id
    assert response.json()["superseded_document_ids"] == []

    # Yeni sürümde belge katalog türüyle Hazir'da: ad + doğum tarihiyle kayıtlı çalışana (satır 3).
    (item,) = read_plan(new_plan).items
    assert (item.route, item.document_type_slug, item.operation, item.target_name) == (
        Route.READY,
        DIPLOMA,
        Operation.PASSTHROUGH,
        DIPLOMA_OUTPUT,
    )
    assert (item.employee.action, item.employee.employee_id, item.employee.matched_by) == (
        EmployeeAction.MATCH,
        employee.id,
        MatchedBy.NAME_DOB,
    )
    assert _names(hazir) == [DIPLOMA_OUTPUT]
    assert (hazir / DIPLOMA_OUTPUT).read_bytes() == content
    (output,) = _outputs(session)
    assert (output.employee_id, output.type_slug, output.plan_id, output.status) == (
        employee.id,
        DIPLOMA,
        new_plan.id,
        "active",
    )
    _, body = _profile(layout, PRUEBA_FOLDER)
    assert _document_row(body, DIPLOMA_OUTPUT)[:3] == [DIPLOMA_NAME, DIPLOMA_OUTPUT, "active"]
    assert _identifiers(session, employee.id) == [(DIPLOMA, normalized(DIPLOMA_NUMBER))]

    # K18: eski plan ve Unknown kaydı yerinde, kuyruk kopyası silinmez; aday yeniden sayılmaz.
    (old_item,) = read_plan(old_plan).items
    assert old_item.route is Route.UNKNOWN
    assert [(row.plan_id, row.kind) for row in _queue_rows(session, upload)] == [
        (first_plan.id, "unknown")
    ]
    assert (unknown_dir / "diploma.pdf").read_bytes() == content
    session.refresh(candidate)
    assert (candidate.seen_count, candidate.sample_page_ids) == (1, [page.id])
    assert _count(session, Employee) == 1

    events = _events(session, upload)
    later = events[len(types) :]
    later_types = _event_types(later)
    for expected in (
        EventType.PAGE_ANALYZED,
        EventType.DOC_TYPE_DETERMINED,
        EventType.PERSON_MATCHED,
        EventType.PLAN_CREATED,
        EventType.PLAN_REANALYZED,
        EventType.OUTPUT_SAVED,
    ):
        assert expected in later_types
    assert EventType.CANDIDATE_TYPE_PROPOSED not in later_types
    (determined,) = [row for row in later if row.type == EventType.DOC_TYPE_DETERMINED]
    assert determined.data_json is not None
    assert determined.data_json["document_type_slug"] == DIPLOMA
    _assert_no_personal_values(events, PRUEBA_PERSONAL)


# --- S15: Word CV ---------------------------------------------------------------------------------

WORD_FILES = [
    pytest.param("cv.docx", make_docx_bytes, id="docx"),
    pytest.param("cv.doc", make_legacy_doc_bytes, id="eski-doc"),
]


@pytest.mark.parametrize(("name", "make"), WORD_FILES)
def test_s15_word_cv_uploaded_from_the_profile_page_lands_in_hazir_unchanged(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    name: str,
    make: Callable[[], bytes],
) -> None:
    employee = _register_sidorov(session, layout)
    content = make()
    upload = _upload_in_context(client, session, employee.id, (name, content))
    # Sağlayıcı geçerli yanıtla hazır: çağrılsaydı analiz ederdi, çağrı sayısı sıfır kalmalı.
    provider = recorded_provider(tmp_path / "kayit", [_passport()])

    _process(session, layout, upload, provider)

    # K2: analiz edilmez, render edilmez, dönüştürülmez; bağlam çalışanının Hazir'ına olduğu gibi.
    assert provider.requests == []
    assert session.scalars(select(Page).where(Page.file_id == upload.files[0].id)).all() == []
    target = f"Ivan_Sidorov-Attachment{Path(name).suffix}"  # K8 adı, uzantı yüklenenin
    (item,) = _items(session, upload)
    assert (item.route, item.document_type_slug, item.operation, item.target_name) == (
        Route.READY,
        ATTACHMENT,
        Operation.PASSTHROUGH,
        target,
    )
    assert item.employee.employee_id == employee.id
    folder = layout.employee_dir(SIDOROV_FOLDER)
    assert _names(folder / "Hazir") == [target]
    assert (folder / "Hazir" / target).read_bytes() == content
    assert _names(folder / "Alinan") == [name]
    assert (folder / "Alinan" / name).read_bytes() == content
    assert layout.resolve(upload.files[0].stored_path).read_bytes() == content
    (output,) = _outputs(session)
    assert (output.employee_id, output.type_slug, output.status) == (
        employee.id,
        ATTACHMENT,
        "active",
    )
    _, body = _profile(layout, SIDOROV_FOLDER)
    assert _document_row(body, target)[:3] == ["Attachment", target, "active"]
    assert _queue_rows(session, upload) == []

    events = _events(session, upload)
    types = _event_types(events)
    for forbidden in (
        EventType.PAGE_RENDERED,
        EventType.PAGE_ANALYZED,
        EventType.IMAGE_WRAPPED,
        EventType.IMAGE_RENDERED,
    ):
        assert forbidden not in types
    (saved,) = [row for row in events if row.type == EventType.OUTPUT_SAVED]
    assert saved.data_json is not None
    assert (saved.document_id, saved.data_json["operation"]) == (output.id, "passthrough")
    _assert_no_personal_values(events, SIDOROV_PERSONAL)


@pytest.mark.parametrize(("name", "make"), WORD_FILES)
def test_s15_word_cv_from_a_general_upload_goes_to_unresolved_unchanged(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    name: str,
    make: Callable[[], bytes],
) -> None:
    # Kayıtlı çalışan olsa da sahibi yükleme bağlamından belli değil: tahmin edilmez (K2, R7).
    employee = _register_sidorov(session, layout)
    content = make()
    upload = _upload(client, session, (name, content))
    assert upload.context_employee_id is None
    # Sağlayıcı geçerli yanıtla hazır: çağrılsaydı analiz ederdi, çağrı sayısı sıfır kalmalı.
    provider = recorded_provider(tmp_path / "kayit", [_passport()])

    _process(session, layout, upload, provider)

    assert provider.requests == []
    (item,) = _items(session, upload)
    assert (item.route, item.document_type_slug, item.operation, item.target_name) == (
        Route.UNRESOLVED,
        ATTACHMENT,
        None,
        None,
    )
    assert item.route_reason == ATTACHMENT_REASON
    assert item.employee.employee_id is None
    (queued,) = _queue_rows(session, upload)
    assert (queued.kind, queued.reason) == ("unresolved", ATTACHMENT_REASON)
    directory = layout.queue_dir("unresolved", upload.id)
    assert _names(directory) == [name, "reason.json"]
    assert (directory / name).read_bytes() == content
    (entry,) = _reason_file(layout, "unresolved", upload)["items"]
    assert (entry["reason"], entry["document_type_slug"]) == (ATTACHMENT_REASON, ATTACHMENT)

    assert _outputs(session) == []
    folder = layout.employee_dir(employee.folder_name)
    assert (_names(folder / "Hazir"), _names(folder / "Alinan")) == ([], [])
    assert sorted(path.name for path in layout.root.rglob("*.pdf")) == []
    events = _events(session, upload)
    types = _event_types(events)
    assert EventType.OUTPUT_SAVED not in types and EventType.PAGE_RENDERED not in types
    assert types[-1] is EventType.QUEUED_UNRESOLVED


# --- S18: mevcut plandan yeniden çalıştırma -------------------------------------------------------


def _s18_pages() -> list[SyntheticPage]:
    """Ehliyet ön/arka, vesikalık, boş sayfa, katalog dışı belge, oturma izni ön/arka: planda hazir
    (vesikalık aynı dosyanın kayıtlı çalışanına — D29), kuyruk ve skip öğeleri birlikte."""
    license_pages = driving_license_pages(
        PERSON_SIDOROV, document_number=LICENSE_NUMBER, expiry_date=date(2031, 6, 30)
    )
    residence = residence_card_pages(
        PERSON_SIDOROV, document_number=RESIDENCE_NUMBER, expiry_date=date(2029, 12, 31)
    )
    diploma = unknown_document_page(
        PERSON_SIDOROV, candidate_type_name="Peruvian Diploma", title="DIPLOMA"
    )
    return [*license_pages, profile_picture_page(), blank_page(), diploma, *residence]


def _state(session: Session, upload: Upload) -> dict[str, Any]:
    """Partinin veritabanındaki izi: planlar, çıktılar, kuyruk kayıtları, çalışanlar."""
    session.expire_all()
    return {
        "plans": [(row.id, row.version, row.plan_hash) for row in _plans(session, upload)],
        "outputs": [
            (row.id, row.employee_id, row.type_slug, row.path, row.plan_id, row.status)
            for row in _outputs(session)
        ],
        "queue": [
            (row.id, row.plan_id, row.plan_item_id, row.kind)
            for row in _queue_rows(session, upload)
        ],
        "employees": session.scalars(select(Employee.id)).all(),
        "identifiers": session.execute(
            select(EmployeeIdentifier.employee_id, EmployeeIdentifier.value)
        ).all(),
    }


def test_s18_rerunning_the_existing_plan_gives_the_same_outputs_without_the_provider(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    _register_sidorov(session, layout)
    pages = _s18_pages()
    content = make_document_pdf_bytes(pages)
    upload = _upload(client, session, ("belgeler.pdf", content))
    first = recorded_provider(tmp_path / "ilk", pages)
    _process(session, layout, upload, first)

    (plan,) = _plans(session, upload)
    items = read_plan(plan).items
    assert [(item.route, item.target_name) for item in items] == [
        (Route.READY, LICENSE_OUTPUT),
        (Route.READY, PHOTO_OUTPUT),
        (Route.SKIP, None),
        (Route.UNKNOWN, None),
        (Route.READY, RESIDENCE_OUTPUT),
    ]
    hazir = layout.ready_dir(SIDOROV_FOLDER)
    assert _names(hazir) == [LICENSE_OUTPUT, PHOTO_OUTPUT, RESIDENCE_OUTPUT]
    analyzed = len(first.requests)
    before_files = _files(layout.root)
    before_state = _state(session, upload)
    before_events = len(_events(session, upload))
    session.commit()  # okuma işlemi kapanır (BEGIN IMMEDIATE); uç noktanın oturumu yazabilsin

    # Sağlayıcı uç noktaya verilse bile çağrılmaz: yeniden çalıştırmanın bağımlılığı değildir.
    provider = recorded_provider(tmp_path / "yeniden", pages)
    _use_provider(client, provider)
    for _ in range(2):
        response = client.post(f"/api/uploads/{upload.id}/rerun")
        assert response.status_code == 200, response.text
        assert response.json() == {
            "upload_id": upload.id,
            "plan_id": plan.id,
            "version": 1,
            "plan_hash": plan.plan_hash,
        }

    assert provider.requests == []
    assert len(first.requests) == analyzed

    # Aynı çıktılar: aynı satırlar, aynı dosyalar bayt bayt; ikinci dosya (`-2`) yok, yeni plan yok.
    assert _state(session, upload) == before_state
    after_files = _files(layout.root)
    assert after_files == before_files
    assert not [path for path in after_files if re.search(r"-2\.[a-z]+$", path)]
    assert _names(hazir) == [LICENSE_OUTPUT, PHOTO_OUTPUT, RESIDENCE_OUTPUT]

    # Olaylar: her yeniden çalıştırmada `PLAN_RERUN`, uygulanmış hazir ve skip öğeleri için
    # `OUTPUT_SKIPPED`; yeni çıktı, kopya, kuyruk olayı ve analiz yok.
    later = _events(session, upload)[before_events:]
    rerun_types = [
        EventType.PLAN_RERUN,
        EventType.OUTPUT_SKIPPED,
        EventType.OUTPUT_SKIPPED,
        EventType.OUTPUT_SKIPPED,
        EventType.OUTPUT_SKIPPED,
    ]
    assert _event_types(later) == rerun_types * 2
    reruns = [row for row in later if row.type == EventType.PLAN_RERUN]
    assert [row.data_json for row in reruns] == [
        {"plan_id": plan.id, "version": 1, "plan_hash": plan.plan_hash}
    ] * 2
    skipped_documents = sorted(row.document_id for row in later[:5] if row.document_id is not None)
    assert skipped_documents == sorted(row[0] for row in before_state["outputs"])
    _assert_no_personal_values(later, SIDOROV_PERSONAL)
