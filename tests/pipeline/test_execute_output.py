"""07.7.1, 07.7.2 — ortak çıktı yazma (§20.5, K10, K15, R13).

07.7.1 — çıktı çalışanın `Hazir/` klasörüne planın adıyla atomik yazılır (K8 sıra eki diskte);
kaynak dosya ve sayfa aralığı `documents.source_refs_json`'a ve `OUTPUT_SAVED` olayına kaydedilir.
07.7.2 — kaynak dosya çalışanın `Alinan/` klasörüne kopyalanır; aynı hash tekrar kopyalanmaz.

Planlayıcıdan geçen testler işlemleri gerçek planla (S5 dahil) yürütür; hata, kayıt ve Alinan
tekilliği testleri planı elle kurar. Dosyalar `tests/fixtures/gen.py` ile üretilen sentetik
belgelerdir (CONVENTIONS §6); yapay zekâ yanıtları kayıtlıdır.
"""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pymupdf
import pytest
from sqlalchemy.orm import Session

import app.pipeline.execute as execute_module
from app.ai.recording_provider import RecordingProvider
from app.catalog import Catalog, import_catalog
from app.db.models import Document, Employee, Plan, Upload, UploadFile, UploadStatus
from app.events import EventType
from app.matching.match import MatchedBy
from app.pipeline.analyze import analyze_upload
from app.pipeline.execute import (
    DirectDocumentMergeError,
    ExecutedItem,
    ExtractImageSourceError,
    ExtractSourceError,
    PassthroughIntegrityError,
    PlanItemReferenceError,
    SourceIntegrityError,
    WrapImageSourceError,
    execute_ready_item,
)
from app.pipeline.plan import Operation, PlanDocument, PlanItem, Route, create_plan, read_plan
from app.pipeline.render import mark_upload_file_single_image_pages
from app.pipeline.validate import ValidationName
from app.storage import DataLayout, write_to_inbox
from tests.fixtures.gen import (
    make_docx_bytes,
    make_half_filled_image_bytes,
    make_pdf_bytes,
    make_text_pdf_bytes,
)
from tests.pipeline.test_execute import _files, _open, _raw_images
from tests.pipeline.test_group import INSTRUCTIONS, S5_RECORDINGS
from tests.pipeline.test_group import _upload as _upload_with_renders
from tests.pipeline.test_plan import (
    CATALOG,
    MODEL,
    PASSPORT,
    PERMIT,
    PHOTO,
    _assert_no_personal_values,
    _catalog_with,
    _count,
    _events,
    _File,
    _image_then_text_pdf_bytes,
    _page,
    _passport,
    _pdf,
    _person,
)
from tests.pipeline.test_plan import _upload as _upload_with_analyses
from tests.pipeline.test_render import _image_page_pdf_bytes

READY_UPLOAD = "u_20260915_0101"
FOLDER = "Test_Ornekova_E0001"
RENDER_DPI = 100


def _execute(session: Session, layout: DataLayout, plan: Plan, item: PlanItem) -> ExecutedItem:
    return execute_ready_item(
        session,
        layout,
        plan,
        item,
        render_image_dpi=RENDER_DPI,
        render_image_jpeg_quality=90,
    )


def _catalog_in_db(session: Session, catalog: Catalog = CATALOG) -> None:
    # `documents.type_slug` katalog tablosuna bağlıdır (yabancı anahtar).
    import_catalog(session, catalog)


def _employee_of(session: Session, item: PlanItem) -> Employee:
    employee = session.get(Employee, item.employee.employee_id)
    assert employee is not None
    return employee


# --- elle kurulan plan -------------------------------------------------------------------------


def _ready_employee(session: Session, layout: DataLayout, employee_id: str = "E0001") -> Employee:
    employee = Employee(
        id=employee_id,
        folder_name=f"Test_Ornekova_{employee_id}",
        given_names="Test",
        surname="Ornekova",
    )
    session.add(employee)
    session.flush()
    layout.ensure_employee_tree(employee.folder_name)
    return employee


def _ready_upload(
    session: Session,
    layout: DataLayout,
    *files: tuple[str, bytes],
    upload_id: str = READY_UPLOAD,
) -> list[UploadFile]:
    upload = Upload(id=upload_id, channel="web", status=UploadStatus.EXECUTING.value)
    session.add(upload)
    rows: list[UploadFile] = []
    for name, content in files:
        stored = write_to_inbox(layout, upload_id, name, content)
        row = UploadFile(
            upload=upload,
            original_name=name,
            stored_path=layout.relative(stored.path),
            sha256=stored.sha256,
            mime="application/octet-stream",
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _ready_item(
    item_id: str,
    sources: list[tuple[int, tuple[int, ...]]],
    *,
    operation: Operation,
    target_name: str,
    slug: str = PERMIT,
    employee_id: str = "E0001",
) -> PlanItem:
    return PlanItem.model_validate(
        {
            "item_id": item_id,
            "document_type_slug": slug,
            "sources": [{"file_id": file_id, "pages": list(pages)} for file_id, pages in sources],
            "operation": operation.value,
            "target_format": target_name.rsplit(".", 1)[1],
            "target_name": target_name,
            "employee": {
                "action": "match",
                "employee_id": employee_id,
                "matched_by": MatchedBy.DOCUMENT_NUMBER.value,
            },
            "route": Route.READY.value,
            "route_reason": None,
            "validations": [{"name": name.value, "ok": True} for name in ValidationName],
        }
    )


def _ready_plan(session: Session, *items: PlanItem, upload_id: str = READY_UPLOAD) -> Plan:
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


def _assert_nothing_written(session: Session, layout: DataLayout, folder: str = FOLDER) -> None:
    assert _files(layout.ready_dir(folder)) == []
    assert _files(layout.received_dir(folder)) == []
    assert _count(session, Document) == 0
    assert _events(session) == []


# --- 07.7.1 — planlanan işlemin çıktısı ve kökeni ----------------------------------------------


def test_output_is_written_atomically_under_hazir_with_its_provenance(
    session: Session, layout: DataLayout
) -> None:
    _catalog_in_db(session)
    upload = _upload_with_analyses(session, layout, _pdf(_passport()))
    (upload_file,) = upload.files
    plan = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
    (item,) = read_plan(plan).items
    assert (item.route, item.operation, item.target_name) == (
        Route.READY,
        Operation.PASSTHROUGH,
        "Test_Ornekova-Passport.pdf",
    )
    planning_events = len(_events(session))

    executed = _execute(session, layout, plan, item)

    employee = _employee_of(session, item)
    assert employee.folder_name == FOLDER
    ready = layout.ready_dir(FOLDER)
    source = layout.resolve(upload_file.stored_path).read_bytes()
    assert executed.output.path == ready / "Test_Ornekova-Passport.pdf"
    assert _files(ready) == ["Test_Ornekova-Passport.pdf"]  # geçici dosya kalmadı
    assert executed.output.path.read_bytes() == source
    document = executed.document
    assert session.get(Document, document.id) is document
    assert (
        document.employee_id,
        document.type_slug,
        document.path,
        document.format,
        document.sequence_no,
        document.plan_id,
        document.status,
    ) == (
        employee.id,
        PASSPORT,
        f"Employees/{FOLDER}/Hazir/Test_Ornekova-Passport.pdf",
        "pdf",
        1,
        plan.id,
        "active",
    )
    assert layout.resolve(document.path) == executed.output.path
    refs = [{"file_id": upload_file.id, "pages": [0]}]
    assert document.source_refs_json == refs
    (saved,) = _events(session)[planning_events:]
    assert (
        saved.type,
        saved.upload_id,
        saved.file_id,
        saved.page_index,
        saved.document_id,
        saved.employee_id,
        saved.message,
    ) == (EventType.OUTPUT_SAVED, upload.id, upload_file.id, 0, document.id, employee.id, None)
    assert saved.data_json == {
        "item_id": "i1",
        "plan_id": plan.id,
        "sources": refs,
        "document_type_slug": PASSPORT,
        "operation": "passthrough",
        "format": "pdf",
        "sequence_no": 1,
        "sha256": upload_file.sha256,
        "received": [{"file_id": upload_file.id, "copied": True}],
    }
    _assert_no_personal_values(session)


def test_same_type_twice_gets_k8_suffix_and_the_shared_source_is_copied_once(
    session: Session, layout: DataLayout
) -> None:
    # Aynı PDF'te aynı kişinin iki pasaport sayfası: iki `extract` öğesi, aynı kaynak dosya.
    _catalog_in_db(session)
    upload = _upload_with_analyses(session, layout, _pdf(_passport(), _passport()))
    (upload_file,) = upload.files
    plan = create_plan(session, layout, upload, catalog=CATALOG, model=MODEL)
    first_item, second_item = read_plan(plan).items

    first = _execute(session, layout, plan, first_item)
    second = _execute(session, layout, plan, second_item)

    assert [result.output.path.name for result in (first, second)] == [
        "Test_Ornekova-Passport.pdf",
        "Test_Ornekova-Passport-2.pdf",
    ]
    assert [result.document.sequence_no for result in (first, second)] == [1, 2]
    for result in (first, second):
        with _open(result.output.path) as output:
            assert output.page_count == 1
    assert [result.document.source_refs_json for result in (first, second)] == [
        [{"file_id": upload_file.id, "pages": [0]}],
        [{"file_id": upload_file.id, "pages": [1]}],
    ]
    received = layout.received_dir(FOLDER)
    assert _files(received) == ["dosya-0"]
    assert [[copy.copied for copy in result.received] for result in (first, second)] == [
        [True],
        [False],
    ]
    assert second.received[0].stored.path == received / "dosya-0"
    extracted = _events(session, EventType.PAGE_EXTRACTED)
    assert [(event.document_id, event.page_index, event.data_json) for event in extracted] == [
        (
            first.document.id,
            0,
            {
                "item_id": "i1",
                "plan_id": plan.id,
                "sources": [{"file_id": upload_file.id, "pages": [0]}],
            },
        ),
        (
            second.document.id,
            1,
            {
                "item_id": "i2",
                "plan_id": plan.id,
                "sources": [{"file_id": upload_file.id, "pages": [1]}],
            },
        ),
    ]
    saved = _events(session, EventType.OUTPUT_SAVED)
    assert [(event.data_json["sequence_no"], event.data_json["received"]) for event in saved] == [
        (1, [{"file_id": upload_file.id, "copied": True}]),
        (2, [{"file_id": upload_file.id, "copied": False}]),
    ]
    _assert_no_personal_values(session)


def test_s5_merge_output_keeps_source_order_in_provenance_and_copies_both_originals(
    session: Session, layout: DataLayout
) -> None:
    # S5: aynı partide ehliyetin ön ve arka yüzü iki JPEG; tek `merge` çıktısı, iki Alinan kopyası.
    front = ("on.jpg", make_half_filled_image_bytes("JPEG", size=(300, 190)))
    back = ("arka.jpg", make_half_filled_image_bytes("JPEG", size=(310, 195)))
    upload = _upload_with_renders(session, layout, [front, back])
    analyze_upload(
        session,
        layout,
        upload,
        provider=RecordingProvider.from_directory(S5_RECORDINGS),
        instructions=INSTRUCTIONS,
    )
    plan = create_plan(session, layout, upload, catalog=CATALOG)
    (item,) = read_plan(plan).items
    assert (item.route, item.operation) == (Route.READY, Operation.MERGE)
    _catalog_in_db(session)
    files = {upload_file.original_name: upload_file for upload_file in upload.files}

    executed = _execute(session, layout, plan, item)

    folder = _employee_of(session, item).folder_name
    assert item.target_name is not None
    assert executed.output.path == layout.ready_dir(folder) / item.target_name
    with _open(executed.output.path) as output:
        assert [_raw_images(output, index) for index in (0, 1)] == [[front[1]], [back[1]]]
    refs = [
        {"file_id": files["on.jpg"].id, "pages": [0]},
        {"file_id": files["arka.jpg"].id, "pages": [0]},
    ]
    assert (executed.document.format, executed.document.source_refs_json) == ("pdf", refs)
    received = layout.received_dir(folder)
    assert _files(received) == ["arka.jpg", "on.jpg"]
    assert (received / "on.jpg").read_bytes() == front[1]
    assert (received / "arka.jpg").read_bytes() == back[1]
    (merged,) = _events(session, EventType.PAGES_MERGED)
    (saved,) = _events(session, EventType.OUTPUT_SAVED)
    for event in (merged, saved):
        assert (event.file_id, event.page_index, event.document_id) == (
            files["on.jpg"].id,
            0,
            executed.document.id,
        )
    assert merged.data_json == {"item_id": item.item_id, "plan_id": plan.id, "sources": refs}
    assert saved.data_json["received"] == [
        {"file_id": files["on.jpg"].id, "copied": True},
        {"file_id": files["arka.jpg"].id, "copied": True},
    ]


def test_extract_image_and_render_image_outputs_are_recorded_with_their_pages(
    session: Session, layout: DataLayout
) -> None:
    # §20.3 satır 5 ve 6: JPEG çıktılı türde taranmış sayfanın gömülü görüntüsü çıkarılır, metin
    # sayfası yapılandırılan DPI'da render edilir; aynı türün ikinci çıktısı `-2` alır.
    catalog = _catalog_with(
        PERMIT, output_format="jpeg", allowed_conversions=["extract_image", "render_image"]
    )
    _catalog_in_db(session, catalog)
    permit = _page(PERMIT, person=_person(document_number="WP-0000042"))
    upload = _upload_with_analyses(
        session, layout, _File(pages=(permit, permit), content=_image_then_text_pdf_bytes())
    )
    (upload_file,) = upload.files
    mark_upload_file_single_image_pages(session, layout, upload_file)
    plan = create_plan(session, layout, upload, catalog=catalog, model=MODEL)
    extract_item, render_item = read_plan(plan).items
    assert (extract_item.operation, render_item.operation) == (
        Operation.EXTRACT_IMAGE,
        Operation.RENDER_IMAGE,
    )
    assert extract_item.employee.employee_id == render_item.employee.employee_id

    extracted = _execute(session, layout, plan, extract_item)
    rendered = _execute(session, layout, plan, render_item)

    assert [result.output.path.name for result in (extracted, rendered)] == [
        "Test_Ornekova-Work-Permit.jpeg",
        "Test_Ornekova-Work-Permit-2.jpeg",
    ]
    assert extracted.output.path.read_bytes() == make_half_filled_image_bytes(size=(60, 85))
    with pymupdf.open(stream=layout.resolve(upload_file.stored_path).read_bytes()) as source:
        expected = source[1].get_pixmap(dpi=RENDER_DPI, alpha=False)
    raster = pymupdf.Pixmap(str(rendered.output.path))
    assert (raster.width, raster.height) == (expected.width, expected.height)
    assert [
        (result.document.format, result.document.source_refs_json)
        for result in (extracted, rendered)
    ] == [
        ("jpeg", [{"file_id": upload_file.id, "pages": [0]}]),
        ("jpeg", [{"file_id": upload_file.id, "pages": [1]}]),
    ]
    image_events = [
        (event.type, event.page_index, event.document_id)
        for event in _events(session)
        if event.type in (EventType.IMAGE_EXTRACTED, EventType.IMAGE_RENDERED)
    ]
    assert image_events == [
        (EventType.IMAGE_EXTRACTED, 0, extracted.document.id),
        (EventType.IMAGE_RENDERED, 1, rendered.document.id),
    ]
    assert _files(layout.received_dir(FOLDER)) == ["dosya-0"]


def test_wrap_image_output_is_a_pdf_recorded_with_image_wrapped(
    session: Session, layout: DataLayout
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    jpeg = make_half_filled_image_bytes("JPEG", size=(300, 190))
    (image_file,) = _ready_upload(session, layout, ("izin.jpg", jpeg))
    item = _ready_item(
        "i1",
        [(image_file.id, (0,))],
        operation=Operation.WRAP_IMAGE,
        target_name="Test_Ornekova-Work-Permit.pdf",
    )
    plan = _ready_plan(session, item)

    executed = _execute(session, layout, plan, item)

    with _open(executed.output.path) as output:
        assert output.page_count == 1
        assert _raw_images(output, 0) == [jpeg]
    assert executed.document.format == "pdf"
    (wrapped,) = _events(session, EventType.IMAGE_WRAPPED)
    assert (wrapped.file_id, wrapped.page_index, wrapped.document_id, wrapped.data_json) == (
        image_file.id,
        0,
        executed.document.id,
        {
            "item_id": "i1",
            "plan_id": plan.id,
            "sources": [{"file_id": image_file.id, "pages": [0]}],
        },
    )
    assert [event.type for event in _events(session)] == [
        EventType.IMAGE_WRAPPED,
        EventType.OUTPUT_SAVED,
    ]


def test_embedded_png_takes_its_real_extension_and_the_next_sequence_of_the_stem(
    session: Session, layout: DataLayout
) -> None:
    # §20.5: gömülü görüntü PNG ise uzantı gerçek biçimdir; `.jpeg` gövdesi dolu olduğu için `-2`.
    _catalog_in_db(session)
    _ready_employee(session, layout)
    png = make_half_filled_image_bytes("PNG", size=(60, 85))
    (pdf_file,) = _ready_upload(session, layout, ("tarama.pdf", _image_page_pdf_bytes(image=png)))
    earlier = layout.ready_dir(FOLDER) / "Test_Ornekova-Profile-Picture.jpeg"
    earlier.write_bytes(b"onceki cikti")
    item = _ready_item(
        "i1",
        [(pdf_file.id, (0,))],
        slug=PHOTO,
        operation=Operation.EXTRACT_IMAGE,
        target_name="Test_Ornekova-Profile-Picture.jpeg",
    )
    plan = _ready_plan(session, item)

    executed = _execute(session, layout, plan, item)

    assert executed.output.path.name == "Test_Ornekova-Profile-Picture-2.png"
    assert (executed.document.format, executed.document.sequence_no) == ("png", 2)
    assert executed.document.path == f"Employees/{FOLDER}/Hazir/Test_Ornekova-Profile-Picture-2.png"
    assert earlier.read_bytes() == b"onceki cikti"
    (saved,) = _events(session, EventType.OUTPUT_SAVED)
    assert (saved.data_json["format"], saved.data_json["sequence_no"]) == ("png", 2)


def test_whole_file_attachment_is_recorded_with_empty_page_range(
    session: Session, layout: DataLayout
) -> None:
    # K2: Word eki sayfasızdır; köken dosyanın bütünüdür (`pages: []`), olayda sayfa yok.
    _catalog_in_db(session)
    _ready_employee(session, layout)
    docx = make_docx_bytes()
    (word_file,) = _ready_upload(session, layout, ("cv.docx", docx))
    item = _ready_item(
        "i1",
        [(word_file.id, ())],
        slug="attachment",
        operation=Operation.PASSTHROUGH,
        target_name="Test_Ornekova-Attachment.docx",
    )
    plan = _ready_plan(session, item)

    executed = _execute(session, layout, plan, item)

    assert executed.output.path.read_bytes() == docx
    assert (executed.document.format, executed.document.source_refs_json) == (
        "docx",
        [{"file_id": word_file.id, "pages": []}],
    )
    (saved,) = _events(session)
    assert (saved.type, saved.file_id, saved.page_index) == (
        EventType.OUTPUT_SAVED,
        word_file.id,
        None,
    )
    assert (layout.received_dir(FOLDER) / "cv.docx").read_bytes() == docx


# --- 07.7.2 — Alinan kopyası -------------------------------------------------------------------


def test_received_copy_is_skipped_for_same_hash_from_another_upload(
    session: Session, layout: DataLayout
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    content = make_text_pdf_bytes(["IZIN"])
    (first_file,) = _ready_upload(session, layout, ("tarama.pdf", content))
    first_plan = _ready_plan(
        session,
        _ready_item(
            "i1",
            [(first_file.id, (0,))],
            operation=Operation.PASSTHROUGH,
            target_name="Test_Ornekova-Work-Permit.pdf",
        ),
    )
    _execute(session, layout, first_plan, read_plan(first_plan).items[0])
    later_upload = "u_20260915_0102"
    again, other = _ready_upload(
        session,
        layout,
        ("yeniden.pdf", content),
        ("tarama.pdf", make_text_pdf_bytes(["BASKA IZIN"])),
        upload_id=later_upload,
    )
    later_plan = _ready_plan(
        session,
        *(
            _ready_item(
                item_id,
                [(upload_file.id, (0,))],
                operation=Operation.PASSTHROUGH,
                target_name="Test_Ornekova-Work-Permit.pdf",
            )
            for item_id, upload_file in (("i1", again), ("i2", other))
        ),
        upload_id=later_upload,
    )
    same, different = (
        _execute(session, layout, later_plan, item) for item in read_plan(later_plan).items
    )

    received = layout.received_dir(FOLDER)
    assert (same.received[0].copied, same.received[0].stored.path) == (
        False,
        received / "tarama.pdf",
    )
    assert (different.received[0].copied, different.received[0].stored.path) == (
        True,
        received / "tarama-2.pdf",
    )
    assert _files(received) == ["tarama-2.pdf", "tarama.pdf"]
    assert (received / "tarama.pdf").read_bytes() == content
    assert _files(layout.ready_dir(FOLDER)) == [
        "Test_Ornekova-Work-Permit-2.pdf",
        "Test_Ornekova-Work-Permit-3.pdf",
        "Test_Ornekova-Work-Permit.pdf",
    ]


def test_each_employee_receives_its_own_copy_of_a_shared_source(
    session: Session, layout: DataLayout
) -> None:
    # Bir dosyada iki kişinin belgesi: Alinan çalışan başınadır, tekillik de çalışan klasöründe.
    _catalog_in_db(session)
    first_employee = _ready_employee(session, layout, "E0001")
    second_employee = _ready_employee(session, layout, "E0002")
    content = make_text_pdf_bytes(["BIR", "IKI"])
    (shared,) = _ready_upload(session, layout, ("iki-kisi.pdf", content))
    items = [
        _ready_item(
            f"i{page + 1}",
            [(shared.id, (page,))],
            operation=Operation.EXTRACT,
            target_name="Test_Ornekova-Work-Permit.pdf",
            employee_id=employee.id,
        )
        for page, employee in enumerate((first_employee, second_employee))
    ]
    plan = _ready_plan(session, *items)

    results = [_execute(session, layout, plan, item) for item in items]

    assert [result.received[0].copied for result in results] == [True, True]
    for employee in (first_employee, second_employee):
        assert (layout.received_dir(employee.folder_name) / "iki-kisi.pdf").read_bytes() == content
    assert [result.document.employee_id for result in results] == ["E0001", "E0002"]


# --- hiçbir şey yazılmayan durumlar ------------------------------------------------------------


JPEG_FRONT = make_half_filled_image_bytes("JPEG", size=(300, 190))
JPEG_BACK = make_half_filled_image_bytes("JPEG", size=(310, 195))


@pytest.mark.parametrize(
    ("operation", "slug", "target_name", "files", "pages", "error"),
    [
        pytest.param(
            Operation.EXTRACT_IMAGE,
            PHOTO,
            "Test_Ornekova-Profile-Picture.jpeg",
            [("metin.pdf", make_text_pdf_bytes(["METIN"]))],
            [(0,)],
            ExtractImageSourceError,
            id="extract_image-sayfa-tek-goruntu-degil",
        ),
        pytest.param(
            Operation.MERGE,
            PASSPORT,
            "Test_Ornekova-Passport.pdf",
            [("on.jpg", JPEG_FRONT), ("arka.jpg", JPEG_BACK)],
            [(0,), (0,)],
            DirectDocumentMergeError,
            id="merge-direkt-belge",
        ),
        pytest.param(
            Operation.EXTRACT,
            PERMIT,
            "Test_Ornekova-Work-Permit.pdf",
            [("tek.pdf", make_pdf_bytes(1))],
            [(3,)],
            ExtractSourceError,
            id="extract-sayfa-yok",
        ),
        pytest.param(
            Operation.WRAP_IMAGE,
            PERMIT,
            "Test_Ornekova-Work-Permit.pdf",
            [("belge.pdf", make_pdf_bytes(1))],
            [(0,)],
            WrapImageSourceError,
            id="wrap_image-goruntu-degil",
        ),
        pytest.param(
            Operation.PASSTHROUGH,
            PERMIT,
            "Test_Ornekova-Work-Permit.pdf",
            [("a.pdf", make_pdf_bytes(1)), ("b.pdf", make_pdf_bytes(2))],
            [(0,), (0,)],
            ValueError,
            id="passthrough-iki-kaynak",
        ),
        pytest.param(
            Operation.RENDER_IMAGE,
            PHOTO,
            "Test_Ornekova-Profile-Picture.jpeg",
            [("iki.pdf", make_pdf_bytes(2))],
            [(0, 1)],
            ValueError,
            id="render_image-iki-sayfa",
        ),
    ],
)
def test_failed_operation_writes_no_output_copy_row_or_event(
    session: Session,
    layout: DataLayout,
    operation: Operation,
    slug: str,
    target_name: str,
    files: list[tuple[str, bytes]],
    pages: list[tuple[int, ...]],
    error: type[Exception],
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    rows = _ready_upload(session, layout, *files)
    item = _ready_item(
        "i1",
        [(row.id, row_pages) for row, row_pages in zip(rows, pages, strict=True)],
        slug=slug,
        operation=operation,
        target_name=target_name,
    )
    plan = _ready_plan(session, item)

    with pytest.raises(error):
        _execute(session, layout, plan, item)

    _assert_nothing_written(session, layout)


def test_queued_item_is_not_executed(session: Session, layout: DataLayout) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    (pdf_file,) = _ready_upload(session, layout, ("belge.pdf", make_pdf_bytes(1)))
    item = PlanItem.model_validate(
        {
            "item_id": "i1",
            "document_type_slug": PERMIT,
            "sources": [{"file_id": pdf_file.id, "pages": [0]}],
            "operation": None,
            "target_format": None,
            "target_name": None,
            "employee": {"action": "none", "employee_id": None, "matched_by": None},
            "route": Route.UNRESOLVED.value,
            "route_reason": "Gerekçe.",
            "validations": [],
        }
    )
    plan = _ready_plan(session, item)

    with pytest.raises(ValueError, match="hazir"):
        _execute(session, layout, plan, item)

    _assert_nothing_written(session, layout)


@pytest.mark.parametrize("missing", ["employee", "type", "file", "file-of-another-upload"])
def test_unknown_reference_is_refused_before_reading_any_source(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    (pdf_file,) = _ready_upload(session, layout, ("belge.pdf", make_pdf_bytes(1)))
    (foreign_file,) = _ready_upload(
        session, layout, ("baska.pdf", make_pdf_bytes(1)), upload_id="u_20260915_0199"
    )
    file_id = {"file": 999, "file-of-another-upload": foreign_file.id}.get(missing, pdf_file.id)
    item = _ready_item(
        "i1",
        [(file_id, (0,))],
        operation=Operation.PASSTHROUGH,
        target_name="Test_Ornekova-Work-Permit.pdf",
        slug="not_in_catalog" if missing == "type" else PERMIT,
        employee_id="E0009" if missing == "employee" else "E0001",
    )
    plan = _ready_plan(session, item)

    def _no_read(_path: Path) -> str:
        raise AssertionError("kaynak okunmamalı")

    monkeypatch.setattr(execute_module, "sha256_file", _no_read)

    with pytest.raises(PlanItemReferenceError):
        _execute(session, layout, plan, item)

    _assert_nothing_written(session, layout)


def test_changed_inbox_original_is_refused(session: Session, layout: DataLayout) -> None:
    # K10: Inbox'taki dosya yüklemede kaydedilen hash'i taşımıyorsa köken kanıtlanamaz.
    _catalog_in_db(session)
    _ready_employee(session, layout)
    (pdf_file,) = _ready_upload(session, layout, ("belge.pdf", make_pdf_bytes(1)))
    layout.resolve(pdf_file.stored_path).write_bytes(make_pdf_bytes(2))
    item = _ready_item(
        "i1",
        [(pdf_file.id, (0,))],
        operation=Operation.PASSTHROUGH,
        target_name="Test_Ornekova-Work-Permit.pdf",
    )
    plan = _ready_plan(session, item)

    with pytest.raises(SourceIntegrityError, match="K10"):
        _execute(session, layout, plan, item)

    _assert_nothing_written(session, layout)


def test_passthrough_copy_not_matching_the_source_is_not_published(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    (pdf_file,) = _ready_upload(session, layout, ("belge.pdf", make_pdf_bytes(1)))
    item = _ready_item(
        "i1",
        [(pdf_file.id, (0,))],
        operation=Operation.PASSTHROUGH,
        target_name="Test_Ornekova-Work-Permit.pdf",
    )
    plan = _ready_plan(session, item)

    def _other_bytes(_path: Path) -> Iterator[bytes]:
        yield b"baska bir icerik"

    monkeypatch.setattr(execute_module, "iter_file_chunks", _other_bytes)

    with pytest.raises(PassthroughIntegrityError):
        _execute(session, layout, plan, item)

    _assert_nothing_written(session, layout)


# --- eşzamanlılık ------------------------------------------------------------------------------


@pytest.mark.parametrize(("dialect", "locks"), [("postgresql", 1), ("sqlite", 0)])
def test_received_copies_of_an_employee_are_serialized_on_postgresql(
    dialect: str, locks: int
) -> None:
    # SQLite işlemi `BEGIN IMMEDIATE` ile zaten yazma kilidindedir; PostgreSQL'de çalışan başına
    # işlem ömürlü advisory kilit alınır.
    statements: list[Any] = []
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name=dialect)),
        execute=statements.append,
    )

    execute_module._lock_employee_outputs(session, "E0001")  # type: ignore[arg-type]
    execute_module._lock_employee_outputs(session, "E0002")  # type: ignore[arg-type]

    assert len(statements) == 2 * locks
    if locks:
        assert all("pg_advisory_xact_lock" in str(statement) for statement in statements)
        keys = [next(iter(statement.compile().params.values())) for statement in statements]
        assert keys[0] != keys[1]
