"""11.5.5 — aday tür incelemesi (`app.catalog.propose`; PLAN.md §C85 "İnceleme"): görülmelerin
bütün sayfaları (arka yüzler dahil), gözlenen kanıtın taslağı ezmesi, kişisel değer sızıntı
denetimi, adayda saklama ve olay.

Sayfalar ve kuyruk öğeleri sentetik satırlardır; analiz görüntüleri Pillow ile üretilir, kişiler
`tests.fixtures.gen`'in sentetik kişileridir (CONVENTIONS §6). Yapay zekâ canlı çağrılmaz: yanıt
kayıtlı taslaktır (`tests/fixtures/ai/type_proposals/`), değiştirilmiş hâli geçici dizine yazılır.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.recording_provider import RecordingProvider
from app.ai.schemas import Side
from app.ai.type_proposal import TypeProposal, TypeProposalError
from app.catalog import import_catalog, load_seed_catalog
from app.catalog.describe import MAX_DESCRIPTION_PAGES
from app.catalog.propose import (
    LEAK_REASON,
    NO_SAMPLES_REASON,
    Evidence,
    ImageLabel,
    PersonalValues,
    SuggestedType,
    apply_evidence,
    build_proposal_prompt,
    examine,
    leaks_personal_value,
    load_proposal,
    personal_values,
    proposal_texts,
    read_examination,
    store_examination,
)
from app.catalog.schema import FileType, FrontBackLayout, PageRange, Sides
from app.db.models import (
    CandidateDocumentType,
    CandidateProposalStatus,
    Event,
    Page,
    QueueItem,
    Upload,
    UploadFile,
    record_candidate_type_sighting,
    utcnow,
)
from app.events import EventType
from app.storage import DataLayout, prepare_data_dir
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    SyntheticPerson,
    document_page,
    make_half_filled_image_bytes,
    make_pdf_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / "tests" / "fixtures" / "ai" / "type_proposals" / "residence_permit" / "0.json"
NAME = "Montenegrin Residence Permit"
UPLOAD = "u_20260926_0001"
OTHER_UPLOAD = "u_20260926_0002"
NUMBER = "ME 0000123"
JPEG = make_half_filled_image_bytes("JPEG")
PNG = make_half_filled_image_bytes("PNG")


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _proposal(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    for key, value in overrides.items():
        if key.startswith("appearance__"):
            data["appearance"][key.removeprefix("appearance__")] = value
        else:
            data[key] = value
    return data


def _provider(tmp_path: Path, *responses: dict[str, Any]) -> RecordingProvider:
    directory = tmp_path / "kayit"
    directory.mkdir(exist_ok=True)
    paths = []
    for number, response in enumerate(responses or (_proposal(),)):
        path = directory / f"{number}.json"
        path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
        paths.append(path)
    return RecordingProvider(paths, model="kayitli-model")


def _analysis(
    side: str,
    *,
    person: SyntheticPerson = PERSON_ORNEKOVA,
    document_number: str | None = NUMBER,
    index: int = 0,
) -> dict[str, Any]:
    shows = ["surname", "given_names", "date_of_birth"]
    if document_number is not None:
        shows.append("document_number")
    page = document_page(
        None,
        title="DOZVOLA ZA BORAVAK",
        person=person,
        document_number=document_number,
        shows=shows,
        side=side,
        language="sr",
        script="latin",
        candidate_type_name=NAME,
    )
    return page.analysis(index, continues_previous_page=index > 0)


@dataclass
class Batch:
    """Sentetik parti kurucusu: dosya yazar, sayfa satırı ve analiz görüntüsü açar."""

    session: Session
    layout: DataLayout

    def file(self, upload_id: str, name: str, content: bytes) -> UploadFile:
        if self.session.get(Upload, upload_id) is None:
            self.session.add(Upload(id=upload_id, channel="web"))
        stored = f"Inbox/{upload_id}/{name}"
        path = self.layout.resolve(stored)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        upload_file = UploadFile(
            upload_id=upload_id,
            original_name=name,
            stored_path=stored,
            sha256="0" * 64,
            # İstemcinin bildirdiği tür bilerek yanlış: dosya türü içerikten okunur (01.2.1).
            mime="application/octet-stream",
        )
        self.session.add(upload_file)
        self.session.flush()
        return upload_file

    def page(
        self,
        upload_file: UploadFile,
        index: int,
        side: str,
        *,
        image: bytes | None = JPEG,
        analysis: dict[str, Any] | None = None,
    ) -> Page:
        image_path = None
        if image is not None:
            path = self.layout.page_image_path(upload_file.id, index)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image)
            image_path = path.relative_to(self.layout.root).as_posix()
        page = Page(
            file=upload_file,
            index=index,
            image_path=image_path,
            analysis_json=analysis if analysis is not None else _analysis(side, index=index),
            analysis_status="done",
        )
        self.session.add(page)
        self.session.flush()
        return page

    def unknown(
        self, upload_id: str, sources: Sequence[tuple[int, Sequence[int]]], **fields: Any
    ) -> QueueItem:
        item = QueueItem(
            upload_id=upload_id,
            plan_item_id=f"i{len(sources)}",
            kind="unknown",
            reason="katalog dışı, aday tür adı: " + NAME,
            payload_json={
                "document_type_slug": None,
                "sources": [
                    {"file_id": file_id, "pages": list(pages)} for file_id, pages in sources
                ],
            },
            **fields,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def see(self, page: Page, upload_id: str = UPLOAD) -> CandidateDocumentType:
        sighting = record_candidate_type_sighting(
            self.session, proposed_name=NAME, upload_id=upload_id, page_id=page.id
        )
        return sighting.candidate_type


@pytest.fixture
def batch(session: Session, layout: DataLayout) -> Batch:
    return Batch(session, layout)


def _card_seen_twice(batch: Batch) -> CandidateDocumentType:
    """İki görülme: ön ve arka yüz ayrı JPEG/PNG dosyalarında (dosyalar arası öğe) ve iki sayfalık
    PDF'te (ön, arka)."""
    front = batch.file(UPLOAD, "on-yuz.jpg", JPEG)
    back = batch.file(UPLOAD, "arka-yuz.png", PNG)
    front_page = batch.page(front, 0, "front")
    batch.page(back, 0, "back", image=PNG)
    batch.unknown(UPLOAD, [(front.id, [0]), (back.id, [0])])
    pdf = batch.file(OTHER_UPLOAD, "kart.pdf", make_pdf_bytes(2))
    pdf_first = batch.page(pdf, 0, "front")
    batch.page(pdf, 1, "back", analysis=_analysis("back", index=1))
    batch.unknown(OTHER_UPLOAD, [(pdf.id, [0, 1])])
    candidate = batch.see(front_page)
    batch.see(pdf_first, OTHER_UPLOAD)
    return candidate


# --- girdi: görülmelerin bütün sayfaları --------------------------------------------------------


def test_back_sides_come_from_the_unknown_item_range_not_only_the_sample_pages(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    candidate = _card_seen_twice(batch)
    assert len(candidate.sample_page_ids) == 2  # yalnız ilk sayfalar

    source = read_examination(session, candidate)
    provider = _provider(tmp_path)
    examination = examine(source, layout, provider)

    assert [len(sighting) for sighting in source.sightings] == [2, 2]
    (request,) = provider.proposal_requests
    assert len(request.images) == 4
    assert [image.media_type for image in request.images] == [
        "image/jpeg",
        "image/png",
        "image/jpeg",
        "image/jpeg",
    ]
    assert examination.status is CandidateProposalStatus.READY
    assert examination.pages == 4
    assert examination.evidence == Evidence(
        file_types=(FileType.PDF, FileType.JPEG, FileType.PNG),
        sides=(Side.FRONT, Side.BACK),
        pages_per_sighting=(2, 2),
    )


def test_the_prompt_carries_name_evidence_catalog_and_image_order_without_personal_values(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    import_catalog(session, load_seed_catalog())
    session.flush()
    candidate = _card_seen_twice(batch)
    provider = _provider(tmp_path)

    examine(read_examination(session, candidate), layout, provider)

    (request,) = provider.proposal_requests
    prompt = request.prompt
    assert prompt.startswith(f"Geçici ad: {NAME}\n")
    assert "- Örnek dosya türleri: pdf, jpeg, png" in prompt
    assert "- Sayfa yüzleri (sayfa analizinden): front, back" in prompt
    assert "- Görülme sayısı: 2" in prompt
    assert "- Görülme başına sayfa sayısı: 2, 2" in prompt
    assert "- Serbian Passport (`serbian_passport`)" in prompt
    assert prompt.endswith(
        "Görüntüler (4, gönderildiği sırayla):\n"
        "1. görülme 1, sayfa 1\n"
        "2. görülme 1, sayfa 2\n"
        "3. görülme 2, sayfa 1\n"
        "4. görülme 2, sayfa 2"
    )
    assert "Hazır önerilen tür kaydı" not in prompt
    for private in ("ORNEKOVA", "Орнекова", "0000123", "1990", "on-yuz", "kart.pdf"):
        assert private not in prompt
    assert request.instructions.startswith("# Tür taslağı talimatı")


def test_a_suggested_type_record_enters_the_prompt() -> None:
    evidence = Evidence((FileType.JPEG,), (), (1,))
    prompt = build_proposal_prompt(
        NAME,
        evidence,
        [],
        [ImageLabel(1, 1)],
        suggested=SuggestedType("Montenegrin Residence Permit", "Residence Permit", "ME"),
    )

    assert "- Sayfa yüzleri (sayfa analizinden): belirlenemedi" in prompt
    assert "Katalogdaki türler:\n- yok" in prompt
    assert (
        "Hazır önerilen tür kaydı:\n- Ad: Montenegrin Residence Permit\n"
        "- Etiket: Residence Permit\n- Ülke: ME"
    ) in prompt


def test_a_sighting_without_an_unknown_item_is_its_first_page_only(
    batch: Batch, session: Session
) -> None:
    pdf = batch.file(UPLOAD, "belge.pdf", make_pdf_bytes(2))
    first = batch.page(pdf, 0, "front")
    batch.page(pdf, 1, "back")
    candidate = batch.see(first)

    source = read_examination(session, candidate)

    assert [[(page.file_id, page.index) for page in sighting] for sighting in source.sightings] == [
        [(pdf.id, 0)]
    ]


def test_the_newest_unknown_item_of_a_first_page_wins_and_a_whole_file_source_takes_all_pages(
    batch: Batch, session: Session
) -> None:
    pdf = batch.file(UPLOAD, "belge.pdf", make_pdf_bytes(3))
    pages = [batch.page(pdf, index, "single") for index in range(3)]
    batch.unknown(UPLOAD, [(pdf.id, [0])])  # plan v1
    batch.unknown(UPLOAD, [(pdf.id, [0, 1, 2])])  # plan v2 (K18): en yeni öğe
    candidate = batch.see(pages[0])

    source = read_examination(session, candidate)
    assert [page.index for page in source.sightings[0]] == [0, 1, 2]

    # Boş sayfa listesi dosyanın bütünüdür (K15).
    batch.unknown(UPLOAD, [(pdf.id, [])])
    batch.unknown(UPLOAD, [(pdf.id, [0]), (pdf.id, "bozuk")])  # type: ignore[list-item]
    assert [page.index for page in read_examination(session, candidate).sightings[0]] == [0, 1, 2]


def test_sightings_of_a_dismissed_upload_are_still_samples(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # §D55: yoksayılan partinin (10.3.4) görülmeleri sayılır ve örnek olarak kullanılabilir.
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(2))
    first = batch.page(pdf, 0, "front")
    batch.page(pdf, 1, "back")
    batch.unknown(
        UPLOAD,
        [(pdf.id, [0, 1])],
        resolved_at=utcnow(),
        resolved_by="ik",
        resolution="dismissed",
    )
    upload = session.get_one(Upload, UPLOAD)
    upload.dismissed_at, upload.dismissed_by = utcnow(), "ik"
    candidate = batch.see(first)

    examination = examine(read_examination(session, candidate), layout, _provider(tmp_path))

    assert examination.status is CandidateProposalStatus.READY
    assert examination.pages == 2


def test_pages_without_an_image_are_skipped_and_at_most_the_limit_is_sent(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    pdf = batch.file(UPLOAD, "uzun.pdf", make_pdf_bytes(MAX_DESCRIPTION_PAGES + 4))
    pages = [
        batch.page(pdf, index, "single", image=None if index == 1 else JPEG)
        for index in range(MAX_DESCRIPTION_PAGES + 4)
    ]
    # Önbellekten silinmiş görüntü (dosya yok) ve JPEG/PNG olmayan içerik de atlanır.
    layout.resolve(pages[2].image_path or "").unlink()
    layout.resolve(pages[3].image_path or "").write_bytes(b"bozuk")
    batch.unknown(UPLOAD, [(pdf.id, list(range(MAX_DESCRIPTION_PAGES + 4)))])
    candidate = batch.see(pages[0])
    provider = _provider(tmp_path)

    examination = examine(read_examination(session, candidate), layout, provider)

    (request,) = provider.proposal_requests
    assert len(request.images) == examination.pages == MAX_DESCRIPTION_PAGES
    assert "2. görülme 1, sayfa 5" in request.prompt  # sayfa 2, 3, 4 atlandı
    assert examination.evidence.pages_per_sighting == (MAX_DESCRIPTION_PAGES + 4,)


def test_a_page_shared_by_two_sightings_is_sent_once(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Yeniden gruplanan parti (K18): ikinci görülmenin ilk sayfası birinci öğenin arka yüzü.
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(2))
    first = batch.page(pdf, 0, "front")
    second = batch.page(pdf, 1, "back")
    batch.unknown(UPLOAD, [(pdf.id, [0, 1])])
    candidate = batch.see(first)
    batch.see(second)
    provider = _provider(tmp_path)

    examination = examine(read_examination(session, candidate), layout, provider)

    (request,) = provider.proposal_requests
    assert len(request.images) == examination.pages == 2
    assert request.prompt.endswith("1. görülme 1, sayfa 1\n2. görülme 1, sayfa 2")
    assert examination.evidence.pages_per_sighting == (2, 1)


def test_no_remaining_image_means_no_samples_without_a_provider_call(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(2))
    first = batch.page(pdf, 0, "front", image=None)
    second = batch.page(pdf, 1, "back")
    layout.resolve(second.image_path or "").unlink()
    batch.unknown(UPLOAD, [(pdf.id, [0, 1])])
    candidate = batch.see(first)
    provider = _provider(tmp_path)

    examination = examine(read_examination(session, candidate), layout, provider)

    assert provider.proposal_requests == []
    assert examination.status is CandidateProposalStatus.NO_SAMPLES
    assert (examination.pages, examination.proposal) == (0, None)
    assert examination.reason == NO_SAMPLES_REASON


def test_a_candidate_without_sample_pages_has_no_samples(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(1))
    candidate = batch.see(batch.page(pdf, 0, "single"))
    candidate.sample_page_ids = []

    examination = examine(read_examination(session, candidate), layout, _provider(tmp_path))

    assert examination.status is CandidateProposalStatus.NO_SAMPLES
    assert examination.evidence == Evidence((), (), ())


def test_a_missing_or_unrecognised_source_file_gives_no_file_type_evidence(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    gone = batch.file(UPLOAD, "silinmis.pdf", make_pdf_bytes(1))
    odd = batch.file(OTHER_UPLOAD, "tuhaf.bin", b"tanimsiz icerik")
    layout.resolve(gone.stored_path).unlink()
    candidate = batch.see(batch.page(gone, 0, "single"))
    batch.see(batch.page(odd, 0, "single"), OTHER_UPLOAD)
    response = _proposal(expected_file_types=["pdf", "png"])

    examination = examine(
        read_examination(session, candidate), layout, _provider(tmp_path, response)
    )

    assert examination.evidence.file_types == ()
    assert examination.proposal is not None
    assert examination.proposal.expected_file_types == (FileType.PDF, FileType.PNG)


# --- kanıt taslağı ezer ------------------------------------------------------------------------


def test_observed_evidence_overrides_the_model_file_types_and_side_structure(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    front = batch.file(UPLOAD, "on.jpg", JPEG)
    back = batch.file(UPLOAD, "arka.jpg", JPEG)
    first = batch.page(front, 0, "front")
    batch.page(back, 0, "back")
    batch.unknown(UPLOAD, [(front.id, [0]), (back.id, [0])])
    candidate = batch.see(first)
    response = _proposal(
        expected_file_types=["pdf"],
        expected_pages={"min": 1, "max": 1},
        sides="single",
        front_back_layouts=[],
    )

    examination = examine(
        read_examination(session, candidate), layout, _provider(tmp_path, response)
    )

    proposal = examination.proposal
    assert proposal is not None
    assert proposal.expected_file_types == (FileType.JPEG,)
    assert proposal.sides is Sides.FRONT_BACK
    assert proposal.front_back_layouts == (FrontBackLayout.SEPARATE,)
    assert proposal.expected_pages == PageRange(min=2, max=2)


BASE = TypeProposal.model_validate(_proposal())


@pytest.mark.parametrize(
    ("sides", "expected"),
    [
        ((Side.FRONT,), (Sides.FRONT_BACK, (FrontBackLayout.SEPARATE,), PageRange(min=2, max=2))),
        (
            (Side.FRONT_AND_BACK,),
            (Sides.FRONT_BACK, (FrontBackLayout.COMBINED,), PageRange(min=1, max=1)),
        ),
        (
            (Side.BACK, Side.FRONT_AND_BACK, Side.SINGLE),
            (
                Sides.FRONT_BACK,
                (FrontBackLayout.SEPARATE, FrontBackLayout.COMBINED),
                PageRange(min=1, max=2),
            ),
        ),
        ((Side.SINGLE, Side.UNKNOWN), (Sides.SINGLE, (), PageRange(min=1, max=2))),
        ((Side.UNKNOWN,), (Sides.FRONT_BACK, BASE.front_back_layouts, BASE.expected_pages)),
        ((), (Sides.FRONT_BACK, BASE.front_back_layouts, BASE.expected_pages)),
    ],
)
def test_apply_evidence_derives_the_side_structure_from_the_observed_sides(
    sides: tuple[Side, ...], expected: tuple[Sides, tuple[FrontBackLayout, ...], PageRange]
) -> None:
    proposal = apply_evidence(BASE, Evidence((), sides, (1,)))

    assert (proposal.sides, proposal.front_back_layouts, proposal.expected_pages) == expected
    assert proposal.expected_file_types == BASE.expected_file_types


def test_apply_evidence_without_evidence_keeps_the_proposal() -> None:
    assert apply_evidence(BASE, Evidence((), (), ())) is BASE


# --- sızıntı denetimi --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        # Soyad aksanlı ve farklı büyüklükte (§20.2.1 normalizasyonu).
        {"description": "Örnekova için verilmiş oturma izni kartı."},
        # Orijinal yazım (Kiril) başlıkta.
        {"appearance__headings": ["DOZVOLA ZA BORAVAK", "ОРНЕКОВА"]},
        # Ad kabul kriterinde.
        {"acceptance_criteria": ["Kartta TEST adı görünür olmalı"]},
        # Belge numarası boşluksuz, konum metninde.
        {
            "appearance__field_locations": [
                {"field": "surname", "location": "ME0000123 numarasının altında"}
            ]
        },
        # Doğum tarihi belgedeki yazımıyla (tek haneli ay).
        {"appearance__side_differences": "Ön yüzde 01.1.1990 tarihi, arka yüzde MRZ"},
        # Doğum tarihi MRZ yazımıyla (YYAAGG).
        {"appearance__mrz": {"line_count": 3, "location": "altta; 900101 ile başlayan satır"}},
        # Ad dosya etiketinde.
        {"file_label": "Ornekova Permit"},
    ],
)
def test_a_proposal_carrying_a_personal_value_is_not_stored(
    overrides: dict[str, Any],
    batch: Batch,
    session: Session,
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(1))
    candidate = batch.see(batch.page(pdf, 0, "front"))
    provider = _provider(tmp_path, _proposal(**overrides))

    examination = examine(read_examination(session, candidate), layout, provider)
    store_examination(session, candidate, examination, provider=provider)
    session.flush()

    assert examination.status is CandidateProposalStatus.FAILED
    assert examination.proposal is None
    assert examination.reason == LEAK_REASON
    assert candidate.proposal_status == "failed"
    assert candidate.description is None
    assert load_proposal(candidate) is None
    (event,) = session.scalars(select(Event).where(Event.type == "CANDIDATE_TYPE_EXAMINED"))
    stored = json.dumps([candidate.proposal_json, event.data_json, event.message], default=str)
    for private in ("ornekova", "орнекова", "0000123", "1990", "900101", "01.1."):
        assert private not in stored.casefold()
    assert candidate.proposal_json is not None
    assert candidate.proposal_json["reason"] == LEAK_REASON
    assert event.data_json is not None and event.data_json["result"] == "failed"


def test_the_leak_check_ignores_short_name_words_and_unrelated_numbers() -> None:
    person = SyntheticPerson("AY", "LI", date(1990, 4, 12))
    personal = personal_values([_analysis("single", person=person, document_number="12")])

    assert personal == PersonalValues(dates=frozenset({date(1990, 4, 12)}))
    texts = ["Ay yıldızlı başlık; LI harfleri", "Sayfa 12 satır", "1990 sonrası baskı"]
    assert not leaks_personal_value(texts, personal)
    assert leaks_personal_value(["Tarih: 12/04/1990"], personal)
    assert leaks_personal_value(["19900412"], personal)
    assert leaks_personal_value(["04-12-1990"], personal)


def test_personal_values_read_person_and_field_readings_even_from_a_broken_record() -> None:
    broken = {
        "person": {"surname": "Prueba", "document_number": "AB-12 34", "date_of_birth": "tarih"},
        "fields": {
            "given_names": {"value": "Ana María", "legible": True},
            "personal_number": {"value": "1234567890123", "legible": True},
            "date_of_birth": {"value": "15.03.1995", "legible": True},
            "surname": "bozuk",
        },
        "language": 7,
    }

    personal = personal_values([broken, {"person": "bozuk"}, {}])

    assert personal.name_words == {"prueba", "ana", "maria"}
    assert personal.numbers == {"ab1234", "1234567890123", "15031995", "tarih"}
    assert personal.dates == frozenset()
    assert leaks_personal_value(["no. AB 1234"], personal)
    assert leaks_personal_value(["15.03.1995"], personal)


def test_proposal_texts_cover_every_free_text() -> None:
    proposal = TypeProposal.model_validate(
        _proposal(appearance__accepted_photo="Beyaz fon", appearance__mrz=None)
    )

    texts = proposal_texts(proposal)

    assert texts == [
        proposal.name,
        proposal.file_label,
        proposal.description,
        *proposal.acceptance_criteria,
        proposal.appearance.layout,
        *proposal.appearance.headings,
        "ön yüzde fotoğrafın sağında, ilk satır",
        "ön yüzün sağ üst köşesi",
        "Ön yüzde fotoğraf ve kişisel alanlar; arka yüzde MRZ",
        "Beyaz fon",
    ]
    assert "arka yüzün altında" in proposal_texts(BASE)


# --- saklama -----------------------------------------------------------------------------------


def test_a_ready_examination_is_stored_with_evidence_model_and_page_count(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    candidate = _card_seen_twice(batch)
    provider = _provider(tmp_path)
    examination = examine(read_examination(session, candidate), layout, provider)

    store_examination(session, candidate, examination, provider=provider)
    session.commit()

    session.refresh(candidate)
    assert candidate.proposal_status == CandidateProposalStatus.READY.value
    assert candidate.proposal_generated_at is not None
    assert candidate.status == "pending"  # kendiliğinden onay yok (K16)
    stored = candidate.proposal_json
    assert stored is not None
    assert stored["model"] == "kayitli-model"
    assert stored["pages"] == 4
    assert stored["reason"] is None
    assert stored["evidence"] == {
        "file_types": ["pdf", "jpeg", "png"],
        "sides": ["front", "back"],
        "pages_per_sighting": [2, 2],
    }
    assert load_proposal(candidate) == examination.proposal
    assert candidate.description == examination.proposal.description  # type: ignore[union-attr]
    (event,) = session.scalars(select(Event).where(Event.type == "CANDIDATE_TYPE_EXAMINED"))
    assert event.actor == "system"
    assert event.upload_id is None
    assert event.data_json == {
        "candidate_type_id": candidate.id,
        "result": "ready",
        "pages": 4,
        "provider": "recording",
        "model": "kayitli-model",
    }


def test_the_description_is_written_only_when_empty(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(1))
    candidate = batch.see(batch.page(pdf, 0, "front"))
    candidate.description = "İK'nın notu"
    provider = _provider(tmp_path)
    examination = examine(read_examination(session, candidate), layout, provider)

    store_examination(session, candidate, examination, provider=provider)

    assert candidate.description == "İK'nın notu"
    assert candidate.proposal_status == "ready"


def test_no_samples_is_stored_without_a_proposal(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(1))
    candidate = batch.see(batch.page(pdf, 0, "front", image=None))
    provider = _provider(tmp_path)
    examination = examine(read_examination(session, candidate), layout, provider)

    store_examination(session, candidate, examination, provider=provider)
    session.flush()

    assert candidate.proposal_status == "no_samples"
    assert candidate.proposal_json is not None
    assert candidate.proposal_json["reason"] == NO_SAMPLES_REASON
    assert candidate.proposal_json["proposal"] is None
    (event,) = session.scalars(select(Event).where(Event.type == "CANDIDATE_TYPE_EXAMINED"))
    assert event.data_json is not None
    assert event.data_json["result"] == "no_samples"


def test_load_proposal_rejects_a_missing_or_broken_record(batch: Batch) -> None:
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(1))
    candidate = batch.see(batch.page(pdf, 0, "front"))

    assert load_proposal(candidate) is None
    candidate.proposal_status = "ready"
    candidate.proposal_json = {"proposal": {"name": "Eksik"}}
    assert load_proposal(candidate) is None
    candidate.proposal_json = {"proposal": _proposal()}
    assert load_proposal(candidate) == BASE


def test_a_schema_violating_response_raises_and_stores_nothing(
    batch: Batch, session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(1))
    candidate = batch.see(batch.page(pdf, 0, "front"))
    provider = _provider(tmp_path, {"name": "Eksik yanıt"})

    with pytest.raises(TypeProposalError):
        examine(read_examination(session, candidate), layout, provider)

    assert candidate.proposal_status is None


def test_the_proposal_status_is_a_closed_set(batch: Batch, session: Session) -> None:
    pdf = batch.file(UPLOAD, "kart.pdf", make_pdf_bytes(1))
    candidate = batch.see(batch.page(pdf, 0, "front"))
    session.commit()

    candidate.proposal_status = "approved"
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert session.get_one(CandidateDocumentType, candidate.id).proposal_status is None
    assert EventType.CANDIDATE_TYPE_EXAMINED.value == "CANDIDATE_TYPE_EXAMINED"
