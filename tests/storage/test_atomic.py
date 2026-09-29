"""00.4.4 bütünlük + atomik yazma ve 00.4.3 sıra eki (üzerine yazmadan yayın).

İçerikler sentetik bayt dizileridir; gerçek belge kullanılmaz (CONVENTIONS §6).
"""

import hashlib
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest

from app.storage import atomic
from app.storage.atomic import (
    CHUNK_SIZE,
    ContentMismatchError,
    StoredFile,
    copy_file,
    find_sequenced,
    is_partial_write,
    remove_partial_writes,
    replace_file,
    sha256_bytes,
    sha256_file,
    write_file,
    write_sequenced,
    write_unique,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STEM = "Ahmet_Cakar-Passport"


def _chunks_then_fail(error: BaseException) -> Iterator[bytes]:
    yield b"%PDF-1.7 sentetik\n" * 1000
    yield b"ikinci parca" * 1000
    raise error


# --- 00.4.4: SHA-256 ------------------------------------------------------------------------


def test_write_file_returns_sha256_of_written_content(tmp_path: Path) -> None:
    data = os.urandom(CHUNK_SIZE * 2 + 123)
    target = tmp_path / "Inbox" / "u1" / "kaynak.pdf"

    stored = write_file(target, data)

    assert stored.path == target
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert stored.size == len(data)
    assert target.read_bytes() == data
    assert sha256_file(target) == sha256_bytes(data) == stored.sha256


def test_write_file_accepts_chunk_iterables(tmp_path: Path) -> None:
    chunks = [b"a" * 10, b"b" * 20, b"", b"c"]

    stored = write_file(tmp_path / "out.bin", iter(chunks))

    assert stored.sha256 == sha256_bytes(b"".join(chunks))
    assert stored.size == 31


def test_copy_file_is_byte_identical(tmp_path: Path) -> None:
    source = tmp_path / "Inbox" / "u1" / "kaynak.pdf"
    write_file(source, os.urandom(CHUNK_SIZE + 7))
    destination = tmp_path / "Employees" / "Ahmet_Cakar_E0001" / "Alinan" / "kaynak.pdf"

    stored = copy_file(source, destination)

    assert stored.sha256 == sha256_file(source)
    assert destination.read_bytes() == source.read_bytes()


def test_text_content_rejected(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        write_file(tmp_path / "out.txt", "metin")  # type: ignore[arg-type]
    assert list(tmp_path.iterdir()) == []


# --- 00.4.4: kesilen yazma yarım dosya bırakmaz -----------------------------------------------


@pytest.mark.parametrize("error", [OSError("disk doldu"), KeyboardInterrupt()])
def test_interrupted_write_leaves_no_file(tmp_path: Path, error: BaseException) -> None:
    target = tmp_path / "Hazir" / f"{STEM}.pdf"

    with pytest.raises(type(error)):
        write_file(target, _chunks_then_fail(error))

    assert list(target.parent.iterdir()) == []


def test_interrupted_sequenced_write_leaves_no_file(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        write_sequenced(tmp_path, STEM, "pdf", _chunks_then_fail(OSError("kesildi")))

    assert list(tmp_path.iterdir()) == []


def test_failed_fsync_leaves_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_fsync(_fd: int) -> None:
        raise OSError("fsync başarısız")

    monkeypatch.setattr(atomic.os, "fsync", failing_fsync)

    with pytest.raises(OSError, match="fsync"):
        write_file(tmp_path / "out.pdf", b"veri")

    assert list(tmp_path.iterdir()) == []


def test_failed_publish_leaves_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_link(_src: object, _dst: object) -> None:
        raise OSError("bağ kurulamadı")

    monkeypatch.setattr(atomic.os, "link", failing_link)

    with pytest.raises(OSError, match="bağ"):
        write_file(tmp_path / "out.pdf", b"veri")

    assert list(tmp_path.iterdir()) == []


_KILLED_WRITER = """
import sys
import time
from pathlib import Path

from app.storage.atomic import write_file


def chunks():
    yield b"%PDF-1.7 sentetik\\n" * 10000
    print("ready", flush=True)
    time.sleep(120)
    yield b"asla yazilmaz"


write_file(Path(sys.argv[1]), chunks())
"""


def test_killed_writer_leaves_no_partial_file_at_target(tmp_path: Path) -> None:
    target = tmp_path / "Employees" / "Ahmet_Cakar_E0001" / "Hazir" / f"{STEM}.pdf"
    process = subprocess.Popen(
        [sys.executable, "-c", _KILLED_WRITER, str(target)],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        stdout=subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == b"ready"
        process.kill()
        process.wait(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
        if process.stdout is not None:
            process.stdout.close()

    assert not target.exists()
    leftovers = list(target.parent.iterdir())
    assert len(leftovers) == 1
    assert leftovers[0].name.startswith(".belgeee-")

    # Açılış temizliği öldürülmüş yazmanın geçici dosyasını siler. Windows öldürülen sürecin
    # dosya tanıtıcısını `wait()` döndükten biraz sonra bırakır; o ana kadar temizlik dosyayı
    # (başka bir sürecin açık yazması gibi) atlar.
    removed: list[Path] = []
    deadline = time.monotonic() + 10
    while not removed and time.monotonic() < deadline:
        removed = remove_partial_writes(tmp_path, older_than=timedelta(0))
        if not removed:
            time.sleep(0.05)
    assert removed == leftovers
    assert list(target.parent.iterdir()) == []


def test_remove_partial_writes_keeps_fresh_and_foreign_files(tmp_path: Path) -> None:
    stale = tmp_path / "Hazir" / f".belgeee-{'a' * 32}.part"
    fresh = tmp_path / "Inbox" / f".belgeee-{'b' * 32}.part"
    foreign = [tmp_path / "Hazir" / ".gizli", tmp_path / "Hazir" / "x.part", tmp_path / "doc.pdf"]
    for path in [stale, fresh, *foreign]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    two_hours_ago = time.time() - 7200
    os.utime(stale, (two_hours_ago, two_hours_ago))

    assert remove_partial_writes(tmp_path) == [stale]
    assert fresh.exists()
    assert all(path.exists() for path in foreign)


# --- 00.4.3: sıra eki ve üzerine yazmama -----------------------------------------------------


def test_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    target = tmp_path / f"{STEM}.pdf"
    write_file(target, b"ilk")

    with pytest.raises(FileExistsError):
        write_file(target, b"ikinci")

    assert target.read_bytes() == b"ilk"
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


def test_second_and_third_document_of_same_type_get_suffixes(tmp_path: Path) -> None:
    stored = [
        write_sequenced(tmp_path, STEM, "pdf", content)
        for content in (b"birinci", b"ikinci", b"ucuncu")
    ]

    assert [s.path.name for s in stored] == [
        "Ahmet_Cakar-Passport.pdf",
        "Ahmet_Cakar-Passport-2.pdf",
        "Ahmet_Cakar-Passport-3.pdf",
    ]
    assert [s.sequence_no for s in stored] == [1, 2, 3]
    assert [s.path.read_bytes() for s in stored] == [b"birinci", b"ikinci", b"ucuncu"]
    assert all(s.sha256 == sha256_file(s.path) for s in stored)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(s.path.name for s in stored)


def test_other_types_do_not_take_a_sequence(tmp_path: Path) -> None:
    write_sequenced(tmp_path, "Ahmet_Cakar-Residence-Card", "pdf", b"oturum")
    write_sequenced(tmp_path, "Ahmet_Cakar-Passport-Copy", "pdf", b"baska tur")

    stored = write_sequenced(tmp_path, STEM, "pdf", b"pasaport")

    assert stored.path.name == "Ahmet_Cakar-Passport.pdf"
    assert stored.sequence_no == 1


def test_same_type_with_other_extension_takes_next_suffix(tmp_path: Path) -> None:
    write_sequenced(tmp_path, "Ahmet_Cakar-Profile-Picture", "jpeg", b"jpeg")

    stored = write_sequenced(tmp_path, "Ahmet_Cakar-Profile-Picture", "PNG", b"png")

    assert stored.path.name == "Ahmet_Cakar-Profile-Picture-2.png"


def test_existing_name_in_other_case_is_not_overwritten(tmp_path: Path) -> None:
    existing = tmp_path / "ahmet_cakar-passport.PDF"
    existing.write_bytes(b"eski")

    stored = write_sequenced(tmp_path, STEM, "pdf", b"yeni")

    assert stored.path.name == "Ahmet_Cakar-Passport-2.pdf"
    assert existing.read_bytes() == b"eski"


def test_free_slot_before_existing_suffix_is_used(tmp_path: Path) -> None:
    second = tmp_path / "Ahmet_Cakar-Passport-2.pdf"
    second.write_bytes(b"ikinci")

    stored = write_sequenced(tmp_path, STEM, "pdf", b"yeni")

    assert stored.path.name == "Ahmet_Cakar-Passport.pdf"
    assert second.read_bytes() == b"ikinci"


def test_name_taken_after_directory_scan_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dizin tarandıktan sonra aynı adı başka bir yazar yayınlamış gibi: tarama boş görünür.
    winner = tmp_path / "Ahmet_Cakar-Passport.pdf"
    winner.write_bytes(b"kazanan")
    monkeypatch.setattr(atomic, "_stems_in_use", lambda _directory: set())

    stored = write_sequenced(tmp_path, STEM, "pdf", b"kaybeden")

    assert stored.path.name == "Ahmet_Cakar-Passport-2.pdf"
    assert winner.read_bytes() == b"kazanan"
    assert stored.path.read_bytes() == b"kaybeden"


def test_concurrent_writers_get_distinct_names(tmp_path: Path) -> None:
    writers = 16
    barrier = threading.Barrier(writers)

    def write(index: int) -> atomic.StoredFile:
        barrier.wait()
        return write_sequenced(tmp_path, STEM, "pdf", f"belge {index}".encode())

    with ThreadPoolExecutor(max_workers=writers) as pool:
        stored = list(pool.map(write, range(writers)))

    assert sorted(s.sequence_no for s in stored) == list(range(1, writers + 1))
    assert len({s.path for s in stored}) == writers
    for index, item in enumerate(stored):
        assert item.path.read_bytes() == f"belge {index}".encode()
    assert len(list(tmp_path.iterdir())) == writers


def test_invalid_stem_rejected_before_writing(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_sequenced(tmp_path, "../Inbox/x", "pdf", b"veri")
    assert list(tmp_path.iterdir()) == []


def test_sequenced_write_publishes_content_matching_expected_hash(tmp_path: Path) -> None:
    stored = write_sequenced(tmp_path, STEM, "pdf", b"veri", expected_sha256=sha256_bytes(b"veri"))

    assert stored.path.read_bytes() == b"veri"


def test_sequenced_write_with_unexpected_hash_publishes_nothing(tmp_path: Path) -> None:
    with pytest.raises(ContentMismatchError):
        write_sequenced(tmp_path, STEM, "pdf", b"degismis", expected_sha256=sha256_bytes(b"veri"))

    assert list(tmp_path.iterdir()) == []


def test_sequenced_write_tries_the_preferred_suffix_first(tmp_path: Path) -> None:
    """10.5.10: arşivden dönen belge boştaysa kendi ekine döner, doluysa ilk boş eki alır."""
    write_sequenced(tmp_path, STEM, "pdf", b"bir")

    kept = write_sequenced(tmp_path, STEM, "pdf", b"uc", preferred_sequence_no=3)
    taken = write_sequenced(tmp_path, STEM, "pdf", b"yine uc", preferred_sequence_no=3)
    first_free = write_sequenced(tmp_path, STEM, "pdf", b"iki", preferred_sequence_no=1)

    assert (kept.sequence_no, kept.path.name) == (3, f"{STEM}-3.pdf")
    assert (taken.sequence_no, taken.path.name) == (2, f"{STEM}-2.pdf")
    assert (first_free.sequence_no, first_free.path.name) == (4, f"{STEM}-4.pdf")


def test_sequenced_write_rejects_an_invalid_preferred_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Sıra numarası"):
        write_sequenced(tmp_path, STEM, "pdf", b"veri", preferred_sequence_no=0)
    assert list(tmp_path.iterdir()) == []


# --- sıra ekiyle yayınlanmış aynı içeriği bulma (07.8.1) -------------------------------------


def _find(
    directory: Path, content: bytes, *, stem: str = STEM, extension: str = "pdf"
) -> list[StoredFile]:
    return find_sequenced(
        directory, stem, extension, sha256=sha256_bytes(content), size=len(content)
    )


def test_find_sequenced_returns_the_files_write_sequenced_published_with_that_content(
    tmp_path: Path,
) -> None:
    published = [write_sequenced(tmp_path, STEM, "pdf", content) for content in (b"a", b"b", b"a")]

    found = _find(tmp_path, b"a")

    assert found == [published[0], published[2]]
    assert [(stored.path.name, stored.sequence_no) for stored in found] == [
        (f"{STEM}.pdf", 1),
        (f"{STEM}-3.pdf", 3),
    ]
    assert _find(tmp_path, b"c") == []


def test_find_sequenced_orders_by_sequence_number_not_by_name(tmp_path: Path) -> None:
    for sequence_no in (10, 2, 9):
        (tmp_path / f"{STEM}-{sequence_no}.pdf").write_bytes(b"ayni")

    assert [stored.sequence_no for stored in _find(tmp_path, b"ayni")] == [2, 9, 10]


@pytest.mark.parametrize(
    "name",
    [
        f"{STEM}.jpeg",  # başka uzantı
        f"{STEM}.PDF",  # write_sequenced uzantıyı küçük harfle yazar
        f"{STEM.lower()}.pdf",  # gövde birebir değil
        f"{STEM}-1.pdf",  # birinci belge eksizdir
        f"{STEM}-02.pdf",  # baştaki sıfır
        f"{STEM}-2x.pdf",
        f"{STEM}-.pdf",
        f"{STEM}-Back.pdf",  # başka türün gövdesi
        f"{STEM}2.pdf",
        f"Baska-{STEM}.pdf",
        f"{STEM}",
        f".belgeee-{'0a' * 16}.part",
    ],
)
def test_find_sequenced_ignores_names_write_sequenced_would_not_publish(
    tmp_path: Path, name: str
) -> None:
    (tmp_path / name).write_bytes(b"ayni")

    assert _find(tmp_path, b"ayni") == []


def test_find_sequenced_ignores_other_content_directories_and_a_missing_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / f"{STEM}.pdf").write_bytes(b"baska")  # aynı boy, başka içerik
    (tmp_path / f"{STEM}-2.pdf").write_bytes(b"ayni-degil")  # başka boy
    (tmp_path / f"{STEM}-3.pdf").mkdir()

    assert _find(tmp_path, b"ayni") == []
    assert _find(tmp_path / "yok", b"ayni") == []


def test_find_sequenced_hashes_only_files_of_the_same_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / f"{STEM}.pdf").write_bytes(b"x" * 100)
    target = write_sequenced(tmp_path, STEM, "pdf", b"ayni")
    hashed: list[Path] = []

    def _recording_sha256_file(path: Path) -> str:
        hashed.append(path)
        return sha256_file(path)

    monkeypatch.setattr(atomic, "sha256_file", _recording_sha256_file)

    assert _find(tmp_path, b"ayni") == [target]
    assert hashed == [target.path]


def test_find_sequenced_rejects_an_invalid_stem_or_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _find(tmp_path, b"veri", stem="../Inbox/x")
    with pytest.raises(ValueError):
        _find(tmp_path, b"veri", extension="p/f")


# --- K8 dışı adla çakışmasız yayın (Alinan kopyası, 07.7.2) ----------------------------------


def test_write_unique_keeps_the_given_name(tmp_path: Path) -> None:
    stored = write_unique(tmp_path / "Alinan", "Tarama 01 (скан).pdf", b"orijinal")

    assert stored.path == tmp_path / "Alinan" / "Tarama 01 (скан).pdf"
    assert (stored.sha256, stored.size, stored.sequence_no) == (sha256_bytes(b"orijinal"), 8, 1)
    assert stored.path.read_bytes() == b"orijinal"


@pytest.mark.parametrize(
    ("name", "second", "third"),
    [
        ("tarama.pdf", "tarama-2.pdf", "tarama-3.pdf"),
        ("arsiv.tar.gz", "arsiv.tar-2.gz", "arsiv.tar-3.gz"),
        ("dosya-0", "dosya-0-2", "dosya-0-3"),
    ],
)
def test_write_unique_suffixes_the_stem_when_name_is_taken(
    tmp_path: Path, name: str, second: str, third: str
) -> None:
    stored = [write_unique(tmp_path, name, content) for content in (b"bir", b"iki", b"uc")]

    assert [s.path.name for s in stored] == [name, second, third]
    assert [s.sequence_no for s in stored] == [1, 2, 3]
    assert [s.path.read_bytes() for s in stored] == [b"bir", b"iki", b"uc"]


def test_write_unique_counts_other_case_as_taken_but_not_other_extension(tmp_path: Path) -> None:
    (tmp_path / "TARAMA.PDF").write_bytes(b"eski")
    (tmp_path / "tarama.jpg").write_bytes(b"baska uzanti")

    stored = write_unique(tmp_path, "tarama.pdf", b"yeni")

    assert stored.path.name == "tarama-2.pdf"
    assert (tmp_path / "TARAMA.PDF").read_bytes() == b"eski"


def test_write_unique_name_taken_after_directory_scan_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    winner = tmp_path / "tarama.pdf"
    winner.write_bytes(b"kazanan")
    monkeypatch.setattr(atomic, "_names_in_use", lambda _directory: set())

    stored = write_unique(tmp_path, "tarama.pdf", b"kaybeden")

    assert stored.path.name == "tarama-2.pdf"
    assert winner.read_bytes() == b"kazanan"


def test_write_unique_with_unexpected_hash_publishes_nothing(tmp_path: Path) -> None:
    with pytest.raises(ContentMismatchError):
        write_unique(tmp_path, "tarama.pdf", b"degismis", expected_sha256=sha256_bytes(b"veri"))

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["", ".", "..", "../x.pdf", "Alt/x.pdf", "Alt\\x.pdf"])
def test_write_unique_rejects_names_that_are_not_one_path_segment(
    tmp_path: Path, name: str
) -> None:
    with pytest.raises(ValueError):
        write_unique(tmp_path, name, b"veri")

    assert list(tmp_path.iterdir()) == []


def test_is_partial_write_matches_only_temporary_names() -> None:
    assert is_partial_write(f".belgeee-{'0a' * 16}.part")
    assert not is_partial_write("tarama.part")
    assert not is_partial_write(f".belgeee-{'0a' * 16}.pdf")


# --- yeniden üretilen türev dosyalar --------------------------------------------------------


def test_replace_file_swaps_content_atomically(tmp_path: Path) -> None:
    profile = tmp_path / "Employees" / "Ahmet_Cakar_E0001" / "profil.md"

    first = replace_file(profile, b"---\nsurum: 1\n---\n")
    second = replace_file(profile, b"---\nsurum: 2\n---\n")

    assert profile.read_bytes() == b"---\nsurum: 2\n---\n"
    assert first.sha256 != second.sha256 == sha256_file(profile)
    assert [p.name for p in profile.parent.iterdir()] == ["profil.md"]


@pytest.mark.parametrize("fail_at", ["content", "replace"])
def test_interrupted_replace_keeps_previous_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_at: str
) -> None:
    reason = tmp_path / "Unresolved" / "u1" / "reason.json"
    replace_file(reason, b'{"reason": "eski"}')

    if fail_at == "content":
        with pytest.raises(OSError):
            replace_file(reason, _chunks_then_fail(OSError("kesildi")))
    else:

        def failing_replace(_src: object, _dst: object) -> None:
            raise OSError("replace başarısız")

        monkeypatch.setattr(atomic.os, "replace", failing_replace)
        with pytest.raises(OSError, match="replace"):
            replace_file(reason, b'{"reason": "yeni"}')

    assert reason.read_bytes() == b'{"reason": "eski"}'
    assert [p.name for p in reason.parent.iterdir()] == ["reason.json"]
