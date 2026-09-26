"""11.9.5 — Toplu taramanın işçi adımı (`app.training.map_scan` `TrainingMapJob`,
`app.worker.idle`; PLAN.md §C87): harita öğeleri birer birer taranır; yerindeki örnek kopyasız
kaydolur, haritanın SHA-256'sı ya da türü tutmazsa ve türü belli dosya mekanik kontrolden geçmezse
öğe "İnceleme gerekli" olur ve yapay zekâya gitmez; yalnız türü belirsiz dosya yapay zekâya gider;
yeniden tarama kayıtlı dosyayı atlar; yükleme işi önce gelir; hata deneme sayacını artırır.

Harita işi sağlayıcı çağırmaz: testlerin sağlayıcısı çağrılırsa test düşer. Yapay zekâ adımı
(11.9.3) sahte sağlayıcıyla sınanır. Belgeler ve kişiler sentetiktir (CONVENTIONS §6).
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import AnalysisProvider, PageAnalysisRequest, TrainingClassificationRequest
from app.ai.recording_provider import RecordingProvider
from app.config import Settings
from app.db.models import (
    Event,
    ExampleFileRecord,
    JobStatus,
    TrainingItem,
    TrainingRun,
    TrainingRunKind,
    UploadJob,
    utcnow,
)
from app.events import EventType
from app.storage import DataLayout, sha256_bytes
from app.storage.examples import list_examples
from app.training import (
    create_run,
    load_example_inventory,
    load_known_types,
    parse_map,
    plan_map,
    preview_map,
    stage_file,
    start_map_scan,
)
from app.training.classification import TrainingClassificationJob
from app.training.map_scan import (
    ABANDONED_NOTE,
    ERROR_NOTE,
    JOB_NAME,
    SHA_MISMATCH,
    TRAINING_MAP_ITEMS,
    MapFile,
    TrainingMapJob,
    scan_map_item,
)
from app.training.mechanical import ExampleInventory
from app.training.placement import ItemNotPlaceableError
from app.web.routers.uploads import IncomingFile, store_upload
from app.worker import IdleContext, IdleJob, Worker
from tests.ai.payloads import training_payload
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    batch_responses,
    make_document_pdf_bytes,
    make_docx_bytes,
    make_half_filled_image_bytes,
    make_mrz_lines,
    make_pdf_bytes,
    make_text_pdf_bytes,
    passport_page,
    write_recordings,
)
from tests.training.invariants import assert_employee_data_untouched

SETTINGS = Settings(
    _env_file=None, database_url="sqlite://", worker_lease_seconds=60, worker_max_attempts=3
)
PASSPORT = "turkish_passport"
IN_PLACE = f"KnownDocuments/examples/{PASSPORT}"


class ForbiddenProvider(AnalysisProvider):
    """Harita işi sağlayıcı çağırmaz; çağrılırsa test düşer."""

    name = "yasak"

    def __init__(self) -> None:
        super().__init__(model="yasak-model")

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("harita taraması sayfa analizi istememeli")

    def _request_training_classification(self, request: TrainingClassificationRequest) -> object:
        raise AssertionError("harita taraması yapay zekâ çağırmamalı")


class Classifier(AnalysisProvider):
    """Eğitim sınıflandırmasının (11.9.3) sahte sağlayıcısı: Arnavutluk pasaportu der."""

    name = "sahte"

    def __init__(self) -> None:
        super().__init__(model="sahte-model")
        self.requests: list[TrainingClassificationRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_training_classification(self, request: TrainingClassificationRequest) -> object:
        self.requests.append(request)
        return training_payload()


def _jpeg(width: int = 200) -> bytes:
    return make_half_filled_image_bytes("JPEG", (width, 100))


def _passport_pdf() -> bytes:
    """Metin katmanında geçerli TD3 MRZ taşıyan sentetik Türk pasaportu PDF'i."""
    lines = make_mrz_lines(
        "TD3",
        document_code="P",
        issuing_state="TUR",
        surname="ORNEKOVA",
        given_names="TEST",
        document_number="U00000001",
        nationality="TUR",
        date_of_birth=date(1990, 1, 1),
        sex="F",
        expiry_date=date(2030, 1, 1),
    )
    return make_text_pdf_bytes(["\n".join(("PASAPORT", *lines))])


def _put(layout: DataLayout, relative: str, content: bytes) -> Path:
    path = layout.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _csv(rows: Sequence[Mapping[str, str]]) -> bytes:
    columns = ("slug", "role", "dest", "source_collection_path", "path", "sha256")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return buffer.getvalue().encode("utf-8")


def _start(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    rows: Sequence[Mapping[str, str]],
    *,
    settings: Settings = SETTINGS,
) -> list[int]:
    """Haritayı (onaylanmış gibi) başlatır; öğelerin kimlikleri."""
    content = _csv(rows)
    with session_factory() as session:
        known = load_known_types(session)
        parsed = parse_map(content, max_bytes=1024 * 1024, max_rows=100)
        plan = plan_map(
            parsed,
            layout,
            known,
            collection_root=settings.training_collection_dir,
            max_files=100,
        )
        preview = preview_map(session, plan, known, inventory=load_example_inventory(layout))
        run = create_run(session, kind=TrainingRunKind.MAP, created_by="ik", map_name="h.csv")
        items = start_map_scan(session, layout, run, plan, preview, content=content, actor="ik")
        session.commit()
        return [item.id for item in items]


def _context(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    *,
    settings: Settings = SETTINGS,
    provider: AnalysisProvider | None = None,
) -> IdleContext:
    return IdleContext(session_factory, layout, settings, provider or ForbiddenProvider())


def _scan_all(
    session_factory: sessionmaker[Session], layout: DataLayout, *, settings: Settings = SETTINGS
) -> int:
    job = TrainingMapJob()
    context = _context(session_factory, layout, settings=settings)
    units = 0
    while job.run_one(context):
        units += 1
    return units


def _item(session_factory: sessionmaker[Session], item_id: int) -> TrainingItem:
    with session_factory() as session:
        item = session.get_one(TrainingItem, item_id)
        session.expunge(item)
    return item


def _run_of(session_factory: sessionmaker[Session], item_id: int) -> TrainingRun:
    with session_factory() as session:
        run = session.get_one(TrainingItem, item_id).run
        session.expunge(run)
    return run


def _records(session_factory: sessionmaker[Session]) -> list[tuple[str, str, str, str | None]]:
    with session_factory() as session:
        return [
            (record.type_slug, record.name, record.method, record.label)
            for record in session.scalars(select(ExampleFileRecord).order_by(ExampleFileRecord.id))
        ]


def _incoming(layout: DataLayout) -> list[str]:
    root = layout.training / "gelen"
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _wait_until(condition: Callable[[], bool], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "koşul zamanında gerçekleşmedi"
        time.sleep(0.02)


# --- yerindeki örnek ve parça parça tarama ---------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_in_place_examples_are_registered_without_a_copy_one_item_per_unit(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    first_content, second_content = _jpeg(201), _jpeg(202)
    _put(layout, f"{IN_PLACE}/a.jpg", first_content)
    _put(layout, f"{IN_PLACE}/b.jpg", second_content)
    first, second = _start(
        session_factory,
        layout,
        [
            {"slug": PASSPORT, "dest": f"{IN_PLACE}/a.jpg", "sha256": sha256_bytes(first_content)},
            {"slug": PASSPORT, "dest": f"{IN_PLACE}\\b.jpg"},
        ],
    )
    job, context = TrainingMapJob(), _context(session_factory, layout)

    assert job.run_one(context) is True  # tek birim: bir öğe

    item = _item(session_factory, first)
    assert (item.status, item.method, item.result_slug, item.staged_path) == (
        "placed",
        "mechanical",
        PASSPORT,
        None,
    )
    assert item.note is not None and item.note.startswith(
        f"Mekanik: harita satırı 2 → `{PASSPORT}`"
    )
    assert "SHA-256 tuttu" in item.note
    assert item.checks_json is not None and item.checks_json["map"]["in_place"] == PASSPORT
    assert _item(session_factory, second).status == "queued"
    assert _run_of(session_factory, first).status == "running"

    assert job.run_one(context) is True
    assert job.run_one(context) is False

    assert _item(session_factory, second).status == "placed"
    assert _records(session_factory) == [
        (PASSPORT, "a.jpg", "mechanical", None),
        (PASSPORT, "b.jpg", "mechanical", None),
    ]
    assert [example.name for example in list_examples(layout, PASSPORT)] == ["a.jpg", "b.jpg"]
    assert (layout.type_examples_dir(PASSPORT) / "a.jpg").read_bytes() == first_content
    assert _incoming(layout) == []  # kopya yok
    run = _run_of(session_factory, first)
    assert (run.status, run.counts_json) == ("done", {"placed": 2})
    with session_factory() as session:
        placed = session.scalars(
            select(Event).where(Event.type == EventType.TRAINING_EXAMPLE_PLACED.value)
        ).all()
        assert [event.data_json["in_place"] for event in placed if event.data_json] == [
            True,
            True,
        ]
        assert_employee_data_untouched(session, layout)


@pytest.mark.usefixtures("catalog")
def test_rescanning_the_same_map_skips_registered_files_and_copies_nothing(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _put(layout, f"{IN_PLACE}/a.jpg", _jpeg(201))
    _put(layout, "gelen/c.jpg", _jpeg(203))
    rows = [
        {"slug": PASSPORT, "dest": f"{IN_PLACE}/a.jpg"},
        {"slug": PASSPORT, "path": "gelen/c.jpg"},
    ]
    in_place, elsewhere = _start(session_factory, layout, rows)
    assert _scan_all(session_factory, layout) == 2
    assert _item(session_factory, elsewhere).status == "placed"
    copies = _incoming(layout)
    assert len(copies) == 1  # yerinde olmayan dosyanın eğitim kopyası
    assert [example.name for example in list_examples(layout, PASSPORT)] == ["a.jpg", "c.jpg"]

    again = _start(session_factory, layout, rows)
    assert _scan_all(session_factory, layout) == 2

    for item_id in again:
        item = _item(session_factory, item_id)
        assert item.status == "skipped"
        assert item.note is not None and "zaten örnek" in item.note
    assert _incoming(layout) == copies  # yeniden taramada kopya yazılmadı
    assert [example.name for example in list_examples(layout, PASSPORT)] == ["a.jpg", "c.jpg"]
    assert len(_records(session_factory)) == 2
    assert (_run_of(session_factory, again[0]).counts_json or {}) == {"skipped": 2}
    assert _item(session_factory, in_place).status == "placed"


# --- inceleme gerekli (yapay zekâya gitmez) --------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_a_sha256_mismatch_waits_for_review_and_never_reaches_the_ai(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _put(layout, f"{IN_PLACE}/a.jpg", _jpeg(201))
    _put(layout, "gelen/b.jpg", _jpeg(202))
    in_place, elsewhere = _start(
        session_factory,
        layout,
        [
            {"slug": PASSPORT, "dest": f"{IN_PLACE}/a.jpg", "sha256": "0" * 64},
            {"path": "gelen/b.jpg", "sha256": "1" * 64},  # türü belirsiz de olsa
        ],
    )

    assert _scan_all(session_factory, layout) == 2

    for item_id in (in_place, elsewhere):
        item = _item(session_factory, item_id)
        assert item.status == "review"
        assert item.note is not None and SHA_MISMATCH in item.note
    assert _item(session_factory, in_place).result_slug == PASSPORT
    assert _records(session_factory) == []
    assert _incoming(layout) == []
    classifier = Classifier()
    context = _context(session_factory, layout, provider=classifier)
    assert TrainingClassificationJob().run_one(context) is False
    assert classifier.requests == []
    assert _run_of(session_factory, in_place).status == "done"  # İK bekleyen çalıştırmayı tutmaz
    with session_factory() as session:
        (event, _other) = session.scalars(
            select(Event).where(Event.type == EventType.TRAINING_ITEM_UNPLACED.value)
        ).all()
        assert event.data_json is not None and event.data_json["status"] == "review"


@pytest.mark.usefixtures("catalog")
def test_an_in_place_file_whose_map_type_differs_waits_for_review(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _put(layout, f"{IN_PLACE}/a.jpg", _jpeg(201))
    (item_id,) = _start(
        session_factory, layout, [{"slug": "albanian_passport", "dest": f"{IN_PLACE}/a.jpg"}]
    )

    _scan_all(session_factory, layout)

    item = _item(session_factory, item_id)
    assert (item.status, item.hint_slug, item.result_slug) == (
        "review",
        "albanian_passport",
        PASSPORT,
    )
    assert item.note == (
        f"İnceleme gerekli (harita satırı 2): haritadaki tür `albanian_passport`, dosya "
        f"`{PASSPORT}` örnek klasöründe"
    )
    assert _records(session_factory) == [] and _incoming(layout) == []


@pytest.mark.usefixtures("catalog")
def test_a_known_type_failing_the_mechanical_checks_waits_for_review_not_the_ai(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # Türk pasaportu PDF ya da JPEG ve tek sayfa bekler (katalog).
    _put(layout, "gelen/a.png", make_half_filled_image_bytes("PNG", (200, 100)))
    _put(layout, "gelen/b.pdf", make_pdf_bytes(2))
    png, two_pages = _start(
        session_factory,
        layout,
        [{"slug": PASSPORT, "path": "gelen/a.png"}, {"slug": PASSPORT, "path": "gelen/b.pdf"}],
    )

    _scan_all(session_factory, layout)

    for item_id, problem in ((png, "dosya türü PNG izinli değil"), (two_pages, "sayfa sayısı 2")):
        item = _item(session_factory, item_id)
        assert (item.status, item.method, item.result_slug) == ("review", "mechanical", PASSPORT)
        assert item.note is not None
        assert problem in item.note and "yapay zekâya gönderilmedi" in item.note
        assert item.staged_path is not None  # "Türe yerleştir" eğitim kopyasını kullanır
    assert _records(session_factory) == []


# --- türü belirsiz dosya ---------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_an_undetermined_file_goes_to_the_ai_and_is_placed_with_the_ai_label(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _put(layout, "gelen/a.jpg", _jpeg(201))
    (item_id,) = _start(session_factory, layout, [{"slug": "yok_boyle_tur", "path": "gelen/a.jpg"}])

    _scan_all(session_factory, layout)

    item = _item(session_factory, item_id)
    assert (item.status, item.hint_slug) == ("ai_pending", "yok_boyle_tur")
    assert item.note is not None and "ipucu `yok_boyle_tur` bilinen bir tür değil" in item.note
    assert item.staged_path is not None
    assert _run_of(session_factory, item_id).status == "running"
    classifier = Classifier()

    assert TrainingClassificationJob().run_one(
        _context(session_factory, layout, provider=classifier)
    )

    item = _item(session_factory, item_id)
    assert (item.status, item.method, item.result_slug) == ("placed", "ai", "albanian_passport")
    assert _records(session_factory) == [("albanian_passport", "a.jpg", "ai", "ai_decision")]
    assert len(classifier.requests) == 1
    assert (layout.root / "gelen" / "a.jpg").exists()  # kaynak yerinde, değişmedi


@pytest.mark.usefixtures("catalog")
def test_a_typeless_row_is_recognized_by_the_mrz_in_the_text_layer(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _put(layout, "gelen/pasaport.pdf", _passport_pdf())
    (item_id,) = _start(session_factory, layout, [{"path": "gelen/pasaport.pdf"}])

    _scan_all(session_factory, layout)

    item = _item(session_factory, item_id)
    assert (item.status, item.method, item.result_slug) == ("placed", "mechanical", PASSPORT)
    assert item.note is not None and "PDF metin katmanında MRZ" in item.note
    assert "ORNEKOVA" not in item.note and "ORNEKOVA" not in str(item.checks_json)
    assert [example.name for example in list_examples(layout, PASSPORT)] == ["pasaport.pdf"]


# --- dosya sorunları ------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_a_vanished_or_unusable_file_fails_at_scan_time(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    gone = _put(layout, "gelen/gidecek.jpg", _jpeg(201))
    _put(layout, "gelen/belge.jpg", make_docx_bytes())
    vanished, unusable = _start(
        session_factory,
        layout,
        [
            {"slug": PASSPORT, "path": "gelen/gidecek.jpg"},
            {"slug": PASSPORT, "path": "gelen/belge.jpg"},
        ],
    )
    gone.unlink()

    _scan_all(session_factory, layout)

    item = _item(session_factory, vanished)
    assert (item.status, item.note) == ("failed", "Taranamadı (harita satırı 2): dosya yok")
    item = _item(session_factory, unusable)
    assert item.status == "failed"
    assert item.note == "'belge.jpg' örnek olamaz: yalnız PDF, JPEG ve PNG kabul edilir."
    assert _run_of(session_factory, vanished).counts_json == {"failed": 2}
    assert _records(session_factory) == [] and _incoming(layout) == []


@pytest.mark.usefixtures("catalog")
def test_collection_rows_resolve_under_the_optional_collection_root(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    collection = tmp_path / "koleksiyon"
    (collection / "tr").mkdir(parents=True)
    content = _jpeg(201)
    (collection / "tr" / "a.jpg").write_bytes(content)
    (collection / "tr" / "b.jpg").write_bytes(_jpeg(202))
    settings = SETTINGS.model_copy(update={"training_collection_dir": collection})
    rows = [
        {"slug": PASSPORT, "source_collection_path": "tr\\a.jpg"},
        {"slug": PASSPORT, "source_collection_path": "tr/b.jpg"},
    ]
    placed, orphaned = _start(session_factory, layout, rows, settings=settings)
    job, context = TrainingMapJob(), _context(session_factory, layout, settings=settings)

    assert job.run_one(context) is True
    # Ayar tarama sürerken kalkarsa kalan satır okunmaz.
    assert _scan_all(session_factory, layout) == 1

    item = _item(session_factory, placed)
    assert (item.status, item.source_ref) == ("placed", "tr/a.jpg")
    assert (layout.type_examples_dir(PASSPORT) / "a.jpg").read_bytes() == content
    assert (collection / "tr" / "a.jpg").read_bytes() == content  # kaynak değişmedi
    item = _item(session_factory, orphaned)
    assert (item.status, item.note) == (
        "failed",
        "Taranamadı (harita satırı 3): koleksiyon kökü ayarlı değil",
    )


# --- çerçeve: yalnız harita öğeleri, deneme sınırı, yükleme önceliği ------------------------


@pytest.mark.usefixtures("catalog")
def test_only_queued_items_of_map_runs_are_taken(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    with session_factory() as session:
        run = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")
        stage_file(session, layout, run, "yukleme.jpg", _jpeg(), max_bytes=1024 * 1024)
        session.commit()
    _put(layout, "gelen/a.jpg", _jpeg(201))
    (item_id,) = _start(session_factory, layout, [{"slug": PASSPORT, "path": "gelen/a.jpg"}])
    with session_factory() as session:
        session.execute(
            update(TrainingItem).where(TrainingItem.id == item_id).values(status="review")
        )
        session.commit()

    assert TrainingMapJob().run_one(_context(session_factory, layout)) is False


@pytest.mark.usefixtures("catalog")
def test_a_failing_unit_counts_attempts_and_fails_at_the_limit(
    session_factory: sessionmaker[Session], layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    _put(layout, "gelen/a.jpg", _jpeg(201))
    (item_id,) = _start(session_factory, layout, [{"slug": PASSPORT, "path": "gelen/a.jpg"}])

    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("disk dolu")

    monkeypatch.setattr("app.training.map_scan.scan_map_item", broken)
    job, context = TrainingMapJob(), _context(session_factory, layout)
    for attempt in (1, 2):
        with pytest.raises(OSError):
            job.run_one(context)
        item = _item(session_factory, item_id)
        assert (item.status, item.idle_attempts, item.idle_claimed_by) == ("queued", attempt, None)
    with pytest.raises(OSError):
        job.run_one(context)

    item = _item(session_factory, item_id)
    assert (item.status, item.note, item.idle_attempts) == (
        "failed",
        ERROR_NOTE.format(error="OSError"),
        3,
    )
    assert "disk dolu" not in (item.note or "")
    assert _run_of(session_factory, item_id).counts_json == {"failed": 1}
    assert job.run_one(context) is False


@pytest.mark.usefixtures("catalog")
def test_an_abandoned_item_out_of_attempts_fails_and_its_run_is_recounted(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _put(layout, "gelen/a.jpg", _jpeg(201))
    (item_id,) = _start(session_factory, layout, [{"slug": PASSPORT, "path": "gelen/a.jpg"}])
    with session_factory() as session:
        session.execute(
            update(TrainingItem)
            .where(TrainingItem.id == item_id)
            .values(
                idle_claimed_by="olen-isleyici",
                idle_claim_expires_at=utcnow() - timedelta(seconds=1),
                idle_attempts=SETTINGS.worker_max_attempts,
            )
        )
        session.commit()

    assert TrainingMapJob().run_one(_context(session_factory, layout)) is False

    item = _item(session_factory, item_id)
    assert (item.status, item.note, item.idle_claimed_by) == ("failed", ABANDONED_NOTE, None)
    run = _run_of(session_factory, item_id)
    assert (run.status, run.counts_json) == ("done", {"failed": 1})


def test_the_map_job_is_an_idle_job() -> None:
    job = TrainingMapJob()

    assert isinstance(job, IdleJob)
    assert job.name == JOB_NAME
    assert TRAINING_MAP_ITEMS.failed == {"status": "failed"}
    assert TRAINING_MAP_ITEMS.abandoned is not None


@pytest.mark.usefixtures("catalog")
def test_upload_work_comes_before_the_map_scan(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    passport = passport_page(
        PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
    )
    _put(layout, "gelen/a.jpg", _jpeg(201))
    (item_id,) = _start(session_factory, layout, [{"slug": PASSPORT, "path": "gelen/a.jpg"}])
    with session_factory() as session:
        upload_id = store_upload(
            session,
            layout,
            SETTINGS,
            [IncomingFile("pasaport.pdf", make_document_pdf_bytes([passport]), "application/pdf")],
            channel="web",
        )
    provider = RecordingProvider.from_directory(
        write_recordings(tmp_path / "kayit", batch_responses([passport]))
    )
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS.model_copy(update={"worker_poll_seconds": 0.02}),
        provider=provider,
        idle_jobs=[TrainingMapJob()],
    )

    worker.start()
    try:
        _wait_until(lambda: _item(session_factory, item_id).status != "queued")
    finally:
        worker.stop()

    with session_factory() as session:
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        assert job.status == JobStatus.FINISHED
        analyzed = session.scalar(
            select(Event.id).where(Event.type == EventType.PAGE_ANALYZED.value).limit(1)
        )
        placed = session.scalar(
            select(Event.id).where(Event.type == EventType.TRAINING_EXAMPLE_PLACED.value)
        )
        assert analyzed is not None and placed is not None and analyzed < placed
    assert _item(session_factory, item_id).status == "placed"
    assert len(provider.training_requests) == 0


@pytest.mark.usefixtures("catalog")
def test_the_example_inventory_recognizes_a_typeless_file_and_is_read_once(
    session_factory: sessionmaker[Session], layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed, other = _jpeg(201), _jpeg(202)
    _put(layout, "gelen/a.jpg", listed)
    _put(layout, "gelen/b.jpg", other)
    layout.example_inventory_path.write_text(
        f"slug,role,sha256\nalbanian_passport,example,{sha256_bytes(listed)}\n", encoding="utf-8"
    )
    first, second = _start(
        session_factory, layout, [{"path": "gelen/a.jpg"}, {"path": "gelen/b.jpg"}]
    )
    reads: list[DataLayout] = []

    def counted(layout: DataLayout) -> ExampleInventory | None:
        reads.append(layout)
        return load_example_inventory(layout)

    monkeypatch.setattr("app.training.map_scan.load_example_inventory", counted)

    assert _scan_all(session_factory, layout) == 2

    item = _item(session_factory, first)
    assert (item.status, item.method, item.result_slug) == (
        "placed",
        "mechanical",
        "albanian_passport",
    )
    assert item.note is not None and "SHA-256 örnek envanterinde" in item.note
    assert _item(session_factory, second).status == "ai_pending"
    assert len(reads) == 1  # envanter değişmedikçe yeniden okunmaz


@pytest.mark.usefixtures("catalog")
def test_a_reference_that_became_unsafe_or_lost_fails_at_scan_time(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _put(layout, "gelen/a.jpg", _jpeg(201))
    _put(layout, "gelen/b.jpg", _jpeg(202))
    unsafe, lost = _start(
        session_factory, layout, [{"path": "gelen/a.jpg"}, {"path": "gelen/b.jpg"}]
    )
    with session_factory() as session:
        session.execute(
            update(TrainingItem).where(TrainingItem.id == unsafe).values(source_ref="../a.jpg")
        )
        session.execute(update(TrainingItem).where(TrainingItem.id == lost).values(checks_json={}))
        session.commit()

    _scan_all(session_factory, layout)

    assert _item(session_factory, unsafe).note == (
        "Taranamadı (harita satırı 2): güvensiz yol (`..` parçası)"
    )
    assert _item(session_factory, lost).note == (
        "Taranamadı (harita satırı 3): haritadaki yol kaydı yok"
    )
    assert _incoming(layout) == []


@pytest.mark.usefixtures("catalog")
def test_an_item_already_decided_is_not_scanned_again(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    _put(layout, "gelen/a.jpg", _jpeg(201))
    (item_id,) = _start(session_factory, layout, [{"path": "gelen/a.jpg"}])
    with session_factory() as session:
        item = session.get_one(TrainingItem, item_id)
        item.status = "review"
        with pytest.raises(ItemNotPlaceableError):
            scan_map_item(
                session,
                layout,
                load_known_types(session),
                item,
                MapFile(layout.root / "gelen" / "a.jpg", _jpeg(201)),
                inventory=None,
                max_bytes=1024 * 1024,
            )
