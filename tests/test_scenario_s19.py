"""09.3 — PRD §9 kabul senaryosu S19 uçtan uca: numarasız belge, ad + doğum tarihiyle yeni çalışan
(05.6.2; §20.2.2 satır 6b, §20.2.4; K7, R8, R9, K1).

S1–S18 gibi senaryo gerçek yoldan geçer: parti yükleme uç noktasıyla açılır, `process_upload` ile
render → analiz → plan → uygulama adımlarından geçer. S19'un türü (zorunlu alanları ad, soyad, doğum
tarihi; belge numarası yok) tohum katalogda olmadığı için test onu kataloğa ekler
(`tests.fixtures.gen.employment_contract_entry`). Ön elemenin bu sayfayı hep ana modele
gönderdiği (`unverified_date_of_birth`) `tests/pipeline/test_prescreen_matrix.py`'nin S19
partisindedir. Dosyalar ve kayıtlı yanıtlar sentetiktir; yapay zekâ canlı çağrılmaz, gerçek
kimlik belgesi yoktur (CONVENTIONS §6). Ortam (geçici veritabanı, veri dizini, yükleme uç noktası)
ve yardımcılar S1–S5'inkilerdir.

**Doğum tarihi okunamıyorsa (PLAN.md §D59).** PRD S19 "onay bekleyen profil (Unresolved)" der;
doğum tarihi türün zorunlu alanıyken okunamayan tarih K1 gereği Unreadable'dır ("Okunamayan
alanlar: date_of_birth") ve çalışan kararından önce gelir. İki durumda da çalışan açılmaz, profil
kendiliğinden çalışana dönmez. Onay bekleyen profil, aynı belgenin türü doğum tarihini zorunlu
tutmadığında görülür (§20.2.4 koşul 1).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import Catalog, CatalogEntry, import_catalog
from app.db.models import Employee, EmployeeAlias, EmployeeIdentifier, QueueItem
from app.events import EventType
from app.matching.match import (
    NAME_ONLY_REASON,
    PENDING_PROFILE_REASON,
    EmployeeAction,
)
from app.pipeline.plan import Operation, Route
from app.pipeline.validate import ValidationName
from app.storage import DataLayout
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    EMPLOYMENT_CONTRACT,
    PERSON_PRUEBA,
    SyntheticPage,
    SyntheticPerson,
    employment_contract_entry,
    employment_contract_page,
    make_document_pdf_bytes,
    recorded_provider,
)
from tests.test_scenarios_s01_s05 import (
    CATALOG,
    _assert_no_personal_values,
    _events,
    _items,
    _names,
    _outputs,
    _process,
    _register_employee,
    _upload,
)
from tests.test_scenarios_s06_s10 import _assert_queued_alone, _count, _failed_validations

NAME = "is-sozlesmesi.pdf"  # kuyruk dizininde `reason.json`'dan önce sıralanır
FOLDER = "Ana_Prueba_E0001"
OUTPUT = "Ana_Prueba-Employment-Contract.pdf"
PRUEBA_PERSONAL = ("PRUEBA", "Prueba", "prueba", "1995-03-15")

# Ortam fikstürleri S1–S5'inkilerdir; pytest onları bu modüldeki adlarından bulur.
engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client


def _with_contract(session: Session, entry: CatalogEntry | None = None) -> None:
    # S19'un numarasız türü kataloğa (veritabanı kaydına) eklenir; analiz ve plan onu okur.
    import_catalog(session, Catalog((*CATALOG, entry or employment_contract_entry())))
    session.commit()


def _contract(**changes: object) -> SyntheticPage:
    return employment_contract_page(PERSON_PRUEBA, **changes)  # type: ignore[arg-type]


def _identifiers(session: Session) -> list[tuple[str, str, str]]:
    rows = session.scalars(select(EmployeeIdentifier).order_by(EmployeeIdentifier.id))
    return [(row.employee_id, row.kind, row.value) for row in rows]


def test_s19_numberless_document_with_name_and_birth_date_opens_a_new_employee(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    _with_contract(session)
    contract = _contract()
    content = make_document_pdf_bytes([contract])
    upload = _upload(client, session, ("is-sozlesmesi.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [contract])

    _process(session, layout, upload, provider)

    # §20.2.2 satır 6b: eşleşme yok, temiz numara yok, Latin ad-soyad ve doğum tarihi (türün
    # zorunlu alanı) okunaklı → `create`; belge yeni çalışanın Hazir'ına.
    (item,) = _items(session, upload)
    assert (item.route, item.operation, item.document_type_slug, item.target_name) == (
        Route.READY,
        Operation.PASSTHROUGH,
        EMPLOYMENT_CONTRACT,
        OUTPUT,
    )
    assert (item.employee.action, item.employee.employee_id, item.employee.matched_by) == (
        EmployeeAction.CREATE,
        "E0001",
        None,
    )
    assert _failed_validations(item) == []

    # Yeni çalışan, K8 klasörü ve profil.md; belge numarası yazılmaz.
    employee = session.get_one(Employee, "E0001")
    assert (employee.folder_name, employee.given_names, employee.surname) == (
        FOLDER,
        PERSON_PRUEBA.given_names,
        PERSON_PRUEBA.surname,
    )
    assert employee.date_of_birth == PERSON_PRUEBA.date_of_birth
    assert _identifiers(session) == []
    assert _count(session, EmployeeAlias) == 1
    folder = layout.employee_dir(FOLDER)
    assert _names(folder) == ["Alinan", "Hazir", "profil.md"]
    assert _names(folder / "Hazir") == [OUTPUT]
    assert (folder / "Hazir" / OUTPUT).read_bytes() == content
    assert _names(folder / "Alinan") == ["is-sozlesmesi.pdf"]
    (output,) = _outputs(session)
    assert (output.employee_id, output.type_slug, output.status) == (
        "E0001",
        EMPLOYMENT_CONTRACT,
        "active",
    )
    assert OUTPUT in (folder / "profil.md").read_text(encoding="utf-8")
    assert session.scalars(select(QueueItem)).all() == []

    # Olay kaydı açılış dayanağını taşır (§8.3): `basis: name_dob`; kişisel değer yok.
    events = _events(session, upload)
    (created,) = [row for row in events if row.type == EventType.EMPLOYEE_CREATED]
    assert (created.employee_id, created.data_json) == (
        "E0001",
        {"action": "create", "basis": "name_dob", "document_type_slug": EMPLOYMENT_CONTRACT},
    )
    assert EventType.EMPLOYEE_PENDING not in {row.type for row in events}
    _assert_no_personal_values(events, PRUEBA_PERSONAL)


def test_s19_blurred_birth_date_opens_nobody(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    # Doğum tarihi zorunlu alan ve okunmuyor: K1 → Unreadable (§D59); çalışan açılmaz, profil
    # önerilmez, tahmin yapılmaz.
    _with_contract(session)
    contract = _contract(blurred=("date_of_birth",))
    content = make_document_pdf_bytes([contract])
    upload = _upload(client, session, ("is-sozlesmesi.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [contract])

    _process(session, layout, upload, provider)

    (item,) = _items(session, upload)
    assert (item.route, item.document_type_slug, item.operation) == (
        Route.UNREADABLE,
        EMPLOYMENT_CONTRACT,
        None,
    )
    assert item.route_reason is not None
    assert item.route_reason.startswith("Okunamayan alanlar: date_of_birth")
    assert _failed_validations(item) == [ValidationName.REQUIRED_FIELDS]
    assert (item.employee.action, item.employee.employee_id) == (EmployeeAction.NONE, None)
    _assert_queued_alone(session, layout, upload, "unreadable", "is-sozlesmesi.pdf", content)
    assert _count(session, Employee) == 0
    assert _names(layout.employees) == []
    types = {row.type for row in _events(session, upload)}
    assert EventType.EMPLOYEE_CREATED not in types and EventType.EMPLOYEE_PENDING not in types


def test_s19_type_not_requiring_the_birth_date_leaves_a_pending_profile(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    # §20.2.4 koşul 1: doğum tarihi türün zorunlu alanı değilse (başkasının tarihini taşıyan tür
    # gibi) sayfada okunsa da satır 6b yoktur → satır 7, onay bekleyen profil (Unresolved).
    _with_contract(session, employment_contract_entry(required_fields=("surname", "given_names")))
    contract = _contract()
    content = make_document_pdf_bytes([contract])
    upload = _upload(client, session, ("is-sozlesmesi.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [contract])

    _process(session, layout, upload, provider)

    (item,) = _items(session, upload)
    assert (item.route, item.route_reason) == (Route.UNRESOLVED, PENDING_PROFILE_REASON)
    assert (item.employee.action, item.employee.employee_id) == (EmployeeAction.PENDING, None)
    entry = _assert_queued_alone(session, layout, upload, "unresolved", NAME, content)
    assert entry["reason"] == PENDING_PROFILE_REASON
    assert _count(session, Employee) == 0
    types = [row.type for row in _events(session, upload)]
    assert EventType.EMPLOYEE_PENDING in types and EventType.EMPLOYEE_CREATED not in types


def test_s19_name_matching_another_birth_date_stays_unresolved(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    # R8 korunur (S10): ad kayıtlı bir çalışanın adıyla eşleşir, doğum tarihi farklı → satır 5;
    # satır 6b'ye inilmez, ikinci çalışan açılmaz.
    _with_contract(session)
    namesake = SyntheticPerson(PERSON_PRUEBA.surname, PERSON_PRUEBA.given_names, date(1980, 1, 1))
    other = _register_employee(session, layout, namesake, [])
    contract = _contract()
    content = make_document_pdf_bytes([contract])
    upload = _upload(client, session, ("is-sozlesmesi.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [contract])

    _process(session, layout, upload, provider)

    (item,) = _items(session, upload)
    assert item.route is Route.UNRESOLVED
    assert item.route_reason is not None and item.route_reason.startswith(NAME_ONLY_REASON)
    assert (item.employee.action, item.employee.employee_id) == (EmployeeAction.NONE, None)
    assert session.scalars(select(Employee.id)).all() == [other.id]
    assert _identifiers(session) == []
    types = {row.type for row in _events(session, upload)}
    assert EventType.EMPLOYEE_CREATED not in types and EventType.EMPLOYEE_PENDING not in types
