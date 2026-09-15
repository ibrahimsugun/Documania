"""04.1.1 — ardışık, aynı tür ve aynı kişiye ait sayfalar tek belge adayı olur; 04.1.2 —
`front_back` türlerde ön ve arka yüz sıralı biçimde eşleşir; 04.2.1 — araya başka belge girmiş
parçalar otomatik birleştirilmez, gerekçesiyle Unresolved'a gider; 04.3.1 — yalnız `direct: false`
türlerde aynı partideki ayrı dosyalardaki ön ve arka yüz eşleştirilir; 04.3.2 — aynı türden birden
fazla ön yüz varsa eşleştirme yapılmaz, hepsi Unresolved'a gider; 04.5.1 — aday, türün sayfa
aralığı dışındaysa Unresolved olur. Kabul senaryoları: S3, S4, S5.

Birim testleri `group_file_pages`'e ve `group_across_files`'a sentetik analizler verir. Entegrasyon
testleri sentetik PDF/JPEG'i gerçek render adımlarından ve kayıtlı yanıt sağlayıcısıyla (03.6)
analizden geçirip `group_upload`'u veritabanı üzerinde koşar — gerçek kişi/belge yok, ağ çağrısı
yok.
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
from app.catalog import Catalog, load_seed_catalog, validate_catalog
from app.config import Settings
from app.db.models import Event, QueueKind, Upload, UploadFile, UploadStatus
from app.events import EventType
from app.pipeline.analyze import analyze_upload
from app.pipeline.group import (
    AmbiguousPairing,
    ContiguityViolation,
    DocumentCandidate,
    FileGrouping,
    GroupingPage,
    PageCountViolation,
    PageRef,
    StoredAnalysisError,
    UploadGrouping,
    group_across_files,
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
PHOTO = "profile_picture"  # single, 1 sayfa

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


def _photo(index: int) -> GroupingPage:
    return _page(index, PHOTO, person=NO_PERSON, fields={})


def _group(*pages: GroupingPage) -> FileGrouping:
    return group_file_pages(FILE_ID, pages, catalog=CATALOG)


def _layout(grouping: FileGrouping) -> list[tuple[int, ...]]:
    return [tuple(page.index for page in candidate.pages) for candidate in grouping.candidates]


def _violations(grouping: FileGrouping) -> list[ContiguityViolation | None]:
    return [candidate.contiguity_violation for candidate in grouping.candidates]


def _file(file_id: int, *pages: GroupingPage, catalog: Catalog = CATALOG) -> FileGrouping:
    return group_file_pages(file_id, pages, catalog=catalog)


def _files(*files: list[GroupingPage]) -> list[FileGrouping]:
    """Dosya kimlikleri 1'den, verilen sırayla."""
    return [_file(file_id, *pages) for file_id, pages in enumerate(files, start=1)]


def _across(*files: FileGrouping, catalog: Catalog = CATALOG) -> UploadGrouping:
    return group_across_files(files, catalog=catalog)


def _refs(candidate: DocumentCandidate) -> list[tuple[int, int]]:
    return [(page.file_id, page.index) for page in candidate.pages]


def _marked(grouping: UploadGrouping) -> dict[PageRef, AmbiguousPairing]:
    """Belirsiz eşleştirmeye takılan adaylar, ilk sayfalarıyla."""
    return {
        PageRef(candidate.pages[0].file_id, candidate.pages[0].index): candidate.ambiguous_pairing
        for candidate in grouping.candidates
        if candidate.ambiguous_pairing is not None
    }


def _catalog_with(slug: str, **changes: Any) -> Catalog:
    entries = [entry.model_dump(mode="json") for entry in CATALOG]
    for entry in entries:
        if entry["slug"] == slug:
            entry.update(changes)
    return validate_catalog(entries)


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


# --- 04.2.1 ardışıklık güvenlik kuralı --------------------------------------------------------


@pytest.mark.parametrize("back_continues", [False, True])
def test_s3_card_faces_with_other_documents_between_go_to_unresolved(back_continues: bool) -> None:
    # S3: ehliyet ön, foto, başka belge, oturum ön, oturum arka, ehliyet arka. Arka yüzün devam
    # işareti önceki sayfaya (oturum izni) göredir; yanlışlıkla `true` gelse de birleştirilmez.
    grouping = _group(
        _front(0),
        _photo(1),
        _page(2, PERMIT),
        _front(3, slug=RESIDENCE),
        _back(4, slug=RESIDENCE),
        _back(5, continues=back_continues),
    )

    assert _layout(grouping) == [(0,), (1,), (2,), (3, 4), (5,)]
    assert _violations(grouping) == [
        ContiguityViolation(pages=(0,), counterparts=((5,),), intervening_pages=(1, 2, 3, 4)),
        None,
        None,
        None,
        ContiguityViolation(pages=(5,), counterparts=((0,),), intervening_pages=(1, 2, 3, 4)),
    ]
    front = grouping.candidates[0].contiguity_violation
    assert front is not None
    assert (front.rule, front.queue) == ("R6", QueueKind.UNRESOLVED)
    assert grouping.candidates[3].sides == (Side.FRONT, Side.BACK)


def test_back_scanned_before_its_front_is_also_a_piece() -> None:
    # Arka yüzü önce taranmış kart da aynı karttır; bitişik olsaydı 04.1 eşleştirmezdi (sıra), araya
    # belge girince gerekçe ardışıklıktır.
    grouping = _group(_back(0, continues=False), _photo(1), _front(2))

    assert _violations(grouping) == [
        ContiguityViolation(pages=(0,), counterparts=((2,),), intervening_pages=(1,)),
        None,
        ContiguityViolation(pages=(2,), counterparts=((0,),), intervening_pages=(1,)),
    ]


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        pytest.param(
            [_front(0), GroupingPage(1), _back(2)],
            [
                ContiguityViolation(pages=(0,), counterparts=((2,),), unanalyzed_pages=(1,)),
                ContiguityViolation(pages=(2,), counterparts=((0,),), unanalyzed_pages=(1,)),
            ],
            id="yalniz-analizsiz",
        ),
        pytest.param(
            [_front(0), _photo(1), GroupingPage(2), _back(3, continues=False)],
            [
                ContiguityViolation(
                    pages=(0,), counterparts=((3,),), intervening_pages=(1,), unanalyzed_pages=(2,)
                ),
                None,
                ContiguityViolation(
                    pages=(3,), counterparts=((0,),), intervening_pages=(1,), unanalyzed_pages=(2,)
                ),
            ],
            id="belge-ve-analizsiz",
        ),
    ],
)
def test_unanalyzed_page_between_pieces_may_be_another_document(
    pages: list[GroupingPage], expected: list[ContiguityViolation | None]
) -> None:
    # Analizi başarısız sayfanın içeriği bilinmez; araya başka belge girmiş olabilir (K5).
    grouping = _group(*pages)

    assert _violations(grouping) == expected


def test_blank_pages_between_pieces_are_not_other_documents() -> None:
    grouping = _group(
        _front(0),
        GroupingPage(1, is_blank=True),
        _photo(2),
        _page(3, None, person=NO_PERSON, **BLANK_READING),
        _back(4, continues=False),
    )

    assert grouping.blank_pages == (1, 3)
    assert _violations(grouping) == [
        ContiguityViolation(pages=(0,), counterparts=((4,),), intervening_pages=(2,)),
        None,
        ContiguityViolation(pages=(4,), counterparts=((0,),), intervening_pages=(2,)),
    ]


@pytest.mark.parametrize(
    "pages",
    [
        pytest.param([_front(0), _back(1, continues=False)], id="bitisik"),
        pytest.param(
            [_front(0), GroupingPage(1, is_blank=True), _back(2, continues=False)], id="bos-sayfa"
        ),
        pytest.param(
            [
                _front(0),
                _page(1, None, continues=True, person=NO_PERSON, **BLANK_READING),
                _back(2),
            ],
            id="analizcinin-bos-dedigi-sayfa",
        ),
        pytest.param([_back(0, continues=False), _front(1, continues=True)], id="bitisik-ters"),
    ],
)
def test_pieces_with_no_document_between_are_not_violations(pages: list[GroupingPage]) -> None:
    # Eksik parçalar ayrı kalır ama araya belge girmemiştir; rotaları sayfa sayısı/yüz kontrolünün.
    grouping = _group(*pages)

    assert len(grouping.candidates) == 2
    assert _violations(grouping) == [None, None]


@pytest.mark.parametrize(
    "pages",
    [
        pytest.param([_front(0), _photo(1), _front(2)], id="iki-on-yuz"),
        pytest.param(
            [_front(0), _back(1), _photo(2), _back(3, continues=False)], id="tam-cift-ve-arka"
        ),
        pytest.param([_front(0), _photo(1), _front(2), _back(3)], id="on-ve-tam-cift"),
        pytest.param(
            [_front(0), _photo(1), _page(2, LICENSE, side="unknown", person=NO_PERSON)],
            id="yuzu-belirsiz",
        ),
        pytest.param(
            [_front(0), _photo(1), _back(2, slug=RESIDENCE, continues=False)], id="baska-tur"
        ),
        pytest.param(
            [
                _front(0),
                _photo(1),
                _page(2, LICENSE, side="back", person={**NO_PERSON, "document_number": "00 09"}),
            ],
            id="baska-kisi",
        ),
        pytest.param(
            [_page(0), _page(1, continues=True), _photo(2), _page(3)], id="sayfa-siniri-asilir"
        ),
        pytest.param([_page(0, PASSPORT), _photo(1), _page(2, PASSPORT)], id="tek-sayfalik-tur"),
        pytest.param(
            [
                _page(0, None, candidate_type_name="Peruvian Diploma", fields={}),
                _photo(1),
                _page(2, None, candidate_type_name="Peruvian Diploma", fields={}),
            ],
            id="katalog-disi-tur",
        ),
        pytest.param([_page(0, None), _photo(1), _page(2, None)], id="tur-belirsiz"),
    ],
)
def test_candidates_that_cannot_be_one_document_are_not_pieces(pages: list[GroupingPage]) -> None:
    grouping = _group(*pages)

    assert all(violation is None for violation in _violations(grouping))


def test_single_sided_pieces_fitting_one_document_go_to_unresolved() -> None:
    # 1–2 sayfalık çalışma izni: iki ayrı izin mi, araya foto girmiş tek izin mi bilinemez (R7).
    grouping = _group(_page(0), _photo(1), _page(2))

    assert _violations(grouping) == [
        ContiguityViolation(pages=(0,), counterparts=((2,),), intervening_pages=(1,)),
        None,
        ContiguityViolation(pages=(2,), counterparts=((0,),), intervening_pages=(1,)),
    ]


def test_type_without_page_range_has_no_page_limit_for_pieces() -> None:
    entries = [entry.model_dump(mode="json") for entry in CATALOG]
    for entry in entries:
        if entry["slug"] == PERMIT:
            entry["expected_pages"] = None
    catalog = validate_catalog(entries)
    pages = [_page(0), _page(1, continues=True), _photo(2), _page(3)]

    grouping = group_file_pages(FILE_ID, pages, catalog=catalog)

    assert _violations(grouping) == [
        ContiguityViolation(pages=(0, 1), counterparts=((3,),), intervening_pages=(2,)),
        None,
        ContiguityViolation(pages=(3,), counterparts=((0, 1),), intervening_pages=(2,)),
    ]


def test_slug_missing_from_catalog_is_not_judged_for_pieces() -> None:
    catalog = validate_catalog(
        [entry.model_dump(mode="json") for entry in CATALOG if entry.slug != LICENSE]
    )

    grouping = group_file_pages(
        FILE_ID, [_front(0), _photo(1), _back(2, continues=False)], catalog=catalog
    )

    assert _violations(grouping) == [None, None, None]


def test_piece_lists_every_counterpart_and_only_other_documents_between() -> None:
    grouping = _group(
        _front(0),
        _photo(1),
        _back(2, continues=False),
        _page(3, PASSPORT),
        _back(4, continues=False),
    )

    assert _violations(grouping) == [
        # Öteki parçalar arada kalsa da başka belge sayılmaz.
        ContiguityViolation(pages=(0,), counterparts=((2,), (4,)), intervening_pages=(1, 3)),
        None,
        ContiguityViolation(pages=(2,), counterparts=((0,),), intervening_pages=(1,)),
        None,
        # İki arka yüz aynı belgenin parçası olamaz: yakındaki arka yüz buradan bakınca başka belge.
        ContiguityViolation(pages=(4,), counterparts=((0,),), intervening_pages=(1, 2, 3)),
    ]


@pytest.mark.parametrize(
    ("violation", "reason"),
    [
        pytest.param(
            ContiguityViolation(pages=(0,), counterparts=((5,),), intervening_pages=(1, 2, 3, 4)),
            "Ardışıklık güvenlik kuralı (R6): bu parça (sayfa 1) ile aynı belgeye ait olabilecek "
            "parça (sayfa 6) arasında başka belgeye ait sayfa (sayfa 2, 3, 4, 5) var; parçalar "
            "otomatik birleştirilmez.",
            id="s3",
        ),
        pytest.param(
            ContiguityViolation(pages=(2,), counterparts=((0,),), unanalyzed_pages=(1,)),
            "Ardışıklık güvenlik kuralı (R6): bu parça (sayfa 3) ile aynı belgeye ait olabilecek "
            "parça (sayfa 1) arasında analizi yapılamamış, başka belgeye ait olabilecek sayfa "
            "(sayfa 2) var; parçalar otomatik birleştirilmez.",
            id="analizsiz-sayfa",
        ),
        pytest.param(
            ContiguityViolation(
                pages=(0, 1),
                counterparts=((3,), (6, 7)),
                intervening_pages=(2, 5),
                unanalyzed_pages=(4,),
            ),
            "Ardışıklık güvenlik kuralı (R6): bu parça (sayfa 1, 2) ile aynı belgeye ait "
            "olabilecek parçalar (sayfa 4; sayfa 7, 8) arasında başka belgeye ait sayfa "
            "(sayfa 3, 6) ve analizi yapılamamış, başka belgeye ait olabilecek sayfa (sayfa 5) "
            "var; parçalar otomatik birleştirilmez.",
            id="birden-cok-parca",
        ),
    ],
)
def test_violation_reason_names_rule_pieces_and_pages_between(
    violation: ContiguityViolation, reason: str
) -> None:
    assert violation.reason == reason


# --- 04.3.1 dosyalar arası gruplama -----------------------------------------------------------


@pytest.mark.parametrize("slug", [LICENSE, RESIDENCE])
@pytest.mark.parametrize(
    ("front_file", "back_file"), [(1, 2), (2, 1)], ids=["on-once-yuklendi", "arka-once-yuklendi"]
)
def test_s5_front_and_back_in_separate_files_form_one_candidate(
    slug: str, front_file: int, back_file: int
) -> None:
    # S5: aynı partide `on.jpg` ve `arka.jpg`. Yükleme sırası belge yapısı değildir; aday önce ön,
    # sonra arka yüzü taşır.
    grouping = _across(
        _file(front_file, _front(0, slug=slug)),
        _file(back_file, _back(0, slug=slug, continues=False)),
    )

    (candidate,) = grouping.cross_file_candidates
    assert _refs(candidate) == [(front_file, 0), (back_file, 0)]
    assert candidate.file_ids == (front_file, back_file)
    assert candidate.sides == (Side.FRONT, Side.BACK)
    assert candidate.document_type_slug == slug
    assert (candidate.contiguity_violation, candidate.ambiguous_pairing) == (None, None)
    assert [file_grouping.file_id for file_grouping in grouping.files] == [1, 2]
    assert all(file_grouping.candidates == () for file_grouping in grouping.files)
    assert grouping.candidates == (candidate,)


def test_faces_inside_multi_page_files_pair_and_other_candidates_stay() -> None:
    grouping = _across(
        _file(1, _photo(0), _front(1), _page(2, PASSPORT)),
        _file(2, _page(0, PERMIT), _back(1, continues=False)),
    )

    assert [_layout(file_grouping) for file_grouping in grouping.files] == [[(0,), (2,)], [(0,)]]
    assert [_refs(candidate) for candidate in grouping.candidates] == [
        [(1, 0)],
        [(1, 2)],
        [(2, 0)],
        [(1, 1), (2, 1)],
    ]
    assert grouping.candidates[0].file_ids == (1,)


@pytest.mark.parametrize(
    "files",
    [
        pytest.param([[_front(0), _back(1, continues=False)]], id="bitisik"),
        pytest.param([[_back(0, continues=False), _front(1, continues=True)]], id="bitisik-ters"),
        pytest.param(
            [[_front(0), _back(1, continues=False)], [_photo(0)]], id="baska-dosyada-foto"
        ),
    ],
)
def test_faces_in_the_same_file_are_not_paired_across_files(
    files: list[list[GroupingPage]],
) -> None:
    grouping = _across(*_files(*files))

    assert grouping.cross_file_candidates == ()
    assert _layout(grouping.files[0]) == [(0,), (1,)]
    assert _marked(grouping) == {}


def test_direct_document_faces_in_separate_files_are_not_paired() -> None:
    # K3: Direkt Belge'ye başka dosyadan sayfa eklenmez; yüzler eksik aday kalır (04.5).
    catalog = _catalog_with(LICENSE, direct=True, allowed_conversions=[])

    grouping = _across(
        _file(1, _front(0), catalog=catalog),
        _file(2, _back(0, continues=False), catalog=catalog),
        catalog=catalog,
    )

    assert grouping.cross_file_candidates == ()
    assert [_refs(candidate) for candidate in grouping.candidates] == [[(1, 0)], [(2, 0)]]
    assert _marked(grouping) == {}


@pytest.mark.parametrize(
    "files",
    [
        pytest.param([[_page(0)], [_page(0, continues=True)]], id="tek-yuzlu-tur"),
        pytest.param(
            [[_page(0, side="front")], [_page(0, side="back", person=NO_PERSON)]],
            id="tek-yuzlu-turde-on-ve-arka-okunmus",
        ),
        pytest.param([[_front(0)], [_back(0, slug=RESIDENCE, continues=False)]], id="farkli-tur"),
        pytest.param(
            [
                [_page(0, None, side="front", candidate_type_name="Bosnian Identity Card")],
                [_page(0, None, side="back", candidate_type_name="Bosnian Identity Card")],
            ],
            id="katalog-disi-tur",
        ),
        pytest.param(
            [[_page(0, None, side="front")], [_page(0, None, side="back", person=NO_PERSON)]],
            id="tur-belirsiz",
        ),
        pytest.param(
            [[_front(0)], [_page(0, LICENSE, side="unknown", person=NO_PERSON)]],
            id="yuzu-belirsiz",
        ),
        pytest.param([[_front(0)], [_front(0)]], id="yalniz-on-yuzler"),
    ],
)
def test_only_a_front_and_a_back_of_a_catalog_type_pair_across_files(
    files: list[list[GroupingPage]],
) -> None:
    grouping = _across(*_files(*files))

    assert grouping.cross_file_candidates == ()
    assert len(grouping.candidates) == 2
    assert _marked(grouping) == {}


def test_faces_showing_different_persons_are_not_paired() -> None:
    # Arka yüzde başka bir belge numarası yazılı: aynı kart değildir, işaretsiz ayrı kalır (04.5).
    other = {**NO_PERSON, "document_number": "00 0000009"}

    grouping = _across(_file(1, _front(0)), _file(2, _page(0, LICENSE, side="back", person=other)))

    assert grouping.cross_file_candidates == ()
    assert [_refs(candidate) for candidate in grouping.candidates] == [[(1, 0)], [(2, 0)]]
    assert _marked(grouping) == {}


def test_complete_pair_does_not_compete_for_faces_in_other_files() -> None:
    grouping = _across(
        _file(1, _front(0), _back(1)),
        _file(2, _front(0)),
        _file(3, _back(0, continues=False)),
    )

    assert [_refs(candidate) for candidate in grouping.candidates] == [
        [(1, 0), (1, 1)],
        [(2, 0), (3, 0)],
    ]
    assert grouping.files[0].candidates[0].sides == (Side.FRONT, Side.BACK)
    assert _marked(grouping) == {}


def test_confidently_typed_documents_and_blank_pages_do_not_block_pairing() -> None:
    # Başka katalog türü, tek yüzlü katalog dışı belge, başka türün yüzleri ve boş sayfa bu türün
    # yüzü olamaz.
    grouping = _across(
        _file(1, _front(0)),
        _file(2, _back(0, continues=False)),
        _file(
            3,
            _page(0, PASSPORT),
            _photo(1),
            GroupingPage(2, is_blank=True),
            _page(3, None, person=NO_PERSON, **BLANK_READING),
            _page(4, None, candidate_type_name="Peruvian Diploma", person=NO_PERSON, fields={}),
            _front(5, slug=RESIDENCE),
            _back(6, slug=RESIDENCE),
            _front(7, slug=RESIDENCE),
        ),
    )

    (candidate,) = grouping.cross_file_candidates
    assert _refs(candidate) == [(1, 0), (2, 0)]
    assert _layout(grouping.files[2]) == [(0,), (1,), (4,), (5, 6), (7,)]
    assert _marked(grouping) == {}


def test_each_type_pairs_on_its_own_in_order_of_front_faces() -> None:
    grouping = _across(
        _file(1, _back(0, slug=RESIDENCE, continues=False)),
        _file(2, _front(0)),
        _file(3, _front(0, slug=RESIDENCE)),
        _file(4, _back(0, continues=False)),
    )

    assert [_refs(candidate) for candidate in grouping.cross_file_candidates] == [
        [(2, 0), (4, 0)],
        [(3, 0), (1, 0)],
    ]
    assert [candidate.document_type_slug for candidate in grouping.cross_file_candidates] == [
        LICENSE,
        RESIDENCE,
    ]
    assert all(file_grouping.candidates == () for file_grouping in grouping.files)


def test_file_groupings_are_read_in_file_order_whatever_the_input_order() -> None:
    files = [_file(5, _photo(0)), _file(2, _back(0, continues=False)), _file(3, _front(0))]

    grouping = group_across_files(iter(files), catalog=CATALOG)

    assert [file_grouping.file_id for file_grouping in grouping.files] == [2, 3, 5]
    assert [_refs(candidate) for candidate in grouping.candidates] == [[(5, 0)], [(3, 0), (2, 0)]]


def test_repeated_file_is_rejected() -> None:
    with pytest.raises(ValueError, match="birden fazla"):
        _across(_file(1, _front(0)), _file(1, _back(0)))


def test_upload_grouping_without_files_has_no_candidates() -> None:
    grouping = group_across_files([], catalog=CATALOG)

    assert (grouping.files, grouping.cross_file_candidates, grouping.candidates) == ((), (), ())


# --- 04.3.2 belirsiz eşleştirmenin reddi ------------------------------------------------------


def _ambiguities(
    faces: list[tuple[int, int]],
    fronts: list[tuple[int, int]],
    backs: list[tuple[int, int]],
    **pages: Any,
) -> dict[PageRef, AmbiguousPairing]:
    front_refs = tuple(PageRef(*ref) for ref in fronts)
    back_refs = tuple(PageRef(*ref) for ref in backs)
    blockers = {name: tuple(PageRef(*ref) for ref in refs) for name, refs in pages.items()}
    return {
        PageRef(*face): AmbiguousPairing(PageRef(*face), front_refs, back_refs, **blockers)
        for face in faces
    }


@pytest.mark.parametrize(
    "second_front_person",
    [
        pytest.param({}, id="ayni-kisi"),
        pytest.param({"surname": "DENEMEVA", "document_number": "00 0000002"}, id="baska-kisi"),
    ],
)
def test_several_fronts_of_a_type_are_not_paired_and_all_go_to_unresolved(
    second_front_person: dict[str, Any],
) -> None:
    # 04.3.2: arka yüzde kimlik yazmaz; hangi ön yüzle aynı karta ait olduğu bilinemez.
    grouping = _across(
        _file(1, _front(0)),
        _file(2, _page(0, LICENSE, side="front", person=second_front_person)),
        _file(3, _back(0, continues=False)),
    )

    assert grouping.cross_file_candidates == ()
    assert len(grouping.candidates) == 3
    faces = [(1, 0), (2, 0), (3, 0)]
    assert _marked(grouping) == _ambiguities(faces, fronts=[(1, 0), (2, 0)], backs=[(3, 0)])
    first = grouping.candidates[0].ambiguous_pairing
    assert first is not None and first.queue is QueueKind.UNRESOLVED


@pytest.mark.parametrize(
    ("files", "fronts", "backs"),
    [
        pytest.param(
            [[_front(0)], [_back(0, continues=False)], [_front(0)], [_back(0, continues=False)]],
            [(1, 0), (3, 0)],
            [(2, 0), (4, 0)],
            id="iki-kart",
        ),
        pytest.param(
            [[_front(0)], [_back(0, continues=False)], [_back(0, continues=False)]],
            [(1, 0)],
            [(2, 0), (3, 0)],
            id="bir-on-iki-arka",
        ),
        pytest.param(
            [[_front(0), _photo(1), _front(2)], [_back(0, continues=False)]],
            [(1, 0), (1, 2)],
            [(2, 0)],
            id="iki-on-yuz-ayni-dosyada",
        ),
        pytest.param(
            [[_front(0), _back(1, continues=False)], [_back(0, continues=False)]],
            [(1, 0)],
            [(1, 1), (2, 0)],
            id="ayni-dosyada-eslesmemis-arka",
        ),
    ],
)
def test_more_than_one_unpaired_front_or_back_makes_pairing_ambiguous(
    files: list[list[GroupingPage]], fronts: list[tuple[int, int]], backs: list[tuple[int, int]]
) -> None:
    grouping = _across(*_files(*files))

    assert grouping.cross_file_candidates == ()
    assert _marked(grouping) == _ambiguities([*fronts, *backs], fronts, backs)


def test_contiguity_pieces_are_never_paired_but_count_as_unpaired_faces() -> None:
    # Ardışıklık kuralına takılan parça dosyalar arası eşleşmez; eşi aynı dosyada olabileceği için
    # başka dosyalardaki yüzlerin eşleşmesini de belirsiz yapar. Parça yalnız R6 hükmünü taşır.
    grouping = _across(
        _file(1, _front(0), _photo(1), _back(2, continues=False)),
        _file(2, _front(0)),
        _file(3, _back(0, continues=False)),
    )

    assert grouping.cross_file_candidates == ()
    front_piece, photo, back_piece = grouping.files[0].candidates
    assert front_piece.contiguity_violation is not None
    assert back_piece.contiguity_violation is not None
    assert photo.contiguity_violation is None
    assert _marked(grouping) == _ambiguities(
        [(2, 0), (3, 0)], fronts=[(1, 0), (2, 0)], backs=[(1, 2), (3, 0)]
    )


@pytest.mark.parametrize(
    "other_file",
    [
        pytest.param([_back(0, continues=False)], id="arka-yuz"),
        pytest.param([_front(0)], id="on-yuz"),
    ],
)
def test_contiguity_piece_and_a_face_in_another_file_are_not_judged(
    other_file: list[GroupingPage],
) -> None:
    # Eşleşebilecek yüz çifti yok: parçalar R6 ile Unresolved'da, öteki yüz eksik aday (04.5).
    grouping = _across(*_files([_front(0), _photo(1), _back(2, continues=False)], other_file))

    assert grouping.cross_file_candidates == ()
    assert [candidate.contiguity_violation is not None for candidate in grouping.candidates] == [
        True,
        False,
        True,
        False,
    ]
    assert _marked(grouping) == {}


@pytest.mark.parametrize(
    ("files", "blockers"),
    [
        pytest.param(
            [[_front(0)], [_back(0, continues=False)], [_page(0, LICENSE, side="unknown")]],
            {"unoriented_pages": [(3, 0)]},
            id="turun-yuzu-belirsiz-sayfasi",
        ),
        pytest.param(
            [[_front(0)], [_back(0, continues=False)], [_page(0, LICENSE, side="single")]],
            {"unoriented_pages": [(3, 0)]},
            id="turun-tek-yuzlu-okunmus-sayfasi",
        ),
        pytest.param(
            [[_front(0)], [_back(0, continues=False)], [_photo(0), GroupingPage(1)]],
            {"unanalyzed_pages": [(3, 1)]},
            id="analizsiz-sayfa",
        ),
        pytest.param(
            [[_front(0), GroupingPage(1)], [_back(0, continues=False)]],
            {"unanalyzed_pages": [(1, 1)]},
            id="on-yuzun-dosyasinda-analizsiz-sayfa",
        ),
        pytest.param(
            [[_front(0)], [_back(0, continues=False)], [_page(0, None, side="unknown")]],
            {"uncertain_type_pages": [(3, 0)]},
            id="turu-belirsiz-sayfa",
        ),
        pytest.param(
            [
                [_front(0)],
                [_back(0, continues=False)],
                [
                    _page(0, None, candidate_type_name="Employment Contract"),
                    _page(1, None, side="back", candidate_type_name="Driving License", fields={}),
                ],
            ],
            {"uncertain_type_pages": [(3, 1)]},
            id="aday-turlu-kart-yuzu",
        ),
        pytest.param(
            [
                [_front(0), GroupingPage(1)],
                [_back(0, continues=False), _page(1, LICENSE, side="unknown", person=NO_PERSON)],
                [_page(0, None, side="front"), GroupingPage(1)],
            ],
            {
                "unoriented_pages": [(2, 1)],
                "unanalyzed_pages": [(1, 1), (3, 1)],
                "uncertain_type_pages": [(3, 0)],
            },
            id="hepsi",
        ),
    ],
)
def test_page_that_may_be_another_face_makes_pairing_ambiguous(
    files: list[list[GroupingPage]], blockers: dict[str, list[tuple[int, int]]]
) -> None:
    # Tek ön ve tek arka yüz ayrı dosyalarda; ama partide bu türün yüzü olmadığı kesin olmayan bir
    # sayfa var: eşleştirme tahmin olurdu.
    grouping = _across(*_files(*files))

    assert grouping.cross_file_candidates == ()
    assert _marked(grouping) == _ambiguities(
        [(1, 0), (2, 0)], fronts=[(1, 0)], backs=[(2, 0)], **blockers
    )


def test_page_whose_slug_is_missing_from_catalog_makes_pairing_ambiguous() -> None:
    catalog = validate_catalog(
        [entry.model_dump(mode="json") for entry in CATALOG if entry.slug != PERMIT]
    )

    grouping = _across(
        _file(1, _front(0), catalog=catalog),
        _file(2, _back(0, continues=False), catalog=catalog),
        _file(3, _page(0, side="unknown"), _page(1, continues=True), catalog=catalog),
        catalog=catalog,
    )

    assert grouping.cross_file_candidates == ()
    assert _marked(grouping) == _ambiguities(
        [(1, 0), (2, 0)], fronts=[(1, 0)], backs=[(2, 0)], uncertain_type_pages=[(3, 0)]
    )


def test_ambiguity_of_one_type_does_not_stop_pairing_of_another() -> None:
    grouping = _across(
        _file(1, _front(0)),
        _file(2, _front(0)),
        _file(3, _back(0, continues=False)),
        _file(4, _front(0, slug=RESIDENCE)),
        _file(5, _back(0, slug=RESIDENCE, continues=False)),
    )

    (residence,) = grouping.cross_file_candidates
    assert _refs(residence) == [(4, 0), (5, 0)]
    assert residence.ambiguous_pairing is None
    assert set(_marked(grouping)) == {PageRef(1, 0), PageRef(2, 0), PageRef(3, 0)}


@pytest.mark.parametrize(
    ("ambiguity", "reason"),
    [
        pytest.param(
            AmbiguousPairing(
                face=PageRef(11, 0),
                fronts=(PageRef(11, 0), PageRef(13, 0)),
                backs=(PageRef(12, 0),),
            ),
            "Belirsiz ön/arka yüz eşleştirmesi: bu yüz (dosya 11, sayfa 1) partide tek anlamlı bir "
            "eşle eşleştirilemiyor. Eşleşmemiş ön yüzler: dosya 11, sayfa 1; dosya 13, sayfa 1. "
            "Eşleşmemiş arka yüzler: dosya 12, sayfa 1. Yüzler dosyalar arasında otomatik "
            "eşleştirilmez.",
            id="iki-on-yuz",
        ),
        pytest.param(
            AmbiguousPairing(
                face=PageRef(12, 2),
                fronts=(PageRef(11, 0),),
                backs=(PageRef(12, 2),),
                unoriented_pages=(PageRef(14, 0),),
                unanalyzed_pages=(PageRef(11, 1), PageRef(15, 3)),
                uncertain_type_pages=(PageRef(16, 0),),
            ),
            "Belirsiz ön/arka yüz eşleştirmesi: bu yüz (dosya 12, sayfa 3) partide tek anlamlı bir "
            "eşle eşleştirilemiyor. Eşleşmemiş ön yüzler: dosya 11, sayfa 1. Eşleşmemiş arka "
            "yüzler: dosya 12, sayfa 3. Aynı türün yüzü ön ya da arka okunmamış sayfaları: dosya "
            "14, sayfa 1. Analizi yapılamamış sayfalar: dosya 11, sayfa 2; dosya 15, sayfa 4. Türü "
            "kesin belirlenemeyen sayfalar: dosya 16, sayfa 1. Yüzler dosyalar arasında otomatik "
            "eşleştirilmez.",
            id="baska-yuz-olabilecek-sayfalar",
        ),
    ],
)
def test_ambiguous_pairing_reason_lists_faces_and_pages_that_may_be_faces(
    ambiguity: AmbiguousPairing, reason: str
) -> None:
    assert ambiguity.reason == reason


# --- 04.5.1 beklenen sayfa sayısı kontrolü ------------------------------------------------------


def test_lone_front_with_no_counterpart_anywhere_is_a_page_count_violation() -> None:
    # 04.3.2 yalnız eşleşebilecek karşı yüz varken hüküm verir; karşı yüz partide hiç yoksa 04.5'in.
    grouping = _across(_file(1, _front(0)))

    assert grouping.cross_file_candidates == ()
    (candidate,) = grouping.candidates
    assert (candidate.contiguity_violation, candidate.ambiguous_pairing) == (None, None)
    assert candidate.page_count_violation == PageCountViolation(
        pages=(PageRef(1, 0),), expected_min=2, expected_max=2
    )
    assert candidate.page_count_violation.queue is QueueKind.UNRESOLVED


def test_adjacent_front_and_back_are_each_a_page_count_violation() -> None:
    # Bitişik eksik parçalar R6'nın konusu değildir (araya belge girmemiş); sayfa sayısı 04.5'in.
    grouping = _across(_file(1, _front(0), _back(1, continues=False)))

    (front, back) = grouping.files[0].candidates
    assert (front.contiguity_violation, front.ambiguous_pairing) == (None, None)
    assert (back.contiguity_violation, back.ambiguous_pairing) == (None, None)
    assert front.page_count_violation == PageCountViolation(
        pages=(PageRef(1, 0),), expected_min=2, expected_max=2
    )
    assert back.page_count_violation == PageCountViolation(
        pages=(PageRef(1, 1),), expected_min=2, expected_max=2
    )


def test_single_sided_candidate_beyond_the_expected_maximum_is_a_page_count_violation() -> None:
    entry = CATALOG.get(PERMIT)
    assert entry is not None and entry.expected_pages is not None
    assert (entry.expected_pages.min, entry.expected_pages.max) == (1, 2)
    file_grouping = _file(1, _page(0), _page(1, continues=True), _page(2, continues=True))
    assert _layout(file_grouping) == [(0, 1, 2)]  # gruplama sayfa sayısıyla bölmez (04.1.2 notu)

    grouping = _across(file_grouping)

    (candidate,) = grouping.candidates
    assert candidate.page_count_violation == PageCountViolation(
        pages=(PageRef(1, 0), PageRef(1, 1), PageRef(1, 2)), expected_min=1, expected_max=2
    )


@pytest.mark.parametrize("page_count", [1, 2], ids=["alt-sinir", "ust-sinir"])
def test_single_sided_candidate_within_range_is_not_a_page_count_violation(page_count: int) -> None:
    pages = [_page(0), *(_page(i, continues=True) for i in range(1, page_count))]

    grouping = _across(_file(1, *pages))

    (candidate,) = grouping.candidates
    assert candidate.page_count_violation is None


def test_type_without_page_range_has_no_page_count_limit() -> None:
    catalog = _catalog_with(PERMIT, expected_pages=None)
    file_grouping = group_file_pages(
        FILE_ID, [_page(0), _page(1, continues=True), _page(2, continues=True)], catalog=catalog
    )

    grouping = group_across_files([file_grouping], catalog=catalog)

    (candidate,) = grouping.candidates
    assert candidate.page_count_violation is None


def test_slug_missing_from_catalog_is_not_judged_for_page_count() -> None:
    catalog = validate_catalog(
        [entry.model_dump(mode="json") for entry in CATALOG if entry.slug != PERMIT]
    )
    file_grouping = group_file_pages(FILE_ID, [_page(0)], catalog=catalog)

    grouping = group_across_files([file_grouping], catalog=catalog)

    (candidate,) = grouping.candidates
    assert candidate.document_type_slug == PERMIT
    assert candidate.page_count_violation is None


def test_candidate_type_name_without_catalog_entry_is_not_judged_for_page_count() -> None:
    grouping = _across(_file(1, _page(0, None, candidate_type_name="Peruvian Diploma", fields={})))

    (candidate,) = grouping.candidates
    assert candidate.page_count_violation is None


def test_contiguity_violation_pieces_are_not_also_page_count_violations() -> None:
    # R6 zaten Unresolved'a gönderir; aynı adaya iki gerekçe eklenmez.
    grouping = _across(_file(1, _front(0), _photo(1), _back(2, continues=False)))

    front, photo, back = grouping.files[0].candidates
    assert front.contiguity_violation is not None and back.contiguity_violation is not None
    assert (front.page_count_violation, back.page_count_violation) == (None, None)
    assert photo.contiguity_violation is None and photo.page_count_violation is None


def test_ambiguous_pairing_faces_are_not_also_page_count_violations() -> None:
    # 04.3.2 zaten Unresolved'a gönderir; aynı adaya iki gerekçe eklenmez.
    grouping = _across(
        _file(1, _front(0)),
        _file(2, _page(0, LICENSE, side="front")),
        _file(3, _back(0, continues=False)),
    )

    assert all(candidate.ambiguous_pairing is not None for candidate in grouping.candidates)
    assert all(candidate.page_count_violation is None for candidate in grouping.candidates)


@pytest.mark.parametrize(
    ("violation", "reason"),
    [
        pytest.param(
            PageCountViolation(pages=(PageRef(1, 0),), expected_min=2, expected_max=2),
            "Beklenen sayfa sayısı kontrolü (04.5.1): bu aday 1 sayfa (dosya 1, sayfa 1) "
            "taşıyor, tür 2 sayfa bekliyor.",
            id="sabit-aralik",
        ),
        pytest.param(
            PageCountViolation(
                pages=(PageRef(1, 0), PageRef(1, 1), PageRef(1, 2)), expected_min=1, expected_max=2
            ),
            "Beklenen sayfa sayısı kontrolü (04.5.1): bu aday 3 sayfa (dosya 1, sayfa 1; dosya 1, "
            "sayfa 2; dosya 1, sayfa 3) taşıyor, tür 1-2 sayfa bekliyor.",
            id="degisken-aralik",
        ),
    ],
)
def test_page_count_violation_reason_names_count_and_expected_range(
    violation: PageCountViolation, reason: str
) -> None:
    assert violation.reason == reason


def test_group_upload_marks_a_lone_face_with_no_counterpart_as_a_page_count_violation(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Partide arka yüz hiç yok: 04.3.2 hüküm vermez (eşleşebilecek karşı yüz yok); sayfa sayısı
    # kontrolü (04.5.1) Unresolved'a gönderir.
    upload = _upload(session, layout, [("on.pdf", make_text_pdf_bytes(["ON YUZ"]))])
    provider = _recordings(tmp_path, [_payload(0, LICENSE, side="front")])
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    grouping = group_upload(session, upload, catalog=CATALOG)

    file_id = upload.files[0].id
    (candidate,) = grouping.candidates
    assert candidate.ambiguous_pairing is None
    violation = candidate.page_count_violation
    assert violation == PageCountViolation(
        pages=(PageRef(file_id, 0),), expected_min=2, expected_max=2
    )
    (determined,) = _events(session, EventType.DOC_TYPE_DETERMINED)
    assert determined.message == violation.reason
    assert determined.data_json == {
        "document_type_slug": LICENSE,
        "pages": [0],
        "sides": ["front"],
        "page_count_violation": {
            "queue": "unresolved",
            "pages": [{"file_id": file_id, "page_index": 0}],
            "expected_min": 2,
            "expected_max": 2,
        },
    }


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


S3_RECORDINGS = RECORDINGS / "s3_interleaved_pdf"
S3_PERSONAL_VALUES = (
    "SIDOROV",
    "IVAN",
    "1985-05-05",
    "000123456",
    "AB1234567",
    "WP-0000042",
    "Belgrade",
)


def _piece_event_data(
    pages: list[int], sides: list[str], counterparts: list[list[int]]
) -> dict[str, Any]:
    return {
        "document_type_slug": LICENSE,
        "pages": pages,
        "sides": sides,
        "contiguity_violation": {
            "rule": "R6",
            "queue": "unresolved",
            "counterparts": counterparts,
            "intervening_pages": [1, 2, 3, 4],
            "unanalyzed_pages": [],
        },
    }


@pytest.mark.parametrize("third_page_known", [True, False], ids=["bilinen-tur", "katalog-disi"])
def test_s3_license_pieces_go_to_unresolved_with_reason(
    session: Session, layout: DataLayout, tmp_path: Path, third_page_known: bool
) -> None:
    # S3: 6 sayfalık PDF — ehliyet ön, foto, başka belge, oturum ön, oturum arka, ehliyet arka.
    # Beklenen: oturum izni (4-5) ve foto (2) aday; ehliyet 1 ve 6 Unresolved (R6); sayfa 3
    # türüne göre (katalog türü ya da aday tür) kendi yolunda.
    pdf = make_text_pdf_bytes(
        ["EHLIYET ON", "FOTOGRAF", "BASKA BELGE", "OTURUM ON", "OTURUM ARKA", "EHLIYET ARKA"]
    )
    upload = _upload(session, layout, [("belgeler.pdf", pdf)])
    if third_page_known:
        provider = RecordingProvider.from_directory(S3_RECORDINGS)
    else:
        responses = [
            json.loads((S3_RECORDINGS / f"{number}.json").read_text(encoding="utf-8"))
            for number in range(6)
        ]
        responses[2] = _payload(
            2, None, candidate_type_name="Peruvian Diploma", person=NO_PERSON, fields={}
        )
        provider = _recordings(tmp_path, responses)
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    grouping = group_upload(session, upload, catalog=CATALOG)

    file_id = upload.files[0].id
    (file_grouping,) = grouping.files
    assert _layout(file_grouping) == [(0,), (1,), (2,), (3, 4), (5,)]
    license_front, photo, other, residence, license_back = file_grouping.candidates
    assert (photo.document_type_slug, residence.document_type_slug) == (PHOTO, RESIDENCE)
    assert residence.sides == (Side.FRONT, Side.BACK)
    assert (other.document_type_slug is not None) is third_page_known
    for candidate in (photo, other, residence):
        assert candidate.contiguity_violation is None
    front_violation = license_front.contiguity_violation
    back_violation = license_back.contiguity_violation
    assert front_violation == ContiguityViolation(
        pages=(0,), counterparts=((5,),), intervening_pages=(1, 2, 3, 4)
    )
    assert back_violation == ContiguityViolation(
        pages=(5,), counterparts=((0,),), intervening_pages=(1, 2, 3, 4)
    )
    assert "(R6)" in front_violation.reason
    assert "bu parça (sayfa 1)" in front_violation.reason
    assert "bu parça (sayfa 6)" in back_violation.reason

    determined = _events(session, EventType.DOC_TYPE_DETERMINED)
    by_page = {event.page_index: event for event in determined}
    assert sorted(by_page) == ([0, 1, 2, 3, 5] if third_page_known else [0, 1, 3, 5])
    assert all(event.file_id == file_id for event in determined)
    assert by_page[0].data_json == _piece_event_data([0], ["front"], [[5]])
    assert by_page[5].data_json == _piece_event_data([5], ["back"], [[0]])
    assert (by_page[0].message, by_page[5].message) == (
        front_violation.reason,
        back_violation.reason,
    )
    assert by_page[3].data_json == {
        "document_type_slug": RESIDENCE,
        "pages": [3, 4],
        "sides": ["front", "back"],
    }
    assert by_page[1].message is None and by_page[3].message is None
    unknown = _events(session, EventType.DOC_TYPE_UNKNOWN)
    if third_page_known:
        assert not unknown
        assert by_page[2].data_json == {
            "document_type_slug": PERMIT,
            "pages": [2],
            "sides": ["single"],
        }
    else:
        assert [(event.page_index, event.message) for event in unknown] == [(2, None)]
        assert "contiguity_violation" not in unknown[0].data_json
    logged = json.dumps(
        [(event.data_json, event.message) for event in (*determined, *unknown)],
        ensure_ascii=False,
    )
    for value in S3_PERSONAL_VALUES:
        assert value not in logged


def test_pieces_in_different_files_are_not_judged_by_contiguity(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Ardışıklık dosyadaki sayfa sırasıdır; başka dosyadaki eşle dosyalar arası gruplama (04.3)
    # eşleştirir.
    upload = _upload(
        session,
        layout,
        [
            ("on.pdf", make_text_pdf_bytes(["ON YUZ", "FOTOGRAF"])),
            ("arka.pdf", make_text_pdf_bytes(["ARKA YUZ"])),
        ],
    )
    responses = [
        _payload(0, LICENSE, side="front"),
        _payload(1, PHOTO, person=NO_PERSON, fields={}),
        _payload(0, LICENSE, side="back", person=NO_PERSON),
    ]
    analyze_upload(
        session,
        layout,
        upload,
        provider=_recordings(tmp_path, responses),
        instructions=INSTRUCTIONS,
    )

    grouping = group_upload(session, upload, catalog=CATALOG)

    front_file, back_file = upload.files
    assert [_layout(file_grouping) for file_grouping in grouping.files] == [[(1,)], []]
    (card,) = grouping.cross_file_candidates
    assert _refs(card) == [(front_file.id, 0), (back_file.id, 0)]
    assert all(candidate.contiguity_violation is None for candidate in grouping.candidates)
    events = _events(session, EventType.DOC_TYPE_DETERMINED)
    assert [(event.file_id, event.page_index) for event in events] == [
        (front_file.id, 1),
        (front_file.id, 0),
    ]
    assert all("contiguity_violation" not in event.data_json for event in events)


S5_RECORDINGS = RECORDINGS / "s5_front_back_images"
S5_PERSONAL_VALUES = ("SIDOROV", "IVAN", "1985-05-05", "000123456", "2031-06-30")


def _recording(directory: Path, number: int) -> dict[str, Any]:
    return json.loads((directory / f"{number}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("back_uploaded_first", [False, True], ids=["on-once", "arka-once"])
def test_s5_front_and_back_images_form_one_driving_license_candidate(
    session: Session, layout: DataLayout, tmp_path: Path, back_uploaded_first: bool
) -> None:
    # S5: aynı partide `on.jpg` ve `arka.jpg` ehliyet (Direkt Belge kapalı) → tek Driving License
    # adayı, önce ön sonra arka yüz. Kayıpsız sarma ve birleştirme işlem seçimi (06.2) ve
    # uygulayıcının (07.3, 07.4) işidir.
    entry = CATALOG.get(LICENSE)
    assert entry is not None and not entry.direct and entry.file_label == "Driving License"
    front = ("on.jpg", make_half_filled_image_bytes("JPEG", size=(300, 190)))
    back = ("arka.jpg", make_half_filled_image_bytes("JPEG", size=(310, 195)))
    if back_uploaded_first:
        upload = _upload(session, layout, [back, front])
        responses = [_recording(S5_RECORDINGS, 1), _recording(S5_RECORDINGS, 0)]
        provider = _recordings(tmp_path, responses)
        back_file, front_file = upload.files
    else:
        upload = _upload(session, layout, [front, back])
        provider = RecordingProvider.from_directory(S5_RECORDINGS)
        front_file, back_file = upload.files
    analyze_upload(session, layout, upload, provider=provider, instructions=INSTRUCTIONS)

    grouping = group_upload(session, upload, catalog=CATALOG)

    assert all(file_grouping.candidates == () for file_grouping in grouping.files)
    (card,) = grouping.candidates
    assert grouping.cross_file_candidates == (card,)
    assert _refs(card) == [(front_file.id, 0), (back_file.id, 0)]
    assert card.document_type_slug == LICENSE
    assert card.sides == (Side.FRONT, Side.BACK)
    assert (card.contiguity_violation, card.ambiguous_pairing) == (None, None)
    (determined,) = _events(session, EventType.DOC_TYPE_DETERMINED)
    assert (determined.upload_id, determined.file_id, determined.page_index) == (
        UPLOAD_ID,
        front_file.id,
        0,
    )
    assert determined.message is None
    assert determined.data_json == {
        "document_type_slug": LICENSE,
        "sources": [
            {"file_id": front_file.id, "pages": [0]},
            {"file_id": back_file.id, "pages": [0]},
        ],
        "sides": ["front", "back"],
    }
    assert not _events(session, EventType.DOC_TYPE_UNKNOWN)
    logged = json.dumps(determined.data_json)
    for value in S5_PERSONAL_VALUES:
        assert value not in logged


def _ambiguity_event_data(
    side: str, fronts: list[int], backs: list[int], unanalyzed: list[tuple[int, int]]
) -> dict[str, Any]:
    return {
        "document_type_slug": LICENSE,
        "pages": [0],
        "sides": [side],
        "ambiguous_pairing": {
            "queue": "unresolved",
            "fronts": [{"file_id": file_id, "page_index": 0} for file_id in fronts],
            "backs": [{"file_id": file_id, "page_index": 0} for file_id in backs],
            "unoriented_pages": [],
            "unanalyzed_pages": [
                {"file_id": file_id, "page_index": index} for file_id, index in unanalyzed
            ],
            "uncertain_type_pages": [],
        },
    }


def test_several_license_fronts_in_a_batch_go_to_unresolved_with_reason(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # 04.3.2: iki kişinin ehliyet ön yüzü ve tek arka yüz aynı partide — hangi ön yüzün arka yüzle
    # aynı karta ait olduğu bilinemez; eşleştirme yapılmaz, üç yüz de gerekçesiyle Unresolved'a.
    other_person = {
        "surname": "DENEMEVA",
        "given_names": "ORNEK",
        "original_script_name": None,
        "date_of_birth": "1991-02-02",
        "document_number": "00 0000002",
    }
    upload = _upload(
        session,
        layout,
        [
            ("on-1.jpg", make_half_filled_image_bytes("JPEG", size=(300, 190))),
            ("on-2.jpg", make_half_filled_image_bytes("JPEG", size=(310, 195))),
            ("arka.jpg", make_half_filled_image_bytes("JPEG", size=(320, 200))),
        ],
    )
    responses = [
        _payload(0, LICENSE, side="front"),
        _payload(0, LICENSE, side="front", person=other_person),
        _payload(0, LICENSE, side="back", person=NO_PERSON),
    ]
    analyze_upload(
        session,
        layout,
        upload,
        provider=_recordings(tmp_path, responses),
        instructions=INSTRUCTIONS,
    )

    grouping = group_upload(session, upload, catalog=CATALOG)

    first, second, back = (upload_file.id for upload_file in upload.files)
    assert grouping.cross_file_candidates == ()
    expected = [
        AmbiguousPairing(
            face=PageRef(file_id, 0),
            fronts=(PageRef(first, 0), PageRef(second, 0)),
            backs=(PageRef(back, 0),),
        )
        for file_id in (first, second, back)
    ]
    assert [candidate.ambiguous_pairing for candidate in grouping.candidates] == expected
    determined = _events(session, EventType.DOC_TYPE_DETERMINED)
    assert [(event.file_id, event.page_index, event.message) for event in determined] == [
        (ambiguity.face.file_id, 0, ambiguity.reason) for ambiguity in expected
    ]
    assert [event.data_json for event in determined] == [
        _ambiguity_event_data(side, [first, second], [back], [])
        for side in ("front", "front", "back")
    ]
    logged = json.dumps(
        [(event.data_json, event.message) for event in determined], ensure_ascii=False
    )
    for value in (
        SYNTHETIC_SURNAME,
        SYNTHETIC_DOCUMENT_NUMBER,
        "1990-01-01",
        "DENEMEVA",
        "00 0000002",
        "1991-02-02",
    ):
        assert value not in logged


def test_failed_page_analysis_in_the_batch_keeps_faces_unpaired(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Analizi başarısız fotoğraf aslında başka bir ehliyetin yüzü olabilir (parti `partial`);
    # eşleştirme tahmin olurdu, yüzler gerekçesiyle Unresolved'a gider.
    upload = _upload(
        session,
        layout,
        [
            ("on.jpg", make_half_filled_image_bytes("JPEG", size=(300, 190))),
            ("arka.jpg", make_half_filled_image_bytes("JPEG", size=(310, 195))),
            ("foto.jpg", make_half_filled_image_bytes("JPEG", size=(320, 200))),
        ],
    )
    broken = _payload(0, PHOTO, person=NO_PERSON, fields={})
    del broken["side"]
    responses = [_recording(S5_RECORDINGS, 0), _recording(S5_RECORDINGS, 1), broken]
    result = analyze_upload(
        session,
        layout,
        upload,
        provider=_recordings(tmp_path, responses),
        instructions=INSTRUCTIONS,
    )
    assert result.is_partial

    grouping = group_upload(session, upload, catalog=CATALOG)

    front, back, photo = (upload_file.id for upload_file in upload.files)
    assert grouping.cross_file_candidates == ()
    assert grouping.files[2].unanalyzed_pages == (0,)
    determined = _events(session, EventType.DOC_TYPE_DETERMINED)
    assert [event.data_json for event in determined] == [
        _ambiguity_event_data(side, [front], [back], [(photo, 0)]) for side in ("front", "back")
    ]
    assert all("Analizi yapılamamış sayfalar" in (event.message or "") for event in determined)
    logged = json.dumps(
        [(event.data_json, event.message) for event in determined], ensure_ascii=False
    )
    for value in S5_PERSONAL_VALUES:
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
