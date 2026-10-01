"""08.1.3 — şifre yüzünden kopyalanamayan kaynak Unreadable kuyruğuna (K9, K11, PLAN.md §D76).

Sahip parolalı (AES) ya da parola korumalı PDF'ten sayfa çıkarması ya da birleştirmesi gereken
`hazir` öğe partiyi durdurmaz: uygulayıcı hiçbir şey yazmadan reddeder, öğe kaynak kopyası ve
gerekçesiyle Unreadable'a gider, planın öbür öğeleri uygulanır. Bozuk PDF, okuyucular arasında
sayfa sayısı uyuşmazlığı ve bütünlük hataları bugünkü gibi uygulamayı durdurur.

Planlar elle (`tests/pipeline/test_execute_output.py`'nin yardımcılarıyla) ya da gerçek boru
hattından kurulur; dosyalar `tests/fixtures/gen.py`'nin sentetik belgeleridir (CONVENTIONS §6),
yapay zekâ yanıtları kayıtlıdır.
"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.pipeline.execute_pdf as execute_pdf_module
from app.ai.recording_provider import RecordingProvider
from app.catalog import import_catalog
from app.config import Settings
from app.db.models import Document, Plan, QueueItem, Upload, UploadStatus
from app.events import EventType
from app.pipeline import execute
from app.pipeline.execute import (
    EncryptedSourceError,
    ExtractEncryptedSourceError,
    ExtractImageSourceError,
    ExtractSourceError,
    MergeEncryptedSourceError,
    MergeSource,
    MergeSourceError,
    PdfProtection,
    RenderImageSourceError,
    SourceIntegrityError,
    execute_extract,
    execute_extract_image,
    execute_merge,
    execute_render_image,
)
from app.pipeline.orchestrate import (
    current_plan,
    execute_plan,
    plan_executor,
    process_upload,
    rerun_plan,
)
from app.pipeline.plan import Operation, PlanItem, Route, read_plan
from app.pipeline.route import QueueItemNotAssignableError, assign_queue_item, route_queue_item
from app.storage import DataLayout
from tests.fixtures.gen import (
    A4,
    make_half_filled_image_bytes,
    make_owner_locked_pdf_bytes,
    make_sized_pdf_bytes,
    make_text_pdf_bytes,
)
from tests.pipeline.test_execute_output import (
    FOLDER,
    READY_UPLOAD,
    _catalog_in_db,
    _ready_employee,
    _ready_item,
    _ready_plan,
    _ready_upload,
)
from tests.pipeline.test_plan import PERMIT, _count, _events
from tests.pipeline.test_process_upload import CATALOG, RECORDINGS, _received_upload

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
PERMIT_NAME = "Test_Ornekova-Work-Permit.pdf"
ENCRYPTED_REASON = "Şifreli PDF, sayfalar kopyalanamıyor (08.1.3)"


def _owner_locked(content: bytes) -> bytes:
    """`content`'i AES-256 ile yalnız sahip parolalı şifreler: parolasız açılır, metni ve boş
    sayfası aynı kalır; pypdf `cryptography` olmadan sayfalarını çözemez."""
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="sahip-parolasi",
            user_pw="",
            permissions=int(pymupdf.PDF_PERM_PRINT),
        )


AES_PDF = make_owner_locked_pdf_bytes(2)
PASSWORD_PDF = make_sized_pdf_bytes([A4], password="gizli")
PLAIN_PDF = make_text_pdf_bytes(["SENTETIK DUZ"])
CORRUPT_PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def _files(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir()) if directory.exists() else []


def _run(session: Session, layout: DataLayout, plan: Plan) -> None:
    execute_plan(
        session,
        layout,
        plan,
        read_plan(plan),
        render_image_dpi=SETTINGS.render_image_dpi,
        render_image_jpeg_quality=SETTINGS.render_image_jpeg_quality,
    )


def _reason_json(layout: DataLayout, upload_id: str = READY_UPLOAD) -> dict:
    return json.loads(layout.queue_reason_path("unreadable", upload_id).read_text("utf-8"))


def _plain_item(item_id: str, file_id: int) -> PlanItem:
    return _ready_item(
        item_id, [(file_id, (0,))], operation=Operation.PASSTHROUGH, target_name=PERMIT_NAME
    )


# --- uygulayıcı: şifre kaynaklı ret ayrı alt sınıftır ----------------------------------------


@pytest.mark.parametrize(
    ("content", "protection", "message"),
    [
        pytest.param(AES_PDF, PdfProtection.AES, r"şifreli \(AES\)", id="aes-sahip-parolali"),
        pytest.param(PASSWORD_PDF, PdfProtection.PASSWORD, "parola korumalı", id="parola"),
    ],
)
def test_extract_refuses_an_encrypted_source_with_its_own_subclass(
    tmp_path: Path, content: bytes, protection: PdfProtection, message: str
) -> None:
    source = tmp_path / "kaynak.pdf"
    source.write_bytes(content)
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(ExtractEncryptedSourceError, match=message) as refused:
        execute_extract(source, destination, pages=[0])

    assert isinstance(refused.value, ExtractSourceError)
    assert (refused.value.source_position, refused.value.protection) == (0, protection)
    assert not destination.exists()
    # K11: kaynak yeniden yazılmadı.
    assert source.read_bytes() == content


@pytest.mark.parametrize(
    ("content", "protection"),
    [
        pytest.param(AES_PDF, PdfProtection.AES, id="aes-sahip-parolali"),
        pytest.param(PASSWORD_PDF, PdfProtection.PASSWORD, id="parola"),
    ],
)
def test_merge_names_the_position_of_the_encrypted_source(
    tmp_path: Path, content: bytes, protection: PdfProtection
) -> None:
    plain = tmp_path / "duz.pdf"
    plain.write_bytes(PLAIN_PDF)
    encrypted = tmp_path / "sifreli.pdf"
    encrypted.write_bytes(content)
    destination = tmp_path / "hedef.pdf"

    with pytest.raises(MergeEncryptedSourceError, match=r"sources\[1\]") as refused:
        execute_merge(
            [MergeSource(plain, (0,)), MergeSource(encrypted, (0,))], destination, direct=False
        )

    assert isinstance(refused.value, MergeSourceError)
    assert (refused.value.source_position, refused.value.protection) == (1, protection)
    assert not destination.exists()


@pytest.mark.parametrize("corrupt_first", [True, False], ids=["bozuk-once", "bozuk-sonra"])
def test_a_corrupt_merge_source_wins_over_an_encrypted_one(
    tmp_path: Path, corrupt_first: bool
) -> None:
    corrupt = MergeSource(tmp_path / "bozuk.pdf", (0,))
    corrupt.path.write_bytes(CORRUPT_PDF)
    encrypted = MergeSource(tmp_path / "sifreli.pdf", (0,))
    encrypted.path.write_bytes(AES_PDF)
    sources = [corrupt, encrypted] if corrupt_first else [encrypted, corrupt]

    with pytest.raises(MergeSourceError, match="pypdf ile okunamadı") as refused:
        execute_merge(sources, tmp_path / "hedef.pdf", direct=False)

    assert not isinstance(refused.value, EncryptedSourceError)


def test_a_missing_page_of_a_plain_merge_source_wins_over_an_encrypted_one(
    tmp_path: Path,
) -> None:
    encrypted = MergeSource(tmp_path / "sifreli.pdf", (0,))
    encrypted.path.write_bytes(AES_PDF)
    plain = MergeSource(tmp_path / "duz.pdf", (4,))
    plain.path.write_bytes(PLAIN_PDF)

    with pytest.raises(MergeSourceError, match="sayfası kaynakta yok") as refused:
        execute_merge([encrypted, plain], tmp_path / "hedef.pdf", direct=False)

    assert not isinstance(refused.value, EncryptedSourceError)


def test_image_operations_keep_refusing_a_password_protected_pdf_with_their_own_error(
    tmp_path: Path,
) -> None:
    # 08.1.3 yalnız sayfa kopyalayan işlemlerin (extract, merge) konusudur.
    source = tmp_path / "parolali.pdf"
    source.write_bytes(PASSWORD_PDF)

    with pytest.raises(ExtractImageSourceError, match="parola korumalı") as extracted:
        execute_extract_image(source, tmp_path / "gorsel.jpeg", page=0)
    with pytest.raises(RenderImageSourceError, match="parola korumalı") as rendered:
        execute_render_image(source, tmp_path / "gorsel.jpeg", page=0, dpi=72, jpeg_quality=80)

    assert not isinstance(extracted.value, EncryptedSourceError)
    assert not isinstance(rendered.value, EncryptedSourceError)


def test_encrypted_source_errors_keep_the_public_module_path() -> None:
    for error in (EncryptedSourceError, ExtractEncryptedSourceError, MergeEncryptedSourceError):
        assert error.__module__ == "app.pipeline.execute"
        assert getattr(execute, error.__name__) is error


# --- uygulama: öğe Unreadable'a, plan sürer ----------------------------------------------------


def test_owner_locked_aes_extract_goes_to_unreadable_and_the_plain_item_is_applied(
    session: Session, layout: DataLayout
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    locked, plain = _ready_upload(session, layout, ("resmi.pdf", AES_PDF), ("duz.pdf", PLAIN_PDF))
    encrypted_item = _ready_item(
        "i1", [(locked.id, (1,))], operation=Operation.EXTRACT, target_name=PERMIT_NAME
    )
    plan = _ready_plan(session, encrypted_item, _plain_item("i2", plain.id))
    frozen = (plan.plan_hash, json.dumps(plan.json, sort_keys=True))

    _run(session, layout, plan)

    # Şifreli öğe: kuyruk kaydı, gerekçe metni dosyayı, istenen işlemi ve nedeni söyler.
    (queued,) = session.scalars(select(QueueItem)).all()
    reason = (
        f"{ENCRYPTED_REASON}: dosya {locked.id}, istenen işlem extract — sahip parolalı (AES), "
        "pypdf sayfaları çözemiyor; şifre kaldırılmaz, dosya yeniden yazılmaz (K11)."
    )
    assert (queued.kind, queued.plan_id, queued.plan_item_id, queued.reason) == (
        "unreadable",
        plan.id,
        "i1",
        reason,
    )
    assert queued.resolved_at is None
    encrypted_source = {"operation": "extract", "file_id": locked.id, "protection": "aes"}
    assert queued.payload_json == {
        "document_type_slug": PERMIT,
        "sources": [{"file_id": locked.id, "pages": [1]}],
        "employee_guess": {
            "action": "match",
            "employee_id": "E0001",
            "matched_by": "document_number",
        },
        "encrypted_source": encrypted_source,
    }
    # Kaynak kopyası bayt bayt aynı, gerekçe dosyası kaydı taşır; Inbox'taki orijinal değişmedi.
    unreadable = layout.queue_dir("unreadable", READY_UPLOAD)
    assert _files(unreadable) == ["reason.json", "resmi.pdf"]
    assert (unreadable / "resmi.pdf").read_bytes() == AES_PDF
    assert layout.resolve(locked.stored_path).read_bytes() == AES_PDF
    (entry,) = _reason_json(layout)["items"]
    assert (entry["plan_item_id"], entry["reason"], entry["encrypted_source"]) == (
        "i1",
        reason,
        encrypted_source,
    )
    (event,) = _events(session, EventType.QUEUED_UNREADABLE)
    assert (event.upload_id, event.file_id, event.page_index, event.message) == (
        READY_UPLOAD,
        locked.id,
        1,
        reason,
    )
    assert event.data_json is not None
    assert (event.data_json["item_id"], event.data_json["queue_item_id"]) == ("i1", queued.id)
    assert event.data_json["encrypted_source"] == encrypted_source
    assert _events(session, EventType.PAGE_EXTRACTED) == []

    # Öbür öğe uygulandı: çıktı Hazir'da, kaynağı Alinan'da; şifreli kaynak Alinan'a girmedi.
    (output,) = session.scalars(select(Document)).all()
    assert output.source_refs_json == [{"file_id": plain.id, "pages": [0]}]
    assert _files(layout.ready_dir(FOLDER)) == [PERMIT_NAME]
    assert _files(layout.received_dir(FOLDER)) == ["duz.pdf"]
    assert layout.profile_path(FOLDER).is_file()
    # K9: plan değişmedi.
    assert (plan.plan_hash, json.dumps(plan.json, sort_keys=True)) == frozen


@pytest.mark.parametrize(
    ("content", "protection", "text"),
    [
        pytest.param(PASSWORD_PDF, "password", "açmak için parola gerekiyor", id="parola"),
        pytest.param(AES_PDF, "aes", "sahip parolalı (AES)", id="aes-sahip-parolali"),
    ],
)
def test_encrypted_merge_source_goes_to_unreadable_and_the_plain_item_is_applied(
    session: Session, layout: DataLayout, content: bytes, protection: str, text: str
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    front, locked, plain = _ready_upload(
        session,
        layout,
        ("on.pdf", make_text_pdf_bytes(["ON YUZ"])),
        ("arka.pdf", content),
        ("duz.pdf", PLAIN_PDF),
    )
    merged = _ready_item(
        "i1",
        [(front.id, (0,)), (locked.id, (0,))],
        operation=Operation.MERGE,
        target_name=PERMIT_NAME,
    )
    plan = _ready_plan(session, merged, _plain_item("i2", plain.id))

    _run(session, layout, plan)

    (queued,) = session.scalars(select(QueueItem)).all()
    assert (queued.kind, queued.plan_item_id) == ("unreadable", "i1")
    assert queued.reason.startswith(
        f"{ENCRYPTED_REASON}: dosya {locked.id}, istenen işlem merge — {text}"
    )
    assert queued.payload_json is not None
    assert queued.payload_json["encrypted_source"] == {
        "operation": "merge",
        "file_id": locked.id,
        "protection": protection,
    }
    # Öğenin bütün kaynakları kuyruğa kopyalandı (08.1.1); ikisi de Alinan'a girmedi.
    assert _files(layout.queue_dir("unreadable", READY_UPLOAD)) == [
        "arka.pdf",
        "on.pdf",
        "reason.json",
    ]
    assert _events(session, EventType.PAGES_MERGED) == []
    (output,) = session.scalars(select(Document)).all()
    assert output.source_refs_json == [{"file_id": plain.id, "pages": [0]}]
    assert _files(layout.received_dir(FOLDER)) == ["duz.pdf"]


class _ShortReader(PdfReader):
    """Bozuk PDF'i MuPDF'ten farklı onaran okuyucu: son sayfayı görmez."""

    @property
    def pages(self):  # type: ignore[override]
        return super().pages[:-1]


@pytest.mark.parametrize(
    ("case", "error", "message"),
    [
        pytest.param("bozuk-pdf", MergeSourceError, "pypdf ile okunamadı", id="bozuk-pdf"),
        pytest.param(
            "okuyucu-sayfa-sayisi",
            ExtractSourceError,
            "MuPDF 2, pypdf 1",
            id="okuyucu-sayfa-sayisi",
        ),
        pytest.param("sha-uyusmazligi", SourceIntegrityError, "SHA-256", id="sha-uyusmazligi"),
    ],
)
def test_non_password_errors_still_stop_the_execution(
    session: Session,
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    error: type[Exception],
    message: str,
) -> None:
    # Şifreli kaynak da taşıyan ya da taşımayan öğe şifre dışı bir hatayla durur; ardındaki düz
    # öğe uygulanmaz, hiçbir şey kuyruğa alınmaz.
    _catalog_in_db(session)
    _ready_employee(session, layout)
    locked, corrupt, two_pages, plain = _ready_upload(
        session,
        layout,
        ("sifreli.pdf", AES_PDF),
        ("bozuk.pdf", CORRUPT_PDF),
        ("belge.pdf", make_text_pdf_bytes(["A", "B"])),
        ("duz.pdf", PLAIN_PDF),
    )
    if case == "bozuk-pdf":
        failing = _ready_item(
            "i1",
            [(locked.id, (0,)), (corrupt.id, (0,))],
            operation=Operation.MERGE,
            target_name=PERMIT_NAME,
        )
    else:
        failing = _ready_item(
            "i1", [(two_pages.id, (1,))], operation=Operation.EXTRACT, target_name=PERMIT_NAME
        )
    if case == "okuyucu-sayfa-sayisi":
        monkeypatch.setattr(execute_pdf_module, "PdfReader", _ShortReader)
    if case == "sha-uyusmazligi":
        layout.resolve(two_pages.stored_path).write_bytes(make_text_pdf_bytes(["A", "C"]))
    plan = _ready_plan(session, failing, _plain_item("i2", plain.id))

    with pytest.raises(error, match=message) as stopped:
        _run(session, layout, plan)

    assert not isinstance(stopped.value, EncryptedSourceError)
    assert _count(session, QueueItem) == 0
    assert _events(session, EventType.QUEUED_UNREADABLE) == []
    assert _count(session, Document) == 0
    assert _files(layout.queue_dir("unreadable", READY_UPLOAD)) == []
    assert _files(layout.ready_dir(FOLDER)) == []


def test_rerunning_the_plan_gives_the_same_result(session: Session, layout: DataLayout) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    locked, plain = _ready_upload(session, layout, ("resmi.pdf", AES_PDF), ("duz.pdf", PLAIN_PDF))
    plan = _ready_plan(
        session,
        _ready_item(
            "i1", [(locked.id, (0,))], operation=Operation.EXTRACT, target_name=PERMIT_NAME
        ),
        _plain_item("i2", plain.id),
    )
    _run(session, layout, plan)
    session.commit()
    reason_file = layout.queue_reason_path("unreadable", READY_UPLOAD)
    before = (reason_file.read_bytes(), reason_file.stat().st_mtime_ns)
    queued = _events(session, EventType.QUEUED_UNREADABLE)

    run = rerun_plan(
        session, layout, session.get_one(Upload, READY_UPLOAD), executor=plan_executor(SETTINGS)
    )
    session.commit()

    # 06.6.1: aynı plan, aynı kuyruk kaydı; ikinci kopya, ikinci olay ya da yeni gerekçe yok.
    assert run.plan.id == plan.id
    (row,) = session.scalars(select(QueueItem)).all()
    assert (row.plan_id, row.plan_item_id, row.kind) == (plan.id, "i1", "unreadable")
    assert _events(session, EventType.QUEUED_UNREADABLE) == queued
    assert (reason_file.read_bytes(), reason_file.stat().st_mtime_ns) == before
    assert _files(layout.queue_dir("unreadable", READY_UPLOAD)) == ["reason.json", "resmi.pdf"]
    assert _count(session, Document) == 1
    assert _files(layout.ready_dir(FOLDER)) == [PERMIT_NAME]
    assert [row.document_id for row in _events(session, EventType.OUTPUT_SKIPPED)] == [
        session.scalars(select(Document.id)).one()
    ]


def test_the_redirected_item_cannot_be_assigned_while_the_source_is_encrypted(
    session: Session, layout: DataLayout
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    (locked,) = _ready_upload(session, layout, ("resmi.pdf", AES_PDF))
    plan = _ready_plan(
        session,
        _ready_item(
            "i1", [(locked.id, (1,))], operation=Operation.EXTRACT, target_name=PERMIT_NAME
        ),
    )
    _run(session, layout, plan)
    (queued,) = session.scalars(select(QueueItem)).all()
    events = len(_events(session))

    with pytest.raises(QueueItemNotAssignableError, match=r"şifreli \(AES\)"):
        assign_queue_item(
            session,
            layout,
            queued.id,
            "E0001",
            actor="ik",
            render_image_dpi=SETTINGS.render_image_dpi,
            render_image_jpeg_quality=SETTINGS.render_image_jpeg_quality,
        )

    assert queued.resolved_at is None
    assert _count(session, Document) == 0
    assert len(_events(session)) == events


@pytest.mark.parametrize("case", ["kuyruk-rotasi", "passthrough", "konum-yok"])
def test_the_encrypted_redirect_is_only_for_page_copying_ready_items(
    session: Session, layout: DataLayout, case: str
) -> None:
    _catalog_in_db(session)
    _ready_employee(session, layout)
    (locked,) = _ready_upload(session, layout, ("resmi.pdf", AES_PDF))
    item = _ready_item(
        "i1",
        [(locked.id, (0, 1))],
        operation=Operation.PASSTHROUGH if case == "passthrough" else Operation.EXTRACT,
        target_name=PERMIT_NAME,
    )
    if case == "kuyruk-rotasi":
        item = PlanItem.model_validate(
            {
                **item.model_dump(mode="json"),
                "operation": None,
                "target_format": None,
                "target_name": None,
                "route": Route.UNREADABLE.value,
                "route_reason": "Gerekçe.",
            }
        )
    plan = _ready_plan(session, item)
    refused = ExtractEncryptedSourceError(
        "extract kaynağı şifreli (AES)",
        source_position=1 if case == "konum-yok" else 0,
        protection=PdfProtection.AES,
    )

    with pytest.raises(ValueError, match="Şifreli kaynak yönlendirmesi"):
        route_queue_item(session, layout, plan, item, encrypted=refused)

    assert _count(session, QueueItem) == 0
    assert _files(layout.queue_dir("unreadable", READY_UPLOAD)) == []


# --- uçtan uca: parti `failed` olmaz ----------------------------------------------------------


@pytest.fixture
def catalog(session: Session) -> None:
    import_catalog(session, CATALOG)
    session.commit()


@pytest.mark.usefixtures("catalog")
def test_an_upload_with_an_owner_locked_passport_ends_done_with_the_passport_in_unreadable(
    session: Session, layout: DataLayout
) -> None:
    # Pasaport sayfası + boş sayfa (extract gerekir) sahip parolalı AES; aynı partide ön/arka
    # yüz görüntüleri (S5) düz birleştirilir.
    passport = _owner_locked(make_text_pdf_bytes(["PASAPORT", None]))
    upload = _received_upload(
        session,
        layout,
        ("pasaport.pdf", passport),
        ("on.jpg", make_half_filled_image_bytes("JPEG")),
        ("arka.jpg", make_half_filled_image_bytes("JPEG", (100, 200))),
    )
    provider = RecordingProvider(
        [
            RECORDINGS / "russian_passport" / "0.json",
            RECORDINGS / "s5_front_back_images" / "0.json",
            RECORDINGS / "s5_front_back_images" / "1.json",
        ]
    )

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=provider)

    plan = current_plan(session, upload)
    assert plan is not None
    assert (result.status, result.failed_stage) == (UploadStatus.DONE, None)
    assert _events(session, EventType.PIPELINE_FAILED) == []
    items = {item.item_id: item for item in read_plan(plan).items}
    passport_item = next(item for item in items.values() if item.sources[0].file_id == 1)
    assert (passport_item.route, passport_item.operation) == (Route.READY, Operation.EXTRACT)
    # Pasaport Unreadable'da, gerekçesiyle; ön/arka yüz birleştirilip yazıldı.
    (queued,) = session.scalars(select(QueueItem)).all()
    assert (queued.kind, queued.plan_item_id) == ("unreadable", passport_item.item_id)
    assert queued.reason.startswith(f"{ENCRYPTED_REASON}: dosya 1, istenen işlem extract")
    assert _files(layout.queue_dir("unreadable", upload.id)) == ["pasaport.pdf", "reason.json"]
    (output,) = session.scalars(select(Document)).all()
    assert output.source_refs_json == [
        {"file_id": 2, "pages": [0]},
        {"file_id": 3, "pages": [0]},
    ]
    assert layout.resolve(output.path).name == "Ivan_Sidorov-Driving-License.pdf"
    assert len(_events(session, EventType.QUEUED_UNREADABLE)) == 1
    # K10/K11: Inbox'taki şifreli orijinal olduğu gibi.
    assert layout.resolve(upload.files[0].stored_path).read_bytes() == passport


@pytest.mark.usefixtures("catalog")
def test_a_reader_disagreement_still_fails_the_upload(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(execute_pdf_module, "PdfReader", _ShortReader)
    upload = _received_upload(
        session, layout, ("pasaport.pdf", make_text_pdf_bytes(["PASAPORT", None]))
    )

    result = process_upload(
        session,
        layout,
        upload,
        settings=SETTINGS,
        provider=RecordingProvider.from_directory(RECORDINGS / "russian_passport"),
    )

    assert (result.status, result.failed_stage) == (UploadStatus.FAILED, UploadStatus.EXECUTING)
    (failed,) = _events(session, EventType.PIPELINE_FAILED)
    assert failed.data_json is not None
    assert failed.data_json["error"] == "app.pipeline.execute.ExtractSourceError"
    assert _count(session, QueueItem) == 0
