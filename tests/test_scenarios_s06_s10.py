"""09.3.3 — PRD §9 kabul senaryoları S6–S10 uçtan uca.

S1–S5 (`tests/test_scenarios_s01_s05.py`) gibi her senaryo gerçek yoldan geçer: parti yükleme uç
noktasıyla açılır, `process_upload` ile render → analiz → plan → uygulama adımlarından geçer.
Dosyalar ve sağlayıcının kayıtlı yanıtları `tests/fixtures/gen.py`'nin aynı sentetik sayfa
tanımlarından üretilir; yapay zekâ canlı çağrılmaz, gerçek kimlik belgesi yoktur (CONVENTIONS §6).
Ortam (geçici veritabanı, veri dizini, yükleme uç noktası) ve yardımcılar S1–S5'inkilerdir.

S6'nın "katalog yalnız PDF bekliyor" koşulu tohum kataloğunda yoktur (pasaport `pdf`/`jpeg`
bekler); senaryo, İK'nın kataloğu değiştirdiği durumdur: güncel katalog veritabanındakidir
(`export_catalog`), pasaportun `expected_file_types`'ı yüklemeden önce `[pdf]` yapılır.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import import_catalog, validate_catalog
from app.db.models import (
    Document,
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    Event,
    Upload,
)
from app.events import EventType
from app.matching.match import (
    NAME_ONLY_REASON,
    EmployeeAction,
    MatchedBy,
    normalize_document_number,
)
from app.pipeline.plan import Operation, PlanItem, Route, ValidationName
from app.storage import DataLayout
from tests import test_scenarios_s01_s05 as s01_s05
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    SyntheticPage,
    SyntheticPerson,
    blank_page,
    make_document_pdf_bytes,
    make_page_image_bytes,
    passport_page,
    recorded_provider,
    residence_card_pages,
    work_permit_page,
)
from tests.test_scenarios_s01_s05 import (
    CATALOG,
    ORNEKOVA_FOLDER,
    ORNEKOVA_PERSONAL,
    PASSPORT_NUMBER,
    PASSPORT_OUTPUT,
    PERMIT_NUMBER,
    PERMIT_OUTPUT,
    RESIDENCE_NUMBER,
    RESIDENCE_OUTPUT,
    SIDOROV_FOLDER,
    SIDOROV_PERSONAL,
    _assert_no_personal_values,
    _events,
    _items,
    _names,
    _outputs,
    _process,
    _queued,
    _register_employee,
    _upload,
)

PASSPORT = "russian_passport"
LICENSE_NUMBER = "000123456"
ORNEKOVA_RESIDENCE_NUMBER = "CD7654321"
ORNEKOVA_PERMIT_NUMBER = "WP-0000007"
UPLOAD_AGAIN = "Uygun formatta yeniden gönderin."
S6_REASON = f"Direkt Belge: beklenen dosya türü pdf, gelen jpeg. {UPLOAD_AGAIN}"
S9_REASON = "Okunamayan alanlar: document_number"
S9_NOTES = (
    "Belge numarası ve MRZ bölgesi bulanık, karakterler seçilemiyor. Karşılanmayan kabul "
    "kriteri: MRZ iki satırı da okunabilir olmalı"
)
S10_REASON = (
    f"{NAME_ONLY_REASON}. İsmi eşleşen çalışan: E0001. Yalnız isim eşleşmesi otomatik "
    "eşleştirme sayılmaz (R8)."
)
ORNEKOVA_OUTPUT_PREFIX = "Test_Ornekova-"

# Ortam fikstürleri (geçici veritabanı, veri dizini, yükleme uç noktası) S1–S5'inkilerdir; pytest
# onları bu modüldeki adlarından bulur.
engine = s01_s05.engine
session = s01_s05.session
layout = s01_s05.layout
client = s01_s05.client


# --- yardımcılar ------------------------------------------------------------------------------


def _count(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _event_types(events: Sequence[Event]) -> list[EventType]:
    return [EventType(row.type) for row in events]


def _reason_file(layout: DataLayout, kind: str, upload: Upload) -> dict[str, Any]:
    path = layout.queue_reason_path(kind, upload.id)
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _content_streams(pdf: bytes | Path) -> list[bytes | None]:
    """Sayfaların içerik akışları; boş sayfanın akışı yoktur (`None`)."""
    content = pdf.read_bytes() if isinstance(pdf, Path) else pdf
    streams: list[bytes | None] = []
    for page in PdfReader(BytesIO(content)).pages:
        stream = page.get_contents()
        streams.append(None if stream is None else stream.get_data())
    return streams


def _assert_page_copy(output: Path, source: bytes, pages: Sequence[int]) -> None:
    """Çıktı kaynak sayfaların kendisidir: sayfa sayısı ve içerik akışları bayt bayt aynı."""
    source_streams = _content_streams(source)
    copied = [source_streams[index] for index in pages]
    assert None not in copied
    assert _content_streams(output) == copied


def _failed_validations(item: PlanItem) -> list[ValidationName]:
    return [validation.name for validation in item.validations if not validation.ok]


def _passport(**changes: Any) -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1), **changes
    )


def _register_ornekova(
    session: Session,
    layout: DataLayout,
    numbers: Sequence[tuple[str, str]] = ((PASSPORT, PASSPORT_NUMBER),),
) -> Employee:
    return _register_employee(session, layout, PERSON_ORNEKOVA, numbers)


def _assert_queued_alone(
    session: Session, layout: DataLayout, upload: Upload, kind: str, name: str, content: bytes
) -> dict[str, Any]:
    """Partinin tek öğesi `kind` kuyruğunda: yüklenen dosyanın bayt bayt kopyası + `reason.json`."""
    assert {key: row.kind for key, row in _queued(session, upload).items()} == {"i1": kind}
    directory = layout.queue_dir(kind, upload.id)
    assert _names(directory) == [name, "reason.json"]
    assert (directory / name).read_bytes() == content
    assert layout.resolve(upload.files[0].stored_path).read_bytes() == content
    (entry,) = _reason_file(layout, kind, upload)["items"]
    return entry


# --- S6: Direkt Belge beklenmeyen biçimde ---------------------------------------------------------


@pytest.mark.parametrize(
    "registered", [False, True], ids=["kayitli-calisan-yok", "kayitli-calisan"]
)
def test_s6_direct_passport_as_jpeg_goes_to_unresolved_without_conversion(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path, registered: bool
) -> None:
    # İK kataloğu değiştirmiş: pasaport (Direkt Belge, K3) yalnız PDF bekliyor.
    entries = [entry.model_dump(mode="json") for entry in CATALOG]
    for entry in entries:
        if entry["slug"] == PASSPORT:
            assert entry["direct"] is True
            entry["expected_file_types"] = ["pdf"]
    import_catalog(session, validate_catalog(entries))
    session.commit()
    employee = _register_ornekova(session, layout) if registered else None
    passport = _passport()
    jpeg = make_page_image_bytes(passport)
    upload = _upload(client, session, ("pasaport.jpg", jpeg))
    provider = recorded_provider(tmp_path / "kayit", [passport])

    _process(session, layout, upload, provider)

    # Tür okunur, format kontrolü işlemden önce keser: işlem ve hedef yok, gerekçe PRD'nin notu.
    (item,) = _items(session, upload)
    assert (item.route, item.document_type_slug, item.operation, item.target_name) == (
        Route.UNRESOLVED,
        PASSPORT,
        None,
        None,
    )
    assert item.route_reason == S6_REASON
    assert _failed_validations(item) == [ValidationName.FILE_TYPE]
    # Kayıtlı çalışan yalnız kişi tahminidir; kayıt yoksa temiz numaradan çalışan açılmaz.
    if employee is None:
        assert (item.employee.action, item.employee.employee_id) == (EmployeeAction.NONE, None)
    else:
        assert (item.employee.action, item.employee.employee_id) == (
            EmployeeAction.MATCH,
            employee.id,
        )
    assert _count(session, Employee) == int(registered)
    assert (_count(session, EmployeeAlias), _count(session, EmployeeIdentifier)) == (
        int(registered),
        int(registered),
    )

    # Unresolved: JPEG olduğu gibi (dönüştürülmeden) kuyrukta, gerekçe dosyasında PRD notu.
    entry = _assert_queued_alone(session, layout, upload, "unresolved", "pasaport.jpg", jpeg)
    assert entry["reason"] == S6_REASON
    assert (entry["document_type_slug"], entry["sources"]) == (
        PASSPORT,
        [{"file_id": upload.files[0].id, "pages": [0]}],
    )

    # Dönüşüm yok: çıktı yok, sarma olayı yok, veri dizininin hiçbir yerinde PDF yok.
    assert _outputs(session) == []
    assert sorted(path.name for path in layout.root.rglob("*.pdf")) == []
    if employee is not None:
        folder = layout.employee_dir(employee.folder_name)
        assert (_names(folder / "Hazir"), _names(folder / "Alinan")) == ([], [])
    else:
        assert _names(layout.employees) == []
    events = _events(session, upload)
    types = _event_types(events)
    assert EventType.IMAGE_WRAPPED not in types and EventType.OUTPUT_SAVED not in types
    assert EventType.EMPLOYEE_CREATED not in types and EventType.EMPLOYEE_PENDING not in types
    (check,) = [row for row in events if row.type == EventType.DIRECT_DOC_CHECK]
    assert check.message == S6_REASON
    assert check.data_json is not None
    assert (check.data_json["check"], check.data_json["file_types"]) == ("file_type", ["jpeg"])
    assert types[-1] is EventType.QUEUED_UNRESOLVED
    _assert_no_personal_values(events, ORNEKOVA_PERSONAL)


# --- S7: çok sayfalı PDF'in içindeki pasaport sayfası ---------------------------------------------


def _s7_pages() -> list[SyntheticPage]:
    """Çalışma izni, pasaport, oturma izni ön ve arka: pasaport ikinci sayfa."""
    permit = work_permit_page(
        PERSON_ORNEKOVA, document_number=ORNEKOVA_PERMIT_NUMBER, expiry_date=date(2027, 3, 31)
    )
    residence = residence_card_pages(
        PERSON_ORNEKOVA, document_number=ORNEKOVA_RESIDENCE_NUMBER, expiry_date=date(2029, 12, 31)
    )
    return [permit, _passport(), *residence]


def test_s7_passport_page_inside_a_multi_page_pdf_is_extracted_alone_without_rendering(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path
) -> None:
    employee = _register_ornekova(
        session,
        layout,
        [
            (PASSPORT, PASSPORT_NUMBER),
            ("work_permit", ORNEKOVA_PERMIT_NUMBER),
            ("serbian_residence_card", ORNEKOVA_RESIDENCE_NUMBER),
        ],
    )
    pages = _s7_pages()
    content = make_document_pdf_bytes(pages)
    upload = _upload(client, session, ("taramalar.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", pages)

    _process(session, layout, upload, provider)

    # Pasaport (Direkt Belge) tek kaynağın tek sayfası: §20.3 satır 2, `extract`; matris izin verir.
    items = _items(session, upload)
    assert [(item.document_type_slug, item.sources[0].pages) for item in items] == [
        ("work_permit", (0,)),
        (PASSPORT, (1,)),
        ("serbian_residence_card", (2, 3)),
    ]
    permit, passport, residence = items
    assert (passport.route, passport.operation, passport.target_name) == (
        Route.READY,
        Operation.EXTRACT,
        PASSPORT_OUTPUT,
    )
    assert (passport.employee.employee_id, passport.employee.matched_by) == (
        employee.id,
        MatchedBy.DOCUMENT_NUMBER,
    )
    assert passport.validations and all(validation.ok for validation in passport.validations)

    # Passport.pdf tek sayfadır ve kaynak sayfanın kendisidir: içerik akışı bayt bayt aynı,
    # metin katmanı duruyor, sayfada görüntü yok — render edilmedi (K11, K12).
    hazir = layout.ready_dir(ORNEKOVA_FOLDER)
    output = hazir / PASSPORT_OUTPUT
    _assert_page_copy(output, content, [1])
    with pymupdf.open(output) as document:
        (page,) = document
        assert page.get_images(full=True) == []
        text = page.get_text()
    assert "PASSPORT" in text and PASSPORT_NUMBER in text
    assert all(line in text for line in pages[1].mrz_lines)

    # Öteki belgeler de kendi sayfalarıyla ayrı çıktılar; hiçbiri kuyrukta değil.
    assert (permit.route, residence.route) == (Route.READY, Route.READY)
    assert _names(hazir) == sorted(
        [
            PASSPORT_OUTPUT,
            f"{ORNEKOVA_OUTPUT_PREFIX}Residence-Card.pdf",
            f"{ORNEKOVA_OUTPUT_PREFIX}Work-Permit.pdf",
        ]
    )
    passport_output = next(row for row in _outputs(session) if row.type_slug == PASSPORT)
    assert passport_output.source_refs_json == [{"file_id": upload.files[0].id, "pages": [1]}]
    assert _queued(session, upload) == {}

    # Olaylar: çıktı sayfa çıkarmayla yazıldı; hiçbir çıktı için görüntü render edilmedi.
    events = _events(session, upload)
    extracted = [
        row
        for row in events
        if row.type == EventType.PAGE_EXTRACTED and row.document_id == passport_output.id
    ]
    assert len(extracted) == 1
    types = _event_types(events)
    assert EventType.IMAGE_RENDERED not in types and EventType.IMAGE_EXTRACTED not in types
    saved = [
        row
        for row in events
        if row.type == EventType.OUTPUT_SAVED and row.document_id == passport_output.id
    ]
    assert [row.data_json and row.data_json["operation"] for row in saved] == ["extract"]
    _assert_no_personal_values(events, ORNEKOVA_PERSONAL)


# --- S8: PDF ortasında boş sayfa ----------------------------------------------------------------


def _sidorov_residence() -> tuple[SyntheticPage, SyntheticPage]:
    return residence_card_pages(
        PERSON_SIDOROV, document_number=RESIDENCE_NUMBER, expiry_date=date(2029, 12, 31)
    )


def _sidorov_permit() -> SyntheticPage:
    return work_permit_page(
        PERSON_SIDOROV, document_number=PERMIT_NUMBER, expiry_date=date(2027, 3, 31)
    )


def _register_sidorov(session: Session, layout: DataLayout) -> Employee:
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


def _blank_between_card_faces() -> list[SyntheticPage]:
    front, back = _sidorov_residence()
    return [front, blank_page(), back]


def _blank_between_documents() -> list[SyntheticPage]:
    return [_sidorov_permit(), blank_page(), *_sidorov_residence()]


@pytest.mark.parametrize(
    ("pages", "outputs"),
    [
        pytest.param(
            _blank_between_card_faces, {RESIDENCE_OUTPUT: [0, 2]}, id="kartin-yuzleri-arasinda"
        ),
        pytest.param(
            _blank_between_documents,
            {PERMIT_OUTPUT: [0], RESIDENCE_OUTPUT: [2, 3]},
            id="iki-belge-arasinda",
        ),
    ],
)
def test_s8_blank_page_in_the_middle_of_a_pdf_is_skipped_not_an_error(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    pages: Callable[[], list[SyntheticPage]],
    outputs: dict[str, list[int]],
) -> None:
    blank = 1  # iki düzende de ikinci sayfa
    employee = _register_sidorov(session, layout)
    synthetic: list[SyntheticPage] = pages()
    content = make_document_pdf_bytes(synthetic)
    upload = _upload(client, session, ("belgeler.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", synthetic)

    # Parti hatasız biter (`_process`: `done`); boş sayfa analize gitmez.
    _process(session, layout, upload, provider)
    analyzed = [index for index in range(len(synthetic)) if index != blank]
    assert [request.page_index for request in provider.requests] == analyzed

    # Boş sayfa tek bir `skip` öğesidir; belgeler onun iki yanındaki sayfalarla çıkarılır.
    items = _items(session, upload)
    (skipped,) = [item for item in items if item.route is Route.SKIP]
    file_id = upload.files[0].id
    assert [(source.file_id, source.pages) for source in skipped.sources] == [(file_id, (blank,))]
    assert skipped.route_reason == (
        f"Boş sayfa (dosya {file_id}, sayfa {blank + 1}): atlanır; çıktıya ve kuyruğa girmez, "
        "hata sayılmaz."
    )
    documents = [item for item in items if item.route is not Route.SKIP]
    assert [
        (item.route, item.operation, item.target_name, list(item.sources[0].pages))
        for item in documents
    ] == [
        (Route.READY, Operation.EXTRACT, name, source_pages)
        for name, source_pages in outputs.items()
    ]
    assert all(item.employee.employee_id == employee.id for item in documents)

    # Çıktılar yalnız belge sayfalarının kopyasıdır: boş sayfa hiçbir çıktıya girmez.
    hazir = layout.ready_dir(SIDOROV_FOLDER)
    assert _names(hazir) == sorted(outputs)
    for name, source_pages in outputs.items():
        _assert_page_copy(hazir / name, content, source_pages)
    assert all(
        blank not in ref["pages"] for row in _outputs(session) for ref in row.source_refs_json
    )

    # Hata değil: kuyruk yok, hata olayı yok; boş sayfa işaretlenir ve atlandığı loglanır.
    assert _queued(session, upload) == {}
    events = _events(session, upload)
    types = _event_types(events)
    for failure in (
        EventType.PIPELINE_FAILED,
        EventType.PAGE_ANALYSIS_FAILED,
        EventType.PAGE_UNREADABLE,
        EventType.VALIDATION_FAILED,
    ):
        assert failure not in types
    assert [
        (row.file_id, row.page_index) for row in events if row.type == EventType.PAGE_BLANK
    ] == [(file_id, blank)]
    assert [
        (row.page_index, row.document_id) for row in events if row.type == EventType.OUTPUT_SKIPPED
    ] == [(blank, None)]
    _assert_no_personal_values(events, SIDOROV_PERSONAL)


# --- S9: bulanık pasaport -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "registered", [False, True], ids=["kayitli-calisan-yok", "kayitli-calisan"]
)
def test_s9_blurred_passport_number_goes_to_unreadable_naming_the_field(
    session: Session, layout: DataLayout, client: TestClient, tmp_path: Path, registered: bool
) -> None:
    # Kayıtlı çalışan numarasıyla bilinir; numara okunmadığı için ancak ad + doğum tarihi uyar.
    employee = _register_ornekova(session, layout) if registered else None
    passport = _passport(blurred={"document_number"}, mrz_legible=False, notes=S9_NOTES)
    content = make_document_pdf_bytes([passport])
    upload = _upload(client, session, ("pasaport.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [passport])

    _process(session, layout, upload, provider)

    # K1: zorunlu alan okunmuyor → Unreadable, gerekçe okunmayan alanın adıyla başlar.
    (item,) = _items(session, upload)
    assert (item.route, item.document_type_slug, item.operation, item.target_name) == (
        Route.UNREADABLE,
        PASSPORT,
        None,
        None,
    )
    assert item.route_reason is not None and item.route_reason.startswith(S9_REASON)
    assert _failed_validations(item) == [ValidationName.REQUIRED_FIELDS]
    entry = _assert_queued_alone(session, layout, upload, "unreadable", "pasaport.pdf", content)
    assert entry["reason"] == item.route_reason

    # Okunamayan belgeden çalışan açılmaz, profil önerilmez, kayıtlı çalışana hiçbir şey eklenmez;
    # kayıtlı çalışan yalnız kişi tahmini olarak kalır.
    if employee is None:
        assert (item.employee.action, item.employee.employee_id) == (EmployeeAction.NONE, None)
        assert _names(layout.employees) == []
    else:
        assert (item.employee.action, item.employee.employee_id, item.employee.matched_by) == (
            EmployeeAction.MATCH,
            employee.id,
            MatchedBy.NAME_DOB,
        )
        folder = layout.employee_dir(employee.folder_name)
        assert (_names(folder / "Hazir"), _names(folder / "Alinan")) == ([], [])
    assert _count(session, Employee) == int(registered)
    assert (_count(session, EmployeeAlias), _count(session, EmployeeIdentifier)) == (
        int(registered),
        int(registered),
    )
    assert _outputs(session) == []

    events = _events(session, upload)
    types = _event_types(events)
    assert EventType.EMPLOYEE_CREATED not in types and EventType.EMPLOYEE_PENDING not in types
    queued = [row for row in events if row.type == EventType.QUEUED_UNREADABLE]
    assert [(row.file_id, row.page_index, row.message) for row in queued] == [
        (upload.files[0].id, 0, item.route_reason)
    ]
    _assert_no_personal_values(events, (*ORNEKOVA_PERSONAL, "2030-01-01"))


# --- S10: yalnız isimle eşleşen belge -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _NameOnly:
    """S10 düzeni: yüklenen belge ve İK'nın kayıtlı çalışanı (kişi, bildiği belge numaraları)."""

    page: SyntheticPage
    person: SyntheticPerson
    numbers: tuple[tuple[str, str], ...]


def _name_without_birth_date() -> _NameOnly:
    # Çalışma izninde doğum tarihi yok; numarası temiz ama çalışanın kayıtlı numaralarında değil.
    return _NameOnly(
        _sidorov_permit(), PERSON_SIDOROV, (("serbian_driving_license", LICENSE_NUMBER),)
    )


def _name_with_another_birth_date() -> _NameOnly:
    # Pasaportun doğum tarihi kayıtlı çalışanınkinden farklı; numarası temiz ama kayıtlı değil.
    return _NameOnly(_passport(), replace(PERSON_ORNEKOVA, date_of_birth=date(1980, 1, 1)), ())


@pytest.mark.parametrize(
    "arrange",
    [
        pytest.param(_name_without_birth_date, id="dogum-tarihi-yok"),
        pytest.param(_name_with_another_birth_date, id="dogum-tarihi-farkli"),
    ],
)
def test_s10_name_only_match_goes_to_unresolved_without_matching_or_a_new_employee(
    session: Session,
    layout: DataLayout,
    client: TestClient,
    tmp_path: Path,
    arrange: Callable[[], _NameOnly],
) -> None:
    case = arrange()
    employee = _register_employee(session, layout, case.person, case.numbers)
    page = case.page
    content = make_document_pdf_bytes([page])
    upload = _upload(client, session, ("belge.pdf", content))
    provider = recorded_provider(tmp_path / "kayit", [page])

    _process(session, layout, upload, provider)

    # §20.2.2 satır 5: isim eşleşti, doğum tarihi yok ya da farklı → Unresolved (R8). Numara temiz
    # olsa da satır 6'ya inilmez: yeni çalışan açılmaz.
    (item,) = _items(session, upload)
    assert (item.route, item.operation, item.target_name, item.route_reason) == (
        Route.UNRESOLVED,
        None,
        None,
        S10_REASON,
    )
    assert (item.employee.action, item.employee.employee_id, item.employee.matched_by) == (
        EmployeeAction.NONE,
        None,
        None,
    )
    assert item.validations and all(validation.ok for validation in item.validations)
    entry = _assert_queued_alone(session, layout, upload, "unresolved", "belge.pdf", content)
    assert entry["reason"] == S10_REASON
    assert entry["employee_guess"] == {"action": "none", "employee_id": None, "matched_by": None}

    # Otomatik eşleştirme yok: kayıtlı çalışanın klasörüne ve kaydına hiçbir şey girmez.
    assert session.scalars(select(Employee.id)).all() == [employee.id]
    assert _count(session, EmployeeAlias) == 1
    assert session.scalars(select(EmployeeIdentifier.value)).all() == [
        normalize_document_number(number) for _, number in case.numbers
    ]
    assert _names(layout.employees) == [employee.folder_name]
    folder = layout.employee_dir(employee.folder_name)
    assert (_names(folder / "Hazir"), _names(folder / "Alinan")) == ([], [])
    assert _count(session, Document) == 0

    events = _events(session, upload)
    types = _event_types(events)
    for forbidden in (
        EventType.PERSON_MATCHED,
        EventType.EMPLOYEE_CREATED,
        EventType.EMPLOYEE_PENDING,
        EventType.OUTPUT_SAVED,
    ):
        assert forbidden not in types
    (not_matched,) = [row for row in events if row.type == EventType.PERSON_NOT_MATCHED]
    assert (not_matched.employee_id, not_matched.data_json) == (
        None,
        {"rule": "name_only", "queue": "unresolved", "employee_ids": ["E0001"]},
    )
    assert types[-1] is EventType.QUEUED_UNRESOLVED
    _assert_no_personal_values(events, (*ORNEKOVA_PERSONAL, *SIDOROV_PERSONAL))
