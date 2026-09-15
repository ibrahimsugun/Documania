"""Plan JSON üretimi, belirleyicilik, işlem seçimi ve Direkt Belge kuralı — PRD 06.1.1, 06.1.2,
06.2.1, 06.3.1, 06.3.2 (§8.5, §20.3, §20.4; K3, K9, R5, R10, R7).

Sayfa analizleri kayıtlı yanıt biçimindeki sentetik sözlüklerdir, dosyalar `tests/fixtures/gen.py`
ile üretilir (CONVENTIONS §6). Plan üretimi sayfaları veritabanından okur; render ve analiz adımları
yalnız S4 entegrasyon testinde, gömülü görüntü tespiti (02.5.1) işlem seçimi testinde gerçek hâliyle
çalışır.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import build_page_analysis_instructions
from app.ai.recording_provider import RecordingProvider
from app.catalog import (
    Catalog,
    CatalogEntry,
    FileType,
    OutputFormat,
    load_seed_catalog,
    validate_catalog,
)
from app.config import Settings
from app.db.models import (
    Base,
    CandidateDocumentType,
    Employee,
    EmployeeAlias,
    EmployeeContact,
    EmployeeIdentifier,
    Event,
    Page,
    Plan,
    QueueKind,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType
from app.matching.match import (
    NAME_ONLY_REASON,
    NO_PERSON_REASON,
    PENDING_PROFILE_REASON,
    EmployeeAction,
    MatchedBy,
    normalize_document_number,
)
from app.matching.mrz import MrzFormat
from app.matching.names import normalize_name
from app.pipeline.analyze import analyze_upload
from app.pipeline.group import AttachmentWithoutContext
from app.pipeline.plan import (
    DIRECT_OPERATIONS,
    DirectFileTypeMismatch,
    DirectOperationForbidden,
    NoApplicableOperation,
    Operation,
    OperationSource,
    PlanDocument,
    PlanEmployee,
    PlanIntegrityError,
    PlanItem,
    PlanSource,
    Route,
    SelectedOperation,
    check_direct_file_types,
    check_direct_operation,
    create_plan,
    read_plan,
    select_operation,
)
from app.pipeline.render import (
    extract_upload_file_text,
    mark_upload_file_blank_pages,
    mark_upload_file_single_image_pages,
    render_upload_file,
)
from app.storage import DataLayout, FileKind, prepare_data_dir, write_to_inbox
from tests.fixtures.gen import (
    A4,
    make_docx_bytes,
    make_half_filled_image_bytes,
    make_pdf_bytes,
    make_text_pdf_bytes,
)
from tests.matching.test_mrz import make_mrz

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()
UPLOAD_ID = "u_20260915_0001"
MODEL = "claude-opus-5"

PASSPORT = "russian_passport"  # direct, keep, 1 sayfa, iki kabul kriteri
PERMIT = "work_permit"  # single, pdf, 1–2 sayfa, doğum tarihi zorunlu değil
RESIDENCE = "serbian_residence_card"  # front_back, pdf
LICENSE = "serbian_driving_license"  # front_back, pdf
PHOTO = "profile_picture"  # zorunlu alan yok

SURNAME, GIVEN, BORN, NUMBER = "ORNEKOVA", "TEST", "1990-01-01", "00 0000001"
PHONE = "+000 00 000 0000"
PERSONAL_VALUES = (
    SURNAME,
    "Ornekova",
    "ornekova",
    "Орнекова",
    "0000001",
    BORN,
    "AB1234567",
    "WP-0000042",
    PHONE,
    "PRUEBA",
    "SIDOROV",
    "IVAN",
    "1985-05-05",
    "000123456",
)

BLANK = "blank"  # 02.4.1 boş sayfa: analize gönderilmedi
FAILED = "failed"  # analizi başarısız sayfa
NO_PERSON: dict[str, Any] = {
    "surname": None,
    "given_names": None,
    "other_names": None,
    "original_script_name": None,
    "date_of_birth": None,
    "nationality": None,
    "document_number": None,
    "mrz_lines": None,
    "contact": {"phone": None, "email": None, "address": None},
}
NOBODY = PlanEmployee(action=EmployeeAction.NONE, employee_id=None, matched_by=None)
UNMET_MRZ = "MRZ iki satırı da okunabilir olmalı"


def _person(**changes: Any) -> dict[str, Any]:
    person = copy.deepcopy(NO_PERSON)
    person.update(
        surname=SURNAME,
        given_names=GIVEN,
        date_of_birth=BORN,
        nationality="RUS",
        document_number=NUMBER,
    )
    person.update(changes)
    return person


def _page(
    slug: str | None,
    *,
    side: str = "single",
    continues: bool = False,
    person: dict[str, Any] | None = None,
    illegible: tuple[str, ...] = (),
    **top: Any,
) -> dict[str, Any]:
    """Sentetik §8.4 yanıtı; türün zorunlu alanları `illegible` dışında kişiden okunaklı yazılır."""
    person = _person() if person is None else person
    entry = CATALOG.get(slug) if slug is not None else None
    fields: dict[str, Any] = {}
    for name in () if entry is None else entry.required_fields:
        value = person.get(name) or "2030-01-01"
        fields[name] = (
            {"value": None, "legible": False}
            if name in illegible
            else {"value": str(value), "legible": True}
        )
    payload: dict[str, Any] = {
        "page_index": 0,
        "is_blank": False,
        "is_readable": True,
        "language": "en",
        "script": "latin",
        "document_type_slug": slug,
        "candidate_type_name": None,
        "side": side,
        "continues_previous_page": continues,
        "person": person,
        "fields": fields,
        "notes": None,
    }
    payload.update(top)
    return payload


def _back(slug: str, *, continues: bool = True) -> dict[str, Any]:
    # Kartın arka yüzünde kişi yazmaz; zorunlu alanlar bu yüzde okunmaz.
    entry = CATALOG.get(slug)
    assert entry is not None
    return _page(
        slug,
        side="back",
        continues=continues,
        person=copy.deepcopy(NO_PERSON),
        illegible=entry.required_fields,
    )


def _photo() -> dict[str, Any]:
    return _page(PHOTO, person=copy.deepcopy(NO_PERSON))


def _passport(**top: Any) -> dict[str, Any]:
    """Kayıtlı pasaport yanıtı (MRZ haneleri geçerli, temiz numara)."""
    text = (RECORDINGS / "russian_passport" / "0.json").read_text(encoding="utf-8")
    payload: dict[str, Any] = json.loads(text)
    payload.update(top)
    return payload


def _illegible_expiry(payload: dict[str, Any]) -> dict[str, Any]:
    # MRZ görünen okuması olmayan alanı doldurur (05.3.3); okunmayan alan için MRZ de yok.
    payload["person"]["mrz_lines"] = None
    payload["fields"]["expiry_date"] = {"value": None, "legible": False}
    return payload


@dataclass(frozen=True)
class _File:
    pages: tuple[dict[str, Any] | str, ...] = ()
    content: bytes = field(default_factory=make_pdf_bytes)
    duplicate_of: int | None = None  # partideki sırası


def _pdf(*pages: dict[str, Any] | str) -> _File:
    return _File(pages=pages, content=make_pdf_bytes(len(pages)))


def _image(page: dict[str, Any], fmt: str = "JPEG") -> _File:
    return _File(pages=(page,), content=make_half_filled_image_bytes(fmt))


def _upload(
    session: Session,
    layout: DataLayout,
    *files: _File,
    context_employee_id: str | None = None,
    created_at: datetime | None = None,
    reorder_keys: bool = False,
) -> Upload:
    """Partiyi Inbox'a yazar ve sayfaları saklanmış analizleriyle açar (render/analiz yok)."""
    upload = Upload(
        id=UPLOAD_ID,
        channel="web",
        status=UploadStatus.PLANNING.value,
        context_employee_id=context_employee_id,
        created_at=created_at,
    )
    session.add(upload)
    rows: list[UploadFile] = []
    for number, spec in enumerate(files):
        stored = write_to_inbox(layout, UPLOAD_ID, f"dosya-{number}", spec.content)
        row = UploadFile(
            upload=upload,
            original_name=f"dosya-{number}",
            stored_path=stored.path.relative_to(layout.root).as_posix(),
            sha256=stored.sha256,
            mime="application/octet-stream",
            is_duplicate_of=None if spec.duplicate_of is None else rows[spec.duplicate_of].id,
        )
        session.add(row)
        session.flush()
        rows.append(row)
        for index, page in enumerate(spec.pages):
            if page == BLANK:
                session.add(Page(file=row, index=index, is_blank=True, analysis_status="skipped"))
            elif page == FAILED:
                session.add(Page(file=row, index=index, analysis_status="failed"))
            else:
                assert isinstance(page, dict)
                analysis = {**page, "page_index": index}
                session.add(
                    Page(
                        file=row,
                        index=index,
                        analysis_json=_reordered(analysis) if reorder_keys else analysis,
                        analysis_status="done",
                    )
                )
    session.flush()
    return upload


def _reordered(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _reordered(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reordered(item) for item in value]
    return value


def _employee(
    session: Session,
    employee_id: str = "E0007",
    *,
    born: date | None = date(1990, 1, 1),
    names: tuple[str, ...] = ("Test Ornekova",),
    numbers: tuple[str, ...] = (),
) -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"Kayitli_Kisi_{employee_id}",
        given_names="Kayitli",
        surname="Kisi",
        date_of_birth=born,
    )
    session.add(employee)
    for raw in names:
        session.add(
            EmployeeAlias(employee=employee, raw_name=raw, normalized_name=normalize_name(raw))
        )
    for number in numbers:
        session.add(
            EmployeeIdentifier(
                employee=employee, kind=PASSPORT, value=normalize_document_number(number)
            )
        )
    session.flush()
    return employee


def _plan(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    *,
    catalog: Catalog = CATALOG,
    **kwargs: Any,
) -> PlanDocument:
    return read_plan(create_plan(session, layout, upload, catalog=catalog, model=MODEL, **kwargs))


def _item(
    item_id: str,
    sources: list[tuple[int, tuple[int, ...]]],
    *,
    slug: str | None = None,
    employee: PlanEmployee = NOBODY,
    route: Route = Route.UNRESOLVED,
    reason: str | None = None,
    operation: Operation | None = None,
    target: tuple[str | None, str | None] = (None, None),
) -> PlanItem:
    target_format, target_name = target
    return PlanItem.model_validate(
        {
            "item_id": item_id,
            "document_type_slug": slug,
            "sources": [{"file_id": file_id, "pages": pages} for file_id, pages in sources],
            "operation": operation,
            "target_format": target_format,
            "target_name": target_name,
            "employee": employee.model_dump(mode="json"),
            "route": route,
            "route_reason": reason,
            "validations": [],
        }
    )


def _created(employee_id: str = "E0001") -> PlanEmployee:
    return PlanEmployee(action=EmployeeAction.CREATE, employee_id=employee_id, matched_by=None)


def _matched(
    employee_id: str = "E0007", by: MatchedBy | None = MatchedBy.DOCUMENT_NUMBER
) -> PlanEmployee:
    return PlanEmployee(action=EmployeeAction.MATCH, employee_id=employee_id, matched_by=by)


def _file_ids(upload: Upload) -> list[int]:
    return [upload_file.id for upload_file in upload.files]


def _count(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _events(session: Session, event_type: EventType | None = None) -> list[Event]:
    query = select(Event).order_by(Event.id)
    if event_type is not None:
        query = query.where(Event.type == event_type)
    return list(session.scalars(query))


def _assert_no_personal_values(session: Session) -> None:
    logged = json.dumps(
        [[event.data_json, event.message] for event in _events(session)], ensure_ascii=False
    )
    for value in PERSONAL_VALUES:
        assert value not in logged


def _catalog_with(slug: str, **changes: Any) -> Catalog:
    entries = [entry.model_dump(mode="json") for entry in CATALOG]
    for entry in entries:
        if entry["slug"] == slug:
            entry.update(changes)
    return validate_catalog(entries)


# --- §8.5 sözleşmesi --------------------------------------------------------------------------


def _item_data(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "item_id": "i1",
        "document_type_slug": PASSPORT,
        "sources": [{"file_id": 1, "pages": [0]}],
        "operation": "passthrough",
        "target_format": "pdf",
        "target_name": "Test_Ornekova-Passport.pdf",
        "employee": {"action": "create", "employee_id": "E0001", "matched_by": None},
        "route": "hazir",
        "route_reason": None,
        "validations": [],
    }
    data.update(changes)
    return data


def _document_data(*items: dict[str, Any], **changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "upload_id": UPLOAD_ID,
        "version": 1,
        "model": MODEL,
        "items": list(items),
    }
    data.update(changes)
    return data


QUEUED = {
    "route": "unresolved",
    "route_reason": "Gerekçe.",
    "operation": None,
    "target_format": None,
}


def test_contract_value_sets_are_those_of_the_prd() -> None:
    assert {operation.value for operation in Operation} == {
        "passthrough",
        "extract",
        "merge",
        "wrap_image",
        "extract_image",
        "render_image",
    }
    assert {route.value for route in Route} == {
        "hazir",
        "unknown",
        "unreadable",
        "unresolved",
        "skip",
    }
    assert {action.value for action in EmployeeAction} == {"match", "create", "pending", "none"}


def test_prd_example_item_is_a_valid_plan_item() -> None:
    # §8.5 örneği birebir.
    item = PlanItem.model_validate(
        {
            "item_id": "i1",
            "document_type_slug": "serbian_residence_card",
            "sources": [{"file_id": 1, "pages": [3, 4]}],
            "operation": "extract",
            "target_format": "pdf",
            "target_name": "Ahmet_Cakar-Residence-Card.pdf",
            "employee": {
                "action": "match",
                "employee_id": "E0007",
                "matched_by": "document_number",
            },
            "route": "hazir",
            "route_reason": None,
            "validations": [{"name": "required_fields", "ok": True}],
        }
    )

    assert item.operation is Operation.EXTRACT
    assert item.employee == _matched()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"sources": []}, "at least 1 item"),
        ({"sources": [{"file_id": 1, "pages": [1, 0]}]}, "artan sırada"),
        ({"sources": [{"file_id": 1, "pages": [0, 0]}]}, "tekrarsız"),
        (
            {"sources": [{"file_id": 1, "pages": [0]}, {"file_id": 1, "pages": [1]}]},
            "bir kez geçer",
        ),
        ({"operation": "crop"}, "operation"),
        ({"item_id": "1"}, "item_id"),
        ({"unexpected": True}, "Extra inputs"),
        (
            {"employee": {"action": "none", "employee_id": "E0001", "matched_by": None}},
            "employee_id yalnız match ve create",
        ),
        (
            {"employee": {"action": "match", "employee_id": None, "matched_by": None}},
            "employee_id yalnız match ve create",
        ),
        (
            {
                "employee": {
                    "action": "create",
                    "employee_id": "E0001",
                    "matched_by": "document_number",
                }
            },
            "matched_by yalnız match",
        ),
        ({"route_reason": "Gerekçe."}, "hazir öğede route_reason boş"),
        (
            {
                "employee": {"action": "pending", "employee_id": None, "matched_by": None},
                "target_format": None,
                "target_name": None,
            },
            "hazir öğenin çalışanı olmalı",
        ),
        ({**QUEUED, "target_name": None, "route_reason": None}, "route_reason zorunlu"),
        (QUEUED, "hedef yalnız hazir öğede"),
        ({**QUEUED, "target_name": None, "operation": "extract"}, "operation yalnız hazir öğede"),
        ({"operation": None}, "hazir öğede operation zorunlu"),
        ({"target_format": None, "target_name": None}, "hazir öğede target_format ve target_name"),
        ({"target_name": None}, "hazir öğede target_format ve target_name"),
        ({"target_format": "jpeg"}, "uzantısı target_format"),
        ({"target_format": None}, "uzantısı target_format"),
        ({"target_name": "../Passport.pdf"}, "target_name"),
    ],
)
def test_invalid_item_is_rejected(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        PlanItem.model_validate(_item_data(**changes))


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([_item_data(), _item_data(sources=[{"file_id": 1, "pages": [1]}])], "item_id"),
        ([_item_data(), _item_data(item_id="i2")], "bir sayfa birden fazla öğeye"),
        (
            [_item_data(), _item_data(item_id="i2", sources=[{"file_id": 1, "pages": []}])],
            "bütün olarak alınan dosyanın",
        ),
        (
            [_item_data(sources=[{"file_id": 1, "pages": []}]), _item_data(item_id="i2")],
            "bütün olarak alınan dosyanın",
        ),
    ],
)
def test_overlapping_items_are_rejected(items: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        PlanDocument.model_validate(_document_data(*items))


@pytest.mark.parametrize(
    "changes", [{"version": 0}, {"upload_id": "../u1"}, {"model": ""}, {"items": None}]
)
def test_invalid_document_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PlanDocument.model_validate(_document_data(_item_data(), **changes))


def test_plan_hash_is_the_sha256_of_the_canonical_json() -> None:
    document = PlanDocument.model_validate(
        _document_data(
            _item_data(), _item_data(item_id="i2", sources=[{"file_id": 2, "pages": []}])
        )
    )
    expected = json.dumps(
        document.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    assert document.canonical_json() == expected
    assert b" " not in expected.replace(b"Test_Ornekova", b"")
    assert document.plan_hash == hashlib.sha256(expected).hexdigest()


def test_plan_hash_does_not_depend_on_key_order_but_on_every_value() -> None:
    data = _document_data(_item_data())
    document = PlanDocument.model_validate(data)

    assert PlanDocument.model_validate(_reordered(data)).plan_hash == document.plan_hash
    for changed in (
        _document_data(_item_data(), version=2),
        _document_data(_item_data(), model="claude-sonnet-5"),
        _document_data(_item_data(target_name="Test_Ornekova-Passport-X.pdf")),
        _document_data(_item_data(sources=[{"file_id": 1, "pages": [1]}])),
    ):
        assert PlanDocument.model_validate(changed).plan_hash != document.plan_hash


# --- 06.1.1 plan öğeleri ------------------------------------------------------------------------


def test_clean_passport_without_registered_employee_is_frozen_as_a_plan(
    session: Session, layout: DataLayout
) -> None:
    # S11: temiz numara, kayıtlı çalışan yok → yeni çalışan, klasör, iletişim bilgisi; belge Hazir.
    # S1: tek sayfalık pasaport PDF'i `passthrough`.
    passport = _passport()
    passport["person"]["contact"]["phone"] = PHONE
    upload = _upload(session, layout, _pdf(passport))
    (file_id,) = _file_ids(upload)

    row = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)

    document = read_plan(row)
    assert document.items == (
        _item(
            "i1",
            [(file_id, (0,))],
            slug=PASSPORT,
            employee=_created(),
            route=Route.READY,
            operation=Operation.PASSTHROUGH,
            target=("pdf", "Test_Ornekova-Passport.pdf"),
        ),
    )
    assert (row.upload_id, row.version, row.model) == (UPLOAD_ID, 1, MODEL)
    assert (document.upload_id, document.version, document.model) == (UPLOAD_ID, 1, MODEL)
    assert row.json == document.model_dump(mode="json")
    assert row.plan_hash == document.plan_hash
    assert session.get_one(Employee, "E0001").folder_name == "Test_Ornekova_E0001"
    assert layout.ready_dir("Test_Ornekova_E0001").is_dir()
    contact = session.scalars(select(EmployeeContact)).one()
    assert (contact.employee_id, contact.kind, contact.value) == ("E0001", "phone", PHONE)
    (event,) = _events(session, EventType.PLAN_CREATED)
    assert (event.upload_id, event.file_id, event.page_index, event.message) == (
        UPLOAD_ID,
        None,
        None,
        None,
    )
    assert event.data_json == {
        "plan_id": row.id,
        "version": 1,
        "plan_hash": row.plan_hash,
        "model": MODEL,
        "items": 1,
        "routes": {"hazir": 1},
    }
    assert [e.type for e in _events(session)][-3:] == [
        EventType.PERSON_NOT_MATCHED,
        EventType.EMPLOYEE_CREATED,
        EventType.PLAN_CREATED,
    ]
    _assert_no_personal_values(session)


def test_every_page_and_file_of_the_upload_belongs_to_exactly_one_item(
    session: Session, layout: DataLayout
) -> None:
    # Adaylar, boş sayfalar (S8), analizi yapılamamış sayfalar, Word/Excel eki, tekrar yükleme
    # (S2) ve işlenemeyen dosya: hiçbir sayfa plandan düşmez, öğeler dosya ve sayfa sırasıyla.
    upload = _upload(
        session,
        layout,
        _pdf(
            _page(PERMIT, person=_person(document_number="WP-0000042")),
            BLANK,
            _photo(),
            FAILED,
            BLANK,
        ),
        _File(content=make_docx_bytes()),
        _File(content=make_pdf_bytes(), duplicate_of=0),
        _File(content=make_pdf_bytes()),
    )
    first, attachment, duplicate, pageless = _file_ids(upload)

    document = _plan(session, layout, upload)

    assert document.items == (
        _item(
            "i1",
            [(first, (0,))],
            slug=PERMIT,
            employee=_created(),
            route=Route.READY,
            operation=Operation.EXTRACT,
            target=("pdf", "Test_Ornekova-Work-Permit.pdf"),
        ),
        _item(
            "i2",
            [(first, (1, 4))],
            route=Route.SKIP,
            reason=f"Boş sayfa (dosya {first}, sayfa 2, 5): atlanır; çıktıya ve kuyruğa girmez, "
            "hata sayılmaz.",
        ),
        _item("i3", [(first, (2,))], slug=PHOTO, reason=NO_PERSON_REASON),
        _item(
            "i4",
            [(first, (3,))],
            reason=f"Analizi yapılamamış sayfa (dosya {first}, sayfa 4): içeriği bilinmediği için "
            "hiçbir belgeye katılmaz ve çıktı üretmez (R7); yeniden analizle değerlendirilir.",
        ),
        _item(
            "i5",
            [(attachment, ())],
            slug="attachment",
            reason=AttachmentWithoutContext(attachment, "attachment").reason,
        ),
        _item(
            "i6",
            [(duplicate, ())],
            route=Route.SKIP,
            reason=f"Tekrar yükleme (01.4.1): dosya {duplicate}, daha önce yüklenen dosya {first} "
            "ile aynı içerikte; yeniden işlenmez, çıktı üretmez.",
        ),
        _item(
            "i7",
            [(pageless, ())],
            reason=f"İşlenemeyen dosya (dosya {pageless}): sayfası üretilmemiş ve Word/Excel eki "
            "olarak tanınmadı; çıktı üretmez (R7).",
        ),
    )
    (event,) = _events(session, EventType.PLAN_CREATED)
    assert event.data_json is not None
    assert event.data_json["routes"] == {"hazir": 1, "skip": 2, "unresolved": 4}
    _assert_no_personal_values(session)


def test_number_match_is_ready_for_the_registered_employee_and_accumulates(
    session: Session, layout: DataLayout
) -> None:
    # §20.2.2 satır 1: hedef adı çalışan kaydının adıdır; yeni yazım ve iletişim bilgisi birikir.
    _employee(session, numbers=(NUMBER,))
    passport = _passport()
    passport["person"]["contact"]["phone"] = PHONE
    upload = _upload(session, layout, _pdf(passport))
    (file_id,) = _file_ids(upload)

    document = _plan(session, layout, upload)

    assert document.items == (
        _item(
            "i1",
            [(file_id, (0,))],
            slug=PASSPORT,
            employee=_matched(),
            route=Route.READY,
            operation=Operation.PASSTHROUGH,
            target=("pdf", "Kayitli_Kisi-Passport.pdf"),
        ),
    )
    aliases = session.scalars(select(EmployeeAlias.raw_name).order_by(EmployeeAlias.id))
    assert list(aliases) == ["Test Ornekova", "TEST ORNEKOVA", "Орнекова Тест"]
    contact = session.scalars(select(EmployeeContact)).one()
    assert (contact.employee_id, contact.kind, contact.value) == ("E0007", "phone", PHONE)
    assert _count(session, Employee) == 1


def test_name_only_match_goes_to_unresolved_without_an_employee(
    session: Session, layout: DataLayout
) -> None:
    # S10 / R8: yalnız isim eşleşmesi otomatik eşleştirme sayılmaz, yeni çalışan da açılmaz.
    _employee(session, born=date(1980, 1, 1))
    upload = _upload(session, layout, _pdf(_page(PERMIT, person=_person(document_number="AB12"))))

    (item,) = _plan(session, layout, upload).items

    assert (item.route, item.employee) == (Route.UNRESOLVED, NOBODY)
    assert item.route_reason is not None and item.route_reason.startswith(NAME_ONLY_REASON)
    assert (_count(session, Employee), _count(session, EmployeeAlias)) == (1, 1)


def test_name_without_clean_number_is_a_pending_profile(
    session: Session, layout: DataLayout
) -> None:
    # §20.2.2 satır 7 (K7): numara 5 karakterden kısa, temiz değil → onay bekleyen profil.
    upload = _upload(session, layout, _pdf(_page(PERMIT, person=_person(document_number="AB12"))))
    (file_id,) = _file_ids(upload)

    document = _plan(session, layout, upload)

    pending = PlanEmployee(action=EmployeeAction.PENDING, employee_id=None, matched_by=None)
    assert document.items == (
        _item(
            "i1", [(file_id, (0,))], slug=PERMIT, employee=pending, reason=PENDING_PROFILE_REASON
        ),
    )
    assert _count(session, Employee) == 0
    (event,) = _events(session, EventType.EMPLOYEE_PENDING)
    assert (event.file_id, event.page_index) == (file_id, 0)


@pytest.mark.parametrize("registered", [False, True], ids=["nobody", "number-registered"])
def test_unreadable_document_opens_and_accumulates_nothing_but_keeps_the_person_guess(
    session: Session, layout: DataLayout, registered: bool
) -> None:
    # K1: son geçerlilik okunmayan pasaport Unreadable; numarası temiz olsa da çalışan açılmaz,
    # kayıtlı çalışana yazım ya da iletişim bilgisi eklenmez — eşleşme yalnız kişi tahminidir.
    if registered:
        _employee(session, numbers=(NUMBER,))
    passport = _illegible_expiry(_passport())
    passport["person"]["contact"]["phone"] = PHONE
    upload = _upload(session, layout, _pdf(passport))
    (file_id,) = _file_ids(upload)

    document = _plan(session, layout, upload)

    assert document.items == (
        _item(
            "i1",
            [(file_id, (0,))],
            slug=PASSPORT,
            employee=_matched() if registered else NOBODY,
            route=Route.UNREADABLE,
            reason="Okunamayan alanlar: expiry_date",
        ),
    )
    assert _count(session, Employee) == int(registered)
    assert (_count(session, EmployeeAlias), _count(session, EmployeeIdentifier)) == (
        int(registered),
        int(registered),
    )
    assert _count(session, EmployeeContact) == 0
    assert list(layout.employees.iterdir()) == []


def test_every_verdict_sending_the_document_to_a_queue_is_in_the_reason(
    session: Session, layout: DataLayout
) -> None:
    # Okunamayan alan kuyruğu seçer (K1); karşılanmayan kabul kriteri ve yalnız isim eşleşmesi
    # gerekçeye sırayla eklenir (08.1.2).
    _employee(session, born=date(1980, 1, 1))
    passport = _illegible_expiry(_passport(notes=f"Karşılanmayan kabul kriteri: {UNMET_MRZ}"))
    upload = _upload(session, layout, _pdf(passport))

    (item,) = _plan(session, layout, upload).items

    assert (item.route, item.employee) == (Route.UNREADABLE, NOBODY)
    assert item.route_reason == (
        f'Okunamayan alanlar: expiry_date Karşılanmayan kabul kriterleri: "{UNMET_MRZ}" '
        f"{NAME_ONLY_REASON}. İsmi eşleşen çalışan: E0007. Yalnız isim eşleşmesi otomatik "
        "eşleştirme sayılmaz (R8)."
    )


def test_unmet_acceptance_criterion_alone_goes_to_unresolved(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(
        session, layout, _pdf(_passport(notes=f"Karşılanmayan kabul kriteri: {UNMET_MRZ}"))
    )

    (item,) = _plan(session, layout, upload).items

    assert (item.route, item.route_reason) == (
        Route.UNRESOLVED,
        f'Karşılanmayan kabul kriterleri: "{UNMET_MRZ}"',
    )
    assert _count(session, Employee) == 0


def test_mrz_priority_is_applied_before_the_legibility_gate(
    session: Session, layout: DataLayout
) -> None:
    # 05.3.3 / §20.1.7: numara hanesi tutmayan MRZ görünen okunaklı numarayı okunamadı yapar.
    passport = _passport()
    line = passport["person"]["mrz_lines"][1]
    passport["person"]["mrz_lines"][1] = line[:9] + "2" + line[10:]
    upload = _upload(session, layout, _pdf(passport))

    (item,) = _plan(session, layout, upload).items

    assert (item.route, item.route_reason) == (
        Route.UNREADABLE,
        "Okunamayan alanlar: document_number",
    )
    assert _count(session, Employee) == 0


def test_structural_verdicts_precede_the_legibility_gate_and_open_nobody(
    session: Session, layout: DataLayout
) -> None:
    # S3 / R6: araya belge girmiş ehliyet parçaları Unresolved; ön yüzün temiz numarası çalışan
    # açmaz, arka yüz "okunamayan alanlar" almaz. Aradaki çalışma izni kendi yolunda.
    upload = _upload(
        session,
        layout,
        _pdf(
            _page(LICENSE, side="front"),
            _page(PERMIT, person=_person(document_number="WP-0000042")),
            _back(LICENSE, continues=False),
        ),
    )
    (file_id,) = _file_ids(upload)

    items = _plan(session, layout, upload).items

    assert [(item.item_id, item.route, item.employee) for item in items] == [
        ("i1", Route.UNRESOLVED, NOBODY),
        ("i2", Route.READY, _created()),
        ("i3", Route.UNRESOLVED, NOBODY),
    ]
    for piece in (items[0], items[2]):
        assert piece.route_reason is not None
        assert piece.route_reason.startswith("Ardışıklık güvenlik kuralı (R6)")
        assert "Okunamayan alanlar" not in piece.route_reason
    assert [item.sources for item in items] == [
        (PlanSource(file_id=file_id, pages=(page,)),) for page in range(3)
    ]
    identifiers = session.scalars(select(EmployeeIdentifier.value))
    assert list(identifiers) == ["WP0000042"]


@pytest.mark.parametrize("output_format", ["pdf", "jpeg"])
def test_page_count_outside_the_range_goes_to_unresolved(
    session: Session, layout: DataLayout, output_format: str
) -> None:
    # Parça ya da eksik belgeye işlem seçimi uygulanmaz: üç sayfa JPEG'e çevrilemez ama gerekçe
    # yalnız yapısal hükmü taşır.
    catalog = _catalog_with(PERMIT, output_format=output_format)
    person = _person(document_number="WP-0000042")
    upload = _upload(
        session,
        layout,
        _pdf(*[_page(PERMIT, person=person, continues=index > 0) for index in range(3)]),
    )

    (item,) = _plan(session, layout, upload, catalog=catalog).items

    assert (item.route, item.employee, item.sources[0].pages) == (
        Route.UNRESOLVED,
        NOBODY,
        (0, 1, 2),
    )
    assert item.route_reason is not None
    assert item.route_reason.startswith("Beklenen sayfa sayısı kontrolü (04.5.1)")
    assert "İşlem seçilemedi" not in item.route_reason
    assert _count(session, Employee) == 0


def test_ambiguous_pairing_and_unanalyzed_page_go_to_unresolved(
    session: Session, layout: DataLayout
) -> None:
    # 04.3.2: partide analizi yapılamamış sayfa varken yüzler dosyalar arasında eşleştirilmez.
    upload = _upload(
        session,
        layout,
        _image(_page(RESIDENCE, side="front")),
        _image(_back(RESIDENCE, continues=False)),
        _pdf(FAILED),
    )
    front, back, failed = _file_ids(upload)

    items = _plan(session, layout, upload).items

    assert [(item.sources, item.route) for item in items] == [
        ((PlanSource(file_id=front, pages=(0,)),), Route.UNRESOLVED),
        ((PlanSource(file_id=back, pages=(0,)),), Route.UNRESOLVED),
        ((PlanSource(file_id=failed, pages=(0,)),), Route.UNRESOLVED),
    ]
    for face in items[:2]:
        assert face.route_reason is not None
        assert face.route_reason.startswith("Belirsiz ön/arka yüz eşleştirmesi")
    assert _count(session, Employee) == 0


@pytest.mark.parametrize("registered", [False, True], ids=["nobody", "name-and-birth-date"])
def test_unknown_type_goes_to_unknown_with_a_person_guess(
    session: Session, layout: DataLayout, registered: bool
) -> None:
    # S14 / 04.6.1: katalogda olmayan tür zorla atanmaz; eşleşen çalışan yalnız tahmindir.
    if registered:
        _employee(session, names=("Ana Prueba",), born=date(1995, 3, 15))
    text = (RECORDINGS / "s14_peruvian_diploma" / "0.json").read_text(encoding="utf-8")
    upload = _upload(session, layout, _pdf(json.loads(text)))

    (item,) = _plan(session, layout, upload).items

    guess = _matched(by=MatchedBy.NAME_DOB) if registered else NOBODY
    assert (item.document_type_slug, item.route, item.employee) == (None, Route.UNKNOWN, guess)
    assert item.route_reason is not None and '"Peruvian Diploma"' in item.route_reason
    assert _count(session, CandidateDocumentType) == 1
    assert _count(session, EmployeeAlias) == int(registered)
    _assert_no_personal_values(session)


def test_front_and_back_images_become_one_ready_pdf_item(
    session: Session, layout: DataLayout
) -> None:
    # S5: ayrı dosyalardaki ön ve arka yüz tek öğe; kaynaklar önce ön yüzün dosyası; `merge`.
    upload = _upload(
        session,
        layout,
        _image(_back(RESIDENCE, continues=False), "PNG"),
        _image(_page(RESIDENCE, side="front")),
    )
    back, front = _file_ids(upload)

    document = _plan(session, layout, upload)

    assert document.items == (
        _item(
            "i1",
            [(front, (0,)), (back, (0,))],
            slug=RESIDENCE,
            employee=_created(),
            route=Route.READY,
            operation=Operation.MERGE,
            target=("pdf", "Test_Ornekova-Residence-Card.pdf"),
        ),
    )


@pytest.mark.parametrize(("fmt", "extension"), [("JPEG", "jpeg"), ("PNG", "png")])
def test_keep_output_takes_the_format_of_the_source_content(
    session: Session, layout: DataLayout, fmt: str, extension: str
) -> None:
    catalog = _catalog_with(PASSPORT, expected_file_types=["pdf", "jpeg", "png"])
    upload = _upload(session, layout, _image(_passport(), fmt))

    (item,) = _plan(session, layout, upload, catalog=catalog).items

    assert (item.route, item.operation, item.target_format, item.target_name) == (
        Route.READY,
        Operation.PASSTHROUGH,
        extension,
        f"Test_Ornekova-Passport.{extension}",
    )


def test_same_type_twice_gets_the_same_target_name_without_a_sequence_suffix(
    session: Session, layout: DataLayout
) -> None:
    # K8 `-2` eki yazma anında diskte seçilir (00.4.3); plan diskin durumuna bağlı değildir.
    upload = _upload(session, layout, _pdf(_passport(), _passport()))

    items = _plan(session, layout, upload).items

    assert [(item.employee, item.operation, item.target_name) for item in items] == [
        (_created(), Operation.EXTRACT, "Test_Ornekova-Passport.pdf"),
        (_matched("E0001"), Operation.EXTRACT, "Test_Ornekova-Passport.pdf"),
    ]


def test_attachment_belongs_to_the_context_employee(session: Session, layout: DataLayout) -> None:
    # S15 / 04.7.1: profil sayfasından yüklenen Word eki bağlam çalışanının Hazir'ına değişmeden
    # (`passthrough`) gider.
    _employee(session)
    upload = _upload(session, layout, _File(content=make_docx_bytes()), context_employee_id="E0007")
    (file_id,) = _file_ids(upload)

    document = _plan(session, layout, upload)

    assert document.items == (
        _item(
            "i1",
            [(file_id, ())],
            slug="attachment",
            employee=_matched(by=None),
            route=Route.READY,
            operation=Operation.PASSTHROUGH,
            target=("docx", "Kayitli_Kisi-Attachment.docx"),
        ),
    )


def test_decisions_follow_item_order_so_a_new_employee_is_found_by_the_next_item(
    session: Session, layout: DataLayout
) -> None:
    # Aynı yeni kişinin pasaportu çalışanı açar; oturma izni onunla ad-soyad + doğum tarihinden
    # eşleşir ve temiz numarası birikir — mükerrer çalışan doğmaz.
    upload = _upload(
        session,
        layout,
        _pdf(
            _passport(),
            _page(RESIDENCE, side="front", person=_person(document_number="AB1234567")),
            _back(RESIDENCE),
        ),
    )

    items = _plan(session, layout, upload).items

    assert [(item.item_id, item.employee, item.operation, item.target_name) for item in items] == [
        ("i1", _created(), Operation.EXTRACT, "Test_Ornekova-Passport.pdf"),
        (
            "i2",
            _matched("E0001", MatchedBy.NAME_DOB),
            Operation.EXTRACT,
            "Test_Ornekova-Residence-Card.pdf",
        ),
    ]
    assert items[1].sources == (PlanSource(file_id=_file_ids(upload)[0], pages=(1, 2)),)
    assert _count(session, Employee) == 1
    identifiers = session.execute(
        select(EmployeeIdentifier.kind, EmployeeIdentifier.value).order_by(EmployeeIdentifier.id)
    )
    assert [tuple(row) for row in identifiers] == [
        (PASSPORT, "000000001"),
        (RESIDENCE, "AB1234567"),
    ]


def _mrz_passport(birth: str) -> dict[str, Any]:
    passport = _passport()
    passport["person"]["mrz_lines"] = make_mrz(
        MrzFormat.TD3,
        state="RUS",
        name="ORNEKOVA<<TEST",
        number="000000001",
        nationality="RUS",
        birth=birth,
        expiry="300101",
    )
    passport["person"]["date_of_birth"] = "1925-01-01"
    passport["fields"]["date_of_birth"] = {"value": "1925-01-01", "legible": True}
    return passport


@pytest.mark.parametrize(
    ("reference_date", "employee", "route"),
    [
        (None, _matched(by=MatchedBy.NAME_DOB), Route.READY),
        (date(2026, 9, 15), NOBODY, Route.UNRESOLVED),
    ],
    ids=["upload-day", "explicit-day"],
)
def test_mrz_century_is_chosen_with_the_day_the_upload_was_received(
    session: Session,
    layout: DataLayout,
    reference_date: date | None,
    employee: PlanEmployee,
    route: Route,
) -> None:
    # §20.1.6: MRZ `250101` 2024'te alınan partide 1925, 2026'ya göre 2025'tir. Saat plana girmez.
    _employee(session, born=date(1925, 1, 1))
    received = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    upload = _upload(session, layout, _pdf(_mrz_passport("250101")), created_at=received)

    (item,) = _plan(session, layout, upload, reference_date=reference_date).items

    assert (item.employee, item.route) == (employee, route)


def test_new_plan_of_the_same_upload_takes_the_next_version(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, _pdf(_photo()))

    first = create_plan(session, layout, upload, catalog=CATALOG)
    second = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)

    assert [(row.version, row.model) for row in (first, second)] == [(1, None), (2, MODEL)]
    assert read_plan(first).items == read_plan(second).items
    assert first.plan_hash != second.plan_hash
    assert [row.id for row in upload.plans] == [first.id, second.id]


def test_plan_creation_does_not_commit(session: Session, layout: DataLayout) -> None:
    upload = _upload(session, layout, _pdf(_passport()))
    session.commit()

    create_plan(session, layout, upload, catalog=CATALOG)
    session.rollback()

    assert (_count(session, Plan), _count(session, Employee)) == (0, 0)
    assert _events(session, EventType.PLAN_CREATED) == []


# --- 06.1.2 belirleyicilik ---------------------------------------------------------------------


def _rich_upload(session: Session, layout: DataLayout, *, reorder_keys: bool = False) -> Upload:
    _employee(session, "E0003", names=("Ivan Sidorov",), born=date(1985, 5, 5))
    passport = _passport()
    passport["person"]["contact"]["phone"] = PHONE
    return _upload(
        session,
        layout,
        _pdf(passport, BLANK, _photo(), FAILED, _illegible_expiry(_passport())),
        _image(_page(RESIDENCE, side="front", person=_person(document_number="AB1234567"))),
        _image(_back(RESIDENCE, continues=False), "PNG"),
        _pdf(
            _page(
                PERMIT,
                person=_person(surname="SIDOROV", given_names="IVAN", document_number="AB12"),
            )
        ),
        _File(content=make_docx_bytes()),
        reorder_keys=reorder_keys,
    )


def test_plan_generated_twice_from_the_same_analyses_has_the_same_hash(
    session: Session, layout: DataLayout
) -> None:
    upload = _rich_upload(session, layout)
    session.commit()

    first = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
    frozen = (copy.deepcopy(first.json), first.plan_hash, first.version)
    routes = {item.route for item in read_plan(first).items}
    session.rollback()
    second = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)

    assert (second.json, second.plan_hash, second.version) == frozen
    assert routes == {Route.READY, Route.SKIP, Route.UNREADABLE, Route.UNRESOLVED}
    assert read_plan(second).canonical_json() == read_plan(first).canonical_json()


def test_plan_hash_does_not_depend_on_the_database_or_stored_key_order(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _rich_upload(session, layout)
    expected = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL).plan_hash

    engine = create_db_engine(f"sqlite:///{(tmp_path / 'second.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as other:
            other_layout = prepare_data_dir(tmp_path / "second-data")
            other_upload = _rich_upload(other, other_layout, reorder_keys=True)
            row = create_plan(other, other_layout, other_upload, catalog=CATALOG, model=MODEL)
            assert row.plan_hash == expected
    finally:
        engine.dispose()


def test_plan_hash_changes_when_an_analysis_changes(session: Session, layout: DataLayout) -> None:
    upload = _upload(session, layout, _pdf(_passport()))
    session.commit()
    readable = create_plan(session, layout, upload, catalog=CATALOG).plan_hash
    session.rollback()

    page = upload.files[0].pages[0]
    page.analysis_json = _illegible_expiry(copy.deepcopy(page.analysis_json))
    unreadable = create_plan(session, layout, upload, catalog=CATALOG).plan_hash

    assert unreadable != readable


@pytest.fixture
def frozen(session: Session, layout: DataLayout) -> Iterator[Plan]:
    upload = _upload(session, layout, _pdf(_passport()))
    yield create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)


def test_stored_plan_reads_back_to_the_same_document(frozen: Plan) -> None:
    document = read_plan(frozen)

    assert document.model_dump(mode="json") == frozen.json
    assert document.plan_hash == frozen.plan_hash


def test_changed_stored_plan_is_not_read(frozen: Plan) -> None:
    changed = copy.deepcopy(frozen.json)
    changed["items"][0]["target_name"] = "Baska_Kisi-Passport.pdf"
    frozen.json = changed

    with pytest.raises(PlanIntegrityError, match="hash'i kaydıyla uyuşmuyor"):
        read_plan(frozen)


@pytest.mark.parametrize(
    ("column", "value"), [("version", 2), ("upload_id", "u_20260915_0002"), ("model", None)]
)
def test_stored_plan_of_another_identity_is_not_read(
    frozen: Plan, column: str, value: object
) -> None:
    setattr(frozen, column, value)

    with pytest.raises(PlanIntegrityError, match="parti, sürüm ya da modeli"):
        read_plan(frozen)


def test_stored_plan_breaking_the_contract_is_not_read_and_not_repeated(frozen: Plan) -> None:
    changed = copy.deepcopy(frozen.json)
    changed["items"][0]["target_name"] = "Test Ornekova.pdf"
    changed["items"][0]["route"] = "hazir-degil"
    frozen.json = changed

    with pytest.raises(PlanIntegrityError, match="sözleşmesine uymuyor") as raised:
        read_plan(frozen)

    assert "items.0.target_name" in str(raised.value)
    assert "Ornekova" not in str(raised.value)


# --- 06.2.1 işlem seçimi (§20.3) ----------------------------------------------------------------

PDF, JPEG, PNG, DOCX = FileKind.PDF, FileKind.JPEG, FileKind.PNG, FileKind.DOCX
KEEP, TO_PDF, TO_JPEG = OutputFormat.KEEP, OutputFormat.PDF, OutputFormat.JPEG
NO_OPERATION = "İşlem seçilemedi (06.2.1): "
NO_OPERATION_TAIL = (
    "§20.3'te bu kaynak, kapsama ve biçim için uyan fiziksel işlem yok; belge dönüştürülmez."
)


def _source(
    kind: FileKind | None,
    pages: tuple[int, ...] = (0,),
    *,
    file_id: int = 1,
    file_pages: Iterable[int] | None = None,
    blank: Iterable[int] = (),
    single_image: Iterable[int] = (),
) -> OperationSource:
    """Kaynak dosya; `file_pages` verilmezse dosya yalnız alınan sayfalardan oluşur."""
    return OperationSource(
        file_id=file_id,
        kind=kind,
        pages=pages,
        file_pages=frozenset(pages if file_pages is None else file_pages),
        blank_pages=frozenset(blank),
        single_image_pages=frozenset(single_image),
    )


@pytest.mark.parametrize(
    ("sources", "output_format", "operation", "target_format"),
    [
        # Satır 1: tek dosya, tüm sayfalar, aynı biçim (ya da `keep`).
        pytest.param([_source(PDF)], KEEP, Operation.PASSTHROUGH, "pdf", id="1-pdf-keep"),
        pytest.param(
            [_source(PDF, (0, 1, 2))], TO_PDF, Operation.PASSTHROUGH, "pdf", id="1-pdf-all-pages"
        ),
        pytest.param([_source(JPEG)], KEEP, Operation.PASSTHROUGH, "jpeg", id="1-jpeg-keep"),
        pytest.param([_source(PNG)], KEEP, Operation.PASSTHROUGH, "png", id="1-png-keep"),
        pytest.param([_source(JPEG)], TO_JPEG, Operation.PASSTHROUGH, "jpeg", id="1-jpeg-to-jpeg"),
        pytest.param([_source(DOCX, ())], KEEP, Operation.PASSTHROUGH, "docx", id="1-word-file"),
        pytest.param(
            [_source(PDF, single_image=(0,))],
            TO_PDF,
            Operation.PASSTHROUGH,
            "pdf",
            id="1-image-page-pdf-to-pdf",
        ),
        # Satır 2: tek PDF, ardışık alt küme, PDF → PDF.
        pytest.param(
            [_source(PDF, (1,), file_pages=range(3))],
            KEEP,
            Operation.EXTRACT,
            "pdf",
            id="2-page-inside-pdf",
        ),
        pytest.param(
            [_source(PDF, (1, 2), file_pages=range(4))],
            TO_PDF,
            Operation.EXTRACT,
            "pdf",
            id="2-contiguous-pages",
        ),
        pytest.param(
            [_source(PDF, (0, 2), file_pages=range(3), blank=(1,))],
            TO_PDF,
            Operation.EXTRACT,
            "pdf",
            id="2-blank-page-between",
        ),
        pytest.param(
            [_source(PDF, (0,), file_pages=range(2), blank=(1,))],
            KEEP,
            Operation.EXTRACT,
            "pdf",
            id="2-trailing-blank-page-left-out",
        ),
        pytest.param(
            [_source(PDF, (1,), file_pages=range(3), single_image=(1,))],
            TO_PDF,
            Operation.EXTRACT,
            "pdf",
            id="2-image-page-to-pdf",
        ),
        # Satır 3: birden çok dosya → PDF.
        pytest.param(
            [_source(JPEG), _source(PNG, file_id=2)], TO_PDF, Operation.MERGE, "pdf", id="3-images"
        ),
        pytest.param(
            [_source(PDF, (0, 1)), _source(PDF, file_id=2)],
            KEEP,
            Operation.MERGE,
            "pdf",
            id="3-pdfs-keep",
        ),
        # Satır 4: tek JPEG/PNG, tek sayfa, görüntü → PDF.
        pytest.param([_source(JPEG)], TO_PDF, Operation.WRAP_IMAGE, "pdf", id="4-jpeg"),
        pytest.param([_source(PNG)], TO_PDF, Operation.WRAP_IMAGE, "pdf", id="4-png"),
        # Satır 5: tek PDF, tek sayfa, PDF → JPEG, gömülü tek görüntü var.
        pytest.param(
            [_source(PDF, single_image=(0,))],
            TO_JPEG,
            Operation.EXTRACT_IMAGE,
            "jpeg",
            id="5-single-page-pdf",
        ),
        pytest.param(
            [_source(PDF, (2,), file_pages=range(5), single_image=(1, 2))],
            TO_JPEG,
            Operation.EXTRACT_IMAGE,
            "jpeg",
            id="5-page-inside-pdf",
        ),
        # Satır 6: tek PDF, tek sayfa, PDF → JPEG, gömülü tek görüntü yok.
        pytest.param([_source(PDF)], TO_JPEG, Operation.RENDER_IMAGE, "jpeg", id="6-single-page"),
        pytest.param(
            [_source(PDF, (2,), file_pages=range(5), single_image=(1, 3))],
            TO_JPEG,
            Operation.RENDER_IMAGE,
            "jpeg",
            id="6-only-other-pages-are-images",
        ),
    ],
)
def test_operation_is_selected_by_the_first_matching_row(
    sources: list[OperationSource],
    output_format: OutputFormat,
    operation: Operation,
    target_format: str,
) -> None:
    selection = select_operation(sources, output_format=output_format)

    assert selection == SelectedOperation(operation, FileType(target_format))


@pytest.mark.parametrize(
    ("sources", "output_format", "described"),
    [
        pytest.param(
            [_source(PNG, file_id=3)],
            TO_JPEG,
            "Kaynak: dosya 3, sayfa 1 (png, dosyanın tüm sayfaları). Hedef biçim: jpeg. ",
            id="png-to-jpeg",
        ),
        pytest.param(
            [_source(DOCX, (), file_id=4)],
            TO_PDF,
            "Kaynak: dosya 4 (docx, bütün dosya). Hedef biçim: pdf. ",
            id="word-to-pdf",
        ),
        pytest.param(
            [_source(PDF, (0, 1))],
            TO_JPEG,
            "Kaynak: dosya 1, sayfa 1, 2 (pdf, dosyanın tüm sayfaları). Hedef biçim: jpeg. ",
            id="two-pages-to-jpeg",
        ),
        pytest.param(
            [_source(PDF, (1, 2), file_pages=range(4))],
            TO_JPEG,
            "Kaynak: dosya 1, sayfa 2, 3 (pdf, dosyanın ardışık alt kümesi). Hedef biçim: jpeg. ",
            id="subset-to-jpeg",
        ),
        pytest.param(
            [_source(PDF, (0, 2), file_pages=range(3))],
            TO_PDF,
            "Kaynak: dosya 1, sayfa 1, 3 (pdf, dosyanın ardışık olmayan alt kümesi). "
            "Hedef biçim: pdf. ",
            id="page-between-is-not-blank",
        ),
        pytest.param(
            [_source(JPEG), _source(JPEG, file_id=2)],
            KEEP,
            "Kaynaklar: dosya 1, sayfa 1 (jpeg, dosyanın tüm sayfaları); dosya 2, sayfa 1 (jpeg, "
            "dosyanın tüm sayfaları). Hedef biçim: jpeg. ",
            id="several-files-to-jpeg",
        ),
        pytest.param(
            [_source(JPEG), _source(PNG, file_id=2)],
            KEEP,
            "Hedef biçim: belirlenemedi (output_format: keep, kaynaklar farklı biçimde). ",
            id="keep-different-formats",
        ),
        pytest.param(
            [_source(None)],
            KEEP,
            "Kaynak: dosya 1, sayfa 1 (biçimi tanınmadı, dosyanın tüm sayfaları). Hedef biçim: "
            "belirlenemedi (output_format: keep, kaynak biçimi tanınmadı). ",
            id="keep-unrecognized",
        ),
        pytest.param(
            [_source(None)],
            TO_PDF,
            "(biçimi tanınmadı, dosyanın tüm sayfaları). Hedef biçim: pdf. ",
            id="unrecognized-to-pdf",
        ),
    ],
)
def test_without_a_matching_row_no_operation_is_selected_and_the_reason_is_written(
    sources: list[OperationSource], output_format: OutputFormat, described: str
) -> None:
    # Satır 7: işlem yok → Unresolved; gerekçe kaynağı, kapsamayı ve hedef biçimi yazar.
    selection = select_operation(sources, output_format=output_format)

    assert isinstance(selection, NoApplicableOperation)
    assert selection.queue is QueueKind.UNRESOLVED
    assert (selection.target_format is None) == ("belirlenemedi" in described)
    assert selection.reason.startswith(NO_OPERATION)
    assert selection.reason.endswith(described + NO_OPERATION_TAIL)


def test_whole_file_source_is_whole_and_contiguous() -> None:
    source = OperationSource(file_id=1, kind=FileKind.DOCX)

    assert (source.whole, source.contiguous) == (True, True)


def test_s7_passport_page_inside_a_multi_page_pdf_is_extracted_without_render(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, _pdf(_photo(), _passport(), _photo()))
    (file_id,) = _file_ids(upload)

    items = _plan(session, layout, upload).items

    assert items[1] == _item(
        "i2",
        [(file_id, (1,))],
        slug=PASSPORT,
        employee=_created(),
        route=Route.READY,
        operation=Operation.EXTRACT,
        target=("pdf", "Test_Ornekova-Passport.pdf"),
    )
    assert [(item.route, item.operation) for item in (items[0], items[2])] == [
        (Route.UNRESOLVED, None),
        (Route.UNRESOLVED, None),
    ]
    # Direkt Belge'de `extract` izinlidir (06.3.1): ret olayı yok.
    assert _events(session, EventType.DIRECT_DOC_CHECK) == []


def test_s8_blank_page_between_the_faces_stays_out_of_the_extracted_document(
    session: Session, layout: DataLayout
) -> None:
    # Dupleks taramada kartın yüzleri arasındaki boş sayfa başka belge değildir (K5): aday `[0, 2]`
    # ardışık alt kümedir, `extract` boş sayfayı çıktıya almaz; boş sayfa atlanır.
    upload = _upload(session, layout, _pdf(_page(LICENSE, side="front"), BLANK, _back(LICENSE)))
    (file_id,) = _file_ids(upload)

    document = _plan(session, layout, upload)

    assert document.items == (
        _item(
            "i1",
            [(file_id, (0, 2))],
            slug=LICENSE,
            employee=_created(),
            route=Route.READY,
            operation=Operation.EXTRACT,
            target=("pdf", "Test_Ornekova-Driving-License.pdf"),
        ),
        _item(
            "i2",
            [(file_id, (1,))],
            route=Route.SKIP,
            reason=f"Boş sayfa (dosya {file_id}, sayfa 2): atlanır; çıktıya ve kuyruğa girmez, "
            "hata sayılmaz.",
        ),
    )


def _image_then_text_pdf_bytes() -> bytes:
    """İki sayfalık PDF: 1. sayfa tek tam sayfa gömülü görüntü (tarama), 2. sayfa metin."""
    document = pymupdf.open()
    scanned = document.new_page(width=A4[0], height=A4[1])
    scanned.insert_image(
        scanned.rect, stream=make_half_filled_image_bytes(size=(60, 85)), keep_proportion=False
    )
    document.new_page(width=A4[0], height=A4[1]).insert_text((72, 72), "METIN SAYFASI")
    content = document.tobytes()
    document.close()
    return content


def test_pdf_page_to_jpeg_extracts_the_embedded_image_or_renders_the_page(
    session: Session, layout: DataLayout
) -> None:
    # K12: JPEG çıktılı türde gömülü tek görüntülü sayfanın görüntüsü kayıpsız çıkarılır, öteki
    # sayfa render edilir. İşaret gerçek PDF içeriğinden 02.5.1 ile okunur.
    catalog = _catalog_with(
        PERMIT, output_format="jpeg", allowed_conversions=["extract_image", "render_image"]
    )
    permit = _page(PERMIT, person=_person(document_number="WP-0000042"))
    upload = _upload(
        session, layout, _File(pages=(permit, permit), content=_image_then_text_pdf_bytes())
    )
    (upload_file,) = upload.files
    mark_upload_file_single_image_pages(session, layout, upload_file)

    document = _plan(session, layout, upload, catalog=catalog)

    target = ("jpeg", "Test_Ornekova-Work-Permit.jpeg")
    assert document.items == (
        _item(
            "i1",
            [(upload_file.id, (0,))],
            slug=PERMIT,
            employee=_created(),
            route=Route.READY,
            operation=Operation.EXTRACT_IMAGE,
            target=target,
        ),
        _item(
            "i2",
            [(upload_file.id, (1,))],
            slug=PERMIT,
            employee=_matched("E0001"),
            route=Route.READY,
            operation=Operation.RENDER_IMAGE,
            target=target,
        ),
    )


def test_page_without_a_page_row_makes_the_document_a_subset(
    session: Session, layout: DataLayout
) -> None:
    # Render sayfa sayısını yazdı ama ikinci sayfanın satırı yok: dosya bütün olarak kopyalanmaz,
    # yalnız alınan sayfa çıkarılır.
    upload = _upload(session, layout, _File(pages=(_passport(),), content=make_pdf_bytes(2)))
    upload.files[0].page_count = 2

    (item,) = _plan(session, layout, upload).items

    assert (item.route, item.operation, item.sources) == (
        Route.READY,
        Operation.EXTRACT,
        (PlanSource(file_id=upload.files[0].id, pages=(0,)),),
    )


def test_document_without_an_operation_goes_to_unresolved_and_opens_nobody(
    session: Session, layout: DataLayout
) -> None:
    # Satır 7: `keep` türde içeriği tanınmayan kaynağın hedef biçimi yok. İşlem seçimi çalışan
    # kararından önce yapılır: temiz numaralı belgeden çalışan açılmaz. Tür Direkt Belge değil —
    # Direkt Belge'de aynı kaynak format kontrolünde (06.3.2) reddedilir.
    catalog = _catalog_with(PASSPORT, direct=False)
    upload = _upload(session, layout, _File(pages=(_passport(),), content=b"tanimsiz icerik"))
    (file_id,) = _file_ids(upload)

    document = _plan(session, layout, upload, catalog=catalog)

    assert document.items == (
        _item(
            "i1",
            [(file_id, (0,))],
            slug=PASSPORT,
            reason=f"{NO_OPERATION}Kaynak: dosya {file_id}, sayfa 1 (biçimi tanınmadı, dosyanın "
            "tüm sayfaları). Hedef biçim: belirlenemedi (output_format: keep, kaynak biçimi "
            f"tanınmadı). {NO_OPERATION_TAIL}",
        ),
    )
    assert (_count(session, Employee), _count(session, EmployeeIdentifier)) == (0, 0)
    assert _events(session, EventType.EMPLOYEE_CREATED) == []
    assert list(layout.employees.iterdir()) == []


@pytest.mark.parametrize("registered", [False, True], ids=["nobody", "number-registered"])
def test_front_and_back_in_different_formats_without_a_common_format_are_not_converted(
    session: Session, layout: DataLayout, registered: bool
) -> None:
    # `keep` türde JPEG ön yüz ve PNG arka yüzün ortak biçimi yok: işlem yok, Unresolved. Kayıtlı
    # çalışan yalnız kişi tahminidir; yazım ya da numara birikmez.
    if registered:
        _employee(session, numbers=(NUMBER,))
    catalog = _catalog_with(RESIDENCE, output_format="keep")
    upload = _upload(
        session,
        layout,
        _image(_page(RESIDENCE, side="front")),
        _image(_back(RESIDENCE, continues=False), "PNG"),
    )
    front, back = _file_ids(upload)

    (item,) = _plan(session, layout, upload, catalog=catalog).items

    assert item == _item(
        "i1",
        [(front, (0,)), (back, (0,))],
        slug=RESIDENCE,
        employee=_matched() if registered else NOBODY,
        reason=f"{NO_OPERATION}Kaynaklar: dosya {front}, sayfa 1 (jpeg, dosyanın tüm sayfaları); "
        f"dosya {back}, sayfa 1 (png, dosyanın tüm sayfaları). Hedef biçim: belirlenemedi "
        f"(output_format: keep, kaynaklar farklı biçimde). {NO_OPERATION_TAIL}",
    )
    assert _count(session, Employee) == int(registered)
    assert (_count(session, EmployeeAlias), _count(session, EmployeeIdentifier)) == (
        int(registered),
        int(registered),
    )
    assert list(layout.employees.iterdir()) == []


def test_no_operation_verdict_follows_the_legibility_gate(
    session: Session, layout: DataLayout
) -> None:
    # Okunamayan alan kuyruğu seçer; işlem gerekçesi ardından eklenir.
    upload = _upload(
        session,
        layout,
        _File(pages=(_illegible_expiry(_passport()),), content=b"tanimsiz icerik"),
    )

    (item,) = _plan(session, layout, upload, catalog=_catalog_with(PASSPORT, direct=False)).items

    assert item.route is Route.UNREADABLE
    assert item.route_reason is not None
    assert item.route_reason.startswith(f"Okunamayan alanlar: expiry_date {NO_OPERATION}")
    assert item.route_reason.endswith(NO_OPERATION_TAIL)


@pytest.mark.parametrize("context", [True, False], ids=["context", "no-context"])
def test_attachment_without_an_operation_goes_to_unresolved(
    session: Session, layout: DataLayout, context: bool
) -> None:
    # K2: Word eki dönüştürülmez; tür PDF çıktısı isterse işlem yok. Bağlam çalışanı kişi tahmini
    # kalır; bağlam yoksa sahiplik gerekçesi işlem gerekçesinin ardından gelir.
    _employee(session)
    catalog = _catalog_with("attachment", output_format="pdf")
    upload = _upload(
        session,
        layout,
        _File(content=make_docx_bytes()),
        context_employee_id="E0007" if context else None,
    )
    (file_id,) = _file_ids(upload)

    (item,) = _plan(session, layout, upload, catalog=catalog).items

    no_operation = (
        f"{NO_OPERATION}Kaynak: dosya {file_id} (docx, bütün dosya). Hedef biçim: pdf. "
        f"{NO_OPERATION_TAIL}"
    )
    ownerless = AttachmentWithoutContext(file_id, "attachment").reason
    assert item == _item(
        "i1",
        [(file_id, ())],
        slug="attachment",
        employee=_matched(by=None) if context else NOBODY,
        reason=no_operation if context else f"{no_operation} {ownerless}",
    )


# --- 06.3 Direkt Belge (§20.4) ------------------------------------------------------------------

UPLOAD_AGAIN = "Uygun formatta yeniden gönderin."


def _entry(slug: str, catalog: Catalog = CATALOG) -> CatalogEntry:
    entry = catalog.get(slug)
    assert entry is not None
    return entry


def _forbidden(operation: str) -> str:
    return f"Direkt Belge: {operation} bu tür için yapılamaz."


def test_direct_document_keeps_only_passthrough_and_extract() -> None:
    assert frozenset({Operation.PASSTHROUGH, Operation.EXTRACT}) == DIRECT_OPERATIONS


@pytest.mark.parametrize(
    ("operation", "allowed"),
    [
        (Operation.PASSTHROUGH, True),
        (Operation.EXTRACT, True),
        (Operation.MERGE, False),
        (Operation.WRAP_IMAGE, False),
        (Operation.EXTRACT_IMAGE, False),
        (Operation.RENDER_IMAGE, False),
    ],
)
def test_direct_document_matrix_forbids_merge_wrap_and_render(
    operation: Operation, allowed: bool
) -> None:
    # §20.4: Direkt Belge'de tek kaynağın sayfaları olduğu gibi alınır; belge başka kaynaklardan
    # kurulmaz, biçimi değişmez. `direct: false` sütununda matris reddetmez (dönüşüm izni 06.4'ün).
    refusal = check_direct_operation(operation, entry=_entry(PASSPORT))

    assert check_direct_operation(operation, entry=_entry(LICENSE)) is None
    if allowed:
        assert refusal is None
    else:
        assert refusal == DirectOperationForbidden(operation)
        assert refusal.queue is QueueKind.UNRESOLVED
        assert refusal.reason == _forbidden(operation.value)


@pytest.mark.parametrize(
    ("slug", "sources", "received"),
    [
        pytest.param(PASSPORT, [_source(PDF)], None, id="pdf-expected"),
        pytest.param(PASSPORT, [_source(JPEG)], None, id="jpeg-expected"),
        pytest.param(PASSPORT, [_source(PDF), _source(JPEG, file_id=2)], None, id="all-expected"),
        pytest.param("attachment", [_source(DOCX, ())], None, id="word-attachment"),
        pytest.param(LICENSE, [_source(DOCX, ())], None, id="not-direct"),
        pytest.param(PASSPORT, [_source(PNG)], "png", id="png-not-expected"),
        pytest.param(PASSPORT, [_source(None)], "tanınmayan biçim", id="unrecognized"),
        pytest.param(
            PASSPORT,
            [
                _source(PDF),
                _source(PNG, file_id=2),
                _source(None, file_id=3),
                _source(PNG, file_id=4),
            ],
            "png/tanınmayan biçim",
            id="unexpected-sources-once-in-order",
        ),
    ],
)
def test_direct_document_source_must_be_an_expected_file_type(
    slug: str, sources: list[OperationSource], received: str | None
) -> None:
    # §20.4.1: kaynak biçimi (içerikten) türün `expected_file_types`'ında değilse işlem yok.
    mismatch = check_direct_file_types(sources, entry=_entry(slug))

    if received is None:
        assert mismatch is None
    else:
        assert isinstance(mismatch, DirectFileTypeMismatch)
        assert mismatch.queue is QueueKind.UNRESOLVED
        assert mismatch.reason == (
            f"Direkt Belge: beklenen dosya türü pdf/jpeg, gelen {received}. {UPLOAD_AGAIN}"
        )


@pytest.mark.parametrize("registered", [False, True], ids=["nobody", "number-registered"])
def test_s6_direct_passport_in_an_unexpected_format_goes_to_unresolved_without_conversion(
    session: Session, layout: DataLayout, registered: bool
) -> None:
    # S6 / K3: katalog pasaportu yalnız PDF bekler, JPEG geldi. `keep` türde satır 1 uyardı; format
    # kontrolü işlemden önce keser: işlem ve hedef yok, çalışan açılmaz, kimlik birikmez. Kayıtlı
    # çalışan yalnız kişi tahminidir.
    if registered:
        _employee(session, numbers=(NUMBER,))
    catalog = _catalog_with(PASSPORT, expected_file_types=["pdf"])
    upload = _upload(session, layout, _image(_passport()))
    (file_id,) = _file_ids(upload)

    document = _plan(session, layout, upload, catalog=catalog)

    reason = f"Direkt Belge: beklenen dosya türü pdf, gelen jpeg. {UPLOAD_AGAIN}"
    assert document.items == (
        _item(
            "i1",
            [(file_id, (0,))],
            slug=PASSPORT,
            employee=_matched() if registered else NOBODY,
            reason=reason,
        ),
    )
    assert _count(session, Employee) == int(registered)
    assert (_count(session, EmployeeAlias), _count(session, EmployeeIdentifier)) == (
        int(registered),
        int(registered),
    )
    assert list(layout.employees.iterdir()) == []
    (event,) = _events(session, EventType.DIRECT_DOC_CHECK)
    assert (event.upload_id, event.file_id, event.page_index, event.message) == (
        UPLOAD_ID,
        file_id,
        0,
        reason,
    )
    assert event.data_json == {
        "document_type_slug": PASSPORT,
        "check": "file_type",
        "operation": None,
        "expected_file_types": ["pdf"],
        "file_types": ["jpeg"],
        "queue": "unresolved",
    }
    assert [e.type for e in _events(session)][-2:] == [
        EventType.DIRECT_DOC_CHECK,
        EventType.PLAN_CREATED,
    ]
    _assert_no_personal_values(session)


def test_file_type_refusal_follows_the_legibility_gate_and_no_operation_row_is_tried(
    session: Session, layout: DataLayout
) -> None:
    # §20.4.1 işlemden önce: tanınmayan içerikli Direkt Belge'de satır 7 denenmez; gerekçe yalnız
    # format kontrolünündür ve okunaklılık gerekçesinin ardından gelir.
    upload = _upload(
        session,
        layout,
        _File(pages=(_illegible_expiry(_passport()),), content=b"tanimsiz icerik"),
    )

    (item,) = _plan(session, layout, upload).items

    assert (item.route, item.operation, item.route_reason) == (
        Route.UNREADABLE,
        None,
        "Okunamayan alanlar: expiry_date Direkt Belge: beklenen dosya türü pdf/jpeg, gelen "
        f"tanınmayan biçim. {UPLOAD_AGAIN}",
    )
    (event,) = _events(session, EventType.DIRECT_DOC_CHECK)
    assert event.data_json is not None
    assert (event.data_json["check"], event.data_json["file_types"]) == ("file_type", [None])


def test_direct_type_with_pdf_output_does_not_wrap_an_image(
    session: Session, layout: DataLayout
) -> None:
    # 06.3.1: format beklenen türlerden (JPEG) ama §20.3 satır 4 `wrap_image` Direkt Belge'de yasak.
    catalog = _catalog_with(PASSPORT, output_format="pdf")
    upload = _upload(session, layout, _image(_passport()))
    (file_id,) = _file_ids(upload)

    document = _plan(session, layout, upload, catalog=catalog)

    assert document.items == (
        _item("i1", [(file_id, (0,))], slug=PASSPORT, reason=_forbidden("wrap_image")),
    )
    assert _count(session, Employee) == 0
    (event,) = _events(session, EventType.DIRECT_DOC_CHECK)
    assert (event.file_id, event.page_index, event.message) == (
        file_id,
        0,
        _forbidden("wrap_image"),
    )
    assert event.data_json == {
        "document_type_slug": PASSPORT,
        "check": "operation",
        "operation": "wrap_image",
        "expected_file_types": ["pdf", "jpeg"],
        "file_types": ["jpeg"],
        "queue": "unresolved",
    }


def test_direct_type_with_jpeg_output_neither_extracts_the_image_nor_renders_the_page(
    session: Session, layout: DataLayout
) -> None:
    # 06.3.1 / K12: JPEG çıktılı Direkt Belge türünde gömülü görüntü çıkarılmaz (satır 5), sayfa
    # render edilmez (satır 6); işlem plana girmez, belge Unresolved'a gider, çalışan açılmaz.
    catalog = _catalog_with(PASSPORT, output_format="jpeg")
    upload = _upload(
        session,
        layout,
        _File(pages=(_passport(), _passport()), content=_image_then_text_pdf_bytes()),
    )
    (upload_file,) = upload.files
    mark_upload_file_single_image_pages(session, layout, upload_file)

    document = _plan(session, layout, upload, catalog=catalog)

    file_id = upload_file.id
    assert document.items == (
        _item("i1", [(file_id, (0,))], slug=PASSPORT, reason=_forbidden("extract_image")),
        _item("i2", [(file_id, (1,))], slug=PASSPORT, reason=_forbidden("render_image")),
    )
    assert _count(session, Employee) == 0
    events = _events(session, EventType.DIRECT_DOC_CHECK)
    assert [
        (event.page_index, event.data_json and event.data_json["operation"]) for event in events
    ] == [(0, "extract_image"), (1, "render_image")]
    _assert_no_personal_values(session)


# --- entegrasyon: gerçek render ve kayıtlı yanıt → plan ---------------------------------------


def test_s4_recorded_pdf_with_registered_employee_plans_three_documents(
    session: Session, layout: DataLayout
) -> None:
    # S4: ehliyet ön/arka, foto, oturum ön/arka. Ehliyet ve oturum izni numarasından kayıtlı
    # çalışanın Hazir'ına; fotoğrafta kişi yok, §20.2.2 satır 8 gereği Unresolved (PLAN.md D12).
    _employee(
        session,
        names=("Ivan Sidorov",),
        born=date(1985, 5, 5),
        numbers=("000123456", "AB1234567"),
    )
    pdf = make_text_pdf_bytes(
        ["EHLIYET ON YUZ", "EHLIYET ARKA YUZ", "FOTOGRAF", "OTURUM IZNI ON", "OTURUM IZNI ARKA"]
    )
    upload = Upload(id=UPLOAD_ID, channel="web", status=UploadStatus.ANALYZING.value)
    session.add(upload)
    stored = write_to_inbox(layout, upload.id, "belgeler.pdf", pdf)
    upload_file = UploadFile(
        upload=upload,
        original_name="belgeler.pdf",
        stored_path=stored.path.relative_to(layout.root).as_posix(),
        sha256=stored.sha256,
        mime="application/pdf",
    )
    session.add(upload_file)
    session.flush()
    settings = Settings(_env_file=None, database_url="sqlite://")
    render_upload_file(session, layout, settings, upload_file)
    extract_upload_file_text(session, layout, upload_file)
    mark_upload_file_blank_pages(session, layout, upload_file)
    provider = RecordingProvider.from_directory(RECORDINGS / "s4_sequential_pdf")
    instructions = build_page_analysis_instructions(CATALOG)
    analyze_upload(session, layout, upload, provider=provider, instructions=instructions)

    row = create_plan(session, layout, upload, catalog=CATALOG, model=provider.model)
    session.commit()

    file_id = upload_file.id
    assert read_plan(row).items == (
        _item(
            "i1",
            [(file_id, (0, 1))],
            slug=LICENSE,
            employee=_matched(),
            route=Route.READY,
            operation=Operation.EXTRACT,
            target=("pdf", "Kayitli_Kisi-Driving-License.pdf"),
        ),
        _item("i2", [(file_id, (2,))], slug=PHOTO, reason=NO_PERSON_REASON),
        _item(
            "i3",
            [(file_id, (3, 4))],
            slug=RESIDENCE,
            employee=_matched(),
            route=Route.READY,
            operation=Operation.EXTRACT,
            target=("pdf", "Kayitli_Kisi-Residence-Card.pdf"),
        ),
    )
    assert row.model == provider.model
    person_events = [
        (event.type, event.page_index, event.employee_id)
        for event in _events(session)
        if event.type in {EventType.PERSON_MATCHED, EventType.PERSON_NOT_MATCHED}
    ]
    assert person_events == [
        (EventType.PERSON_MATCHED, 0, "E0007"),
        (EventType.PERSON_NOT_MATCHED, 2, None),
        (EventType.PERSON_MATCHED, 3, "E0007"),
    ]
    _assert_no_personal_values(session)
