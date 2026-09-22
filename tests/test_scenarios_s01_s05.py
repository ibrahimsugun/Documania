"""09.3.2 — PRD §9 kabul senaryoları S1–S5 uçtan uca.

Her senaryo gerçek yoldan geçer: parti yükleme uç noktasıyla (`POST /api/uploads`, Inbox +
`FILE_UPLOADED`/`FILE_DUPLICATE`) açılır, `process_upload` ile render → analiz → plan → uygulama
adımlarından geçer. Dosyalar ve sağlayıcının kayıtlı yanıtları `tests/fixtures/gen.py`'nin aynı
sentetik sayfa tanımlarından üretilir; yapay zekâ canlı çağrılmaz, gerçek kimlik belgesi yoktur
(CONVENTIONS §6). "Kayıtlı çalışan" İK'nın bildiği kayıttır: E numarası, klasörü, isim yazımı ve
belge numaraları (`employee_identifiers`) yüklemeden önce yazılır.

**S3/S4 fotoğrafı (PLAN.md D12, D29).** Vesikalıkta ne isim ne numara vardır (§20.2.2 satır 8).
Sahibini aynı yüklenen dosyadaki kimlikli belgelerden alır: dosyanın kişi okunan adaylarının hepsi
tek bir kayıtlı çalışana satır 1/3 ile bağlıysa ve en az biri Hazir'a gidiyorsa fotoğraf o
çalışanın `Profile-Picture.jpeg`'idir — sayfanın gömülü görüntüsü kayıpsız çıkarılır
(`extract_image`, K12). Kayıtlı çalışan yoksa dosyada o bağ kurulmaz, fotoğraf Unresolved kalır ve
İK atamasıyla (08.2) aynı çıktı üretilir. Fotoğraf ayrıca katalogdaki kurallarla denetlenir
(11.7.1; kayıtlı kontrol yanıtı analizinin ardından gelir): kural ihlali olan fotoğraf sahibi
olsa da Unresolved'da kalır ve değiştirilmez (11.7.2). Her açık kuraldan geçip Hazir'a giren
fotoğraf örnek işaretlenir ve Profile Picture'ın tür açıklamasını besler (11.8.1).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai import AnalysisProvider, PageAnalysisRequest, TypeDescriptionRequest
from app.ai.recording_provider import RecordingProvider
from app.catalog import FileType, import_catalog, load_seed_catalog
from app.catalog.describe import accepted_photos, describe_type
from app.config import Settings, get_settings
from app.db.models import (
    Base,
    Document,
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    Event,
    KnownDocumentType,
    Page,
    QueueItem,
    Upload,
    UploadStatus,
    allocate_employee_number,
)
from app.db.session import create_db_engine, create_session_factory, get_session
from app.events import EventType
from app.main import create_app
from app.matching.match import EmployeeAction, MatchedBy, normalize_document_number
from app.matching.names import normalize_name
from app.pipeline.orchestrate import ProcessedUpload, current_plan, process_upload
from app.pipeline.plan import Operation, PlanEmployee, PlanItem, Route, read_plan
from app.pipeline.render import image_copy
from app.pipeline.route import assign_queue_item
from app.storage import DataLayout, employee_folder_name, prepare_data_dir
from app.web.auth import PanelUser, get_current_user
from app.web.routers.uploads import get_layout
from tests.ai.payloads import description_payload
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    SyntheticPage,
    SyntheticPerson,
    driving_license_pages,
    make_document_pdf_bytes,
    make_page_image_bytes,
    make_portrait_image_bytes,
    passport_page,
    photo_check_response,
    profile_picture_page,
    recorded_provider,
    residence_card_pages,
    unknown_document_page,
    work_permit_page,
)

CATALOG = load_seed_catalog()
SETTINGS = Settings(_env_file=None, database_url="sqlite://")
SIGNED_IN = PanelUser(id=1, username="ik-uzmani", role="admin")

PASSPORT_NUMBER = "00 0000001"
LICENSE_NUMBER = "000123456"
RESIDENCE_NUMBER = "AB1234567"
PERMIT_NUMBER = "WP-0000042"
ORNEKOVA_PERSONAL = ("ORNEKOVA", "Ornekova", "Орнекова", "0000001", "1990-01-01")
SIDOROV_PERSONAL = ("SIDOROV", "Sidorov", "123456", "1234567", "0000042", "1985-05-05")

ORNEKOVA_FOLDER = "Test_Ornekova_E0001"
SIDOROV_FOLDER = "Ivan_Sidorov_E0001"
PASSPORT_OUTPUT = "Test_Ornekova-Passport.pdf"
LICENSE_OUTPUT = "Ivan_Sidorov-Driving-License.pdf"
RESIDENCE_OUTPUT = "Ivan_Sidorov-Residence-Card.pdf"
PERMIT_OUTPUT = "Ivan_Sidorov-Work-Permit.pdf"
PHOTO_OUTPUT = "Ivan_Sidorov-Profile-Picture.jpeg"
PHOTO = "profile_picture"
R6_REASON = "Ardışıklık güvenlik kuralı (R6)"
NO_PERSON_REASON = "Kişi tespit edilemedi: belgede ne ad-soyad ne belge numarası okundu."


# --- ortam: geçici veritabanı, veri dizini ve gerçek yükleme uç noktası -------------------------


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'scenarios.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as db_session:
        import_catalog(db_session, CATALOG)
        db_session.commit()
        yield db_session


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


@pytest.fixture
def client(engine: Engine, layout: DataLayout) -> Iterator[TestClient]:
    application = create_app()
    factory = create_session_factory(engine)

    def _override_get_session() -> Iterator[Session]:
        with factory() as db_session:
            yield db_session

    application.dependency_overrides[get_session] = _override_get_session
    application.dependency_overrides[get_layout] = lambda: layout
    application.dependency_overrides[get_settings] = lambda: SETTINGS
    # Uç noktalar oturum ister (10.1.2); senaryolar panel kullanıcısı olarak yükler.
    application.dependency_overrides[get_current_user] = lambda: SIGNED_IN
    yield TestClient(application)
    application.dependency_overrides.clear()


# --- yardımcılar ------------------------------------------------------------------------------


def _upload(client: TestClient, session: Session, *files: tuple[str, bytes]) -> Upload:
    """Partiyi yükleme uç noktasıyla açar (`received`, commit edilmiş)."""
    response = client.post(
        "/api/uploads",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )
    assert response.status_code == 201, response.text
    return session.get_one(Upload, response.json()["upload_id"])


def _process(
    session: Session, layout: DataLayout, upload: Upload, provider: RecordingProvider
) -> ProcessedUpload:
    result = process_upload(session, layout, upload, settings=SETTINGS, provider=provider)
    assert result.status is UploadStatus.DONE
    return result


def _register_employee(
    session: Session,
    layout: DataLayout,
    person: SyntheticPerson,
    numbers: Sequence[tuple[str, str]],
) -> Employee:
    """İK'nın kayıtlı çalışanı: E numarası, klasör, `Ad Soyad` yazımı, (tür, numara) çiftleri."""
    employee_id = allocate_employee_number(session)
    given_names, surname = person.given_names.title(), person.surname.title()
    employee = Employee(
        id=employee_id,
        folder_name=employee_folder_name(given_names, surname, employee_id),
        given_names=given_names,
        surname=surname,
        date_of_birth=person.date_of_birth,
        nationality=person.nationality,
    )
    session.add(employee)
    raw_name = f"{given_names} {surname}"
    session.add(
        EmployeeAlias(
            employee=employee, raw_name=raw_name, normalized_name=normalize_name(raw_name)
        )
    )
    for kind, number in numbers:
        session.add(
            EmployeeIdentifier(
                employee=employee, kind=kind, value=normalize_document_number(number)
            )
        )
    session.flush()
    layout.ensure_employee_tree(employee.folder_name)
    session.commit()
    return employee


def _items(session: Session, upload: Upload) -> tuple[PlanItem, ...]:
    plan = current_plan(session, upload)
    assert plan is not None
    return read_plan(plan).items


def _events(session: Session, upload: Upload) -> list[Event]:
    query = select(Event).where(Event.upload_id == upload.id).order_by(Event.id)
    return list(session.scalars(query))


def _chain(events: Sequence[Event]) -> list[tuple[EventType, int | None, int | None]]:
    return [(EventType(row.type), row.file_id, row.page_index) for row in events]


def _assert_no_personal_values(events: Sequence[Event], values: Sequence[str]) -> None:
    logged = json.dumps([[row.data_json, row.message] for row in events], ensure_ascii=False)
    for value in values:
        assert value not in logged


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir()) if directory.exists() else []


def _outputs(session: Session) -> list[Document]:
    return list(session.scalars(select(Document).order_by(Document.id)))


def _queued(session: Session, upload: Upload) -> dict[str, QueueItem]:
    query = select(QueueItem).where(QueueItem.upload_id == upload.id)
    return {row.plan_item_id or "": row for row in session.scalars(query)}


def _page_contents(pdf: bytes | Path) -> list[bytes]:
    """Sayfaların içerik akışları: sayfa kopyası (extract) bunları bayt bayt taşır."""
    content = pdf.read_bytes() if isinstance(pdf, Path) else pdf
    contents: list[bytes] = []
    for page in PdfReader(BytesIO(content)).pages:
        stream = page.get_contents()
        assert stream is not None
        contents.append(stream.get_data())
    return contents


def _embedded_images(pdf: Path) -> list[list[bytes]]:
    """Her sayfanın gömülü görüntülerinin saklanan baytları, sayfa sırasıyla."""
    with pymupdf.open(pdf) as document:
        return [
            [document.extract_image(image[0])["image"] for image in page.get_images(full=True)]
            for page in document
        ]


# --- S1: kayıtlı çalışanın tek sayfalık pasaportu ------------------------------------------------


def _passport() -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1)
    )


def _register_ornekova(session: Session, layout: DataLayout) -> Employee:
    return _register_employee(
        session, layout, PERSON_ORNEKOVA, [("russian_passport", PASSPORT_NUMBER)]
    )


def test_s1_a_registered_employee_s_passport_is_passed_through_to_hazir(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee = _register_ornekova(session, layout)
    passport = _passport()
    content = make_document_pdf_bytes([passport])
    upload = _upload(client, session, ("pasaport.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [passport])

    result = _process(session, layout, upload, provider)

    # Plan: tek öğe, numarasından kayıtlı çalışana eşleşir, Direkt Belge olduğu gibi geçer.
    (item,) = _items(session, upload)
    assert (item.route, item.operation, item.document_type_slug, item.target_name) == (
        Route.READY,
        Operation.PASSTHROUGH,
        "russian_passport",
        PASSPORT_OUTPUT,
    )
    assert (item.employee.action, item.employee.employee_id, item.employee.matched_by) == (
        EmployeeAction.MATCH,
        employee.id,
        MatchedBy.DOCUMENT_NUMBER,
    )
    assert [request.page_index for request in provider.requests] == [0]

    # Hazir'daki çıktı yüklenen dosyanın kendisidir; Alinan'da orijinalin kopyası var (K10).
    folder = layout.employee_dir(ORNEKOVA_FOLDER)
    assert _names(folder / "Hazir") == [PASSPORT_OUTPUT]
    assert (folder / "Hazir" / PASSPORT_OUTPUT).read_bytes() == content
    assert _names(folder / "Alinan") == ["pasaport.pdf"]
    assert (folder / "Alinan" / "pasaport.pdf").read_bytes() == content
    assert layout.resolve(upload.files[0].stored_path).read_bytes() == content
    (output,) = _outputs(session)
    assert result.plan is not None
    assert (output.employee_id, output.type_slug, output.plan_id, output.status) == (
        employee.id,
        "russian_passport",
        result.plan.id,
        "active",
    )
    assert layout.resolve(output.path) == folder / "Hazir" / PASSPORT_OUTPUT
    assert output.source_refs_json == [{"file_id": 1, "pages": [0]}]
    assert session.scalars(select(Employee.id)).all() == [employee.id]
    assert _queued(session, upload) == {}
    assert PASSPORT_OUTPUT in (folder / "profil.md").read_text(encoding="utf-8")

    # Olay zinciri tam: yükleme → render → analiz → tür → kişi → boş profil alanı (05.7.3: kayıtta
    # orijinal yazım yoktu, pasaport okudu) → plan → çıktı, hepsi partide.
    events = _events(session, upload)
    assert _chain(events) == [
        (EventType.FILE_UPLOADED, 1, None),
        (EventType.PAGE_RENDERED, 1, 0),
        (EventType.PAGE_ANALYZED, 1, 0),
        (EventType.DOC_TYPE_DETERMINED, 1, 0),
        (EventType.PERSON_MATCHED, 1, 0),
        (EventType.EMPLOYEE_FIELD_FILLED, 1, 0),
        (EventType.PLAN_CREATED, None, None),
        (EventType.OUTPUT_SAVED, 1, 0),
    ]
    matched, filled, saved = events[4], events[5], events[-1]
    assert matched.employee_id == employee.id
    assert (filled.employee_id, filled.data_json) == (
        employee.id,
        {"field": "original_script_name", "source": "document", "rule": "05.7.3"},
    )
    assert session.get_one(Employee, employee.id).original_script_name == "Орнекова Тест"
    assert (saved.employee_id, saved.document_id) == (employee.id, output.id)
    assert saved.data_json is not None
    assert saved.data_json["operation"] == "passthrough"
    assert saved.data_json["sources"] == [{"file_id": 1, "pages": [0]}]
    assert saved.data_json["received"] == [{"file_id": 1, "copied": True}]
    assert saved.data_json["plan_id"] == result.plan.id
    _assert_no_personal_values(events, ORNEKOVA_PERSONAL)


# --- S2: aynı dosya ikinci kez --------------------------------------------------------------------


def test_s2_the_s1_file_uploaded_again_is_detected_and_not_analyzed_or_output_twice(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    _register_ornekova(session, layout)
    passport = _passport()
    content = make_document_pdf_bytes([passport])
    first = _upload(client, session, ("pasaport.pdf", content))
    _process(session, layout, first, recorded_provider(tmp_path / "ilk", [passport]))
    folder = layout.employee_dir(ORNEKOVA_FOLDER)
    before = {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}

    second = _upload(client, session, ("pasaport.pdf", content))
    # Sağlayıcı geçerli yanıtla hazır: çağrılsaydı analiz ederdi, çağrı sayısı sıfır kalmalı.
    provider = recorded_provider(tmp_path / "ikinci", [passport])
    _process(session, layout, second, provider)

    assert provider.requests == []
    (duplicate,) = second.files
    assert (duplicate.is_duplicate_of, duplicate.page_count) == (first.files[0].id, None)
    assert session.scalars(select(Page).where(Page.file_id == duplicate.id)).all() == []
    (item,) = _items(session, second)
    assert item.route is Route.SKIP
    assert item.route_reason is not None and "Tekrar yükleme (01.4.1)" in item.route_reason

    # İkinci çıktı ve ikinci Alinan kopyası yok; çalışan klasörü bayt bayt aynı.
    assert len(_outputs(session)) == 1
    assert _names(folder / "Hazir") == [PASSPORT_OUTPUT]
    assert _names(folder / "Alinan") == ["pasaport.pdf"]
    assert {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before
    assert _queued(session, second) == {}

    events = _events(session, second)
    assert _chain(events) == [
        (EventType.FILE_DUPLICATE, duplicate.id, None),
        (EventType.PLAN_CREATED, None, None),
        (EventType.OUTPUT_SKIPPED, duplicate.id, None),
    ]
    assert events[0].data_json == {"duplicate_of_file_id": first.files[0].id}
    assert events[-1].document_id is None
    _assert_no_personal_values(events, ORNEKOVA_PERSONAL)


# --- S3 ve S4: tek PDF'te birden çok belge --------------------------------------------------------


def _license() -> tuple[SyntheticPage, SyntheticPage]:
    return driving_license_pages(
        PERSON_SIDOROV, document_number=LICENSE_NUMBER, expiry_date=date(2031, 6, 30)
    )


def _residence() -> tuple[SyntheticPage, SyntheticPage]:
    return residence_card_pages(
        PERSON_SIDOROV, document_number=RESIDENCE_NUMBER, expiry_date=date(2029, 12, 31)
    )


def _work_permit() -> SyntheticPage:
    return work_permit_page(
        PERSON_SIDOROV, document_number=PERMIT_NUMBER, expiry_date=date(2027, 3, 31)
    )


def _unknown_type() -> SyntheticPage:
    return unknown_document_page(
        PERSON_SIDOROV, candidate_type_name="Peruvian Diploma", title="DIPLOMA"
    )


def _s3_pages(third: SyntheticPage) -> list[SyntheticPage]:
    """Ehliyet ön, foto, başka belge, oturum ön, oturum arka, ehliyet arka."""
    license_front, license_back = _license()
    residence_front, residence_back = _residence()
    return [
        license_front,
        profile_picture_page(),
        third,
        residence_front,
        residence_back,
        license_back,
    ]


def _s3_pages_with_work_permit() -> list[SyntheticPage]:
    return _s3_pages(_work_permit())


def _s4_pages() -> list[SyntheticPage]:
    """Ehliyet ön, ehliyet arka, foto, oturum ön, oturum arka."""
    return [*_license(), profile_picture_page(), *_residence()]


def _register_sidorov(session: Session, layout: DataLayout) -> Employee:
    # Kayıtlı çalışan belgelerinin numaralarıyla bilinir: çalışma izninde doğum tarihi yoktur,
    # numarası kayıtlı olmasa yalnız isimden eşleşirdi (§20.2.2 satır 5, Unresolved — D12 notu).
    return _register_employee(
        session,
        layout,
        PERSON_SIDOROV,
        [
            ("serbian_driving_license", LICENSE_NUMBER),
            ("serbian_residence_card", RESIDENCE_NUMBER),
            ("work_permit", PERMIT_NUMBER),
        ],
    )


def _run_pdf_batch(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    pages: Sequence[SyntheticPage],
) -> tuple[Upload, bytes]:
    content = make_document_pdf_bytes(pages)
    upload = _upload(client, session, ("belgeler.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", pages)
    _process(session, layout, upload, provider)
    assert [request.page_index for request in provider.requests] == list(range(len(pages)))
    return upload, content


def _assert_page_copy(output: Path, source: bytes, pages: Sequence[int]) -> None:
    """Çıktı kaynak sayfaların kendisidir: sayfa sayısı ve içerik akışları bayt bayt aynı."""
    source_pages = _page_contents(source)
    assert _page_contents(output) == [source_pages[index] for index in pages]


def _assert_photo_item(item: PlanItem, employee: Employee) -> None:
    """Fotoğraf kayıtlı çalışanın Hazir'ına gider: gömülü görüntü kayıpsız çıkarılır (K12). Sahibi
    kimliğinden eşleşmedi, aynı dosyanın kimlikli belgelerinden alındı (`matched_by` boş, D29)."""
    assert (item.document_type_slug, item.route, item.route_reason) == (PHOTO, Route.READY, None)
    assert (item.operation, item.target_format, item.target_name) == (
        Operation.EXTRACT_IMAGE,
        FileType.JPEG,
        PHOTO_OUTPUT,
    )
    assert item.employee == PlanEmployee(
        action=EmployeeAction.MATCH, employee_id=employee.id, matched_by=None
    )


@pytest.mark.parametrize(
    ("third", "third_route"),
    [
        pytest.param(_work_permit, Route.READY, id="katalogdaki-tur-hazir"),
        pytest.param(_unknown_type, Route.UNKNOWN, id="katalog-disi-tur-unknown"),
    ],
)
def test_s3_interleaved_pdf_splits_documents_and_queues_the_license_pieces(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    third: Callable[[], SyntheticPage],
    third_route: Route,
) -> None:
    employee = _register_sidorov(session, layout)
    upload, content = _run_pdf_batch(session, layout, client, tmp_path, _s3_pages(third()))

    items = _items(session, upload)
    assert [(item.item_id, item.sources[0].pages, item.route) for item in items] == [
        ("i1", (0,), Route.UNRESOLVED),
        ("i2", (1,), Route.READY),
        ("i3", (2,), third_route),
        ("i4", (3, 4), Route.READY),
        ("i5", (5,), Route.UNRESOLVED),
    ]
    license_front, photo, other, residence, license_back = items

    # Oturma izni: sayfa 4-5 çıkarılır, kayıtlı çalışanın Hazir'ına.
    assert (residence.operation, residence.target_name, residence.employee.employee_id) == (
        Operation.EXTRACT,
        RESIDENCE_OUTPUT,
        employee.id,
    )
    hazir = layout.ready_dir(SIDOROV_FOLDER)
    _assert_page_copy(hazir / RESIDENCE_OUTPUT, content, [3, 4])

    # Ehliyet 1 ve 6: arada başka belgeler var, birleştirilmez; iki parça ayrı ayrı Unresolved (R6).
    for piece, counterpart in ((license_front, 6), (license_back, 1)):
        assert piece.document_type_slug == "serbian_driving_license"
        assert piece.route_reason is not None and piece.route_reason.startswith(R6_REASON)
        assert f"olabilecek parça (sayfa {counterpart})" in piece.route_reason
    assert LICENSE_OUTPUT not in _names(hazir)

    # Sayfa 3 türüne göre: katalogdaki çalışma izni Hazir'a, katalog dışı tür Unknown'a.
    queued = _queued(session, upload)
    if third_route is Route.READY:
        assert (other.document_type_slug, other.operation, other.target_name) == (
            "work_permit",
            Operation.EXTRACT,
            PERMIT_OUTPUT,
        )
        _assert_page_copy(hazir / PERMIT_OUTPUT, content, [2])
        assert _names(hazir) == [PHOTO_OUTPUT, RESIDENCE_OUTPUT, PERMIT_OUTPUT]
    else:
        assert other.document_type_slug is None
        assert other.route_reason is not None
        assert other.route_reason.startswith("Bilinmeyen belge türü (04.6.1)")
        assert '"Peruvian Diploma"' in other.route_reason
        assert queued["i3"].kind == "unknown"
        assert _names(layout.queue_dir("unknown", upload.id)) == ["belgeler.pdf", "reason.json"]
        assert _names(hazir) == [PHOTO_OUTPUT, RESIDENCE_OUTPUT]

    # Fotoğraf (sayfa 2): kişi taşımıyor; dosyanın kimlikli belgeleri tek kayıtlı çalışana bağlı,
    # sahibi o (D29). Sayfa 3'ün türü sonucu değiştirmez.
    _assert_photo_item(photo, employee)

    assert {key: row.kind for key, row in queued.items() if key != "i3"} == {
        "i1": "unresolved",
        "i5": "unresolved",
    }
    unresolved = layout.queue_dir("unresolved", upload.id)
    assert _names(unresolved) == ["belgeler.pdf", "reason.json"]
    assert (unresolved / "belgeler.pdf").read_bytes() == content
    reason = json.loads((unresolved / "reason.json").read_text(encoding="utf-8"))
    assert json.dumps(reason, ensure_ascii=False).count(R6_REASON) == 2
    assert layout.resolve(upload.files[0].stored_path).read_bytes() == content
    _assert_no_personal_values(_events(session, upload), SIDOROV_PERSONAL)


def test_s4_sequential_pdf_yields_three_independent_documents(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee = _register_sidorov(session, layout)
    upload, content = _run_pdf_batch(session, layout, client, tmp_path, _s4_pages())

    # Üç bağımsız belge: sayfaları ayrık, her biri kendi türü ve kendi rotasıyla.
    license_item, photo, residence = _items(session, upload)
    assert [
        (item.document_type_slug, item.sources[0].pages)
        for item in (license_item, photo, residence)
    ] == [
        ("serbian_driving_license", (0, 1)),
        ("profile_picture", (2,)),
        ("serbian_residence_card", (3, 4)),
    ]
    for item, name in ((license_item, LICENSE_OUTPUT), (residence, RESIDENCE_OUTPUT)):
        assert (item.route, item.operation, item.target_name, item.employee.employee_id) == (
            Route.READY,
            Operation.EXTRACT,
            name,
            employee.id,
        )
    hazir = layout.ready_dir(SIDOROV_FOLDER)
    _assert_page_copy(hazir / LICENSE_OUTPUT, content, [0, 1])
    _assert_page_copy(hazir / RESIDENCE_OUTPUT, content, [3, 4])
    # Üçüncü belge fotoğraf: kişi taşımıyor, sahibi dosyadaki ehliyet ve oturma izninin çalışanı
    # (D29); kuyruk boş.
    _assert_photo_item(photo, employee)
    assert [(row.type_slug, row.source_refs_json) for row in _outputs(session)] == [
        ("serbian_driving_license", [{"file_id": 1, "pages": [0, 1]}]),
        ("profile_picture", [{"file_id": 1, "pages": [2]}]),
        ("serbian_residence_card", [{"file_id": 1, "pages": [3, 4]}]),
    ]
    assert _names(hazir) == [LICENSE_OUTPUT, PHOTO_OUTPUT, RESIDENCE_OUTPUT]
    assert _queued(session, upload) == {}
    _assert_no_personal_values(_events(session, upload), SIDOROV_PERSONAL)


@pytest.mark.parametrize(
    ("pages", "photo_page"),
    [pytest.param(_s3_pages_with_work_permit, 1, id="S3"), pytest.param(_s4_pages, 2, id="S4")],
)
def test_s3_s4_the_photo_page_becomes_the_employee_s_profile_picture(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    pages: Callable[[], list[SyntheticPage]],
    photo_page: int,
) -> None:
    # PRD §9: S3 "Profile-Picture.jpeg (2)", S4 "Üç bağımsız çıktı". Çıktı sayfanın gömülü
    # görüntüsünün kendisidir — render yok, yeniden kodlama yok (K12).
    employee = _register_sidorov(session, layout)
    upload, _ = _run_pdf_batch(session, layout, client, tmp_path, pages())

    (photo,) = [item for item in _items(session, upload) if item.document_type_slug == PHOTO]
    _assert_photo_item(photo, employee)
    assert [(source.file_id, source.pages) for source in photo.sources] == [(1, (photo_page,))]
    assert photo.item_id not in _queued(session, upload)
    output = layout.ready_dir(SIDOROV_FOLDER) / PHOTO_OUTPUT
    assert output.read_bytes() == make_portrait_image_bytes()
    (document,) = [row for row in _outputs(session) if row.type_slug == PHOTO]
    assert (document.employee_id, document.format, document.source_refs_json) == (
        employee.id,
        "jpeg",
        [{"file_id": 1, "pages": [photo_page]}],
    )


def test_s3_without_a_registered_employee_the_photo_stays_queued_and_hr_assigns_it_losslessly(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    # Kayıtlı çalışan yok: ehliyet ön yüzü kimseyle eşleşmez, çalışma izni çalışanı açar (satır
    # 6) — dosyada tek çalışana satır 1/3 ile bağlanan kimlik yok, fotoğrafın sahibi bulunmaz ve
    # satır 8 ile Unresolved kalır (D29). İK öğeyi çalışana atayınca (08.2) çıktı sayfa 2'nin
    # gömülü görüntüsünün kendisidir — render yok, yeniden kodlama yok (K12).
    upload, _ = _run_pdf_batch(session, layout, client, tmp_path, _s3_pages_with_work_permit())
    _, photo, permit, _, _ = _items(session, upload)
    assert (photo.route, photo.route_reason, photo.employee.action) == (
        Route.UNRESOLVED,
        NO_PERSON_REASON,
        EmployeeAction.NONE,
    )
    assert (permit.route, permit.employee.action) == (Route.READY, EmployeeAction.CREATE)
    assert permit.employee.employee_id is not None

    assigned = assign_queue_item(
        session,
        layout,
        _queued(session, upload)["i2"].id,
        permit.employee.employee_id,
        actor="ik.kullanici",
        render_image_dpi=SETTINGS.render_image_dpi,
        render_image_jpeg_quality=SETTINGS.render_image_jpeg_quality,
    )
    session.commit()

    assert assigned.operation is Operation.EXTRACT_IMAGE
    document = assigned.executed.document
    assert document.path.endswith("-Profile-Picture.jpeg")
    assert layout.resolve(document.path).read_bytes() == make_portrait_image_bytes()
    assert document.source_refs_json == [{"file_id": 1, "pages": [1]}]


# --- 11.7: kural ihlali olan fotoğraf Hazir'a girmez, değiştirilmez ------------------------------


@pytest.mark.parametrize(
    ("photo", "portrait", "reason"),
    [
        pytest.param(
            lambda: profile_picture_page(
                people=2, photo_check=photo_check_response({"single_person": "fail"})
            ),
            ((480, 600), 2),
            "Fotoğraf kurallarına uymuyor (11.7.1): Tek kişi.",
            id="iki-kisi",
        ),
        pytest.param(
            lambda: profile_picture_page(size=(300, 400)),
            ((300, 400), 1),
            "Fotoğraf kurallarına uymuyor (11.7.1): Asgari çözünürlük (300×400 piksel; asgari "
            "400×400).",
            id="dusuk-cozunurluk",
        ),
    ],
)
def test_s4_photo_breaking_a_rule_stays_out_of_hazir_and_is_not_changed(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    photo: Callable[[], SyntheticPage],
    portrait: tuple[tuple[int, int], int],
    reason: str,
) -> None:
    # PRD 11.7.1 ve Faz 2 kapanışı: kural ihlali olan fotoğraf Hazir'a girmez, gerekçesi yazılıdır;
    # dosyanın kayıtlı sahibi (D29) ihlali ezmez. 11.7.2: fotoğraf kırpılmaz, düzeltilmez — İK
    # yine de atarsa çıktı gömülü görüntünün kendisidir.
    employee = _register_sidorov(session, layout)
    pages = [*_license(), photo(), *_residence()]
    upload, content = _run_pdf_batch(session, layout, client, tmp_path, pages)

    license_item, photo_item, residence_item = _items(session, upload)
    assert (photo_item.route, photo_item.route_reason, photo_item.employee.action) == (
        Route.UNRESOLVED,
        reason,
        EmployeeAction.NONE,
    )
    assert (license_item.route, residence_item.route) == (Route.READY, Route.READY)
    assert _names(layout.ready_dir(SIDOROV_FOLDER)) == [LICENSE_OUTPUT, RESIDENCE_OUTPUT]
    queued = _queued(session, upload)["i2"]
    assert (queued.kind, queued.reason) == ("unresolved", reason)
    (queued_event,) = [
        event
        for event in _events(session, upload)
        if event.type == EventType.QUEUED_UNRESOLVED and event.page_index == 2
    ]
    assert queued_event.message == reason
    (analyzed,) = [
        event
        for event in _events(session, upload)
        if event.type == EventType.PAGE_ANALYZED and event.page_index == 2
    ]
    assert "fail" in analyzed.data_json["photo_check"].values()
    # Kaynak ve gömülü fotoğraf olduğu gibi kalır (K10, 11.7.2).
    (upload_file,) = upload.files
    assert layout.resolve(upload_file.stored_path).read_bytes() == content
    size, people = portrait
    original_photo = make_portrait_image_bytes(size=size, people=people)
    assert _embedded_images(layout.resolve(upload_file.stored_path))[2] == [original_photo]

    assigned = assign_queue_item(
        session,
        layout,
        queued.id,
        employee.id,
        actor="ik.kullanici",
        render_image_dpi=SETTINGS.render_image_dpi,
        render_image_jpeg_quality=SETTINGS.render_image_jpeg_quality,
    )
    session.commit()

    assert assigned.operation is Operation.EXTRACT_IMAGE
    assert layout.resolve(assigned.executed.document.path).read_bytes() == original_photo


# --- 11.8: kabul edilen fotoğraf örnek işaretlenir ve açıklamayı besler --------------------------


class _Describer(AnalysisProvider):
    """Ağsız test sağlayıcısı: tür açıklaması isteğini saklar, verilen yanıtı döner."""

    name = "aciklayan"

    def __init__(self, response: object) -> None:
        super().__init__(model="aciklayan-model")
        self.response = response
        self.descriptions: list[TypeDescriptionRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_description(self, request: TypeDescriptionRequest) -> object:
        self.descriptions.append(request)
        return self.response


@pytest.mark.parametrize(
    ("photo", "marked"),
    [
        pytest.param(profile_picture_page, True, id="kurallardan-gecti"),
        pytest.param(
            lambda: profile_picture_page(
                photo_check=photo_check_response({"plain_background": "unsure"})
            ),
            False,
            id="emin-degil-hazirda-ama-ornek-degil",
        ),
        pytest.param(
            lambda: profile_picture_page(
                people=2, photo_check=photo_check_response({"single_person": "fail"})
            ),
            False,
            id="kural-ihlali-ik-atasa-da-ornek-degil",
        ),
    ],
)
def test_s4_an_accepted_photo_is_marked_as_example_and_feeds_the_description(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    photo: Callable[[], SyntheticPage],
    marked: bool,
) -> None:
    # PRD 11.8.1: kabul edilen fotoğraf (her açık kural `pass`, Hazir'da) örnek işaretlenir ve
    # açıklamayı besler. `unsure` fotoğraf Hazir'a girer ama kabulü kesin değildir; kural ihlali
    # olan fotoğrafı İK atasa da örnek olmaz.
    employee = _register_sidorov(session, layout)
    upload, _ = _run_pdf_batch(
        session, layout, client, tmp_path, [*_license(), photo(), *_residence()]
    )
    queued = _queued(session, upload)
    if "i2" in queued:
        assign_queue_item(
            session,
            layout,
            queued["i2"].id,
            employee.id,
            actor="ik.kullanici",
            render_image_dpi=SETTINGS.render_image_dpi,
            render_image_jpeg_quality=SETTINGS.render_image_jpeg_quality,
        )
        session.commit()
    (document,) = [row for row in _outputs(session) if row.type_slug == PHOTO]
    stored_rules = session.get_one(KnownDocumentType, PHOTO).photo_rules

    photos = accepted_photos(session, PHOTO, stored_rules)

    if not marked:
        assert photos == ()
        return
    assert [item.document_id for item in photos] == [document.id]
    output = layout.resolve(document.path)
    content = output.read_bytes()
    definition = "Omuzdan yukarı, yüz ortada; düz açık arka plan"
    provider = _Describer(
        description_payload(
            layout="Vesikalık fotoğraf; metin yok",
            headings=[],
            languages=[],
            scripts=[],
            field_locations=[],
            mrz=None,
            accepted_photo=definition,
        )
    )
    entry = CATALOG.get(PHOTO)
    assert entry is not None

    generated = describe_type(entry, layout, SETTINGS, provider, photos=photos)

    (request,) = provider.descriptions
    # Gönderilen, Hazir'daki fotoğrafın (gömülü görüntünün kayıpsız çıkarılmışı) analiz kopyasıdır.
    assert [image.data for image in request.images] == [
        image_copy(content, jpeg_quality=SETTINGS.page_render_jpeg_quality).content
    ]
    assert request.prompt.splitlines()[-1] == "1. kabul edilen fotoğraf 1"
    for value in (*SIDOROV_PERSONAL, SIDOROV_FOLDER, PHOTO_OUTPUT, employee.id):
        assert value not in request.prompt, value
    assert generated.photos == (document.id,)
    assert generated.text.endswith(f"Kabul edilen fotoğraf: {definition}.")
    # Fotoğraf değişmez (K11); açıklama kaydedilmez (tür formu İK'nındır).
    assert output.read_bytes() == content == make_portrait_image_bytes()
    session.expire_all()
    assert session.get_one(KnownDocumentType, PHOTO).prompt_description == entry.prompt_description


# --- S5: aynı partide ön ve arka yüz görüntüsü ---------------------------------------------------


def test_s5_front_and_back_images_become_one_lossless_driving_license_pdf(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    entry = CATALOG.get("serbian_driving_license")
    assert entry is not None and entry.direct is False  # Direkt Belge kapalı (K4)
    front, back = _license()
    front_jpeg, back_jpeg = make_page_image_bytes(front), make_page_image_bytes(back)
    upload = _upload(client, session, ("on.jpg", front_jpeg), ("arka.jpg", back_jpeg))
    provider = recorded_provider(tmp_path / "kayit", [front], [back])

    _process(session, layout, upload, provider)

    (item,) = _items(session, upload)
    assert (item.route, item.operation, item.target_name) == (
        Route.READY,
        Operation.MERGE,
        LICENSE_OUTPUT,
    )
    assert [(source.file_id, source.pages) for source in item.sources] == [(1, (0,)), (2, (0,))]

    # Tek PDF: iki sayfa, her sayfada yüklenen JPEG'in kendisi (kayıpsız sarma), ön sonra arka.
    hazir = layout.ready_dir(SIDOROV_FOLDER)
    assert _names(hazir) == [LICENSE_OUTPUT]
    assert _embedded_images(hazir / LICENSE_OUTPUT) == [[front_jpeg], [back_jpeg]]
    (output,) = _outputs(session)
    assert output.source_refs_json == [{"file_id": 1, "pages": [0]}, {"file_id": 2, "pages": [0]}]
    alinan = layout.employee_dir(SIDOROV_FOLDER) / "Alinan"
    assert _names(alinan) == ["arka.jpg", "on.jpg"]
    assert [(alinan / name).read_bytes() for name in ("on.jpg", "arka.jpg")] == [
        front_jpeg,
        back_jpeg,
    ]

    events = _events(session, upload)
    merged = [row for row in events if row.type == EventType.PAGES_MERGED]
    assert [(row.document_id, row.data_json and row.data_json["sources"]) for row in merged] == [
        (output.id, [{"file_id": 1, "pages": [0]}, {"file_id": 2, "pages": [0]}])
    ]
    _assert_no_personal_values(events, SIDOROV_PERSONAL)
