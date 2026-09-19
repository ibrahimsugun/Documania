"""08.2.1 — kuyruk öğesini çalışana atama: atama sonrası çıktı üretilir ve yapay zekâ çağrılmaz
(K9, K16; fiziksel kurallar K3, K5, K11, K12 atamada da geçerlidir).

Kuyruk öğeleri gerçek planlayıcıdan (06.1) ve kuyruğa yönlendirmeden (08.1) geçer; sayfa analizleri
kayıtlı yanıt biçimindeki sentetik sözlüklerdir, dosyalar `tests/fixtures/gen.py` ile üretilir
(CONVENTIONS §6). Atama başladıktan sonra yapay zekâ sağlayıcısına giden her istek testi düşürür.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.pipeline.execute as execute_module
from app.catalog import Catalog, import_catalog
from app.db.models import Document, DocumentStatus, Employee, Page, Plan, QueueItem, Upload
from app.events import EventType
from app.pipeline.execute import ExtractSourceError
from app.pipeline.plan import (
    Operation,
    PlanIntegrityError,
    Route,
    create_plan,
    read_plan,
)
from app.pipeline.route import (
    AssignedItem,
    AssigneeNotFoundError,
    QueueItemNotAssignableError,
    QueueItemNotFoundError,
    QueueItemResolvedError,
    QueueItemSupersededError,
    QueueSourceIntegrityError,
    assign_queue_item,
    route_queue_item,
)
from app.profiles import render_profile
from app.storage import DataLayout, sha256_file
from tests.fixtures.gen import make_docx_bytes, make_text_pdf_bytes
from tests.pipeline.test_execute import _files, _open
from tests.pipeline.test_orchestrate import _forbid_ai
from tests.pipeline.test_plan import (
    BLANK,
    CATALOG,
    LICENSE,
    MODEL,
    PASSPORT,
    PERMIT,
    RECORDINGS,
    _assert_no_personal_values,
    _back,
    _catalog_with,
    _count,
    _events,
    _File,
    _image,
    _page,
    _passport,
    _pdf,
    _person,
    _photo,
)
from tests.pipeline.test_plan import _upload as _upload_with_analyses

TARGET = "E0042"
TARGET_FOLDER = "Kayitli_Kisi_E0042"
ACTOR = "ik.ayse"
QUEUE_ROUTES = (Route.UNKNOWN, Route.UNREADABLE, Route.UNRESOLVED)


def _queued(
    session: Session,
    layout: DataLayout,
    *files: _File,
    catalog: Catalog = CATALOG,
) -> tuple[Upload, Plan, list[QueueItem]]:
    """Partiyi planlar ve kuyruğa giden öğelerini 08.1 ile kuyruğa alır; atanacak çalışanı açar."""
    import_catalog(session, catalog)  # `documents.type_slug` katalog tablosuna bağlıdır
    upload = _upload_with_analyses(session, layout, *files)
    plan = create_plan(session, layout, upload, catalog=catalog, model=MODEL)
    rows = [
        route_queue_item(session, layout, plan, item).queue_item
        for item in read_plan(plan).items
        if item.route in QUEUE_ROUTES
    ]
    employee = Employee(id=TARGET, folder_name=TARGET_FOLDER, given_names="Kayitli", surname="Kisi")
    session.add(employee)
    session.flush()
    layout.ensure_employee_tree(TARGET_FOLDER)
    return upload, plan, rows


def _assign(
    session: Session,
    layout: DataLayout,
    queue_item_id: int,
    employee_id: str = TARGET,
    *,
    actor: str = ACTOR,
) -> AssignedItem:
    return assign_queue_item(
        session,
        layout,
        queue_item_id,
        employee_id,
        actor=actor,
        render_image_dpi=100,
        render_image_jpeg_quality=90,
    )


def _reason_items(layout: DataLayout, kind: str, upload: Upload) -> list[dict[str, Any]]:
    content = layout.queue_reason_path(kind, upload.id).read_text(encoding="utf-8")
    items: list[dict[str, Any]] = json.loads(content)["items"]
    return items


def _state(session: Session, layout: DataLayout) -> tuple[Any, ...]:
    """Atamanın dokunabileceği her şey: satırlar, olaylar, çalışan klasörü, kuyruk kayıtları."""
    return (
        _count(session, Document),
        [event.id for event in _events(session)],
        _files(layout.ready_dir(TARGET_FOLDER)),
        _files(layout.received_dir(TARGET_FOLDER)),
        [
            (row.id, row.resolved_at, row.resolved_by)
            for row in session.scalars(select(QueueItem).order_by(QueueItem.id))
        ],
    )


# --- 08.2.1 kabul kriteri ------------------------------------------------------------------


def test_assignment_produces_the_output_without_calling_ai(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # K1: soyadı okunmayan çalışma izni Unreadable'da; İK sahibini seçer, belge çıktıya döner.
    upload, plan, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    assert queued.kind == "unreadable"
    (upload_file,) = upload.files
    frozen = (copy.deepcopy(plan.json), plan.plan_hash)
    analyses = [copy.deepcopy(page.analysis_json) for page in session.scalars(select(Page))]
    before = [event.id for event in _events(session)]
    _forbid_ai(monkeypatch)

    assigned = _assign(session, layout, queued.id)

    # Çıktı: atanan çalışanın Hazir'ında K8 adıyla, kaynağın baytları (tek sayfa, bütün dosya).
    assert assigned.operation is Operation.PASSTHROUGH
    output = layout.ready_dir(TARGET_FOLDER) / "Kayitli_Kisi-Work-Permit.pdf"
    assert _files(layout.ready_dir(TARGET_FOLDER)) == [output.name]
    assert sha256_file(output) == upload_file.sha256
    assert _files(layout.received_dir(TARGET_FOLDER)) == [upload_file.original_name]
    document = assigned.executed.document
    assert (
        document.employee_id,
        document.type_slug,
        document.path,
        document.format,
        document.sequence_no,
        document.plan_id,
        document.source_refs_json,
        document.status,
    ) == (
        TARGET,
        PERMIT,
        layout.relative(output),
        "pdf",
        1,
        plan.id,
        [{"file_id": upload_file.id, "pages": [0]}],
        DocumentStatus.ACTIVE.value,
    )

    # Kuyruk kaydı kullanıcı adıyla çözüldü; olay logu çıktıyı ve manuel kararı taşır.
    assert assigned.queue_item is queued
    assert queued.resolved_at is not None and queued.resolved_by == ACTOR
    added = [event for event in _events(session) if event.id not in before]
    assert [event.type for event in added] == [EventType.OUTPUT_SAVED, EventType.MANUAL_ASSIGN]
    manual = added[-1]
    assert (
        manual.actor,
        manual.upload_id,
        manual.file_id,
        manual.page_index,
        manual.document_id,
        manual.employee_id,
        manual.message,
    ) == (ACTOR, upload.id, upload_file.id, 0, document.id, TARGET, None)
    assert manual.data_json == {
        "queue_item_id": queued.id,
        "queue": "unreadable",
        "plan_id": plan.id,
        "item_id": queued.plan_item_id,
        "document_type_slug": PERMIT,
        "operation": "passthrough",
    }
    assert added[0].actor == "system" and added[0].document_id == document.id

    # Yapay zekâ çağrılmadı, analiz ve plan değişmedi, yeni plan sürümü açılmadı (K9).
    assert [copy.deepcopy(page.analysis_json) for page in session.scalars(select(Page))] == analyses
    assert (plan.json, plan.plan_hash) == frozen
    assert _count(session, Plan) == 1
    assert not [event for event in added if event.type == EventType.PAGE_ANALYZED]
    _assert_no_personal_values(session)


def test_blank_page_between_the_faces_stays_out_of_the_assigned_output(
    session: Session, layout: DataLayout
) -> None:
    # Onay bekleyen profil (satır 7) Unresolved'da; kartın yüzleri arasındaki boş sayfa (S8)
    # planın `skip` öğesidir — ardışıklık onunla ölçülür, `extract` onu çıktıya almaz (K5).
    front = _page(LICENSE, side="front", person=_person(document_number="AB12"))
    upload, _, (queued,) = _queued(
        session,
        layout,
        _File(
            pages=(front, BLANK, _back(LICENSE)),
            content=make_text_pdf_bytes(["EHLIYET ON", "ARA", "EHLIYET ARKA"]),
        ),
    )
    (upload_file,) = upload.files

    assigned = _assign(session, layout, queued.id)

    assert assigned.operation is Operation.EXTRACT
    output = layout.ready_dir(TARGET_FOLDER) / "Kayitli_Kisi-Driving-License.pdf"
    with _open(output) as document:
        assert [page.get_text().strip() for page in document] == ["EHLIYET ON", "EHLIYET ARKA"]
    assert assigned.executed.document.source_refs_json == [
        {"file_id": upload_file.id, "pages": [0, 2]}
    ]
    added = _events(session, EventType.PAGE_EXTRACTED)
    assert [event.document_id for event in added] == [assigned.executed.document.id]


def test_word_attachment_without_context_is_filed_unchanged_for_the_assigned_employee(
    session: Session, layout: DataLayout
) -> None:
    # S15 / 04.7.1: genel yüklemedeki Word eki sahipsiz Unresolved'da; atanınca değişmeden Hazir'a.
    upload, _, (queued,) = _queued(session, layout, _File(content=make_docx_bytes()))
    (upload_file,) = upload.files

    assigned = _assign(session, layout, queued.id)

    assert assigned.operation is Operation.PASSTHROUGH
    output = layout.ready_dir(TARGET_FOLDER) / "Kayitli_Kisi-Attachment.docx"
    assert sha256_file(output) == upload_file.sha256
    assert assigned.executed.document.source_refs_json == [{"file_id": upload_file.id, "pages": []}]
    (event,) = _events(session, EventType.MANUAL_ASSIGN)
    assert event.page_index is None


def test_reason_file_marks_the_resolved_item_and_keeps_the_others(
    session: Session, layout: DataLayout
) -> None:
    # İki dosyalı parti: iki çalışma izni de Unreadable. Kuyruk klasöründe hiçbir şey silinmez.
    upload, _, (first, second) = _queued(
        session,
        layout,
        _pdf(_page(PERMIT, illegible=("surname",))),
        _pdf(_page(PERMIT, illegible=("surname",)), BLANK),
    )
    queue_dir = layout.queue_dir("unreadable", upload.id)
    copies = _files(queue_dir)

    _assign(session, layout, first.id)

    items = _reason_items(layout, "unreadable", upload)
    assert [(entry["plan_item_id"], entry["resolved_by"]) for entry in items] == [
        (first.plan_item_id, ACTOR),
        (second.plan_item_id, None),
    ]
    assert items[0]["resolved_at"] == first.resolved_at.isoformat()  # type: ignore[union-attr]
    assert items[1]["resolved_at"] is None
    assert _files(queue_dir) == copies


def test_rerouting_the_assigned_item_writes_nothing_new(
    session: Session, layout: DataLayout
) -> None:
    # Planın yeniden çalıştırılması (06.6.1) kuyruk öğesini yeniden yönlendirir: kayıt tekrar
    # açılmaz, atanmış öğenin ikinci çıktısı üretilmez.
    _, plan, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    _assign(session, layout, queued.id)
    state = _state(session, layout)

    (item,) = read_plan(plan).items
    routed = route_queue_item(session, layout, plan, item)

    assert not routed.applied and routed.queue_item is queued
    assert _state(session, layout) == state


# --- 09.1.1: atamadan sonra çalışanın profili yeniden üretilir --------------------------------


def test_assignment_regenerates_the_assigned_employees_profile(
    session: Session, layout: DataLayout
) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    profile = layout.profile_path(TARGET_FOLDER)
    profile.write_text("bayat profil", encoding="utf-8")  # baştan üretilir
    bystander = Employee(id="E0043", folder_name="Baska_Kisi_E0043", given_names="B", surname="K")
    session.add(bystander)
    session.flush()
    layout.ensure_employee_tree(bystander.folder_name)

    _assign(session, layout, queued.id)

    text = profile.read_text(encoding="utf-8")
    assert text == render_profile(session, session.get_one(Employee, TARGET))
    assert f"employee_id: {TARGET}\n" in text
    assert "| Work Permit | Kayitli_Kisi-Work-Permit.pdf | active |" in text
    # Yalnız çıktının sahibi yeniden üretilir; geçici dosya kalmaz.
    assert not layout.profile_path(bystander.folder_name).exists()
    assert sorted(path.name for path in layout.employee_dir(TARGET_FOLDER).iterdir()) == [
        "Alinan",
        "Hazir",
        "profil.md",
    ]


def test_refused_assignment_does_not_write_the_profile(
    session: Session, layout: DataLayout
) -> None:
    text = (RECORDINGS / "s14_peruvian_diploma" / "0.json").read_text(encoding="utf-8")
    _, _, (queued,) = _queued(session, layout, _pdf(json.loads(text)))

    with pytest.raises(QueueItemNotAssignableError):
        _assign(session, layout, queued.id)

    assert not layout.profile_path(TARGET_FOLDER).exists()


# --- insan kararı aşamaz: tür ve fiziksel kurallar ------------------------------------------


def test_unknown_type_item_cannot_be_assigned(session: Session, layout: DataLayout) -> None:
    # S14: türü katalogda olmayan belgeden K8 adı ve işlem seçilemez.
    text = (RECORDINGS / "s14_peruvian_diploma" / "0.json").read_text(encoding="utf-8")
    _, _, (queued,) = _queued(session, layout, _pdf(json.loads(text)))
    assert queued.kind == "unknown"
    state = _state(session, layout)

    with pytest.raises(QueueItemNotAssignableError, match="belge türü belirlenmedi"):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state


def test_s6_direct_document_in_an_unexpected_format_is_not_converted_by_assignment(
    session: Session, layout: DataLayout
) -> None:
    # K3 / §20.4.1: katalog pasaportu yalnız PDF bekler, JPEG geldi; atama da dönüştürmez.
    catalog = _catalog_with(PASSPORT, expected_file_types=["pdf"])
    _, _, (queued,) = _queued(session, layout, _image(_passport()), catalog=catalog)
    state = _state(session, layout)

    with pytest.raises(QueueItemNotAssignableError) as refused:
        _assign(session, layout, queued.id)

    assert "Direkt Belge: beklenen dosya türü pdf, gelen jpeg." in str(refused.value)
    assert "Uygun formatta yeniden gönderin." in str(refused.value)
    assert _state(session, layout) == state


def test_item_without_an_applicable_operation_is_not_assigned(
    session: Session, layout: DataLayout
) -> None:
    # D15: PNG profil fotoğrafı §20.3'te hiçbir işleme uymuyor (satır 7); atama işlem uydurmaz.
    _, _, (queued,) = _queued(session, layout, _image(_photo(), "PNG"))
    state = _state(session, layout)

    with pytest.raises(QueueItemNotAssignableError, match=r"İşlem seçilemedi \(06\.2\.1\)"):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state


def test_source_in_an_unrecognized_format_is_not_assigned(
    session: Session, layout: DataLayout
) -> None:
    # Biçim içerikten okunur (01.2.1); tanınmayan biçim türün beklediği biçim değildir.
    _, _, (queued,) = _queued(
        session, layout, _File(pages=(_page(PERMIT),), content=b"tanimsiz icerik")
    )
    state = _state(session, layout)

    with pytest.raises(QueueItemNotAssignableError, match="gelen tanınmayan biçim"):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {"direct": True, "allowed_conversions": []},
            "Direkt Belge: wrap_image bu tür için yapılamaz.",
        ),
        ({"allowed_conversions": ["merge"]}, "Dönüşüm izni yok (06.4.1): wrap_image"),
    ],
    ids=["direct-document", "conversion-not-allowed"],
)
def test_catalog_changed_after_planning_is_applied_to_the_assignment(
    session: Session, layout: DataLayout, changes: dict[str, Any], reason: str
) -> None:
    # Planlamada `wrap_image` izinliydi; atama güncel katalogla seçer — Direkt Belge matrisi
    # (06.3.1) ve dönüşüm izni (06.4.1) insan kararıyla aşılmaz (K3, K12).
    _, _, (queued,) = _queued(session, layout, _image(_page(PERMIT, illegible=("surname",))))
    import_catalog(session, _catalog_with(PERMIT, **changes))
    state = _state(session, layout)

    with pytest.raises(QueueItemNotAssignableError) as refused:
        _assign(session, layout, queued.id)

    assert reason in str(refused.value)
    assert _state(session, layout) == state


def test_type_missing_from_the_catalog_is_not_assigned(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    catalog = Catalog(tuple(entry for entry in CATALOG if entry.slug != PERMIT))
    monkeypatch.setattr("app.pipeline.route.export_catalog", lambda _session: catalog)
    state = _state(session, layout)

    with pytest.raises(QueueItemNotAssignableError, match="belge türü katalogda yok"):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state


def test_operation_failure_is_refused_and_writes_nothing(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # İşlem belgeyi üretemezse (§20.5 doğrulaması) atama yapılmaz; belge tahmin edilmez.
    _, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    state = _state(session, layout)

    def _fail(*args: object, **kwargs: object) -> object:
        raise ExtractSourceError("extract kaynağı PDF değil")

    monkeypatch.setattr(execute_module, "_ready_output", _fail)

    with pytest.raises(QueueItemNotAssignableError, match="extract kaynağı PDF değil"):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state


def test_changed_inbox_original_is_refused(session: Session, layout: DataLayout) -> None:
    # K10: Inbox'taki orijinal yüklemedeki SHA-256'yı taşımıyorsa hiçbir şey yazılmaz.
    upload, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    (upload_file,) = upload.files
    layout.resolve(upload_file.stored_path).write_bytes(b"degistirildi")
    state = _state(session, layout)

    with pytest.raises(QueueSourceIntegrityError):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state


# --- çözülmüş, eski sürüm ve bozuk kayıt ----------------------------------------------------


def test_resolved_item_is_not_assigned_again(session: Session, layout: DataLayout) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    _assign(session, layout, queued.id)
    state = _state(session, layout)

    with pytest.raises(QueueItemResolvedError, match="zaten çözülmüş"):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state
    assert _count(session, Document) == 1


def test_item_whose_output_already_exists_is_not_assigned(
    session: Session, layout: DataLayout
) -> None:
    # Savunma: öğenin bu planla çıktısı varsa (07.8.1) ikinci çıktı ya da başka sahip yazılmaz.
    _, plan, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    (item,) = read_plan(plan).items
    session.add(
        Document(
            employee_id=TARGET,
            type_slug=PERMIT,
            path="Employees/Kayitli_Kisi_E0042/Hazir/eski.pdf",
            format="pdf",
            plan_id=plan.id,
            source_refs_json=[source.model_dump(mode="json") for source in item.sources],
        )
    )
    session.flush()
    state = _state(session, layout)

    with pytest.raises(QueueItemResolvedError, match="çıktısı zaten üretilmiş"):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state


def test_item_of_an_older_plan_version_is_not_assigned(
    session: Session, layout: DataLayout
) -> None:
    # K18: yeni sürüm açıldıysa eski sürümün kuyruk kaydı atanmaz; güncel planınki atanır.
    upload, _, (old,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    newer = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
    (item,) = read_plan(newer).items
    current = route_queue_item(session, layout, newer, item).queue_item
    state = _state(session, layout)

    with pytest.raises(QueueItemSupersededError, match="eski sürüm"):
        _assign(session, layout, old.id)

    assert _state(session, layout) == state
    assigned = _assign(session, layout, current.id)
    assert assigned.executed.document.plan_id == newer.id


def test_item_without_a_plan_is_not_assigned(session: Session, layout: DataLayout) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    queued.plan_id = None
    session.flush()

    with pytest.raises(QueueItemSupersededError):
        _assign(session, layout, queued.id)


@pytest.mark.parametrize(
    ("plan_item_id", "kind"),
    [("i99", "unreadable"), ("i1", "unresolved")],
    ids=["missing-item", "other-queue"],
)
def test_queue_row_not_matching_its_plan_item_is_not_assigned(
    session: Session, layout: DataLayout, plan_item_id: str, kind: str
) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    queued.plan_item_id, queued.kind = plan_item_id, kind
    session.flush()
    state = _state(session, layout)

    with pytest.raises(QueueItemNotAssignableError, match="kuyruk öğesini göstermiyor"):
        _assign(session, layout, queued.id)

    assert _state(session, layout) == state


def test_changed_plan_is_not_executed(session: Session, layout: DataLayout) -> None:
    # K9: dondurulduktan sonra değişmiş plan yürütülmez.
    _, plan, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    changed = copy.deepcopy(plan.json)
    changed["items"][0]["route_reason"] = "Değiştirildi."
    plan.json = changed
    session.flush()

    with pytest.raises(PlanIntegrityError):
        _assign(session, layout, queued.id)

    assert _count(session, Document) == 0


# --- istek hataları ---------------------------------------------------------------------------


def test_unknown_queue_item_and_employee_are_reported(session: Session, layout: DataLayout) -> None:
    _, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    state = _state(session, layout)

    with pytest.raises(QueueItemNotFoundError):
        _assign(session, layout, queued.id + 100)
    with pytest.raises(AssigneeNotFoundError):
        _assign(session, layout, queued.id, "E9999")

    assert _state(session, layout) == state


@pytest.mark.parametrize("actor", ["", "   "])
def test_manual_assignment_needs_the_user_name(
    session: Session, layout: DataLayout, actor: str
) -> None:
    # K16: manuel işlem kullanıcı adıyla loglanır.
    _, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))

    with pytest.raises(ValueError, match="K16"):
        _assign(session, layout, queued.id, actor=actor)

    assert queued.resolved_at is None
    assert _count(session, Document) == 0


def test_assignment_leaves_the_transaction_to_the_caller(
    session: Session, layout: DataLayout
) -> None:
    upload, _, (queued,) = _queued(session, layout, _pdf(_page(PERMIT, illegible=("surname",))))
    session.commit()

    _assign(session, layout, queued.id)
    session.rollback()

    assert session.get_one(QueueItem, queued.id).resolved_at is None
    assert _count(session, Document) == 0
    assert _events(session, EventType.MANUAL_ASSIGN) == []
    assert (
        session.scalar(
            select(func.count()).select_from(QueueItem).where(QueueItem.upload_id == upload.id)
        )
        == 1
    )
