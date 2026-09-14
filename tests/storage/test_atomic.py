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
    copy_file,
    remove_partial_writes,
    replace_file,
    sha256_bytes,
    sha256_file,
    write_file,
    write_sequenced,
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
