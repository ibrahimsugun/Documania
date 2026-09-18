"""Kuyruğa yönlendirme ve gerekçe dosyası (§8.2, §8.3; K9, K10, K15).

08.1.1 — Unknown/Unreadable/Unresolved klasörüne kaynak kopyası ve gerekçe dosyası yazılır.
08.1.2 — Gerekçe hangi sayfalar, hangi kural, hangi tür ve kişi tahmini olduğunu içerir.

Elle kurulan planla hata, kopya, tekillik ve idempotenlik testleri; gerçek planlayıcıdan (06.1)
geçen bir test bilinmeyen tür rotasının uçtan uca çalıştığını doğrular (S14).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Plan, QueueItem, Upload, UploadFile, UploadStatus
from app.events import EventType
from app.matching.match import EmployeeAction, MatchedBy
from app.pipeline.plan import PlanDocument, PlanEmployee, PlanItem, Route, create_plan, read_plan
from app.pipeline.route import (
    QueueItemReferenceError,
    QueueSourceIntegrityError,
    RoutedItem,
    route_queue_item,
)
from app.pipeline.validate import ValidationName
from app.storage import DataLayout, sha256_file, write_to_inbox
from tests.fixtures.gen import make_pdf_bytes
from tests.pipeline.test_execute import _files
from tests.pipeline.test_plan import (
    CATALOG,
    MODEL,
    RECORDINGS,
    _assert_no_personal_values,
    _events,
    _pdf,
)
from tests.pipeline.test_plan import _upload as _upload_with_analyses

UPLOAD_ID = "u_20260918_0001"
NOBODY = PlanEmployee(action=EmployeeAction.NONE, employee_id=None, matched_by=None)
GUESS = PlanEmployee(
    action=EmployeeAction.MATCH, employee_id="E0007", matched_by=MatchedBy.NAME_DOB
)


def _manual_upload(session: Session, layout: DataLayout, *names: str) -> list[UploadFile]:
    upload = Upload(id=UPLOAD_ID, channel="web", status=UploadStatus.PLANNING.value)
    session.add(upload)
    rows: list[UploadFile] = []
    for index, name in enumerate(names):
        # Sayfa sayısı dosya başına değişir: aynı ada sahip olmayan dosyalar aynı içerikte olursa
        # hash tekilliği (K10 tarzı dedup) onları kasıtsız birleştirir.
        stored = write_to_inbox(layout, UPLOAD_ID, name, make_pdf_bytes(page_count=2 + index))
        row = UploadFile(
            upload=upload,
            original_name=name,
            stored_path=layout.relative(stored.path),
            sha256=stored.sha256,
            mime="application/pdf",
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _manual_plan(session: Session, *items: PlanItem, upload_id: str = UPLOAD_ID) -> Plan:
    document = PlanDocument(upload_id=upload_id, version=1, model=MODEL, items=items)
    plan = Plan(
        upload_id=upload_id,
        version=1,
        json=document.model_dump(mode="json"),
        model=MODEL,
        plan_hash=document.plan_hash,
    )
    session.add(plan)
    session.flush()
    return plan


def _queued_item(
    item_id: str,
    sources: list[tuple[int, tuple[int, ...]]],
    *,
    route: Route,
    reason: str,
    slug: str | None = None,
    employee: PlanEmployee = NOBODY,
) -> PlanItem:
    return PlanItem.model_validate(
        {
            "item_id": item_id,
            "document_type_slug": slug,
            "sources": [{"file_id": file_id, "pages": list(pages)} for file_id, pages in sources],
            "operation": None,
            "target_format": None,
            "target_name": None,
            "employee": employee.model_dump(mode="json"),
            "route": route.value,
            "route_reason": reason,
            "validations": [],
        }
    )


def _reason_json(layout: DataLayout, kind: str, upload_id: str = UPLOAD_ID) -> dict:
    return json.loads(layout.queue_reason_path(kind, upload_id).read_text(encoding="utf-8"))


def _source_files(directory: Path) -> list[str]:
    # `reason.json` aynı klasörde durur (`queue_reason_path`); kaynak kopyalarını ayrı sayar.
    return sorted(name for name in _files(directory) if name != "reason.json")


# --- 08.1.1 — kaynak kopyası ve kuyruk kaydı -----------------------------------------------


def test_unresolved_item_copies_source_and_writes_queue_row(
    session: Session, layout: DataLayout
) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    item = _queued_item(
        "i1",
        [(file.id, (0, 1))],
        route=Route.UNRESOLVED,
        reason="Ardışıklık ihlali (K5): dosya 1, sayfa 1, 2 arasına başka belge girmiş.",
        slug="work_permit",
        employee=GUESS,
    )
    plan = _manual_plan(session, item)

    routed = route_queue_item(session, layout, plan, item)

    assert isinstance(routed, RoutedItem) and routed.applied
    queue_dir = layout.queue_dir("unresolved", UPLOAD_ID)
    assert _source_files(queue_dir) == ["belge.pdf"]
    source = layout.resolve(file.stored_path)
    assert (queue_dir / "belge.pdf").read_bytes() == source.read_bytes()

    row = routed.queue_item
    assert session.get(QueueItem, row.id) is row
    assert (row.upload_id, row.plan_id, row.plan_item_id, row.kind, row.reason) == (
        UPLOAD_ID,
        plan.id,
        "i1",
        "unresolved",
        item.route_reason,
    )
    assert row.payload_json == {
        "document_type_slug": "work_permit",
        "sources": [{"file_id": file.id, "pages": [0, 1]}],
        "employee_guess": {"action": "match", "employee_id": "E0007", "matched_by": "name_dob"},
    }
    assert (row.resolved_at, row.resolved_by) == (None, None)


def test_unknown_item_has_null_type_and_nobody_guess(session: Session, layout: DataLayout) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    item = _queued_item(
        "i1",
        [(file.id, (0,))],
        route=Route.UNKNOWN,
        reason='Bilinmeyen belge türü (04.6.1): önerilen aday tür: "Diploma".',
        slug=None,
        employee=NOBODY,
    )
    plan = _manual_plan(session, item)

    routed = route_queue_item(session, layout, plan, item)

    assert routed.queue_item.payload_json == {
        "document_type_slug": None,
        "sources": [{"file_id": file.id, "pages": [0]}],
        "employee_guess": {"action": "none", "employee_id": None, "matched_by": None},
    }
    assert _source_files(layout.queue_dir("unknown", UPLOAD_ID)) == ["belge.pdf"]


def test_unreadable_item_writes_queued_unreadable_event(
    session: Session, layout: DataLayout
) -> None:
    (file,) = _manual_upload(session, layout, "pasaport.pdf")
    item = _queued_item(
        "i1",
        [(file.id, (0,))],
        route=Route.UNREADABLE,
        reason="Zorunlu alan okunamadı (K1): surname.",
        slug="russian_passport",
        employee=GUESS,
    )
    plan = _manual_plan(session, item)
    before = len(_events(session))

    routed = route_queue_item(session, layout, plan, item)

    (event,) = _events(session)[before:]
    assert (
        event.type,
        event.upload_id,
        event.file_id,
        event.page_index,
        event.message,
    ) == (EventType.QUEUED_UNREADABLE, UPLOAD_ID, file.id, 0, item.route_reason)
    assert event.data_json == {
        "item_id": "i1",
        "plan_id": plan.id,
        "queue_item_id": routed.queue_item.id,
        **routed.queue_item.payload_json,
    }
    _assert_no_personal_values(session)


def test_first_source_without_pages_gives_null_page_index(
    session: Session, layout: DataLayout
) -> None:
    # Word/Excel eki ya da bütün dosya alan öğe: `pages: []`, olayın `page_index`'i boş kalır.
    (file,) = _manual_upload(session, layout, "ek.docx")
    item = _queued_item(
        "i1",
        [(file.id, ())],
        route=Route.UNRESOLVED,
        reason="İşlenemeyen dosya: sayfası üretilmemiş.",
    )
    plan = _manual_plan(session, item)

    route_queue_item(session, layout, plan, item)

    (event,) = _events(session)
    assert event.page_index is None


# --- 08.1.2 — gerekçe dosyasının içeriği -----------------------------------------------------


def test_reason_file_contains_pages_rule_type_and_person_guess(
    session: Session, layout: DataLayout
) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    reason = "Direkt Belge: beklenen dosya türü pdf, gelen jpeg. Uygun formatta yeniden gönderin."
    item = _queued_item(
        "i1",
        [(file.id, (2, 3))],
        route=Route.UNRESOLVED,
        reason=reason,
        slug="serbian_driving_license",
        employee=GUESS,
    )
    plan = _manual_plan(session, item)

    route_queue_item(session, layout, plan, item)

    content = _reason_json(layout, "unresolved")
    assert content["upload_id"] == UPLOAD_ID
    assert content["kind"] == "unresolved"
    (entry,) = content["items"]
    assert entry["reason"] == reason  # hangi kural
    assert entry["sources"] == [{"file_id": file.id, "pages": [2, 3]}]  # hangi sayfalar
    assert entry["document_type_slug"] == "serbian_driving_license"  # hangi tür
    assert entry["employee_guess"]["employee_id"] == "E0007"  # kişi tahmini
    assert (entry["plan_id"], entry["plan_item_id"]) == (plan.id, "i1")


def test_reason_file_aggregates_every_item_of_the_same_kind_and_upload(
    session: Session, layout: DataLayout
) -> None:
    file_a, file_b = _manual_upload(session, layout, "a.pdf", "b.pdf")
    item_a = _queued_item("i1", [(file_a.id, (0,))], route=Route.UNRESOLVED, reason="A gerekçesi")
    item_b = _queued_item("i2", [(file_b.id, (0,))], route=Route.UNRESOLVED, reason="B gerekçesi")
    plan = _manual_plan(session, item_a, item_b)

    route_queue_item(session, layout, plan, item_a)
    route_queue_item(session, layout, plan, item_b)

    content = _reason_json(layout, "unresolved")
    assert [entry["plan_item_id"] for entry in content["items"]] == ["i1", "i2"]
    assert _source_files(layout.queue_dir("unresolved", UPLOAD_ID)) == ["a.pdf", "b.pdf"]


def test_different_kinds_of_the_same_upload_get_separate_reason_files(
    session: Session, layout: DataLayout
) -> None:
    file_a, file_b = _manual_upload(session, layout, "a.pdf", "b.pdf")
    unknown = _queued_item("i1", [(file_a.id, (0,))], route=Route.UNKNOWN, reason="Bilinmeyen tür")
    unreadable = _queued_item(
        "i2", [(file_b.id, (0,))], route=Route.UNREADABLE, reason="Okunamıyor"
    )
    plan = _manual_plan(session, unknown, unreadable)

    route_queue_item(session, layout, plan, unknown)
    route_queue_item(session, layout, plan, unreadable)

    assert len(_reason_json(layout, "unknown")["items"]) == 1
    assert len(_reason_json(layout, "unreadable")["items"]) == 1


# --- kaynak kopyasının tekilliği ------------------------------------------------------------


def test_same_source_file_across_two_items_is_copied_once(
    session: Session, layout: DataLayout
) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    item_a = _queued_item("i1", [(file.id, (0,))], route=Route.UNRESOLVED, reason="A gerekçesi")
    item_b = _queued_item("i2", [(file.id, (1,))], route=Route.UNRESOLVED, reason="B gerekçesi")
    plan = _manual_plan(session, item_a, item_b)

    route_queue_item(session, layout, plan, item_a)
    route_queue_item(session, layout, plan, item_b)

    assert _source_files(layout.queue_dir("unresolved", UPLOAD_ID)) == ["belge.pdf"]


# --- idempotenlik (06.6.1) -------------------------------------------------------------------


def test_second_call_for_the_same_plan_item_is_idempotent(
    session: Session, layout: DataLayout
) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    item = _queued_item("i1", [(file.id, (0,))], route=Route.UNRESOLVED, reason="Gerekçe")
    plan = _manual_plan(session, item)

    first = route_queue_item(session, layout, plan, item)
    second = route_queue_item(session, layout, plan, item)

    assert first.applied and not second.applied
    assert first.queue_item.id == second.queue_item.id
    assert session.scalar(select(func.count()).select_from(QueueItem)) == 1
    assert _source_files(layout.queue_dir("unresolved", UPLOAD_ID)) == ["belge.pdf"]
    assert len(_events(session)) == 1  # ikinci çağrı olay yazmadı


# --- hatalar ----------------------------------------------------------------------------------


def test_ready_route_is_rejected(session: Session, layout: DataLayout) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    item = PlanItem.model_validate(
        {
            "item_id": "i1",
            "document_type_slug": "work_permit",
            "sources": [{"file_id": file.id, "pages": [0]}],
            "operation": "passthrough",
            "target_format": "pdf",
            "target_name": "Test_Ornekova-Work-Permit.pdf",
            "employee": {"action": "match", "employee_id": "E0007", "matched_by": "name_dob"},
            "route": "hazir",
            "route_reason": None,
            "validations": [{"name": name.value, "ok": True} for name in ValidationName],
        }
    )
    plan = _manual_plan(session, item)

    with pytest.raises(ValueError):
        route_queue_item(session, layout, plan, item)

    assert _events(session) == []


def test_skip_route_is_rejected(session: Session, layout: DataLayout) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    item = _queued_item("i1", [(file.id, ())], route=Route.SKIP, reason="Boş sayfa: atlanır.")
    plan = _manual_plan(session, item)

    with pytest.raises(ValueError):
        route_queue_item(session, layout, plan, item)

    assert _events(session) == []


def test_missing_source_file_raises_reference_error(session: Session, layout: DataLayout) -> None:
    _manual_upload(session, layout, "belge.pdf")
    item = _queued_item("i1", [(9999, (0,))], route=Route.UNRESOLVED, reason="Gerekçe")
    plan = _manual_plan(session, item)

    with pytest.raises(QueueItemReferenceError):
        route_queue_item(session, layout, plan, item)

    assert not layout.queue_dir("unresolved", UPLOAD_ID).exists()
    assert _events(session) == []


def test_source_from_another_upload_raises_reference_error(
    session: Session, layout: DataLayout
) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    other_upload = Upload(id="u_other", channel="web", status=UploadStatus.PLANNING.value)
    session.add(other_upload)
    session.flush()
    item = _queued_item("i1", [(file.id, (0,))], route=Route.UNRESOLVED, reason="Gerekçe")
    plan = _manual_plan(session, item, upload_id="u_other")

    with pytest.raises(QueueItemReferenceError):
        route_queue_item(session, layout, plan, item)


def test_source_hash_mismatch_raises_integrity_error(session: Session, layout: DataLayout) -> None:
    (file,) = _manual_upload(session, layout, "belge.pdf")
    layout.resolve(file.stored_path).write_bytes(b"degistirildi")
    item = _queued_item("i1", [(file.id, (0,))], route=Route.UNRESOLVED, reason="Gerekçe")
    plan = _manual_plan(session, item)

    with pytest.raises(QueueSourceIntegrityError):
        route_queue_item(session, layout, plan, item)

    assert not layout.queue_dir("unresolved", UPLOAD_ID).exists()
    assert _events(session) == []


# --- uçtan uca: gerçek planlayıcı (S14, 04.6.1) -----------------------------------------------


def test_unknown_type_item_from_create_plan_is_queued_end_to_end(
    session: Session, layout: DataLayout
) -> None:
    text = (RECORDINGS / "s14_peruvian_diploma" / "0.json").read_text(encoding="utf-8")
    upload = _upload_with_analyses(session, layout, _pdf(json.loads(text)))
    plan = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
    (item,) = read_plan(plan).items
    assert item.route is Route.UNKNOWN

    routed = route_queue_item(session, layout, plan, item)

    assert routed.applied
    (upload_file,) = upload.files
    queue_dir = layout.queue_dir("unknown", upload.id)
    assert _source_files(queue_dir) == [upload_file.original_name]
    assert sha256_file(queue_dir / upload_file.original_name) == upload_file.sha256
    content = _reason_json(layout, "unknown", upload_id=upload.id)
    (entry,) = content["items"]
    assert entry["document_type_slug"] is None
    assert entry["reason"] == item.route_reason
    _assert_no_personal_values(session)
