"""07.8.1 — uygulayıcı idempotenliği: aynı plan ikinci kez uygulanınca ikinci dosya üretilmez (S18).

Öğe planın kimliği ve kaynaklarıyla tanınır (`documents.plan_id` + `source_refs_json`); uygulanmış
öğe yeniden yürütülmez, `OUTPUT_SKIPPED` loglanır. Geri alınmış uygulamanın diskte kalan çıktısı
ikinci kez yazılmaz, kaydedilir — bu yüzden altı işlemin her biri aynı girdiden aynı baytları
üretmelidir. Dosyalar `tests/fixtures/gen.py` ile üretilen sentetik belgelerdir (CONVENTIONS §6);
yapay zekâ yanıtları kayıtlıdır.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, tzinfo
from itertools import count
from pathlib import Path
from typing import Any

import img2pdf
import pytest
from pypdf import PdfReader
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.pipeline.execute as execute_module
from app.db.models import Document, DocumentStatus, Plan, UploadFile
from app.db.session import create_session_factory
from app.events import EventType
from app.pipeline.execute import (
    SKIPPED_DELETED,
    ExecutedItem,
    execute_wrap_image,
    executed_document,
)
from app.pipeline.orchestrate import rerun_plan
from app.pipeline.plan import Operation, PlanDocument, PlanItem, Route, create_plan, read_plan
from app.storage import DataLayout, delete_document, remove_document_files, sha256_file
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes, make_text_pdf_bytes
from tests.pipeline.test_execute import _files
from tests.pipeline.test_execute_output import (
    FOLDER,
    JPEG_BACK,
    JPEG_FRONT,
    READY_UPLOAD,
    _catalog_in_db,
    _execute,
    _ready_employee,
    _ready_item,
    _ready_plan,
    _ready_upload,
)
from tests.pipeline.test_orchestrate import (
    CATALOG,
    READY_NAME,
    _forbid_ai,
    _passport_upload,
)
from tests.pipeline.test_plan import (
    MODEL,
    PERMIT,
    PHOTO,
    _assert_no_personal_values,
    _count,
    _events,
)
from tests.pipeline.test_render import _image_page_pdf_bytes

PERMIT_NAME = "Test_Ornekova-Work-Permit.pdf"
PHOTO_NAME = "Test_Ornekova-Profile-Picture.jpeg"

# Her işlemin bir öğesi: (işlem, tür, hedef adı, parti dosyaları, dosya başına sayfalar).
OPERATIONS = [
    pytest.param(
        Operation.PASSTHROUGH,
        PERMIT,
        PERMIT_NAME,
        [("izin.pdf", make_text_pdf_bytes(["IZIN"]))],
        [(0,)],
        id="passthrough",
    ),
    pytest.param(
        Operation.EXTRACT,
        PERMIT,
        PERMIT_NAME,
        [("iki.pdf", make_text_pdf_bytes(["BIR", "IZIN"]))],
        [(1,)],
        id="extract",
    ),
    pytest.param(
        Operation.MERGE,
        PERMIT,
        PERMIT_NAME,
        [("on.jpg", JPEG_FRONT), ("arka.pdf", make_text_pdf_bytes(["ARKA"]))],
        [(0,), (0,)],
        id="merge",
    ),
    pytest.param(
        Operation.WRAP_IMAGE,
        PERMIT,
        PERMIT_NAME,
        [("izin.jpg", JPEG_BACK)],
        [(0,)],
        id="wrap_image",
    ),
    pytest.param(
        Operation.WRAP_IMAGE,
        PERMIT,
        PERMIT_NAME,
        [("izin.png", make_half_filled_image_bytes("PNG", size=(120, 80)))],
        [(0,)],
        id="wrap_image-png",
    ),
    pytest.param(
        Operation.EXTRACT_IMAGE,
        PHOTO,
        PHOTO_NAME,
        [("tarama.pdf", _image_page_pdf_bytes(image=make_half_filled_image_bytes(size=(60, 85))))],
        [(0,)],
        id="extract_image",
    ),
    pytest.param(
        Operation.RENDER_IMAGE,
        PHOTO,
        PHOTO_NAME,
        [("metin.pdf", make_text_pdf_bytes(["FOTO"]))],
        [(0,)],
        id="render_image",
    ),
]


def _one_item_plan(
    session: Session,
    layout: DataLayout,
    operation: Operation,
    slug: str,
    target_name: str,
    files: list[tuple[str, bytes]],
    pages: list[tuple[int, ...]],
) -> tuple[Plan, PlanItem]:
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
    return _ready_plan(session, item), item


def _snapshot(layout: DataLayout, folder: str = FOLDER) -> dict[str, dict[str, str]]:
    """Çalışan klasörünün diskteki hâli: `Hazir/` ve `Alinan/` dosyalarının adı ve SHA-256'sı."""
    return {
        directory.name: {path.name: sha256_file(path) for path in sorted(directory.iterdir())}
        for directory in (layout.ready_dir(folder), layout.received_dir(folder))
    }


def _skipped(session: Session) -> list[Any]:
    return _events(session, EventType.OUTPUT_SKIPPED)


def _documents(session: Session) -> list[Document]:
    return list(session.scalars(select(Document).order_by(Document.id)))


# --- uygulanmış öğe yeniden yürütülmez ---------------------------------------------------------


def test_second_application_writes_nothing_and_returns_the_first_output(
    session: Session, layout: DataLayout
) -> None:
    plan, item = _one_item_plan(
        session,
        layout,
        Operation.EXTRACT,
        PERMIT,
        PERMIT_NAME,
        [("iki.pdf", make_text_pdf_bytes(["BIR", "IZIN"]))],
        [(1,)],
    )
    first = _execute(session, layout, plan, item)
    disk = _snapshot(layout)
    logged = [event.id for event in _events(session)]

    again = _execute(session, layout, plan, item)

    assert first.applied and not again.applied
    assert again == ExecutedItem(first.document, None, ())
    assert _snapshot(layout) == disk
    assert list(disk["Hazir"]) == [PERMIT_NAME]
    assert _count(session, Document) == 1
    added = [event for event in _events(session) if event.id not in logged]
    assert [
        (
            event.type,
            event.upload_id,
            event.file_id,
            event.page_index,
            event.document_id,
            event.employee_id,
            event.message,
        )
        for event in added
    ] == [
        (
            EventType.OUTPUT_SKIPPED,
            READY_UPLOAD,
            item.sources[0].file_id,
            1,
            first.document.id,
            "E0001",
            None,
        )
    ]
    assert added[0].data_json == {
        "item_id": "i1",
        "plan_id": plan.id,
        "sources": [{"file_id": item.sources[0].file_id, "pages": [1]}],
    }
    _assert_no_personal_values(session)


@pytest.mark.parametrize(("operation", "slug", "target_name", "files", "pages"), OPERATIONS)
def test_committed_plan_applied_again_produces_no_second_file(
    session: Session,
    layout: DataLayout,
    operation: Operation,
    slug: str,
    target_name: str,
    files: list[tuple[str, bytes]],
    pages: list[tuple[int, ...]],
) -> None:
    plan, item = _one_item_plan(session, layout, operation, slug, target_name, files, pages)
    first = _execute(session, layout, plan, item)
    session.commit()
    disk = _snapshot(layout)

    for _ in range(2):
        again = _execute(session, layout, plan, read_plan(plan).items[0])
        session.commit()
        assert again.document.id == first.document.id
        assert not again.applied

    assert _snapshot(layout) == disk
    assert len(disk["Hazir"]) == 1
    assert _count(session, Document) == 1
    assert len(_events(session, EventType.OUTPUT_SAVED)) == 1
    assert [event.document_id for event in _skipped(session)] == [first.document.id] * 2


def test_already_applied_item_reads_no_source_and_runs_no_operation(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, item = _one_item_plan(
        session,
        layout,
        Operation.PASSTHROUGH,
        PERMIT,
        PERMIT_NAME,
        [("izin.pdf", make_pdf_bytes(1))],
        [(0,)],
    )
    first = _execute(session, layout, plan, item)

    def _refuse(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("uygulanmış öğede kaynak okunmamalı, işlem yürümemeli")

    for name in ("sha256_file", "_ready_output", "find_sequenced", "copy_to_received"):
        monkeypatch.setattr(execute_module, name, _refuse)
    # Inbox'taki kaynak sonradan değişmiş olsa da uygulanmış öğe için okunacak bir şey yok.
    upload_file = session.get_one(UploadFile, item.sources[0].file_id)
    layout.resolve(upload_file.stored_path).write_bytes(make_pdf_bytes(2))

    again = _execute(session, layout, plan, item)

    assert again.document is first.document and not again.applied


def test_moved_or_superseded_output_still_counts_as_applied(
    session: Session, layout: DataLayout
) -> None:
    # Satırın sahibi ve durumu sonradan değişse de (K16 taşıma, K18 eski sürüm) öğe uygulanmıştır;
    # yeniden uygulama ilk çalışanın `Hazir/`'ına çıktıyı geri getirmez.
    plan, item = _one_item_plan(
        session,
        layout,
        Operation.PASSTHROUGH,
        PERMIT,
        PERMIT_NAME,
        [("izin.pdf", make_pdf_bytes(1))],
        [(0,)],
    )
    first = _execute(session, layout, plan, item)
    other = _ready_employee(session, layout, "E0002")
    moved = layout.ready_dir(other.folder_name) / PERMIT_NAME
    first.output.path.rename(moved)  # type: ignore[union-attr]
    first.document.employee_id = other.id
    first.document.path = layout.relative(moved)
    first.document.status = DocumentStatus.SUPERSEDED.value
    session.commit()

    again = _execute(session, layout, plan, item)

    assert again.document is first.document and not again.applied
    assert _files(layout.ready_dir(FOLDER)) == []
    (skipped,) = _skipped(session)
    assert (skipped.document_id, skipped.employee_id) == (first.document.id, "E0002")


def test_executed_document_finds_the_output_of_the_item_only(
    session: Session, layout: DataLayout
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    (pdf_file,) = _ready_upload(session, layout, ("iki.pdf", make_text_pdf_bytes(["A", "B"])))
    items = [
        _ready_item(
            f"i{page + 1}",
            [(pdf_file.id, (page,))],
            operation=Operation.EXTRACT,
            target_name=PERMIT_NAME,
        )
        for page in (0, 1)
    ]
    plan = _ready_plan(session, *items)

    assert [executed_document(session, plan, item) for item in items] == [None, None]
    first = _execute(session, layout, plan, items[0])

    assert [executed_document(session, plan, item) for item in items] == [first.document, None]


# --- geri alınmış uygulamanın diskte kalan çıktısı --------------------------------------------


@pytest.mark.parametrize(("operation", "slug", "target_name", "files", "pages"), OPERATIONS)
def test_output_left_by_a_rolled_back_application_is_recorded_not_written_again(
    session: Session,
    layout: DataLayout,
    operation: Operation,
    slug: str,
    target_name: str,
    files: list[tuple[str, bytes]],
    pages: list[tuple[int, ...]],
) -> None:
    # Dosya sistemi işleme bağlı değildir: geri alınan uygulamanın çıktısı ve Alinan kopyası diskte
    # kalır, satırı ve olayları kalmaz. İşlem aynı baytları ürettiği için ikinci dosya yazılmaz.
    plan, item = _one_item_plan(session, layout, operation, slug, target_name, files, pages)
    session.commit()
    lost = _execute(session, layout, plan, item)
    assert lost.output is not None
    session.rollback()
    assert (_count(session, Document), _events(session)) == (0, [])
    disk = _snapshot(layout)

    recovered = _execute(session, layout, plan, read_plan(plan).items[0])

    assert recovered.applied
    assert recovered.output == lost.output
    assert _snapshot(layout) == disk
    assert len(disk["Hazir"]) == 1
    assert (recovered.document.path, recovered.document.sequence_no) == (
        layout.relative(lost.output.path),
        1,
    )
    assert [copy.copied for copy in recovered.received] == [False] * len(files)
    (saved,) = _events(session, EventType.OUTPUT_SAVED)
    assert (saved.document_id, saved.data_json["sha256"], saved.data_json["sequence_no"]) == (
        recovered.document.id,
        lost.output.sha256,
        1,
    )


@pytest.mark.parametrize(
    "image",
    [JPEG_BACK, make_half_filled_image_bytes("PNG", size=(120, 80))],
    ids=["jpeg", "png"],
)
def test_wrapped_image_does_not_depend_on_the_time_of_wrapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, image: bytes
) -> None:
    # img2pdf varsayılanıyla oluşturma tarihini (ve pikepdf yazıcısıyla zamana bağlı `/ID`'yi)
    # yazar; saat ilerlese de aynı görüntü aynı baytlara sarılmalı ki geri alınmış uygulamanın
    # çıktısı tanınsın.
    moments = (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day) for day in count())

    class _Clock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return next(moments)

    monkeypatch.setattr(img2pdf, "datetime", _Clock)
    source = tmp_path / "izin"
    source.write_bytes(image)

    first = execute_wrap_image(source, tmp_path / "bir.pdf")
    second = execute_wrap_image(source, tmp_path / "iki.pdf")

    assert first.sha256 == second.sha256
    assert next(moments) >= datetime(2026, 1, 3, tzinfo=UTC)  # saat gerçekten okundu
    # pikepdf'in `/ID`'si C tarafında saatten türer, sahte saat onu değiştirmez: kimlik hiç yok.
    assert "/ID" not in PdfReader(first.path).trailer


def test_identical_outputs_of_two_items_are_recorded_separately_after_a_rollback(
    session: Session, layout: DataLayout
) -> None:
    # İki aynı sayfa: iki `extract` öğesi aynı baytları üretir. Bir satırın gösterdiği dosya başka
    # öğeye verilmez — geri almadan sonra da her öğe kendi dosyasını bulur, üçüncü dosya yok.
    _catalog_in_db(session)
    _ready_employee(session, layout)
    (pdf_file,) = _ready_upload(session, layout, ("iki.pdf", make_text_pdf_bytes(["IZIN", "IZIN"])))
    items = [
        _ready_item(
            f"i{page + 1}",
            [(pdf_file.id, (page,))],
            operation=Operation.EXTRACT,
            target_name=PERMIT_NAME,
        )
        for page in (0, 1)
    ]
    plan = _ready_plan(session, *items)
    session.commit()
    lost = [_execute(session, layout, plan, item) for item in items]
    names = [PERMIT_NAME, "Test_Ornekova-Work-Permit-2.pdf"]
    assert [result.output.path.name for result in lost] == names  # type: ignore[union-attr]
    assert len({result.output.sha256 for result in lost}) == 1  # type: ignore[union-attr]
    session.rollback()

    recovered = [_execute(session, layout, plan, item) for item in items]
    session.commit()

    assert [result.output.path.name for result in recovered] == names  # type: ignore[union-attr]
    assert [result.document.sequence_no for result in recovered] == [1, 2]
    assert _files(layout.ready_dir(FOLDER)) == sorted(names)
    assert [_execute(session, layout, plan, item).applied for item in items] == [False, False]
    assert _files(layout.ready_dir(FOLDER)) == sorted(names)


def test_output_recorded_for_another_plan_version_is_not_taken_over(
    session: Session, layout: DataLayout
) -> None:
    # K18: yeni plan sürümü aynı içerikte bile yeni çıktı üretir; eski sürümün dosyası ve satırı
    # yerinde kalır, yeni sürümün öğesi onu kendi çıktısı saymaz.
    plan, item = _one_item_plan(
        session,
        layout,
        Operation.PASSTHROUGH,
        PERMIT,
        PERMIT_NAME,
        [("izin.pdf", make_pdf_bytes(1))],
        [(0,)],
    )
    first = _execute(session, layout, plan, item)
    document = PlanDocument(upload_id=READY_UPLOAD, version=2, model=MODEL, items=(item,))
    next_version = Plan(
        upload_id=READY_UPLOAD,
        version=2,
        json=document.model_dump(mode="json"),
        model=MODEL,
        plan_hash=document.plan_hash,
    )
    session.add(next_version)
    session.flush()

    second = _execute(session, layout, next_version, item)

    assert second.applied
    assert second.output.path.name == "Test_Ornekova-Work-Permit-2.pdf"  # type: ignore[union-attr]
    assert first.output.path.read_bytes() == second.output.path.read_bytes()  # type: ignore[union-attr]
    assert [output.plan_id for output in (first.document, second.document)] == [
        plan.id,
        next_version.id,
    ]


# --- eşzamanlılık ------------------------------------------------------------------------------


def test_the_check_runs_under_the_employee_lock(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, item = _one_item_plan(
        session,
        layout,
        Operation.PASSTHROUGH,
        PERMIT,
        PERMIT_NAME,
        [("izin.pdf", make_pdf_bytes(1))],
        [(0,)],
    )
    calls: list[str] = []
    lock, check = execute_module._lock_employee_outputs, execute_module.executed_document

    def _lock(*args: Any) -> None:
        calls.append("lock")
        lock(*args)

    def _check(*args: Any) -> Document | None:
        calls.append("check")
        return check(*args)

    monkeypatch.setattr(execute_module, "_lock_employee_outputs", _lock)
    monkeypatch.setattr(execute_module, "executed_document", _check)

    _execute(session, layout, plan, item)

    assert calls == ["lock", "check"]


def test_concurrent_applications_of_the_same_item_publish_one_output(
    session: Session, layout: DataLayout, engine: Engine
) -> None:
    # Aynı öğeyi iki işlem aynı anda uygular: ikincisi ilkinin commit'ini bekler ve satırını görür.
    plan, _item = _one_item_plan(
        session,
        layout,
        Operation.PASSTHROUGH,
        PERMIT,
        PERMIT_NAME,
        [("izin.pdf", make_pdf_bytes(1))],
        [(0,)],
    )
    session.commit()
    plan_id = plan.id
    factory = create_session_factory(engine)

    def _apply(_: int) -> tuple[bool, int]:
        with factory() as worker:
            row = worker.get_one(Plan, plan_id)
            result = _execute(worker, layout, row, read_plan(row).items[0])
            worker.commit()
            return result.applied, result.document.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_apply, range(2)))

    assert sorted(applied for applied, _ in results) == [False, True]
    assert len({document_id for _, document_id in results}) == 1
    assert _files(layout.ready_dir(FOLDER)) == [PERMIT_NAME]
    assert _count(session, Document) == 1


# --- S18: mevcut plandan yeniden çalıştırma ----------------------------------------------------


def _apply_ready_items(
    session: Session, layout: DataLayout, plan: Plan, document: PlanDocument
) -> None:
    """`PlanExecutor` sözleşmesiyle planın `hazir` öğelerini gerçek uygulayıcıyla yürütür."""
    for item in document.items:
        if item.route is Route.READY:
            _execute(session, layout, plan, item)


def test_s18_rerun_from_the_existing_plan_gives_the_same_outputs_and_no_second_file(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload = _passport_upload(session, layout)
    plan = create_plan(session, layout, upload, catalog=CATALOG, model="recording")
    _apply_ready_items(session, layout, plan, read_plan(plan))
    session.commit()
    (output,) = _documents(session)
    assert layout.resolve(output.path).name == READY_NAME
    _forbid_ai(monkeypatch)  # sağlayıcı çağrılırsa test düşer
    disk = _snapshot(layout)
    source = layout.resolve(upload.files[0].stored_path).read_bytes()

    for _ in range(2):
        rerun_plan(session, layout, upload, executor=_apply_ready_items)
        session.commit()

    assert [(row.id, row.path, row.sequence_no) for row in _documents(session)] == [
        (output.id, output.path, output.sequence_no)
    ]
    assert _snapshot(layout) == disk
    assert list(disk["Hazir"]) == [READY_NAME]
    assert layout.resolve(output.path).read_bytes() == source
    assert len(_events(session, EventType.OUTPUT_SAVED)) == 1
    assert [event.document_id for event in _skipped(session)] == [output.id] * 2
    assert len(_events(session, EventType.PLAN_RERUN)) == 2
    assert _count(session, Plan) == 1


def test_rerun_does_not_bring_back_a_permanently_deleted_output(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 10.5.12 (K9, §D110 c): silinen çıktının plan öğesi yeniden üretilmez; `OUTPUT_SKIPPED`
    # gerekçesi `deleted`, `Hazir/`'a dosya dönmez.
    upload = _passport_upload(session, layout)
    plan = create_plan(session, layout, upload, catalog=CATALOG, model="recording")
    _apply_ready_items(session, layout, plan, read_plan(plan))
    session.commit()
    (output,) = _documents(session)
    deleted = delete_document(session, layout, output.id, actor="ik")
    session.commit()
    assert remove_document_files(session, deleted) == 0
    _forbid_ai(monkeypatch)

    rerun_plan(session, layout, upload, executor=_apply_ready_items)
    session.commit()

    assert [(row.id, row.status, row.path) for row in _documents(session)] == [
        (output.id, "deleted", None)
    ]
    assert _files(layout.ready_dir(FOLDER)) == []
    (skipped,) = _skipped(session)
    assert skipped.document_id == output.id
    assert skipped.data_json is not None and skipped.data_json["reason"] == SKIPPED_DELETED
    assert len(_events(session, EventType.OUTPUT_SAVED)) == 1
