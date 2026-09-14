"""04.1.1 — ardışık, aynı tür ve aynı kişiye ait sayfalar tek belge adayı olur; 04.1.2 —
`front_back` türlerde ön ve arka yüz sıralı biçimde eşleşir. Kabul senaryosu: S4.

Birim testleri `group_file_pages`'e sentetik analizler verir. Entegrasyon testleri sentetik
PDF/JPEG'i gerçek render adımlarından ve kayıtlı yanıt sağlayıcısıyla (03.6) analizden geçirip
`group_upload`'u veritabanı üzerinde koşar — gerçek kişi/belge yok, ağ çağrısı yok.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import PageAnalysis, Side, build_page_analysis_instructions
from app.ai.recording_provider import RecordingProvider
from app.catalog import load_seed_catalog, validate_catalog
from app.config import Settings
from app.db.models import Event, Upload, UploadFile, UploadStatus
from app.events import EventType
from app.pipeline.analyze import analyze_upload
from app.pipeline.group import (
    FileGrouping,
    GroupingPage,
    StoredAnalysisError,
    group_file_pages,
    group_upload,
)
from app.pipeline.render import (
    extract_upload_file_text,
    mark_upload_file_blank_pages,
    render_image_file,
    render_upload_file,
)
from app.storage import DataLayout, FileKind, detect_file_kind, write_to_inbox
from tests.ai.payloads import SYNTHETIC_DOCUMENT_NUMBER, SYNTHETIC_SURNAME, analysis_payload
from tests.fixtures.gen import make_half_filled_image_bytes, make_text_pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()
INSTRUCTIONS = build_page_analysis_instructions(CATALOG)
UPLOAD_ID = "u_20260914_0001"
FILE_ID = 7

LICENSE = "serbian_driving_license"  # front_back
RESIDENCE = "serbian_residence_card"  # front_back
PERMIT = "work_permit"  # single, 1–2 sayfa
PASSPORT = "russian_passport"  # single, 1 sayfa

NO_PERSON: dict[str, Any] = {
    "surname": None,
    "given_names": None,
    "other_names": None,
    "original_script_name": None,
    "date_of_birth": None,
    "nationality": None,
    "document_number": None,
    "mrz_lines": None,
}
BLANK_READING: dict[str, Any] = {
    "is_blank": True,
    "is_readable": False,
    "language": None,
    "script": None,
    "fields": {},
}


def _payload(
    index: int,
    slug: str | None = PERMIT,
    *,
    side: str = "single",
    continues: bool = False,
    person: dict[str, Any] | None = None,
    **top: Any,
) -> dict[str, Any]:
    """Sentetik §8.4 yanıtı; `person` varsayılan sentetik kişinin alanlarını değiştirir."""
    payload = analysis_payload(
        page_index=index,
        document_type_slug=slug,
        side=side,
        continues_previous_page=continues,
        **top,
    )
    payload["person"].update(person or {})
    return payload


def _page(index: int, slug: str | None = PERMIT, **kwargs: Any) -> GroupingPage:
    return GroupingPage(
        index, analysis=PageAnalysis.model_validate(_payload(index, slug, **kwargs))
    )


def _front(index: int, *, slug: str = LICENSE, continues: bool = False) -> GroupingPage:
    return _page(index, slug, side="front", continues=continues)


def _back(index: int, *, slug: str = LICENSE, continues: bool = True) -> GroupingPage:
    # Kartın arka yüzünde kişi değeri yazmaz.
    return _page(index, slug, side="back", continues=continues, person=NO_PERSON)


def _group(*pages: GroupingPage) -> FileGrouping:
    return group_file_pages(FILE_ID, pages, catalog=CATALOG)


def _layout(grouping: FileGrouping) -> list[tuple[int, ...]]:
    return [tuple(page.index for page in candidate.pages) for candidate in grouping.candidates]


# --- 04.1.1 dosya içi gruplama ----------------------------------------------------------------


def test_continuing_pages_of_same_type_and_person_form_one_candidate() -> None:
    grouping = _group(_page(0), _page(1, continues=True))

    assert _layout(grouping) == [(0, 1)]
    (candidate,) = grouping.candidates
    assert candidate.document_type_slug == PERMIT
    assert candidate.candidate_type_name is None
    assert candidate.sides == (Side.SINGLE, Side.SINGLE)
    assert [(page.file_id, page.analysis.page_index) for page in candidate.pages] == [
        (FILE_ID, 0),
        (FILE_ID, 1),
    ]
    assert grouping.file_id == FILE_ID
    assert grouping.blank_pages == ()
    assert grouping.unanalyzed_pages == ()


@pytest.mark.parametrize(
    "second",
    [
        pytest.param({}, id="ayni-degerler"),
        pytest.param(NO_PERSON, id="kisi-degeri-yok"),
        pytest.param({"surname": None, "document_number": None}, id="bazi-degerler-yok"),
    ],
)
def test_page_without_conflicting_person_values_joins(second: dict[str, Any]) -> None:
    grouping = _group(_page(0), _page(1, continues=True, person=second))

    assert _layout(grouping) == [(0, 1)]


def test_same_type_documents_without_continuation_stay_separate() -> None:
    # Aynı kişinin art arda taranmış iki pasaportu: ardışık, aynı tür, aynı kişi — ama iki belge.
    grouping = _group(_page(0, PASSPORT), _page(1, PASSPORT, continues=False))

    assert _layout(grouping) == [(0,), (1,)]


def test_pages_of_different_types_never_group() -> None:
    grouping = _group(_page(0, PERMIT), _page(1, PASSPORT, continues=True))

    assert _layout(grouping) == [(0,), (1,)]
    assert [candidate.document_type_slug for candidate in grouping.candidates] == [
        PERMIT,
        PASSPORT,
    ]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param({}, {"document_number": "00 0000002"}, id="belge-numarasi"),
        pytest.param({}, {"date_of_birth": "1991-01-01"}, id="dogum-tarihi"),
        pytest.param({}, {"surname": "DENEMEVA"}, id="soyad"),
        pytest.param({}, {"given_names": "ORNEK"}, id="ad"),
        pytest.param(
            {"given_names": "TEST ORNEK"}, {"given_names": "TEST DENEME"}, id="ad-kismen-ortak"
        ),
        pytest.param({}, {"original_script_name": "Денемева Тест"}, id="orijinal-yazim"),
    ],
)
def test_conflicting_person_values_split_pages(
    first: dict[str, Any], second: dict[str, Any]
) -> None:
    grouping = _group(_page(0, person=first), _page(1, continues=True, person=second))

    assert _layout(grouping) == [(0,), (1,)]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param(
            {"document_number": "71 1234567"}, {"document_number": "71-1234567"}, id="numara-bosluk"
        ),
        pytest.param(
            {"document_number": "ab.123/456"}, {"document_number": "AB 123456"}, id="numara-isaret"
        ),
        pytest.param({"surname": "Petrović"}, {"surname": "PETROVIC"}, id="aksan-harf-buyuklugu"),
        pytest.param({"surname": "IŞIK"}, {"surname": "Işık"}, id="noktasiz-i"),
        pytest.param({"surname": "ÇAKAR"}, {"surname": "cakar"}, id="turkce-harf"),
        pytest.param(
            {"given_names": "ANA MARIJA"}, {"given_names": "marija, ana"}, id="kelime-sirasi"
        ),
        pytest.param({"given_names": "ANA"}, {"given_names": "ANA MARIJA"}, id="ikinci-ad-eksik"),
        pytest.param(
            {"original_script_name": "Васильев Дмитрий"},
            {"original_script_name": "ДМИТРИЙ ВАСИЛЬЕВ"},
            id="kiril-yazim",
        ),
    ],
)
def test_person_values_are_compared_after_normalization(
    first: dict[str, Any], second: dict[str, Any]
) -> None:
    grouping = _group(_page(0, person=first), _page(1, continues=True, person=second))

    assert _layout(grouping) == [(0, 1)]


def test_joining_page_is_checked_against_every_page_of_the_candidate() -> None:
    # Değersiz orta sayfa kimseyle çelişmez; üçüncü sayfanın soyadı ilk sayfayla çelişir.
    grouping = _group(
        _page(0),
        _page(1, continues=True, person=NO_PERSON),
        _page(2, continues=True, person={**NO_PERSON, "surname": "DENEMEVA"}),
    )

    assert _layout(grouping) == [(0, 1), (2,)]


def test_pages_whose_type_is_undetermined_never_group() -> None:
    grouping = _group(_page(0, None), _page(1, None, continues=True))

    assert _layout(grouping) == [(0,), (1,)]
    assert all(
        candidate.document_type_slug is None and candidate.candidate_type_name is None
        for candidate in grouping.candidates
    )


@pytest.mark.parametrize(
    ("second_name", "expected"),
    [
        pytest.param("peruvian   DIPLOMA", [(0, 1)], id="ayni-aday-tur"),
        pytest.param("Peruvian Certificate", [(0,), (1,)], id="farkli-aday-tur"),
    ],
)
def test_catalog_less_pages_group_by_candidate_type_name(
    second_name: str, expected: list[tuple[int, ...]]
) -> None:
    grouping = _group(
        _page(0, None, candidate_type_name="Peruvian Diploma", fields={}),
        _page(1, None, continues=True, candidate_type_name=second_name, fields={}),
    )

    assert _layout(grouping) == expected
    assert grouping.candidates[0].candidate_type_name == "Peruvian Diploma"
    assert grouping.candidates[0].document_type_slug is None


@pytest.mark.parametrize(
    ("slug", "top"),
    [
        pytest.param(PERMIT, {}, id="tek-yuzlu-tur"),
        pytest.param(
            None, {"candidate_type_name": "Bosnian Identity Card", "fields": {}}, id="katalog-disi"
        ),
    ],
)
def test_faces_do_not_restrict_single_sided_or_catalog_less_types(
    slug: str | None, top: dict[str, Any]
) -> None:
    grouping = _group(
        _page(0, slug, side="back", **top),
        _page(1, slug, side="front", continues=True, **top),
        _page(2, slug, side="unknown", continues=True, **top),
    )

    assert _layout(grouping) == [(0, 1, 2)]


def test_candidate_is_not_cut_at_expected_page_count() -> None:
    # Sınırda bölmek geçerli görünen iki yanlış belge üretirdi; aralık dışı aday 04.5'in işi.
    entry = CATALOG.get(PERMIT)
    assert entry is not None and entry.expected_pages is not None
    assert entry.expected_pages.max == 2

    grouping = _group(_page(0), _page(1, continues=True), _page(2, continues=True))

    assert _layout(grouping) == [(0, 1, 2)]


def test_slug_missing_from_catalog_is_not_grouped() -> None:
    catalog = validate_catalog(
        [entry.model_dump(mode="json") for entry in CATALOG if entry.slug != PERMIT]
    )

    grouping = group_file_pages(FILE_ID, [_page(0), _page(1, continues=True)], catalog=catalog)

    assert _layout(grouping) == [(0,), (1,)]


def test_first_analyzed_page_claiming_continuation_starts_a_candidate() -> None:
    grouping = _group(
        GroupingPage(0, is_blank=True), _page(1, continues=True), _page(2, PASSPORT, continues=True)
    )

    assert _layout(grouping) == [(1,), (2,)]


def test_blank_page_does_not_break_candidate() -> None:
    # Dupleks tarama: kartın iki yüzü arasına boş sayfa girer; boş sayfa başka belge değildir (K5).
    grouping = _group(
        _front(0),
        GroupingPage(1, is_blank=True),
        GroupingPage(2, is_blank=True),
        _back(3),
        GroupingPage(4, is_blank=True),
    )

    assert _layout(grouping) == [(0, 3)]
    assert grouping.blank_pages == (1, 2, 4)
    assert grouping.unanalyzed_pages == ()


def test_page_without_analysis_breaks_candidate() -> None:
    # Analizi başarısız sayfanın içeriği bilinmez; araya başka belge girmiş olabilir (K5).
    grouping = _group(_front(0), GroupingPage(1), _back(2))

    assert _layout(grouping) == [(0,), (2,)]
    assert grouping.unanalyzed_pages == (1,)
    assert grouping.blank_pages == ()


def test_page_read_as_blank_is_skipped_but_breaks_chain() -> None:
    # Sonraki sayfanın devam işareti boş sayfaya göre verilmiştir; öndeki ön yüze bağlanmaz.
    blank_reading = _page(1, None, continues=True, person=NO_PERSON, **BLANK_READING)

    grouping = _group(_front(0), blank_reading, _back(2))

    assert _layout(grouping) == [(0,), (2,)]
    assert grouping.blank_pages == (1,)
    assert grouping.unanalyzed_pages == ()


@pytest.mark.parametrize(
    ("slug", "person", "top"),
    [
        pytest.param(PASSPORT, NO_PERSON, {}, id="tur-var"),
        pytest.param(None, NO_PERSON, {"candidate_type_name": "Peruvian Diploma"}, id="aday-tur"),
        pytest.param(None, {**NO_PERSON, "surname": SYNTHETIC_SURNAME}, {}, id="kisi-degeri"),
        pytest.param(
            None,
            {**NO_PERSON, "contact": {"phone": None, "email": None, "address": "Ornek Sokak 7"}},
            {},
            id="iletisim",
        ),
        pytest.param(
            None,
            NO_PERSON,
            {"fields": {"surname": {"value": SYNTHETIC_SURNAME, "legible": True}}},
            id="okunakli-alan",
        ),
    ],
)
def test_contradictory_blank_reading_stays_a_candidate(
    slug: str | None, person: dict[str, Any], top: dict[str, Any]
) -> None:
    grouping = _group(_page(0, slug, person=person, **{**BLANK_READING, **top}))

    assert _layout(grouping) == [(0,)]
    assert grouping.blank_pages == ()


def test_pages_are_grouped_in_index_order_whatever_the_input_order() -> None:
    pages = [_page(2, PASSPORT), _page(1, continues=True), GroupingPage(3), _page(0)]

    grouping = group_file_pages(FILE_ID, iter(pages), catalog=CATALOG)

    assert _layout(grouping) == [(0, 1), (2,)]
    assert grouping.unanalyzed_pages == (3,)


def test_repeated_page_index_is_rejected() -> None:
    with pytest.raises(ValueError, match="birden fazla"):
        _group(_page(0), _page(0, continues=True))


# --- 04.1.2 ön/arka yüz yapısı ----------------------------------------------------------------


@pytest.mark.parametrize("slug", [LICENSE, RESIDENCE])
def test_front_and_following_back_pair_into_one_candidate(slug: str) -> None:
    grouping = _group(_front(0, slug=slug), _back(1, slug=slug))

    assert _layout(grouping) == [(0, 1)]
    (candidate,) = grouping.candidates
    assert candidate.sides == (Side.FRONT, Side.BACK)
    assert candidate.document_type_slug == slug


def test_consecutive_cards_pair_in_order() -> None:
    # Yeni kartın ön yüzü devam dese de tamamlanmış çifte katılmaz.
    grouping = _group(_front(0), _back(1), _front(2, continues=True), _back(3))

    assert _layout(grouping) == [(0, 1), (2, 3)]
    assert [candidate.sides for candidate in grouping.candidates] == [(Side.FRONT, Side.BACK)] * 2


def test_back_before_front_is_not_paired() -> None:
    grouping = _group(_back(0, continues=False), _front(1, continues=True))

    assert _layout(grouping) == [(0,), (1,)]


def test_second_front_pairs_with_the_back_that_follows_it() -> None:
    grouping = _group(_front(0), _front(1, continues=True), _back(2))

    assert _layout(grouping) == [(0,), (1, 2)]


def test_extra_back_after_complete_pair_stays_separate() -> None:
    grouping = _group(_front(0), _back(1), _back(2))

    assert _layout(grouping) == [(0, 1), (2,)]


def test_back_without_continuation_is_not_paired() -> None:
    grouping = _group(_front(0), _back(1, continues=False))

    assert _layout(grouping) == [(0,), (1,)]


@pytest.mark.parametrize(
    ("first_side", "second_side"),
    [("single", "back"), ("unknown", "back"), ("front", "single"), ("front", "unknown")],
)
def test_front_back_type_pairs_only_explicit_faces(first_side: str, second_side: str) -> None:
    grouping = _group(
        _page(0, LICENSE, side=first_side),
        _page(1, LICENSE, side=second_side, continues=True, person=NO_PERSON),
    )

    assert _layout(grouping) == [(0,), (1,)]


def test_back_showing_another_persons_number_is_not_paired() -> None:
    other = {**NO_PERSON, "document_number": "00 0000009"}

    grouping = _group(_front(0), _page(1, LICENSE, side="back", continues=True, person=other))

    assert _layout(grouping) == [(0,), (1,)]


# --- entegrasyon: veritabanı, render, kayıtlı yanıt --------------------------------------------


def _settings() -> Settings:
    return Settings(_env_file=None, database_url="sqlite://")


def _upload(session: Session, layout: DataLayout, files: list[tuple[str, bytes]]) -> Upload:
    """Partiyi Inbox'a yazar ve her dosyanın sayfalarını gerçek render adımlarıyla üretir."""
    upload = Upload(id=UPLOAD_ID, channel="web", status=UploadStatus.ANALYZING.value)
    session.add(upload)
    for name, content in files:
        stored = write_to_inbox(layout, upload.id, name, content)
        kind = detect_file_kind(content)
        upload_file = UploadFile(
            upload=upload,
            original_name=name,
            stored_path=stored.path.relative_to(layout.root).as_posix(),
            sha256=stored.sha256,
            mime="application/pdf" if kind is FileKind.PDF else "image/jpeg",
        )
        session.add(upload_file)
        session.flush()
        if kind is FileKind.PDF:
            render_upload_file(session, layout, _settings(), upload_file)
            extract_upload_file_text(session, layout, upload_file)
            mark_upload_file_blank_pages(session, layout, upload_file)
        else:
            render_image_file(session, layout, _settings(), upload_file)
    session.flush()
    return upload


def _recordings(tmp_path: Path, responses: list[dict[str, Any]]) -> RecordingProvider:
    directory = tmp_path / "recordings"
    directory.mkdir()
    for number, response in enumerate(responses):
        text = json.dumps(response, ensure_ascii=False)
        (directory / f"{number}.json").write_text(text, encoding="utf-8")
    return RecordingProvider.from_directory(directory)


def _events(session: Session, event_type: EventType) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.type == event_type).order_by(Event.id)))


def test_s4_sequential_pdf_yields_three_independent_candidates(
    session: Session, layout: DataLayout
) -> None:
    # S4: 5 sayfalık sıralı PDF — ehliyet ön, ehliyet arka, foto, oturum ön, oturum arka.
    pdf = make_text_pdf_bytes(
        ["EHLIYET ON YUZ", "EHLIYET ARKA YUZ", "FOTOGRAF", "OTURUM IZNI ON", "OTURUM IZNI ARKA"]
    )
    upload = _upload(session, layout, [("belgeler.pdf", pdf)])
    provider = RecordingProvider.from_directory(RECORDINGS / "s4_sequential_pdf")
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    grouping = group_upload(session, upload, catalog=CATALOG)

    file_id = upload.files[0].id
    (file_grouping,) = grouping.files
    assert file_grouping.file_id == file_id
    assert _layout(file_grouping) == [(0, 1), (2,), (3, 4)]
    assert grouping.candidates == file_grouping.candidates
    assert [candidate.document_type_slug for candidate in grouping.candidates] == [
        LICENSE,
        "profile_picture",
        RESIDENCE,
    ]
    assert [candidate.sides for candidate in grouping.candidates] == [
        (Side.FRONT, Side.BACK),
        (Side.SINGLE,),
        (Side.FRONT, Side.BACK),
    ]
    assert (file_grouping.blank_pages, file_grouping.unanalyzed_pages) == ((), ())
    determined = _events(session, EventType.DOC_TYPE_DETERMINED)
    assert [(e.upload_id, e.file_id, e.page_index) for e in determined] == [
        (UPLOAD_ID, file_id, 0),
        (UPLOAD_ID, file_id, 2),
        (UPLOAD_ID, file_id, 3),
    ]
    assert [event.data_json for event in determined] == [
        {"document_type_slug": LICENSE, "pages": [0, 1], "sides": ["front", "back"]},
        {"document_type_slug": "profile_picture", "pages": [2], "sides": ["single"]},
        {"document_type_slug": RESIDENCE, "pages": [3, 4], "sides": ["front", "back"]},
    ]
    assert not _events(session, EventType.DOC_TYPE_UNKNOWN)
    logged = json.dumps([event.data_json for event in determined])
    for value in ("SIDOROV", "IVAN", "1985-05-05", "000123456", "AB1234567", "Belgrade"):
        assert value not in logged


def test_group_upload_reads_blank_failed_duplicate_and_catalog_less_pages(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    card = make_text_pdf_bytes(["ON YUZ", None, "ARKA YUZ", "BOZUK"])
    upload = _upload(
        session,
        layout,
        [
            ("kart.pdf", card),
            ("diploma.jpg", make_half_filled_image_bytes("JPEG")),
            ("tekrar.pdf", card),
        ],
    )
    card_file, image_file, duplicate = upload.files
    duplicate.is_duplicate_of = card_file.id
    session.flush()
    broken = _payload(3, LICENSE, side="back", continues=True)
    del broken["side"]
    diploma = _payload(0, None, candidate_type_name="Peruvian Diploma", person=NO_PERSON, fields={})
    responses = [
        _payload(0, LICENSE, side="front"),
        _payload(2, LICENSE, side="back", continues=True, person=NO_PERSON),
        broken,
        diploma,
    ]
    analyze_upload(
        session,
        layout,
        upload,
        provider=_recordings(tmp_path, responses),
        instructions=INSTRUCTIONS,
    )

    grouping = group_upload(session, upload, catalog=CATALOG)

    assert [file_grouping.file_id for file_grouping in grouping.files] == [
        card_file.id,
        image_file.id,
    ]
    card_grouping, image_grouping = grouping.files
    assert _layout(card_grouping) == [(0, 2)]
    assert card_grouping.blank_pages == (1,)
    assert card_grouping.unanalyzed_pages == (3,)
    assert _layout(image_grouping) == [(0,)]
    (determined,) = _events(session, EventType.DOC_TYPE_DETERMINED)
    assert (determined.file_id, determined.page_index, determined.data_json) == (
        card_file.id,
        0,
        {"document_type_slug": LICENSE, "pages": [0, 2], "sides": ["front", "back"]},
    )
    (unknown,) = _events(session, EventType.DOC_TYPE_UNKNOWN)
    assert (unknown.upload_id, unknown.file_id, unknown.page_index, unknown.data_json) == (
        UPLOAD_ID,
        image_file.id,
        0,
        {"candidate_type_name": "Peruvian Diploma", "pages": [0], "sides": ["single"]},
    )


def test_pages_not_yet_analyzed_form_no_candidates(session: Session, layout: DataLayout) -> None:
    upload = _upload(session, layout, [("tarama.pdf", make_text_pdf_bytes(["A", "B"]))])

    grouping = group_upload(session, upload, catalog=CATALOG)

    (file_grouping,) = grouping.files
    assert file_grouping.candidates == ()
    assert file_grouping.unanalyzed_pages == (0, 1)
    assert grouping.candidates == ()
    assert not _events(session, EventType.DOC_TYPE_DETERMINED)
    assert not _events(session, EventType.DOC_TYPE_UNKNOWN)


def test_invalid_stored_analysis_is_rejected_without_personal_values(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    upload = _upload(session, layout, [("foto.jpg", make_half_filled_image_bytes("JPEG"))])
    provider = _recordings(tmp_path, [_payload(0, PASSPORT)])
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)
    (page,) = upload.files[0].pages
    tampered = dict(page.analysis_json)
    del tampered["side"]
    tampered["person"] = {**tampered["person"], "date_of_birth": "01.01.1990"}
    page.analysis_json = tampered
    session.flush()

    with pytest.raises(StoredAnalysisError) as raised:
        group_upload(session, upload, catalog=CATALOG)

    message = str(raised.value)
    assert f"(dosya {upload.files[0].id}, sayfa 0)" in message
    assert "side:" in message
    assert "person.date_of_birth:" in message
    for value in (SYNTHETIC_SURNAME, SYNTHETIC_DOCUMENT_NUMBER, "01.01.1990"):
        assert value not in message
    assert not _events(session, EventType.DOC_TYPE_DETERMINED)
