"""K8 adlandırma — `Ad_Soyad_E0001`, `Ad_Soyad-Belge-Turu.pdf`, `-2`/`-3` ekleri."""

import pytest

from app.storage.naming import (
    NAME_SLUG_MAX_LENGTH,
    document_stem,
    employee_folder_name,
    normalize_extension,
    person_slug,
    sequenced_filename,
    sequenced_stem,
    split_document_filename,
)


def test_employee_folder_name_follows_k8() -> None:
    assert employee_folder_name("Ahmet", "Çakar", "E0001") == "Ahmet_Cakar_E0001"
    assert employee_folder_name("DMITRII", "VASILEV", "E0042") == "Dmitrii_Vasilev_E0042"
    assert employee_folder_name("Дмитрий", "Васильев", "E10000") == "Dmitrii_Vasilev_E10000"
    assert employee_folder_name("فاطمة", "حسن", "E0007") == "Fatma_Hsn_E0007"


@pytest.mark.parametrize("number", ["0001", "E001", "e0001", "E0001 ", "E00a1", "../E0001"])
def test_employee_folder_name_rejects_invalid_number(number: str) -> None:
    with pytest.raises(ValueError, match="çalışan numarası"):
        employee_folder_name("Ahmet", "Çakar", number)


def test_hyphen_in_name_does_not_collide_with_label_separator() -> None:
    assert person_slug("Anna-Maria", "Smith") == "Anna_Maria_Smith"
    assert document_stem("Anna-Maria", "Smith", "Passport") == "Anna_Maria_Smith-Passport"


def test_document_stem_follows_k8() -> None:
    assert document_stem("Ahmet", "Çakar", "Residence Card") == "Ahmet_Cakar-Residence-Card"
    assert document_stem("DMITRII", "VASILEV", "Passport") == "Dmitrii_Vasilev-Passport"


def test_person_slug_is_length_bounded() -> None:
    slug = person_slug("Mohammed " * 20, "Al Saud")
    assert len(slug) <= NAME_SLUG_MAX_LENGTH
    assert slug.startswith("Mohammed_")


def test_sequence_suffix_starts_at_second_document() -> None:
    stem = "Ahmet_Cakar-Passport"
    assert sequenced_filename(stem, 1, "pdf") == "Ahmet_Cakar-Passport.pdf"
    assert sequenced_filename(stem, 2, "pdf") == "Ahmet_Cakar-Passport-2.pdf"
    assert sequenced_filename(stem, 3, ".PDF") == "Ahmet_Cakar-Passport-3.pdf"


@pytest.mark.parametrize("sequence_no", [0, -1])
def test_sequence_number_must_be_positive(sequence_no: int) -> None:
    with pytest.raises(ValueError, match="Sıra numarası"):
        sequenced_stem("Ahmet_Cakar-Passport", sequence_no)


@pytest.mark.parametrize("stem", ["", "../x", "a/b", "a.b", "-x", "Ad Soyad"])
def test_invalid_stem_rejected(stem: str) -> None:
    with pytest.raises(ValueError, match="gövdesi"):
        sequenced_stem(stem, 1)


def test_extension_normalized() -> None:
    assert normalize_extension("JPEG") == "jpeg"
    assert normalize_extension(".docx") == "docx"


@pytest.mark.parametrize("extension", ["", ".", "p/df", "pdf.", "tar.gz", "averyverylongext"])
def test_invalid_extension_rejected(extension: str) -> None:
    with pytest.raises(ValueError, match="uzantısı"):
        normalize_extension(extension)


def test_planned_target_name_splits_into_stem_and_extension() -> None:
    assert split_document_filename("Ahmet_Cakar-Residence-Card.pdf") == (
        "Ahmet_Cakar-Residence-Card",
        "pdf",
    )
    assert split_document_filename("Ahmet_Cakar-Profile-Picture.jpeg") == (
        "Ahmet_Cakar-Profile-Picture",
        "jpeg",
    )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("Ahmet_Cakar-Passport", "uzantı yok"),
        ("../Ahmet_Cakar-Passport.pdf", "gövdesi"),
        ("Ahmet Cakar-Passport.pdf", "gövdesi"),
        (".pdf", "gövdesi"),
        ("Ahmet_Cakar-Passport.p/df", "uzantısı"),
    ],
)
def test_invalid_target_name_rejected(name: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        split_document_filename(name)
