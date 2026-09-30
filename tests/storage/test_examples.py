"""11.2.1 — belge türü örnekleri: yalnız PDF/JPEG/PNG, içerik imzasıyla tür, güvenli ad, aynı içerik
bir kez, baytlar değişmez, çalışan verisinden ayrı dizin.

Veri sentetiktir (`tests/fixtures/gen.py`); gerçek kimlik belgesi yoktur."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.storage import DataLayout, FileKind, prepare_data_dir
from app.storage.examples import (
    ExampleRejectedError,
    StoredExample,
    check_example,
    example_path,
    list_examples,
    store_example,
)
from tests.fixtures.gen import (
    make_docx_bytes,
    make_owner_locked_pdf_bytes,
    make_pdf_bytes,
    make_portrait_image_bytes,
    make_sized_pdf_bytes,
)

SLUG = "russian_passport"
LIMIT = 1024 * 1024


@pytest.fixture
def layout(tmp_path: Path) -> DataLayout:
    return prepare_data_dir(tmp_path / "data")


def _store(layout: DataLayout, name: str, content: bytes, slug: str = SLUG) -> StoredExample:
    kind = check_example(name, content, max_bytes=LIMIT)
    return store_example(layout, slug, name, content, kind)


def _files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


# --- check_example --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "kind"),
    [
        (make_pdf_bytes(2), FileKind.PDF),
        (make_portrait_image_bytes("JPEG"), FileKind.JPEG),
        (make_portrait_image_bytes("PNG"), FileKind.PNG),
    ],
)
def test_pdf_jpeg_and_png_are_accepted_by_their_content(content: bytes, kind: FileKind) -> None:
    # Ad hiçbir şey söylemiyor: tür içerikten gelir.
    assert check_example("tarama", content, max_bytes=LIMIT) is kind


def test_word_excel_and_plain_text_are_not_examples() -> None:
    for content in (make_docx_bytes(), b"sadece metin"):
        with pytest.raises(ExampleRejectedError, match="yalnız PDF, JPEG ve PNG kabul edilir"):
            check_example("ornek.pdf", content, max_bytes=LIMIT)


def test_empty_and_oversized_files_are_rejected() -> None:
    with pytest.raises(ExampleRejectedError, match="'bos.png' dosyası boş"):
        check_example("bos.png", b"", max_bytes=LIMIT)

    big = make_pdf_bytes() + b"\n" * LIMIT
    with pytest.raises(ExampleRejectedError, match="1 MB sınırını aşıyor"):
        check_example("buyuk.pdf", big, max_bytes=LIMIT)
    # Sınırın tam üstü de reddedilir, tam sınırı tutan kabul edilir.
    exact = make_pdf_bytes()
    assert check_example("tam.pdf", exact, max_bytes=len(exact)) is FileKind.PDF
    with pytest.raises(ExampleRejectedError, match="sınırını aşıyor"):
        check_example("tam.pdf", exact, max_bytes=len(exact) - 1)


@pytest.mark.parametrize(
    "content",
    [
        b"%PDF-1.4\nbozuk",
        b"\xff\xd8\xff\xe0bozuk jpeg",
        b"\x89PNG\r\n\x1a\nbozuk png",
        make_portrait_image_bytes("JPEG")[:40],
    ],
)
def test_corrupt_files_are_rejected_even_with_a_valid_signature(content: bytes) -> None:
    with pytest.raises(ExampleRejectedError, match="açılamadı; bozuk olabilir"):
        check_example("bozuk", content, max_bytes=LIMIT)


def test_password_protected_pdf_is_rejected() -> None:
    encrypted = make_sized_pdf_bytes([(595.0, 842.0)], password="gizli")

    with pytest.raises(ExampleRejectedError, match="açılamadı"):
        check_example("sifreli.pdf", encrypted, max_bytes=LIMIT)


def test_owner_locked_pdf_is_an_example_and_is_stored_byte_for_byte(layout: DataLayout) -> None:
    # Resmî kurum PDF'leri: yalnız düzenleme izni kısıtlı, parolasız açılır. Eskiden pypdf'in
    # `DependencyError`'ı yakalanmadığı için burada çöküyordu (tm 137).
    locked = make_owner_locked_pdf_bytes(2)

    assert check_example("resmi-form.pdf", locked, max_bytes=LIMIT) is FileKind.PDF
    stored = _store(layout, "resmi-form.pdf", locked)

    assert (layout.type_examples_dir(SLUG) / stored.name).read_bytes() == locked


def test_aes_pdf_that_needs_a_password_to_open_is_rejected() -> None:
    locked = make_owner_locked_pdf_bytes(1, user_password="gizli")

    with pytest.raises(ExampleRejectedError, match="açılamadı"):
        check_example("sifreli.pdf", locked, max_bytes=LIMIT)


def test_rejection_message_shows_the_file_name_but_never_a_path() -> None:
    with pytest.raises(ExampleRejectedError) as raised:
        check_example("C:\\Users\\biri\\Belgelerim\\not.txt", b"metin", max_bytes=LIMIT)

    assert "'not.txt'" in str(raised.value)
    assert "Belgelerim" not in str(raised.value)


# --- store_example --------------------------------------------------------------------------------


def test_example_is_written_byte_for_byte_under_the_type_directory(layout: DataLayout) -> None:
    content = make_portrait_image_bytes("PNG")

    stored = _store(layout, "on-yuz.png", content)

    path = layout.root / "KnownDocuments" / "examples" / SLUG / "on-yuz.png"
    assert (stored.name, stored.duplicate, stored.size) == ("on-yuz.png", False, len(content))
    assert path.read_bytes() == content
    assert layout.type_examples_dir(SLUG) == path.parent


def test_nothing_but_the_example_file_is_created(layout: DataLayout) -> None:
    # Çalışan verisinden ayrı: Inbox, Employees, kuyruk ve arşiv dizinleri boş kalır.
    _store(layout, "on-yuz.png", make_portrait_image_bytes("PNG"))

    assert _files(layout.root) == [f"KnownDocuments/examples/{SLUG}/on-yuz.png"]


def test_extension_follows_the_content_not_the_name(layout: DataLayout) -> None:
    pdf_named_jpg = _store(layout, "tarama.jpg", make_pdf_bytes())
    jpeg_named_png = _store(layout, "foto.PNG", make_portrait_image_bytes("JPEG"))
    jpeg_without_extension = _store(layout, "fotograf", make_portrait_image_bytes("JPEG", (30, 40)))

    assert pdf_named_jpg.name == "tarama.pdf"
    assert jpeg_named_png.name == "foto.jpg"
    assert jpeg_without_extension.name == "fotograf.jpg"


def test_names_are_reduced_to_safe_words_and_cannot_leave_the_directory(
    layout: DataLayout,
) -> None:
    content = make_portrait_image_bytes("PNG")
    stored = _store(layout, "../../Inbox/Pasaport Ön Yüz (ışık).PNG", content)
    windows = _store(
        layout, "C:\\gizli\\Kimlik Kartı.png", make_portrait_image_bytes("PNG", (9, 9))
    )

    assert stored.name == "Pasaport-On-Yuz-isik.png"
    assert windows.name == "Kimlik-Karti.png"
    assert _files(layout.root) == [
        f"KnownDocuments/examples/{SLUG}/Kimlik-Karti.png",
        f"KnownDocuments/examples/{SLUG}/Pasaport-On-Yuz-isik.png",
    ]


def test_a_name_without_usable_characters_falls_back_and_long_names_are_cut(
    layout: DataLayout,
) -> None:
    empty = _store(layout, "???.png", make_portrait_image_bytes("PNG"))
    long_name = _store(layout, "kelime-" * 40 + ".png", make_portrait_image_bytes("PNG", (9, 9)))

    assert empty.name == "ornek.png"
    assert len(long_name.name) <= 80 + len(".png")
    assert long_name.name.endswith(".png")


def test_same_name_with_different_content_gets_a_sequence_suffix(layout: DataLayout) -> None:
    first = _store(layout, "sayfa.png", make_portrait_image_bytes("PNG", (30, 40)))
    second = _store(layout, "sayfa.png", make_portrait_image_bytes("PNG", (31, 41)))
    third = _store(layout, "sayfa.png", make_portrait_image_bytes("PNG", (32, 42)))

    assert [first.name, second.name, third.name] == ["sayfa.png", "sayfa-2.png", "sayfa-3.png"]
    assert not (first.duplicate or second.duplicate or third.duplicate)


def test_the_same_content_is_stored_once_whatever_it_is_called(layout: DataLayout) -> None:
    content = make_portrait_image_bytes("PNG")
    first = _store(layout, "sayfa.png", content)

    again = _store(layout, "baska-ad.png", content)

    assert again.duplicate is True
    assert again.name == first.name
    assert again.sha256 == first.sha256
    assert _files(layout.root) == [f"KnownDocuments/examples/{SLUG}/sayfa.png"]


def test_examples_of_different_types_do_not_mix(layout: DataLayout) -> None:
    content = make_portrait_image_bytes("PNG")
    _store(layout, "sayfa.png", content, slug="russian_passport")

    other = _store(layout, "sayfa.png", content, slug="turkish_passport")

    assert other.duplicate is False  # tekrar denetimi yalnız türün kendi dizininde
    assert [example.name for example in list_examples(layout, "russian_passport")] == ["sayfa.png"]
    assert [example.name for example in list_examples(layout, "turkish_passport")] == ["sayfa.png"]


def test_an_unsafe_type_slug_cannot_leave_the_examples_directory(layout: DataLayout) -> None:
    content = make_portrait_image_bytes("PNG")

    for slug in ("..", "../Inbox", "a/b"):
        with pytest.raises(ValueError, match="yol parçası"):
            _store(layout, "x.png", content, slug=slug)
        with pytest.raises(ValueError, match="yol parçası"):
            list_examples(layout, slug)
    assert _files(layout.root) == []


# --- list_examples / example_path -----------------------------------------------------------------


def test_listing_an_absent_directory_is_empty(layout: DataLayout) -> None:
    assert list_examples(layout, SLUG) == []


def test_listing_shows_only_allowed_plain_files_in_name_order(layout: DataLayout) -> None:
    directory = layout.type_examples_dir(SLUG)
    directory.mkdir(parents=True)
    (directory / "b.PDF").write_bytes(b"1")
    (directory / "a.jpeg").write_bytes(b"22")
    (directory / "C.png").write_bytes(b"333")
    (directory / "d.jpg").write_bytes(b"4444")
    (directory / "kaynak.docx").write_bytes(b"x")
    (directory / "notlar.txt").write_bytes(b"x")
    (directory / ".gizli.png").write_bytes(b"x")
    (directory / f".belgeee-{'0' * 32}.part").write_bytes(b"x")
    (directory / "klasor.png").mkdir()

    listed = list_examples(layout, SLUG)

    assert [(example.name, example.size) for example in listed] == [
        ("a.jpeg", 2),
        ("b.PDF", 1),
        ("C.png", 3),
        ("d.jpg", 4),
    ]


def test_example_path_resolves_only_listed_names(layout: DataLayout) -> None:
    _store(layout, "sayfa.png", make_portrait_image_bytes("PNG"))
    (layout.root / "KnownDocuments" / "catalog.yaml").write_text("- slug: x\n", encoding="utf-8")

    assert example_path(layout, SLUG, "sayfa.png") == layout.type_examples_dir(SLUG) / "sayfa.png"
    for name in ("yok.png", "../catalog.yaml", "..", ".", "", "sayfa.png/", "SAYFA.PNG"):
        assert example_path(layout, SLUG, name) is None, name
    assert example_path(layout, "turkish_passport", "sayfa.png") is None
