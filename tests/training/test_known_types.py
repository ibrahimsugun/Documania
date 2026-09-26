"""11.9 — bilinen türler: katalog ∪ hazır önerilen tür kaydı (PLAN.md §C86 "Önerilen tür kaydı").

Önerilen tür kaydı yalnız tür adları taşır; testlerde kişi verisi yoktur."""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.catalog import import_catalog, load_seed_catalog, validate_catalog
from app.catalog.schema import Catalog
from app.db.models import KnownDocumentType
from app.training import (
    CATALOG_KINDS,
    KnownTypes,
    KnownTypeSource,
    SuggestedTypeRow,
    SuggestedTypesError,
    build_known_types,
    load_known_types,
    load_suggested_types,
    normalize_type_name,
    parse_suggested_types,
)
from app.training.known_types import (
    SUGGESTED_TYPES_COLUMNS,
    SUGGESTED_TYPES_PACKAGE,
    SUGGESTED_TYPES_RESOURCE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = load_seed_catalog()
HEADER = ",".join(SUGGESTED_TYPES_COLUMNS)


def _csv(*rows: str, header: str = HEADER) -> str:
    return "\n".join((header, *rows)) + "\n"


def _row(slug: str, name: str, label: str, iso3: str = "", iso2: str = "", kind: str = "diger"):
    return SuggestedTypeRow(slug, name, label, iso3 or None, iso2 or None, kind)


def _catalog_with(*records: dict) -> Catalog:
    return validate_catalog([*(entry.model_dump(mode="json") for entry in SEED), *records])


def _record(slug: str, name: str, country: str | None) -> dict:
    record = SEED.get("turkish_passport").model_dump(mode="json")
    return {**record, "slug": slug, "name": name, "country": country}


# --- paketle gelen kayıt -------------------------------------------------------------------------


def test_the_shipped_register_has_484_unique_types() -> None:
    rows = load_suggested_types()

    assert len(rows) == 484
    assert len({row.slug for row in rows}) == 484
    # 29 satırda ISO2 yok: toplayıcının bölge kodları (`EU`, `INT`, `KKTC`).
    no_iso2 = [row for row in rows if row.country_iso2 is None]
    assert len(no_iso2) == 29
    assert {row.country_iso3 for row in no_iso2} == {"EU", "INT", "KKTC"}
    assert all(row.country_iso3 for row in rows)
    assert {"pasaport", "kimlik_karti", "ehliyet", "oturum_izni", "vize"} <= {
        row.doc_kind for row in rows
    }


def test_the_register_is_read_as_utf8_sig_with_its_source_comment() -> None:
    raw = (REPO_ROOT / "app" / "catalog" / SUGGESTED_TYPES_RESOURCE).read_bytes()
    text = raw.decode("utf-8-sig")

    assert raw.startswith(b"\xef\xbb\xbf")
    # Kaynak ve tarih yorumu başta durur; başlık yorumdan sonraki ilk satırdır.
    assert text.startswith("# Hazır önerilen tür kaydı")
    assert "2026-09-23" in text.splitlines()[0]
    first_data = next(line for line in text.splitlines() if not line.startswith("#"))
    assert first_data.split(",") == list(SUGGESTED_TYPES_COLUMNS)


def test_the_register_ships_as_package_data() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert (
        SUGGESTED_TYPES_RESOURCE
        in (pyproject["tool"]["setuptools"]["package-data"][SUGGESTED_TYPES_PACKAGE])
    )
    assert resources.files(SUGGESTED_TYPES_PACKAGE).joinpath(SUGGESTED_TYPES_RESOURCE).is_file()


# --- ayrıştırma ----------------------------------------------------------------------------------


def test_comments_and_bom_are_skipped_and_empty_countries_are_none() -> None:
    text = "﻿# yorum\n# ikinci yorum\n" + _csv(
        "eu_visa,Eu Visa,Visa,EU,,vize,0,1,",
        "afghan_passport,Afghan Passport,Passport,AFG,AF,pasaport,1,0,KnownDocuments/x/",
    )

    assert parse_suggested_types(text) == (
        SuggestedTypeRow("eu_visa", "Eu Visa", "Visa", "EU", None, "vize"),
        SuggestedTypeRow("afghan_passport", "Afghan Passport", "Passport", "AFG", "AF", "pasaport"),
    )


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        (_csv("a,A,B,AFG,AF,pasaport,0,0,", header="slug,ad"), "sütunları"),
        (_csv("Bad-Slug,A,B,AFG,AF,pasaport,0,0,"), "satır 2: geçersiz slug"),
        (_csv("a,,B,AFG,AF,pasaport,0,0,"), "ad ya da dosya etiketi boş"),
        (_csv("a,A,,AFG,AF,pasaport,0,0,"), "ad ya da dosya etiketi boş"),
        (_csv("a,A,B,AFG,AF,,0,0,"), "geçersiz kaynak_tur"),
        (_csv("a,A,B,afg,AF,pasaport,0,0,"), "geçersiz country_iso3"),
        (_csv("a,A,B,AFG,AFG,pasaport,0,0,"), "geçersiz country_iso2"),
        (_csv("a,A,B,AFG,AF,pasaport,0,0,,fazla"), "sütun sayısı"),
        (
            _csv("a,A,B,AFG,AF,pasaport,0,0,", "b,B,B,AFG,AF,vize,0,0,", "a,C,C,AFG,AF,vize,0,0,"),
            "satır 4: slug tekrarlanıyor",
        ),
    ],
)
def test_a_malformed_register_is_rejected_with_its_line(text: str, problem: str) -> None:
    with pytest.raises(SuggestedTypesError, match=problem):
        parse_suggested_types(text)


# --- birleşim ------------------------------------------------------------------------------------


def test_known_types_are_the_catalog_plus_the_suggested_register(known: KnownTypes) -> None:
    assert len(known) == len(SEED) + 484
    assert [known_type.slug for known_type in known] == sorted(
        [*SEED.slugs(), *(row.slug for row in load_suggested_types())]
    )
    passport = known.get("turkish_passport")
    assert passport is not None and passport.in_catalog
    assert passport.entry == SEED.get("turkish_passport")
    suggested = known.get("albanian_passport")
    assert suggested is not None and suggested.source is KnownTypeSource.SUGGESTED
    assert suggested.entry is None
    assert (suggested.name, suggested.file_label) == ("Albanian Passport", "Passport")
    assert (suggested.country_iso3, suggested.country_iso2, suggested.doc_kind) == (
        "ALB",
        "AL",
        "pasaport",
    )
    assert "albanian_passport" in known and "not_a_type" not in known
    assert known.get("not_a_type") is None


def test_the_catalog_wins_a_slug_collision_and_keeps_the_suggested_name_as_alias() -> None:
    suggested = [
        _row("turkish_passport", "Turkish Old Passport", "Old Passport", "TUR", "TR", "vize"),
        _row("albanian_passport", "Albanian Passport", "Passport", "ALB", "AL", "pasaport"),
    ]

    known = build_known_types(SEED, suggested)

    assert len(known) == len(SEED) + 1
    passport = known.get("turkish_passport")
    assert passport is not None and passport.source is KnownTypeSource.CATALOG
    assert (passport.name, passport.file_label, passport.country_iso2) == (
        "Turkish Passport",
        "Passport",
        "TR",
    )
    # Açık eşleme önerilen satırın çiftini de ezer.
    assert (passport.country_iso3, passport.doc_kind) == ("TUR", "pasaport")
    assert known.match_kind("TUR", "vize") is None
    assert known.match_name("Turkish Old Passport") == passport
    assert known.match_name("Turkish Passport") == passport


def test_an_approved_type_on_a_suggested_slug_inherits_its_country_and_kind() -> None:
    # Onaylanan aday tür (§C85) önerilen slug'ı taşır ve kataloğa girer: MRZ ile tanıma (tm 116)
    # için (ülke, tür) çifti önerilen satırdan gelir.
    catalog = _catalog_with(_record("albanian_passport", "Albanian National Passport", "AL"))

    known = build_known_types(catalog)
    albanian = known.get("albanian_passport")

    assert albanian is not None and albanian.in_catalog
    assert albanian.name == "Albanian National Passport"
    assert (albanian.country_iso3, albanian.doc_kind) == ("ALB", "pasaport")
    assert known.match_kind("ALB", "pasaport") == albanian
    assert known.match_name("Albanian Passport") == albanian
    assert known.match_name("Albanian National Passport") == albanian
    assert len(known) == len(SEED) + 484


def test_catalog_types_carry_the_explicit_country_and_kind(known: KnownTypes) -> None:
    assert dict(CATALOG_KINDS) == {
        "russian_passport": ("RUS", "pasaport"),
        "serbian_driving_license": ("SRB", "ehliyet"),
        "serbian_passport": ("SRB", "pasaport"),
        "serbian_residence_card": ("SRB", "oturum_izni"),
        "turkish_passport": ("TUR", "pasaport"),
    }
    assert set(CATALOG_KINDS) <= set(SEED.slugs())
    assert {kind for _, kind in CATALOG_KINDS.values()} <= known.doc_kinds
    for slug, (iso3, kind) in CATALOG_KINDS.items():
        assert known.match_kind(iso3, kind) == known.get(slug)
    for slug in ("work_permit", "profile_picture", "attachment"):
        catalog_type = known.get(slug)
        assert catalog_type is not None
        assert (catalog_type.country_iso3, catalog_type.doc_kind) == (None, None)


def test_the_doc_kind_vocabulary_is_closed(known: KnownTypes) -> None:
    assert known.doc_kinds == {row.doc_kind for row in load_suggested_types()}
    assert len(known.doc_kinds) == 22


# --- eşleşme -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Albanian Passport", "albanian_passport"),
        ("  ALBANIAN   passport ", "albanian_passport"),
        ("Algerian Driving Licence", "algerian_driving_license"),
        ("algerian driving LICENCE", "algerian_driving_license"),
        ("Serbian Driving Licence", "serbian_driving_license"),
        ("Turkish Passport", "turkish_passport"),
        ("Eu Passport", "eu_passport"),
    ],
)
def test_names_match_after_normalization(known: KnownTypes, name: str, slug: str) -> None:
    matched = known.match_name(name)

    assert matched is not None and matched.slug == slug


@pytest.mark.parametrize(
    "name",
    [
        # İki slug'a iner (`turkish_driving_license`, `turkish_international_driving_permit`).
        "Turkish Driving License",
        "Turkish Driving Licence",
        "Martian Passport",
        "",
        "Passport",
    ],
)
def test_ambiguous_or_unknown_names_do_not_match(known: KnownTypes, name: str) -> None:
    assert known.match_name(name) is None


def test_name_normalization() -> None:
    assert normalize_type_name("  Serbian\tDriving   LICENCE ") == "serbian driving license"
    assert normalize_type_name("Licences") == "licenses"


@pytest.mark.parametrize(
    ("country", "kind", "slug"),
    [
        ("ALB", "pasaport", "albanian_passport"),
        (" alb ", " pasaport ", "albanian_passport"),
        ("RUS", "pasaport", "russian_passport"),
        ("SRB", "ehliyet", "serbian_driving_license"),
        ("KKTC", "kimlik_karti", "northern_cyprus_identity_card"),
    ],
)
def test_country_and_kind_match_a_single_type(
    known: KnownTypes, country: str, kind: str, slug: str
) -> None:
    matched = known.match_kind(country, kind)

    assert matched is not None and matched.slug == slug


@pytest.mark.parametrize(
    ("country", "kind"),
    [
        # İki slug'a inen çiftler belirsizdir: tahmin edilmez.
        ("RUS", "kimlik_karti"),
        ("TUR", "ehliyet"),
        ("QQQ", "pasaport"),
        ("ALB", "uzay_belgesi"),
    ],
)
def test_ambiguous_or_unknown_pairs_do_not_match(
    known: KnownTypes, country: str, kind: str
) -> None:
    assert known.match_kind(country, kind) is None


# --- veritabanındaki katalog ---------------------------------------------------------------------


def test_known_types_read_the_catalog_from_the_database(session: Session) -> None:
    import_catalog(session, SEED)
    session.get(KnownDocumentType, "turkish_passport").name = "Turkish Biometric Passport"
    session.flush()

    known = load_known_types(session)

    assert len(known) == len(SEED) + 484
    passport = known.get("turkish_passport")
    assert passport is not None and passport.name == "Turkish Biometric Passport"
    assert known.match_name("Turkish Biometric Passport") == passport
