"""06.5.1 — `required_fields`, `page_count`, `sides`, `direct_single_source`, `file_type`,
`mrz_checksum` ve `dob_plausible` doğrulayıcıları çalışır: her biri geçen ve kalan örneklerle,
karar tablolarının (§20.1.6, §20.1.7) sınır durumlarıyla sınanır. Doğrulamanın plana bağlanışı
(06.5.2: rota, gerekçe, olay) `tests/pipeline/test_plan.py`'dedir.

Analizler sentetik sözlüklerdir; MRZ satırları kontrol haneleri hesaplanarak `make_mrz` ile
üretilir. Gerçek kişi ya da belge yok (CONVENTIONS §6).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import pytest

from app.ai import PageAnalysis
from app.ai.schemas import Side
from app.catalog import CatalogEntry, FileType, load_seed_catalog
from app.db.models import QueueKind
from app.matching.mrz import MrzFormat
from app.pipeline.group import (
    CandidatePage,
    DocumentCandidate,
    GroupingPage,
    PageCountViolation,
    PageRef,
    group_across_files,
    group_file_pages,
)
from app.pipeline.legibility import IllegibleRequiredFields, check_legibility
from app.pipeline.plan import OperationSource, check_direct_file_types
from app.pipeline.validate import (
    MAX_AGE,
    MIN_AGE,
    DirectSourceNotSingle,
    FileTypeMismatch,
    ImplausibleDateOfBirth,
    MrzChecksumFailure,
    MrzPageFailure,
    SidesMismatch,
    Validation,
    ValidationName,
    check_direct_single_source,
    check_dob_plausible,
    check_file_type,
    check_mrz_checksum,
    check_page_count,
    check_required_fields,
    check_sides,
    file_types_text,
    unexpected_file_types,
)
from app.storage import FileKind
from tests.ai.payloads import analysis_payload
from tests.matching.test_mrz import make_mrz

CATALOG = load_seed_catalog()
TODAY = date(2026, 9, 15)
FILE_ID = 7

PASSPORT = "russian_passport"  # direct, single, pdf/jpeg
LICENSE = "serbian_driving_license"  # front_back, 2 sayfa
PERMIT = "work_permit"  # direct değil, pdf/jpeg/png
REQUIRED = ("surname", "given_names", "date_of_birth", "document_number", "expiry_date")
FRONT, BACK, SINGLE, UNKNOWN = Side.FRONT, Side.BACK, Side.SINGLE, Side.UNKNOWN
PDF, JPEG, PNG, DOCX = FileKind.PDF, FileKind.JPEG, FileKind.PNG, FileKind.DOCX

# Kontrol haneleri geçerli, kurgusal TD3 MRZ (Utopia); isteğe bağlı veri tümüyle dolgu.
VALID_TD3 = make_mrz(MrzFormat.TD3)


def _entry(slug: str, **changes: Any) -> CatalogEntry:
    entry = CATALOG.get(slug)
    assert entry is not None
    return CatalogEntry.model_validate({**entry.model_dump(mode="json"), **changes})


def _analysis(
    slug: str = PASSPORT,
    side: Side = SINGLE,
    *,
    mrz: list[str] | None = None,
    illegible: Iterable[str] = (),
    **top: Any,
) -> PageAnalysis:
    payload = analysis_payload(document_type_slug=slug, side=side.value, **top)
    payload["person"]["mrz_lines"] = mrz
    payload["fields"] = {
        name: {"value": None, "legible": False}
        if name in illegible
        else {"value": "OKUNDU", "legible": True}
        for name in REQUIRED
    }
    return PageAnalysis.model_validate(payload)


def _candidate(*pages: PageAnalysis | tuple[int, PageAnalysis]) -> DocumentCandidate:
    """Sayfalar verilen sırayla, dosyadaki sıraları 0'dan; `(file_id, analiz)` başka dosyadır."""
    built = []
    for index, page in enumerate(pages):
        file_id, analysis = page if isinstance(page, tuple) else (FILE_ID, page)
        built.append(CandidatePage(file_id, index, analysis))
    return DocumentCandidate(tuple(built))


def _grouped(*analyses: PageAnalysis) -> tuple[DocumentCandidate, ...]:
    # Sayfa sayısı dosyalar arası gruplamadan sonra işaretlenir (04.5.1).
    pages = [GroupingPage(index, analysis=analysis) for index, analysis in enumerate(analyses)]
    grouping = group_file_pages(FILE_ID, pages, catalog=CATALOG)
    return group_across_files([grouping], catalog=CATALOG).candidates


def _sides(slug: str, *sides: Side) -> DocumentCandidate:
    return _candidate(*(_analysis(slug, side) for side in sides))


def _source(
    kind: FileKind | None,
    pages: tuple[int, ...] = (0,),
    *,
    file_id: int = FILE_ID,
    file_pages: Iterable[int] | None = None,
    blank: Iterable[int] = (),
) -> OperationSource:
    return OperationSource(
        file_id=file_id,
        kind=kind,
        pages=pages,
        file_pages=frozenset(pages if file_pages is None else file_pages),
        blank_pages=frozenset(blank),
    )


def _mutated(lines: list[str], line: int, position: int, char: str) -> list[str]:
    changed = list(lines)
    row = changed[line - 1]
    changed[line - 1] = row[: position - 1] + char + row[position:]
    return changed


# --- ad ve sonuç -------------------------------------------------------------------------------


def test_validators_are_the_seven_of_06_5_1_in_its_order() -> None:
    assert [name.value for name in ValidationName] == [
        "required_fields",
        "page_count",
        "sides",
        "direct_single_source",
        "file_type",
        "mrz_checksum",
        "dob_plausible",
    ]


def test_validation_is_ok_only_without_a_failure() -> None:
    passed = Validation(ValidationName.SIDES)
    failed = Validation(ValidationName.DOB_PLAUSIBLE, ImplausibleDateOfBirth(future=True))

    assert (passed.ok, failed.ok) == (True, False)


# --- required_fields (K1) ----------------------------------------------------------------------


def test_required_fields_passes_when_every_required_field_is_legible() -> None:
    check = check_legibility(_candidate(_analysis()), catalog=CATALOG)

    assert check_required_fields(check) is None


def test_required_fields_fails_to_unreadable_with_the_illegible_field_names() -> None:
    check = check_legibility(
        _candidate(_analysis(illegible=("document_number", "surname"))), catalog=CATALOG
    )

    failure = check_required_fields(check)

    assert failure == IllegibleRequiredFields(("surname", "document_number"))
    assert failure.queue is QueueKind.UNREADABLE
    assert failure.reason == "Okunamayan alanlar: surname, document_number"


def test_required_fields_of_a_type_outside_the_catalog_is_not_judged() -> None:
    assert check_required_fields(None) is None


# --- page_count (04.5.1) -----------------------------------------------------------------------


def test_page_count_passes_inside_the_expected_range() -> None:
    (candidate,) = _grouped(_analysis())
    assert check_page_count(candidate) is None


def test_page_count_fails_outside_the_expected_range() -> None:
    # Ehliyetin yalnız ön yüzü: tür 2 sayfa bekler.
    (candidate,) = _grouped(_analysis(LICENSE, FRONT))
    failure = check_page_count(candidate)

    assert failure == PageCountViolation((PageRef(FILE_ID, 0),), expected_min=2, expected_max=2)
    assert failure.queue is QueueKind.UNRESOLVED


# --- sides (04.1.2) ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidate",
    [
        pytest.param(_sides(LICENSE, FRONT, BACK), id="front-then-back"),
        pytest.param(
            _candidate((1, _analysis(LICENSE, FRONT)), (2, _analysis(LICENSE, BACK))),
            id="faces-from-two-files",
        ),
        pytest.param(_sides(PASSPORT, SINGLE), id="single-sided-type"),
        pytest.param(_sides(PASSPORT, FRONT), id="single-sided-type-ignores-faces"),
    ],
)
def test_sides_passes_for_front_then_back_or_a_single_sided_type(
    candidate: DocumentCandidate,
) -> None:
    entry = _entry(candidate.document_type_slug or "")

    assert check_sides(candidate, entry=entry) is None


@pytest.mark.parametrize(
    "sides",
    [
        pytest.param((FRONT,), id="front-only"),
        pytest.param((BACK,), id="back-only"),
        pytest.param((BACK, FRONT), id="back-then-front"),
        pytest.param((SINGLE,), id="single"),
        pytest.param((UNKNOWN,), id="unknown"),
        pytest.param((FRONT, BACK, BACK), id="extra-back"),
        pytest.param((FRONT, FRONT), id="two-fronts"),
    ],
)
def test_sides_fails_when_a_front_back_type_is_not_front_then_back(
    sides: tuple[Side, ...],
) -> None:
    candidate = _sides(LICENSE, *sides)

    failure = check_sides(candidate, entry=_entry(LICENSE))

    pages = tuple(PageRef(FILE_ID, index) for index in range(len(sides)))
    assert failure == SidesMismatch(pages, sides)
    assert failure.queue is QueueKind.UNRESOLVED


def test_sides_reason_names_each_page_with_its_face() -> None:
    failure = check_sides(_sides(LICENSE, BACK, FRONT), entry=_entry(LICENSE))

    assert failure is not None
    assert failure.reason == (
        "Yüz doğrulaması (06.5.1, sides): tür önce bir ön, sonra bir arka yüz bekliyor (front, "
        "back); bu adayın yüzleri: dosya 7, sayfa 1: back; dosya 7, sayfa 2: front."
    )


# --- direct_single_source (K3, K5) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("slug", "sources"),
    [
        pytest.param(PASSPORT, [_source(PDF)], id="one-page"),
        pytest.param(PASSPORT, [_source(PDF, (1,), file_pages=range(3))], id="page-inside-a-file"),
        pytest.param(
            PASSPORT, [_source(PDF, (0, 2), file_pages=range(3), blank=(1,))], id="blank-between"
        ),
        pytest.param("attachment", [_source(DOCX, ())], id="whole-file"),
        pytest.param(
            LICENSE,
            [_source(JPEG), _source(PDF, (0, 2), file_id=8, file_pages=range(3))],
            id="not-direct",
        ),
    ],
)
def test_direct_single_source_passes_for_contiguous_pages_of_one_file_or_a_non_direct_type(
    slug: str, sources: list[OperationSource]
) -> None:
    assert check_direct_single_source(sources, entry=_entry(slug)) is None


@pytest.mark.parametrize(
    ("sources", "findings"),
    [
        pytest.param(
            [_source(PDF), _source(JPEG, file_id=8)],
            "belgenin sayfaları 2 kaynak dosyadan geliyor",
            id="two-files",
        ),
        pytest.param(
            [_source(PDF, (0, 2), file_pages=range(3))],
            "dosya 7, sayfa 1, 3 ardışık değil",
            id="page-between-is-not-blank",
        ),
        pytest.param(
            [_source(PDF, (0, 2), file_pages=range(3)), _source(PDF, (0, 1), file_id=8)],
            "belgenin sayfaları 2 kaynak dosyadan geliyor; dosya 7, sayfa 1, 3 ardışık değil",
            id="both",
        ),
    ],
)
def test_direct_single_source_fails_for_several_files_or_scattered_pages(
    sources: list[OperationSource], findings: str
) -> None:
    failure = check_direct_single_source(sources, entry=_entry(PASSPORT))

    assert isinstance(failure, DirectSourceNotSingle)
    assert failure.file_ids == tuple(source.file_id for source in sources)
    assert failure.queue is QueueKind.UNRESOLVED
    assert failure.reason == (
        "Direkt Belge tek kaynak doğrulaması (06.5.1, direct_single_source): çıktı tek kaynak "
        f"dosyanın ardışık sayfalarından oluşur (K3); {findings}."
    )


# --- file_type ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("slug", "sources"),
    [
        pytest.param(PERMIT, [_source(PDF)], id="pdf"),
        pytest.param(PERMIT, [_source(JPEG), _source(PNG, file_id=8)], id="jpeg-and-png"),
        pytest.param(PASSPORT, [_source(JPEG)], id="direct-jpeg"),
        pytest.param("attachment", [_source(DOCX, ())], id="word"),
    ],
)
def test_file_type_passes_when_every_source_is_an_expected_type(
    slug: str, sources: list[OperationSource]
) -> None:
    assert check_file_type(sources, entry=_entry(slug)) is None


@pytest.mark.parametrize(
    ("slug", "changes", "sources", "expected", "received"),
    [
        pytest.param(
            PERMIT, {"expected_file_types": ["pdf"]}, [_source(JPEG)], "pdf", "jpeg", id="jpeg"
        ),
        pytest.param(PERMIT, {}, [_source(None)], "pdf/jpeg/png", "tanınmayan biçim", id="unknown"),
        pytest.param(PASSPORT, {}, [_source(PNG)], "pdf/jpeg", "png", id="direct-type-too"),
        pytest.param(
            PERMIT,
            {"expected_file_types": ["pdf"]},
            [
                _source(PDF),
                _source(PNG, file_id=8),
                _source(None, file_id=9),
                _source(PNG, file_id=10),
            ],
            "pdf",
            "png/tanınmayan biçim",
            id="unexpected-types-once-in-source-order",
        ),
    ],
)
def test_file_type_fails_for_an_unexpected_or_unrecognized_type(
    slug: str,
    changes: dict[str, Any],
    sources: list[OperationSource],
    expected: str,
    received: str,
) -> None:
    entry = _entry(slug, **changes)

    failure = check_file_type(sources, entry=entry)

    assert isinstance(failure, FileTypeMismatch)
    assert failure.expected_file_types == entry.expected_file_types
    assert failure.queue is QueueKind.UNRESOLVED
    assert failure.reason == (
        f"Dosya türü doğrulaması (06.5.1, file_type): beklenen dosya türü {expected}, gelen "
        f"{received}. Uygun formatta yeniden gönderin."
    )


def test_direct_format_check_is_the_file_type_validation_of_a_direct_type() -> None:
    # §20.4.1 aynı biçimleri reddeder; yalnız gerekçesi Direkt Belge'nindir.
    sources = [_source(PDF), _source(PNG, file_id=8), _source(None, file_id=9)]
    entry = _entry(PASSPORT)

    direct = check_direct_file_types(sources, entry=entry)
    generic = check_file_type(sources, entry=entry)

    assert direct is not None and generic is not None
    assert direct.received == generic.received == unexpected_file_types(sources, entry=entry)
    assert direct.received == (FileType.PNG, None)
    assert file_types_text(direct.received) == "png/tanınmayan biçim"


# --- mrz_checksum (05.3.2, §20.1.7) ------------------------------------------------------------


@pytest.mark.parametrize(
    "mrz",
    [
        pytest.param(None, id="no-mrz"),
        pytest.param(VALID_TD3, id="valid-td3"),
        pytest.param(make_mrz(MrzFormat.TD2), id="valid-td2"),
        pytest.param(make_mrz(MrzFormat.TD1), id="valid-td1"),
        pytest.param(
            make_mrz(MrzFormat.TD3, checks={"optional_data": "<"}), id="padding-optional-check-<"
        ),
        pytest.param(
            make_mrz(MrzFormat.TD3, checks={"optional_data": "0"}), id="padding-optional-check-0"
        ),
        pytest.param([VALID_TD3[0], VALID_TD3[1][:-1]], id="unrecognized-shape-is-no-mrz"),
    ],
)
def test_mrz_checksum_passes_without_an_mrz_or_with_holding_check_digits(
    mrz: list[str] | None,
) -> None:
    assert check_mrz_checksum(_candidate(_analysis(mrz=mrz)), today=TODAY) is None


def test_mrz_checksum_does_not_count_a_conflict_with_the_visible_text() -> None:
    # §20.1.7: MRZ ile görünen metnin çelişkisi bilgi notudur, doğrulama hatası değildir.
    analysis = _analysis(mrz=VALID_TD3)

    assert analysis.person.surname != "ERIKSSON"
    assert check_mrz_checksum(_candidate(analysis), today=TODAY) is None


def test_mrz_of_a_page_read_as_unreadable_is_not_validated() -> None:
    # C21: kendini okunamaz veren sayfanın MRZ okumasına güvenilmez, doğrulayıcıya girmez.
    broken = _mutated(VALID_TD3, 2, 10, "0" if VALID_TD3[1][9] != "0" else "1")
    analysis = _analysis(mrz=broken, is_readable=False)

    assert check_mrz_checksum(_candidate(analysis), today=TODAY) is None


@pytest.mark.parametrize(
    ("mrz", "failed_checks"),
    [
        pytest.param(make_mrz(MrzFormat.TD3, composite="0"), ("composite",), id="composite"),
        pytest.param(
            make_mrz(MrzFormat.TD3, checks={"document_number": "0"}),
            ("document_number",),
            id="document-number-composite-holds",
        ),
        pytest.param(
            make_mrz(MrzFormat.TD3, checks={"expiry_date": "0"}),
            ("expiry_date",),
            id="expiry-date",
        ),
        pytest.param(
            _mutated(VALID_TD3, 2, 1, "M"), ("document_number", "composite"), id="misread-number"
        ),
        pytest.param(
            make_mrz(MrzFormat.TD3, optional="ZE184226B", checks={"optional_data": "5"}),
            ("optional_data",),
            id="optional-data",
        ),
        pytest.param(
            make_mrz(MrzFormat.TD1, checks={"date_of_birth": "0"}),
            ("date_of_birth",),
            id="td1-date-of-birth",
        ),
    ],
)
def test_mrz_checksum_fails_when_a_check_digit_does_not_hold(
    mrz: list[str], failed_checks: tuple[str, ...]
) -> None:
    failure = check_mrz_checksum(_candidate(_analysis(mrz=mrz)), today=TODAY)

    assert failure == MrzChecksumFailure((MrzPageFailure(PageRef(FILE_ID, 0), failed_checks),))
    assert failure.queue is QueueKind.UNRESOLVED


def test_mrz_with_a_disallowed_character_fails_because_its_digits_cannot_be_checked() -> None:
    # §20.1.2: izin verilmeyen karakter kalan MRZ geçersizdir.
    invalid = _mutated(VALID_TD3, 1, 10, "#")

    failure = check_mrz_checksum(_candidate(_analysis(mrz=invalid)), today=TODAY)

    assert failure == MrzChecksumFailure((MrzPageFailure(PageRef(FILE_ID, 0), invalid=True),))


def test_mrz_checksum_reason_names_only_the_failing_pages_and_check_digits() -> None:
    candidate = _candidate(
        _analysis(LICENSE, FRONT, mrz=VALID_TD3),
        _analysis(LICENSE, BACK, mrz=make_mrz(MrzFormat.TD1, composite="0")),
        (9, _analysis(LICENSE, BACK, mrz=_mutated(VALID_TD3, 1, 10, "#"))),
    )

    failure = check_mrz_checksum(candidate, today=TODAY)

    assert failure is not None
    assert failure.reason == (
        "MRZ kontrol hanesi doğrulaması (06.5.1, mrz_checksum): dosya 7, sayfa 2: tutmayan kontrol "
        "haneleri composite; dosya 9, sayfa 3: izin verilmeyen karakter var, kontrol haneleri "
        "doğrulanamadı. Kontrol hanesi tutmayan MRZ geçersiz sayılır."
    )
    assert "L898902C3" not in failure.reason and "ERIKSSON" not in failure.reason


# --- dob_plausible (§20.1.6) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("born", "today"),
    [
        pytest.param(None, TODAY, id="no-date-of-birth"),
        pytest.param(date(1990, 1, 1), TODAY, id="adult"),
        pytest.param(date(2010, 9, 15), TODAY, id="16th-birthday"),
        pytest.param(date(1935, 9, 16), TODAY, id="day-before-91st-birthday"),
        pytest.param(date(2008, 2, 29), date(2024, 2, 29), id="leap-day-16th-birthday"),
        pytest.param(date(2008, 2, 29), date(2025, 2, 28), id="leap-day-born-aged-16"),
    ],
)
def test_dob_plausible_passes_for_a_past_date_between_16_and_90_years(
    born: date | None, today: date
) -> None:
    assert check_dob_plausible(born, today=today) is None


@pytest.mark.parametrize(
    ("born", "today", "future"),
    [
        pytest.param(date(2026, 9, 16), TODAY, True, id="tomorrow"),
        pytest.param(TODAY, TODAY, True, id="today"),
        pytest.param(date(2010, 9, 16), TODAY, False, id="day-before-16th-birthday"),
        pytest.param(date(1935, 9, 15), TODAY, False, id="91st-birthday"),
        pytest.param(date(2025, 1, 1), TODAY, False, id="mrz-century-too-late"),
        pytest.param(date(1925, 1, 1), TODAY, False, id="mrz-century-too-early"),
        pytest.param(date(2008, 2, 29), date(2024, 2, 28), False, id="leap-day-born-aged-15"),
    ],
)
def test_dob_plausible_fails_for_a_date_not_in_the_past_or_outside_16_to_90_years(
    born: date, today: date, future: bool
) -> None:
    failure = check_dob_plausible(born, today=today)

    assert failure == ImplausibleDateOfBirth(future=future)
    assert failure.queue is QueueKind.UNRESOLVED


def test_dob_plausible_reason_carries_neither_the_date_nor_the_age() -> None:
    assert (MIN_AGE, MAX_AGE) == (16, 90)
    assert ImplausibleDateOfBirth(future=True).reason == (
        "Doğum tarihi doğrulaması (06.5.1, dob_plausible): okunan doğum tarihi geçmişte değil; "
        "tarih yanlış okunmuş olabilir."
    )
    assert ImplausibleDateOfBirth(future=False).reason == (
        "Doğum tarihi doğrulaması (06.5.1, dob_plausible): okunan doğum tarihi referans güne göre "
        "16–90 yaş aralığı dışında; tarih yanlış okunmuş olabilir."
    )
