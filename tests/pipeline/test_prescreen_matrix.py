"""13.2.1 kabulü — kolay sayfalar ucuz modele yönlendirilir; test matrisi doğruluğu düşmez.

Test matrisi PRD §9 kabul senaryolarının partileridir (S1 pasaport, S3 araya girmiş sayfalar, S4
art arda üç belge ve fotoğraf, S5 ön/arka görüntü, yeni çalışan, katalog dışı tür, okunamayan
alan, S19 ad + doğum tarihiyle yeni çalışan). Her parti önce ön elemesiz (yalnız ana model), sonra
ucuz model ön elemesiyle baştan sona işlenir (`process_upload`: render → analiz → plan → uygulama)
ve sonuçlar karşılaştırılır: sayfa analizleri, plan öğeleri, çıktı dosyaları (bayt bayt), kuyruk,
çalışanlar ve belge numaraları aynı olmalıdır. Her koşu ayrı veritabanı ve veri dizinindedir.

Ucuz model birkaç davranışla denenir: ana modelle aynı okuyan (kolay sayfalar onda kalır), belge
numarasını, doğum tarihini ya da MRZ'yi yanlış okuyan, her sayfaya not yazan, sayfayı okunamaz ya
da boş diyen ve şemaya uymayan yanıt veren. Doğum tarihi satır 6b'de (§20.2.4) yeni çalışan açtığı
için doğum tarihi zorunlu türün MRZ'siz sayfası kolay değildir (`unverified_date_of_birth`, §C84):
S19'un iş sözleşmesi hep ana modele gider, yanlış okunan tarih hayalet çalışan açamaz. Yanlış
okuduğu hiçbir değer sonuca sızmamalı: kolay sayfa ölçütü (`prescreen_escalation`) o sayfaları ana
modele göndermeli. Sağlayıcılar ağ çağrısı yapmaz; iki model aynı kayıtlı yanıtlardan
(`tests/fixtures/gen.py`'nin sentetik sayfaları) okur.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import AnalysisProvider, PageAnalysisRequest, PhotoCheckRequest
from app.catalog import Catalog, export_catalog, import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    Base,
    Document,
    Employee,
    EmployeeIdentifier,
    Event,
    Page,
    QueueItem,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.db.session import create_db_engine, create_session_factory
from app.events import PRESCREEN_DATA_KEY, EventType
from app.pipeline.orchestrate import current_plan, plan_executor, process_upload, reanalyze_upload
from app.pipeline.plan import read_plan
from app.storage import DataLayout, prepare_data_dir, write_to_inbox
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_PRUEBA,
    PERSON_SIDOROV,
    PERSON_TESTOVA_SHCHELKINA,
    SyntheticPage,
    SyntheticPerson,
    batch_responses,
    driving_license_pages,
    employment_contract_entry,
    employment_contract_page,
    make_document_pdf_bytes,
    make_page_image_bytes,
    passport_page,
    profile_picture_page,
    residence_card_pages,
    unknown_document_page,
    work_permit_page,
)
from tests.test_scenarios_s01_s05 import _register_employee

# Tohum katalog ve S19'un numarasız türü (zorunlu alanları ad, soyad, doğum tarihi).
CATALOG = Catalog((*load_seed_catalog(), employment_contract_entry()))
SETTINGS = Settings(_env_file=None, database_url="sqlite://")
UPLOAD_ID = "u_20260919_0088"
MAIN, CHEAP = "ana-model", "ucuz-model"

PASSPORT_NUMBER = "00 0000001"
LICENSE_NUMBER = "000123456"
RESIDENCE_NUMBER = "AB1234567"
PERMIT_NUMBER = "WP-0000042"


# --- iki model, tek gerçek ----------------------------------------------------------------------


class _Truth:
    """Partinin kayıtlı yanıtları. Aynı isteği (aynı sayfayı) soran iki model aynı yanıtı okur;
    yeni istek bir sonraki sayfanın yanıtını açar."""

    def __init__(self, responses: Sequence[dict[str, Any]]) -> None:
        self.analyses = [response for response in responses if "page_index" in response]
        self.checks = [response for response in responses if "rules" in response]
        self._position = -1
        self._current: PageAnalysisRequest | None = None

    def answer(self, request: PageAnalysisRequest) -> dict[str, Any]:
        if request is not self._current:
            self._position += 1
            self._current = request
        answer = self.analyses[self._position]
        assert answer["page_index"] == request.page_index
        return copy.deepcopy(answer)


class _Main(AnalysisProvider):
    """Ana model: kayıtlı yanıtı olduğu gibi verir; `cheap` verilirse ön eleme modeli odur."""

    name = "matris"

    def __init__(self, truth: _Truth, cheap: _Cheap | None = None) -> None:
        super().__init__(model=MAIN, prescreen_model=None if cheap is None else cheap.model)
        self.truth = truth
        self.cheap = cheap
        self.requests: list[PageAnalysisRequest] = []

    def _with_model(self, model: str) -> AnalysisProvider:
        assert self.cheap is not None and model == self.cheap.model
        return self.cheap

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        self.requests.append(request)
        return self.truth.answer(request)

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        return self.truth.checks.pop(0)


Reading = Callable[[dict[str, Any]], object]


class _Cheap(AnalysisProvider):
    """Ucuz model: kayıtlı yanıtı `reading` davranışından geçirerek verir."""

    name = "matris"

    def __init__(self, truth: _Truth, reading: Reading) -> None:
        super().__init__(model=CHEAP)
        self.truth = truth
        self.reading = reading
        self.requests: list[PageAnalysisRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        self.requests.append(request)
        return self.reading(self.truth.answer(request))


# --- ucuz modelin davranışları -------------------------------------------------------------------


def _same(answer: dict[str, Any]) -> object:
    return answer


def _misreads_numbers(answer: dict[str, Any]) -> object:
    # Görünen belge numarasının her hanesi yanlış; MRZ olduğu gibi.
    wrong = "987654321"
    if answer["person"]["document_number"] is not None:
        answer["person"]["document_number"] = wrong
    reading = answer["fields"].get("document_number")
    if reading is not None and reading["legible"]:
        reading["value"] = wrong
    return answer


def _misreads_mrz(answer: dict[str, Any]) -> object:
    # MRZ'nin belge numarasının ilk hanesi yanlış (kontrol hanesi tutmaz).
    lines = answer["person"]["mrz_lines"]
    if lines is not None:
        second = lines[1]
        lines[1] = ("7" if second[0] != "7" else "8") + second[1:]
    return answer


def _misreads_birth_dates(answer: dict[str, Any]) -> object:
    # Görünen doğum tarihi başka bir gün; MRZ olduğu gibi.
    wrong = "1970-06-15"
    if answer["person"]["date_of_birth"] is not None:
        answer["person"]["date_of_birth"] = wrong
    reading = answer["fields"].get("date_of_birth")
    if reading is not None and reading["legible"]:
        reading["value"] = wrong
    return answer


def _notes_everything(answer: dict[str, Any]) -> object:
    answer["notes"] = "Görüntü bulanık, alanlar tereddütlü."
    return answer


def _unreadable(answer: dict[str, Any]) -> object:
    answer["is_readable"] = False
    return answer


def _blank(answer: dict[str, Any]) -> object:
    answer["is_blank"] = True
    return answer


def _broken(answer: dict[str, Any]) -> object:
    return {"page_index": answer["page_index"], "bozuk": True}


READINGS: dict[str, Reading] = {
    "ayni": _same,
    "numara-yanlis": _misreads_numbers,
    "mrz-yanlis": _misreads_mrz,
    "dogum-yanlis": _misreads_birth_dates,
    "not": _notes_everything,
    "okunamaz": _unreadable,
    "bos": _blank,
    "bozuk": _broken,
}


def _stays_cheap(reading: str, answer: dict[str, Any], easy: bool) -> bool:
    """Ucuz modelin bu sayfada kalması beklenir mi: ana modelle aynı okuyan için kolay sayfa;
    yanlış okuduğu değer sayfada varsa hiçbiri; not, okunamaz, boş, bozuk için hiçbiri."""
    if reading == "ayni":
        return easy
    if reading == "numara-yanlis":
        return easy and answer["person"]["document_number"] is None
    if reading == "mrz-yanlis":
        return easy and answer["person"]["mrz_lines"] is None
    if reading == "dogum-yanlis":
        return easy and answer["person"]["date_of_birth"] is None
    return False


# --- matris: partiler ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Batch:
    """Bir kabul senaryosunun partisi: dosyalar (ad, sayfalar, biçim), kayıtlı çalışanlar ve
    ana modelle aynı okuyan ucuz modelde kalması beklenen sayfalar (analiz sırasıyla)."""

    files: tuple[tuple[str, tuple[SyntheticPage, ...], str], ...]
    registered: tuple[tuple[SyntheticPerson, tuple[tuple[str, str], ...]], ...]
    easy: tuple[bool, ...]


def _passport(person: SyntheticPerson = PERSON_ORNEKOVA, **overrides: Any) -> SyntheticPage:
    return passport_page(
        person, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1), **overrides
    )


def _license() -> tuple[SyntheticPage, SyntheticPage]:
    return driving_license_pages(
        PERSON_SIDOROV, document_number=LICENSE_NUMBER, expiry_date=date(2031, 6, 30)
    )


def _residence() -> tuple[SyntheticPage, SyntheticPage]:
    return residence_card_pages(
        PERSON_SIDOROV, document_number=RESIDENCE_NUMBER, expiry_date=date(2029, 12, 31)
    )


def _permit() -> SyntheticPage:
    return work_permit_page(
        PERSON_SIDOROV, document_number=PERMIT_NUMBER, expiry_date=date(2027, 3, 31)
    )


ORNEKOVA = (PERSON_ORNEKOVA, (("russian_passport", PASSPORT_NUMBER),))
SIDOROV = (
    PERSON_SIDOROV,
    (
        ("serbian_driving_license", LICENSE_NUMBER),
        ("serbian_residence_card", RESIDENCE_NUMBER),
        ("work_permit", PERMIT_NUMBER),
    ),
)


def _batches() -> dict[str, Batch]:
    license_front, license_back = _license()
    residence_front, residence_back = _residence()
    photo = profile_picture_page()
    return {
        "s1-pasaport": Batch(
            files=(("pasaport.pdf", (_passport(),), "pdf"),),
            registered=(ORNEKOVA,),
            easy=(True,),
        ),
        "s3-araya-giren": Batch(
            files=(
                (
                    "belgeler.pdf",
                    (
                        license_front,
                        photo,
                        _permit(),
                        residence_front,
                        residence_back,
                        license_back,
                    ),
                    "pdf",
                ),
            ),
            registered=(SIDOROV,),
            easy=(False, True, False, False, False, False),
        ),
        "s4-art-arda": Batch(
            files=(
                (
                    "belgeler.pdf",
                    (license_front, license_back, photo, residence_front, residence_back),
                    "pdf",
                ),
            ),
            registered=(SIDOROV,),
            easy=(False, False, True, False, False),
        ),
        "s5-on-arka-goruntu": Batch(
            files=(("on.jpg", (license_front,), "jpeg"), ("arka.jpg", (license_back,), "jpeg")),
            registered=(SIDOROV,),
            easy=(False, False),
        ),
        "yeni-calisan-ve-foto": Batch(
            files=(
                ("pasaport.pdf", (_passport(PERSON_TESTOVA_SHCHELKINA),), "pdf"),
                ("foto.jpg", (photo,), "jpeg"),
            ),
            registered=(),
            easy=(True, True),
        ),
        "katalog-disi-ve-bulanik": Batch(
            files=(
                (
                    "karisik.pdf",
                    (
                        unknown_document_page(
                            PERSON_PRUEBA, candidate_type_name="Peruvian Diploma", title="DIPLOMA"
                        ),
                        _passport(blurred=("expiry_date",)),
                    ),
                    "pdf",
                ),
            ),
            registered=(ORNEKOVA,),
            easy=(False, False),
        ),
        # S19: numarasız belge, ad + doğum tarihi → yeni çalışan (satır 6b). MRZ yok, doğum tarihi
        # zorunlu: sayfa kolay değildir (`unverified_date_of_birth`).
        "s19-ad-dogum-tarihi": Batch(
            files=(("sozlesme.pdf", (employment_contract_page(PERSON_PRUEBA),), "pdf"),),
            registered=(),
            easy=(False,),
        ),
    }


BATCHES = _batches()


# --- koşu ve karşılaştırma ----------------------------------------------------------------------


@contextmanager
def _world(root: Path) -> Iterator[tuple[Session, DataLayout]]:
    """Ayrı veritabanı ve veri dizini; tohum katalog yüklü."""
    root.mkdir(parents=True)
    engine = create_db_engine(f"sqlite:///{(root / 'matris.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        with create_session_factory(engine)() as session:
            import_catalog(session, CATALOG)
            session.commit()
            yield session, prepare_data_dir(root / "data")
    finally:
        engine.dispose()


def _received(session: Session, layout: DataLayout, batch: Batch) -> Upload:
    for person, numbers in batch.registered:
        _register_employee(session, layout, person, list(numbers))
    upload = Upload(id=UPLOAD_ID, channel="web")
    session.add(upload)
    session.flush()
    for name, pages, kind in batch.files:
        content = (
            make_document_pdf_bytes(pages) if kind == "pdf" else make_page_image_bytes(pages[0])
        )
        stored = write_to_inbox(layout, UPLOAD_ID, name, content)
        session.add(
            UploadFile(
                upload=upload,
                original_name=name,
                stored_path=layout.relative(stored.path),
                sha256=stored.sha256,
                mime="application/octet-stream",
            )
        )
        session.flush()
    session.commit()
    return upload


def _responses(batch: Batch) -> list[dict[str, Any]]:
    return batch_responses(*(pages for _, pages, _ in batch.files))


def _snapshot(session: Session, layout: DataLayout, upload: Upload) -> dict[str, Any]:
    """Partinin karşılaştırılan sonucu: analizler, plan, çıktılar (bayt özetiyle), kuyruk,
    çalışanlar ve belge numaraları."""
    plan = current_plan(session, upload)
    assert plan is not None
    pages = session.scalars(
        select(Page).join(UploadFile).where(UploadFile.upload_id == upload.id).order_by(Page.id)
    )
    return {
        "status": upload.status,
        "analyses": [(page.file_id, page.index, page.analysis_json) for page in pages],
        "plan": [item.model_dump(mode="json") for item in read_plan(plan).items],
        "outputs": [
            (
                row.path,
                row.type_slug,
                row.employee_id,
                row.status,
                hashlib.sha256(layout.resolve(row.path).read_bytes()).hexdigest(),
            )
            for row in session.scalars(select(Document).order_by(Document.id))
        ],
        "queue": [
            (row.kind, row.plan_item_id, row.reason)
            for row in session.scalars(select(QueueItem).order_by(QueueItem.id))
        ],
        "employees": [
            (row.id, row.folder_name, row.status, row.surname, row.given_names, row.date_of_birth)
            for row in session.scalars(select(Employee).order_by(Employee.id))
        ],
        "identifiers": sorted(
            (row.employee_id, row.kind, row.value)
            for row in session.scalars(select(EmployeeIdentifier))
        ),
    }


def _analyzed_by(session: Session) -> list[str]:
    query = select(Event).where(Event.type == EventType.PAGE_ANALYZED).order_by(Event.id)
    return [row.data_json["model"] for row in session.scalars(query)]


def _run(root: Path, batch: Batch, reading: Reading | None) -> tuple[dict[str, Any], list[str]]:
    truth = _Truth(_responses(batch))
    cheap = None if reading is None else _Cheap(truth, reading)
    provider = _Main(truth, cheap)
    with _world(root) as (session, layout):
        upload = _received(session, layout, batch)
        result = process_upload(session, layout, upload, settings=SETTINGS, provider=provider)
        assert result.status is not UploadStatus.FAILED
        return _snapshot(session, layout, upload), _analyzed_by(session)


@pytest.mark.parametrize("name", list(BATCHES))
def test_prescreened_batches_end_exactly_as_the_main_model_alone_would_end_them(
    name: str, tmp_path: Path
) -> None:
    batch = BATCHES[name]
    truths = _Truth(_responses(batch)).analyses
    assert len(batch.easy) == len(truths)
    baseline, models = _run(tmp_path / "ana", batch, None)
    assert models == [MAIN] * len(truths)

    for label, reading in READINGS.items():
        snapshot, models = _run(tmp_path / label, batch, reading)

        assert snapshot == baseline, label
        expected = [
            CHEAP if _stays_cheap(label, answer, easy) else MAIN
            for answer, easy in zip(truths, batch.easy, strict=True)
        ]
        assert models == expected, label


def test_matrix_routes_easy_pages_to_the_cheap_model() -> None:
    # Ana modelle aynı okuyan ucuz model matrisin her partisinde en az bir sayfada kalır ve her
    # partide bir sayfa da ana modele gider — iki yol da sınanıyor.
    easy = [flag for batch in BATCHES.values() for flag in batch.easy]
    assert any(easy) and not all(easy)


def test_reanalysis_skips_the_prescreen_and_asks_the_main_model(tmp_path: Path) -> None:
    batch = BATCHES["s1-pasaport"]
    with _world(tmp_path / "yeniden") as (session, layout):
        upload = _received(session, layout, batch)
        truth = _Truth(_responses(batch))
        cheap = _Cheap(truth, _same)
        first = _Main(truth, cheap)
        process_upload(session, layout, upload, settings=SETTINGS, provider=first)
        assert (len(cheap.requests), len(first.requests)) == (1, 0)

        again = _Main(_Truth(_responses(batch)), cheap)
        reanalysis = reanalyze_upload(
            session,
            layout,
            upload,
            provider=again,
            catalog=export_catalog(session),
            executor=plan_executor(SETTINGS),
        )

        assert len(cheap.requests) == 1 and len(again.requests) == 1
        assert reanalysis.plan.model == MAIN
        query = select(Event).where(Event.type == EventType.PAGE_ANALYZED).order_by(Event.id)
        first_event, second_event = session.scalars(query)
        assert first_event.data_json[PRESCREEN_DATA_KEY] == {"model": CHEAP, "accepted": True}
        assert second_event.data_json["model"] == MAIN
        assert PRESCREEN_DATA_KEY not in second_event.data_json
