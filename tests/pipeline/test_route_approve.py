"""08.3.1 — onay bekleyen profili onaylama: onay sonrası çalışan oluşur ve belge ona bağlanır
(§20.2.2 satır 7; K7, K9, K16; fiziksel kurallar K3, K5, K11, K12 onayda da geçerlidir). 10.7.3 —
önerilen profil düzenlenip onaylanır, belge içeriği düzenlenemez (K17).

Onay bekleyen profiller gerçek planlayıcıdan (06.1) ve kuyruğa yönlendirmeden (08.1) geçer; sayfa
analizleri kayıtlı yanıt biçimindeki sentetik sözlüklerdir, dosyalar `tests/fixtures/gen.py` ile
üretilir (CONVENTIONS §6). Onay başladıktan sonra yapay zekâ sağlayıcısına giden her istek testi
düşürür.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.pipeline.execute as execute_module
from app.catalog import Catalog, import_catalog
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    Page,
    Plan,
    QueueItem,
    Upload,
)
from app.events import EventType
from app.matching.match import EmployeeAction, ProfileFields
from app.matching.names import normalize_name
from app.pipeline.execute import ExtractSourceError
from app.pipeline.plan import Operation, Route, create_plan, read_plan
from app.pipeline.route import (
    ApprovedProfile,
    QueueItemNotApprovableError,
    QueueItemNotAssignableError,
    QueueItemNotFoundError,
    QueueItemResolvedError,
    QueueItemSupersededError,
    QueueSourceIntegrityError,
    approve_queued_profile,
    assign_queue_item,
    review_queued_profile,
    route_queue_item,
)
from app.profiles import render_profile
from app.storage import DataLayout, sha256_file
from tests.fixtures.gen import make_text_pdf_bytes
from tests.pipeline.test_execute import _files, _open
from tests.pipeline.test_orchestrate import _forbid_ai
from tests.pipeline.test_plan import (
    BLANK,
    BORN,
    CATALOG,
    GIVEN,
    LICENSE,
    MODEL,
    PERMIT,
    PHONE,
    SURNAME,
    _assert_no_personal_values,
    _back,
    _catalog_with,
    _count,
    _events,
    _File,
    _image,
    _page,
    _pdf,
    _person,
)
from tests.pipeline.test_plan import _upload as _upload_with_analyses
from tests.pipeline.test_route_assign import QUEUE_ROUTES, _reason_items

ACTOR = "ik.ayse"
NEW = "E0001"
FOLDER = "Test_Ornekova_E0001"
# §20.2.3 koşul 2: normalize hâli 5 karakterden kısa numara temiz değildir → satır 7.
SHORT_NUMBER = "AB12"


def _pending(**changes: Any) -> dict[str, Any]:
    """Onay bekleyen profil (satır 7) olarak planlanan çalışma izni sayfası."""
    return _page(PERMIT, person=_person(document_number=SHORT_NUMBER, **changes))


def _queued(
    session: Session,
    layout: DataLayout,
    *files: _File,
    catalog: Catalog = CATALOG,
) -> tuple[Upload, Plan, list[QueueItem]]:
    """Partiyi planlar ve kuyruğa giden öğelerini 08.1 ile kuyruğa alır."""
    import_catalog(session, catalog)  # `documents.type_slug` katalog tablosuna bağlıdır
    upload = _upload_with_analyses(session, layout, *files)
    plan = create_plan(session, layout, upload, catalog=catalog, model=MODEL)
    rows = [
        route_queue_item(session, layout, plan, item).queue_item
        for item in read_plan(plan).items
        if item.route in QUEUE_ROUTES
    ]
    return upload, plan, rows


def _approve(
    session: Session, layout: DataLayout, queue_item_id: int, *, actor: str = ACTOR
) -> ApprovedProfile:
    return approve_queued_profile(
        session,
        layout,
        queue_item_id,
        actor=actor,
        render_image_dpi=100,
        render_image_jpeg_quality=90,
    )


def _state(session: Session, layout: DataLayout) -> tuple[Any, ...]:
    """Onayın dokunabileceği her şey: çalışan kayıtları ve klasörleri, çıktılar, olaylar, kuyruk."""
    return (
        [employee.id for employee in session.scalars(select(Employee).order_by(Employee.id))],
        _count(session, EmployeeAlias),
        _count(session, EmployeeIdentifier),
        _count(session, EmployeeContact),
        _count(session, Document),
        [event.id for event in _events(session)],
        _files(layout.employees),
        [
            (row.id, row.resolved_at, row.resolved_by)
            for row in session.scalars(select(QueueItem).order_by(QueueItem.id))
        ],
    )


def _register_same_name(session: Session, *, born: date | None) -> None:
    employee = Employee(
        id="E0042",
        folder_name="Kayitli_Kisi_E0042",
        given_names=GIVEN,
        surname=SURNAME,
        date_of_birth=born,
    )
    session.add(employee)
    session.add(
        EmployeeAlias(
            employee=employee,
            raw_name=f"{GIVEN} {SURNAME}",
            normalized_name=normalize_name(GIVEN, SURNAME),
        )
    )
    session.flush()


# --- 08.3.1 kabul kriteri ------------------------------------------------------------------


def test_approval_opens_the_employee_and_binds_the_document(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # K7: numarası temiz olmayan çalışma izni onay bekleyen profil olarak Unresolved'da; İK onaylar,
    # çalışan önerilen profille açılır ve belge onun Hazir'ına yazılır.
    contact = {"phone": PHONE, "email": None, "address": None}
    upload, plan, (queued,) = _queued(session, layout, _pdf(_pending(contact=contact)))
    assert queued.kind == "unresolved"
    (item,) = read_plan(plan).items
    assert item.employee.action is EmployeeAction.PENDING
    (upload_file,) = upload.files
    frozen = (copy.deepcopy(plan.json), plan.plan_hash)
    analyses = [copy.deepcopy(page.analysis_json) for page in session.scalars(select(Page))]
    before = [event.id for event in _events(session)]
    _forbid_ai(monkeypatch)

    approved = _approve(session, layout, queued.id)

    # Çalışan oluştu: önerilen profilin okumaları, E numarası ve klasörü (K8).
    employee = approved.employee
    assert (employee.id, employee.folder_name) == (NEW, FOLDER)
    assert (
        employee.given_names,
        employee.surname,
        employee.date_of_birth.isoformat() if employee.date_of_birth else None,
        employee.nationality,
    ) == (GIVEN, SURNAME, BORN, "RUS")
    assert [
        (alias.raw_name, alias.normalized_name, alias.script)
        for alias in session.scalars(select(EmployeeAlias))
    ] == [(f"{GIVEN} {SURNAME}", normalize_name(GIVEN, SURNAME), "latin")]
    # Temiz olmayan numara yazılmaz (§20.2.3, D11); belgedeki iletişim bilgisi eklenir (05.8).
    assert _count(session, EmployeeIdentifier) == 0
    (phone,) = session.scalars(select(EmployeeContact))
    assert (phone.employee_id, phone.kind, phone.value, phone.is_current) == (
        NEW,
        "phone",
        PHONE,
        True,
    )

    # Belge ona bağlandı: Hazir'da K8 adıyla kaynağın baytları, Alinan'da orijinal, köken kaydı.
    assert approved.operation is Operation.PASSTHROUGH
    output = layout.ready_dir(FOLDER) / "Test_Ornekova-Work-Permit.pdf"
    assert _files(layout.ready_dir(FOLDER)) == [output.name]
    assert sha256_file(output) == upload_file.sha256
    assert _files(layout.received_dir(FOLDER)) == [upload_file.original_name]
    document = approved.executed.document
    assert (
        document.employee_id,
        document.type_slug,
        document.path,
        document.plan_id,
        document.source_refs_json,
        document.status,
    ) == (
        NEW,
        PERMIT,
        layout.relative(output),
        plan.id,
        [{"file_id": upload_file.id, "pages": [0]}],
        DocumentStatus.ACTIVE.value,
    )
    assert phone.source_document_id == document.id

    # Kuyruk kaydı kullanıcı adıyla çözüldü; olay logu çalışanı, çıktıyı ve manuel onayı taşır.
    assert approved.queue_item is queued
    assert queued.resolved_at is not None and queued.resolved_by == ACTOR
    added = [event for event in _events(session) if event.id not in before]
    assert [(event.type, event.actor) for event in added] == [
        (EventType.EMPLOYEE_CREATED, ACTOR),
        (EventType.OUTPUT_SAVED, "system"),
        (EventType.MANUAL_APPROVE, ACTOR),
    ]
    created, _, manual = added
    assert (created.upload_id, created.file_id, created.page_index, created.employee_id) == (
        upload.id,
        upload_file.id,
        0,
        NEW,
    )
    assert created.data_json == {"action": "pending", "document_type_slug": PERMIT}
    assert (
        manual.upload_id,
        manual.file_id,
        manual.page_index,
        manual.document_id,
        manual.employee_id,
        manual.message,
    ) == (upload.id, upload_file.id, 0, document.id, NEW, None)
    assert manual.data_json == {
        "queue_item_id": queued.id,
        "queue": "unresolved",
        "plan_id": plan.id,
        "item_id": queued.plan_item_id,
        "document_type_slug": PERMIT,
        "operation": "passthrough",
    }
    (entry,) = _reason_items(layout, "unresolved", upload)
    assert entry["resolved_by"] == ACTOR and entry["resolved_at"] == queued.resolved_at.isoformat()

    # Yapay zekâ çağrılmadı, analiz ve plan değişmedi, yeni plan sürümü açılmadı (K9).
    assert [copy.deepcopy(page.analysis_json) for page in session.scalars(select(Page))] == analyses
    assert (plan.json, plan.plan_hash) == frozen
    assert _count(session, Plan) == 1
    _assert_no_personal_values(session)


# --- 09.1.1: onaydan sonra açılan çalışanın profili üretilir ----------------------------------


def test_approval_writes_the_new_employees_profile(session: Session, layout: DataLayout) -> None:
    # Profil çıktı ve belgeden eklenen iletişim bilgisi yazıldıktan sonra üretilir.
    contact = {"phone": PHONE, "email": None, "address": None}
    _, _, (queued,) = _queued(session, layout, _pdf(_pending(contact=contact)))

    approved = _approve(session, layout, queued.id)

    text = layout.profile_path(FOLDER).read_text(encoding="utf-8")
    assert text == render_profile(session, approved.employee)
    front_matter = yaml.safe_load(text.split("---\n")[1])
    assert (front_matter["employee_id"], front_matter["folder_name"]) == (NEW, FOLDER)
    assert front_matter["contacts"] == [{"kind": "phone", "value": PHONE}]
    assert "| Work Permit | Test_Ornekova-Work-Permit.pdf | active |" in text
    assert sorted(path.name for path in layout.employee_dir(FOLDER).iterdir()) == [
        "Alinan",
        "Hazir",
        "profil.md",
    ]


def test_refused_approval_does_not_write_a_profile(session: Session, layout: DataLayout) -> None:
    _, _, (queued,) = _queued(session, layout, _image(_pending()))
    import_catalog(session, _catalog_with(PERMIT, allowed_conversions=["merge"]))

    with pytest.raises(QueueItemNotAssignableError, match="Dönüşüm izni yok"):
        _approve(session, layout, queued.id)

    assert _files(layout.employees) == []


def test_blank_page_between_the_faces_stays_out_of_the_approved_output(
    session: Session, layout: DataLayout
) -> None:
    # Kartın yüzleri arasındaki boş sayfa (S8) planın `skip` öğesidir: onayda da `extract` onu
    # çıktıya almaz (K5).
    front = _page(LICENSE, side="front", person=_person(document_number=SHORT_NUMBER))
    upload, _, (queued,) = _queued(
        session,
        layout,
        _File(
            pages=(front, BLANK, _back(LICENSE)),
            content=make_text_pdf_bytes(["EHLIYET ON", "ARA", "EHLIYET ARKA"]),
        ),
    )
    (upload_file,) = upload.files

    approved = _approve(session, layout, queued.id)

    assert approved.operation is Operation.EXTRACT
    output = layout.ready_dir(FOLDER) / "Test_Ornekova-Driving-License.pdf"
    with _open(output) as document:
        assert [page.get_text().strip() for page in document] == ["EHLIYET ON", "EHLIYET ARKA"]
    assert approved.executed.document.source_refs_json == [
        {"file_id": upload_file.id, "pages": [0, 2]}
    ]


def test_other_pending_document_of_the_same_person_is_assigned_not_approved(
    session: Session, layout: DataLayout
) -> None:
    # Aynı kişinin her numarasız belgesi ayrı öneridir (C29). İlki onaylanınca kişi kayıtlıdır:
    # ikinci öneri onaylanmaz (satır 3 — ikinci çalışan açılmaz), belge yeni çalışana atanır.
    _, _, (first, second) = _queued(session, layout, _pdf(_pending()), _pdf(_pending()))
    _approve(session, layout, first.id)
    state = _state(session, layout)

    with pytest.raises(QueueItemNotApprovableError) as refused:
        _approve(session, layout, second.id)

    message = str(refused.value)
    assert message == (
        f"Kuyruk öğesi {second.id} onaylanamaz: Onay bekleyen profil onaylanmaz "
        "(§20.2.2 satır 7, K7): eşleştirme hükmü name_dob."
    )
    assert _state(session, layout) == state

    assign_queue_item(
        session,
        layout,
        second.id,
        NEW,
        actor=ACTOR,
        render_image_dpi=100,
        render_image_jpeg_quality=90,
    )
    assert _count(session, Employee) == 1
    assert _files(layout.ready_dir(FOLDER)) == [
        "Test_Ornekova-Work-Permit-2.pdf",
        "Test_Ornekova-Work-Permit.pdf",
    ]


def test_person_registered_after_the_proposal_is_not_approved(
    session: Session, layout: DataLayout
) -> None:
    # Öneriden sonra kişi kayıtlı bir çalışanla eşleşiyor (ör. temiz numaralı belgesi çalışanı
    # açtı): onay hükmü yeniden değerlendirir, ikinci çalışan açılmaz.
    _, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    _register_same_name(session, born=None)
    state = _state(session, layout)

    with pytest.raises(QueueItemNotApprovableError, match="eşleştirme hükmü name_only") as refused:
        _approve(session, layout, queued.id)

    assert _state(session, layout) == state
    for value in (GIVEN, SURNAME, BORN, SHORT_NUMBER):
        assert value not in str(refused.value)


@pytest.mark.parametrize(
    ("page", "registered"),
    [(_page(PERMIT, illegible=("surname",)), False), (_pending(), True)],
    ids=["unreadable", "name-only"],
)
def test_only_a_pending_profile_is_approved(
    session: Session, layout: DataLayout, page: dict[str, Any], registered: bool
) -> None:
    # Öteki kuyruk öğelerinin kişisi onayla açılmaz; belge kayıtlı çalışana atanır (08.2.1). Yalnız
    # isim eşleşmesi (satır 5) de profil önerisi değildir.
    if registered:
        _register_same_name(session, born=date(1980, 1, 1))
    _, plan, (queued,) = _queued(session, layout, _pdf(page))
    (item,) = read_plan(plan).items
    assert item.employee.action is EmployeeAction.NONE
    state = _state(session, layout)

    with pytest.raises(QueueItemNotApprovableError, match="onay bekleyen profil değil"):
        _approve(session, layout, queued.id)

    assert _state(session, layout) == state


# --- onay aşamaz: fiziksel kurallar ve bütünlük; çalışan açılmaz ----------------------------------


def test_physical_rule_refusal_opens_no_employee(session: Session, layout: DataLayout) -> None:
    # Planlamada `wrap_image` izinliydi; onay güncel katalogla seçer — dönüşüm izni (06.4.1) insan
    # kararıyla aşılmaz (K12) ve ret çalışan açtırmaz.
    _, _, (queued,) = _queued(session, layout, _image(_pending()))
    import_catalog(session, _catalog_with(PERMIT, allowed_conversions=["merge"]))
    state = _state(session, layout)

    with pytest.raises(QueueItemNotAssignableError, match="Dönüşüm izni yok"):
        _approve(session, layout, queued.id)

    assert _state(session, layout) == state


def test_changed_inbox_original_opens_no_employee(session: Session, layout: DataLayout) -> None:
    # K10: Inbox'taki orijinal yüklemedeki SHA-256'yı taşımıyorsa hiçbir şey yazılmaz.
    upload, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    (upload_file,) = upload.files
    layout.resolve(upload_file.stored_path).write_bytes(b"degistirildi")
    state = _state(session, layout)

    with pytest.raises(QueueSourceIntegrityError):
        _approve(session, layout, queued.id)

    assert _state(session, layout) == state


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        ({"analysis_json": None}, "saklanan sayfa analizi yok"),
        ({"analysis_status": "failed"}, "saklanan sayfa analizi yok"),
        ({"analysis_json": {"page_index": 0}}, "saklanan sayfa analizi §8.4 şemasına uymuyor"),
    ],
    ids=["no-analysis", "failed-analysis", "invalid-analysis"],
)
def test_profile_is_not_rebuilt_from_a_missing_or_invalid_analysis(
    session: Session, layout: DataLayout, damage: dict[str, Any], reason: str
) -> None:
    # Profil saklanan analizden yeniden kurulur (K9); okunamayan analizden profil tahmin edilmez.
    upload, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    (page,) = session.scalars(select(Page))
    for name, value in damage.items():
        setattr(page, name, value)
    session.flush()
    state = _state(session, layout)

    with pytest.raises(QueueItemNotApprovableError) as refused:
        _approve(session, layout, queued.id)

    assert str(refused.value) == (
        f"Kuyruk öğesi {queued.id} onaylanamaz: {reason} (dosya {upload.files[0].id}, sayfa 0)"
    )
    assert _state(session, layout) == state


def test_operation_failure_after_opening_the_employee_is_rolled_back_by_the_caller(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # İşlem belgeyi üretemezse (§20.5 doğrulaması) onay tamamlanmaz; çağıranın geri alması
    # açılan çalışanı da geri alır (yalnız boş klasör diskte kalır).
    _, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    session.commit()

    def _fail(*args: object, **kwargs: object) -> object:
        raise ExtractSourceError("extract kaynağı PDF değil")

    monkeypatch.setattr(execute_module, "_ready_output", _fail)

    with pytest.raises(QueueItemNotAssignableError, match="extract kaynağı PDF değil"):
        _approve(session, layout, queued.id)
    session.rollback()

    assert _count(session, Employee) == 0
    assert _count(session, Document) == 0
    assert _events(session, EventType.EMPLOYEE_CREATED) == []
    assert session.get_one(QueueItem, queued.id).resolved_at is None
    assert _files(layout.ready_dir(FOLDER)) == []


# --- çözülmüş, eski sürüm ve istek hataları -----------------------------------------------------


def test_approved_item_is_not_approved_again(session: Session, layout: DataLayout) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    _approve(session, layout, queued.id)
    state = _state(session, layout)

    with pytest.raises(QueueItemResolvedError, match="zaten çözülmüş"):
        _approve(session, layout, queued.id)

    assert _state(session, layout) == state
    assert _count(session, Employee) == 1


def test_rerouting_the_approved_item_writes_nothing_new(
    session: Session, layout: DataLayout
) -> None:
    # Planın yeniden çalıştırılması (06.6.1) onaylanmış öğeyi yeniden kuyruğa almaz.
    _, plan, (queued,) = _queued(session, layout, _pdf(_pending()))
    _approve(session, layout, queued.id)
    state = _state(session, layout)

    (item,) = read_plan(plan).items
    routed = route_queue_item(session, layout, plan, item)

    assert not routed.applied and routed.queue_item is queued
    assert _state(session, layout) == state


def test_item_of_an_older_plan_version_is_not_approved(
    session: Session, layout: DataLayout
) -> None:
    # K18: yeni sürüm açıldıysa eski sürümün önerisi onaylanmaz; güncel planınki onaylanır.
    upload, _, (old,) = _queued(session, layout, _pdf(_pending()))
    newer = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
    (item,) = read_plan(newer).items
    assert (item.route, item.employee.action) == (Route.UNRESOLVED, EmployeeAction.PENDING)
    current = route_queue_item(session, layout, newer, item).queue_item
    state = _state(session, layout)

    with pytest.raises(QueueItemSupersededError, match="eski sürüm"):
        _approve(session, layout, old.id)

    assert _state(session, layout) == state
    approved = _approve(session, layout, current.id)
    assert approved.executed.document.plan_id == newer.id


def test_unknown_queue_item_is_reported(session: Session, layout: DataLayout) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    state = _state(session, layout)

    with pytest.raises(QueueItemNotFoundError):
        _approve(session, layout, queued.id + 100)

    assert _state(session, layout) == state


@pytest.mark.parametrize("actor", ["", "   "])
def test_manual_approval_needs_the_user_name(
    session: Session, layout: DataLayout, actor: str
) -> None:
    # K16: manuel işlem kullanıcı adıyla loglanır.
    _, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    state = _state(session, layout)

    with pytest.raises(ValueError, match="K16"):
        _approve(session, layout, queued.id, actor=actor)

    assert _state(session, layout) == state


def test_approval_leaves_the_transaction_to_the_caller(
    session: Session, layout: DataLayout
) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    session.commit()

    _approve(session, layout, queued.id)
    session.rollback()

    assert session.get_one(QueueItem, queued.id).resolved_at is None
    assert _count(session, Employee) == 0
    assert _count(session, Document) == 0
    assert _events(session, EventType.MANUAL_APPROVE) == []


# --- 10.7.3: önerilen profil düzenlenip onaylanır; belge içeriği düzenlenemez ------------------


def test_edited_profile_changes_the_employee_record_but_not_the_document(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # İK önerinin soyadını ve doğum tarihini düzeltir: çalışan kaydı ve çıktının K8 adı düzeltmeyi
    # taşır; çıktı yine kaynak sayfanın baytlarıdır, analizler ve plan değişmez (K9, K11, K17).
    upload, plan, (queued,) = _queued(session, layout, _pdf(_pending()))
    (upload_file,) = upload.files
    frozen = (copy.deepcopy(plan.json), plan.plan_hash)
    analyses = [copy.deepcopy(page.analysis_json) for page in session.scalars(select(Page))]
    proposal = review_queued_profile(session, queued.id)
    fields = ProfileFields(
        given_names=proposal.given_names,
        surname="ORNEKOVIC",
        date_of_birth=date(1990, 2, 1),
        nationality=proposal.nationality,
    )
    _forbid_ai(monkeypatch)

    approved = approve_queued_profile(
        session,
        layout,
        queued.id,
        actor=ACTOR,
        render_image_dpi=100,
        render_image_jpeg_quality=90,
        fields=fields,
    )

    employee = approved.employee
    folder = "Test_Ornekovic_E0001"
    assert (employee.folder_name, employee.surname, employee.date_of_birth) == (
        folder,
        "ORNEKOVIC",
        date(1990, 2, 1),
    )
    output = layout.ready_dir(folder) / "Test_Ornekovic-Work-Permit.pdf"
    assert _files(layout.ready_dir(folder)) == [output.name]
    assert sha256_file(output) == upload_file.sha256
    document = approved.executed.document
    assert (document.employee_id, document.type_slug, document.source_refs_json) == (
        NEW,
        PERMIT,
        [{"file_id": upload_file.id, "pages": [0]}],
    )
    assert [copy.deepcopy(page.analysis_json) for page in session.scalars(select(Page))] == analyses
    assert (plan.json, plan.plan_hash) == frozen
    (created,) = _events(session, EventType.EMPLOYEE_CREATED)
    assert created.data_json == {
        "action": "pending",
        "document_type_slug": PERMIT,
        "edited_fields": ["surname", "date_of_birth"],
    }
    assert queued.resolved_by == ACTOR
    _assert_no_personal_values(session)


def test_review_shows_the_proposal_the_approval_would_write_and_writes_nothing(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    state = _state(session, layout)
    _forbid_ai(monkeypatch)

    proposal = review_queued_profile(session, queued.id)

    assert (
        proposal.given_names,
        proposal.surname,
        proposal.date_of_birth,
        proposal.nationality,
    ) == (GIVEN, SURNAME, date.fromisoformat(BORN), "RUS")
    assert _state(session, layout) == state
    approved = _approve(session, layout, queued.id)
    assert approved.employee.surname == proposal.surname


def test_review_refuses_what_the_approval_refuses(session: Session, layout: DataLayout) -> None:
    upload, _, (pending, unreadable) = _queued(
        session, layout, _pdf(_pending()), _pdf(_page(PERMIT, illegible=("surname",)))
    )
    state = _state(session, layout)

    with pytest.raises(QueueItemNotApprovableError, match="onay bekleyen profil değil"):
        review_queued_profile(session, unreadable.id)
    with pytest.raises(QueueItemNotApprovableError, match="Profil alanları geçersiz"):
        review_queued_profile(
            session, pending.id, fields=ProfileFields(given_names="", surname=SURNAME)
        )
    with pytest.raises(QueueItemNotFoundError):
        review_queued_profile(session, pending.id + 100)
    assert _state(session, layout) == state

    _approve(session, layout, pending.id)
    with pytest.raises(QueueItemResolvedError):
        review_queued_profile(session, pending.id)
    newer = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
    assert newer.version == 2
    with pytest.raises(QueueItemSupersededError):
        review_queued_profile(session, unreadable.id)


def test_edited_profile_matching_a_registered_employee_opens_no_employee(
    session: Session, layout: DataLayout
) -> None:
    # Düzeltilmiş ad-soyad + doğum tarihi kayıtlı çalışana uyuyor: ikinci çalışan açılmaz.
    _, _, (queued,) = _queued(session, layout, _pdf(_pending()))
    employee = Employee(
        id="E0042", folder_name="Kayitli_Kisi_E0042", given_names="KAYITLI", surname="KISI"
    )
    employee.date_of_birth = date(1985, 5, 5)
    session.add(employee)
    session.add(
        EmployeeAlias(
            employee=employee,
            raw_name="KAYITLI KISI",
            normalized_name=normalize_name("KAYITLI", "KISI"),
        )
    )
    session.flush()
    state = _state(session, layout)
    fields = ProfileFields(given_names="KAYITLI", surname="KISI", date_of_birth=date(1985, 5, 5))

    with pytest.raises(QueueItemNotApprovableError, match=r"name_dob \(E0042\)"):
        approve_queued_profile(
            session,
            layout,
            queued.id,
            actor=ACTOR,
            render_image_dpi=100,
            render_image_jpeg_quality=90,
            fields=fields,
        )

    assert _state(session, layout) == state
