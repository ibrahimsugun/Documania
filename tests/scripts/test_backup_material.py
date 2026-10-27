"""13.4.2 — eğitim malzemesi gece arşivinin dışındadır, ayrıca artımlı yedeklenir (PLAN.md §D129).

`scripts/backup.sh` `examples`, `_egitim` ve `_referans` dizinlerini arşive almaz;
`scripts/backup-material.sh` onları `rsync` ile sıkıştırmadan, silmeden kopyalar ve `--restore` ile
var olan dosyanın üzerine yazmadan geri koyar. Veri sentetiktir.
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import pytest

from tests.scripts.conftest import Project, file_hashes

MATERIAL = {
    "examples/russian_passport/ornek ğ.jpg": b"\xff\xd8 synthetic example",
    "_egitim/gelen/run1/item1.pdf": b"%PDF synthetic incoming",
    "_referans/referans.png": b"\x89PNG synthetic reference",
}


def _known(project: Project) -> Path:
    return project.data / "KnownDocuments"


def _add_material(project: Project) -> None:
    for relative, content in MATERIAL.items():
        path = _known(project) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _archive_names(project: Project) -> list[str]:
    (archive,) = project.archives()
    with tarfile.open(archive) as handle:
        return handle.getnames()


def _manifest_material(project: Project) -> str:
    (archive,) = project.archives()
    with tarfile.open(archive) as handle:
        member = handle.extractfile("MANIFEST.txt")
        assert member is not None
        lines = member.read().decode().splitlines()
    return dict(line.split("=", 1) for line in lines)["material"]


def test_nightly_archive_leaves_the_training_material_out(project: Project) -> None:
    _add_material(project)
    (_known(project) / "_sablonlar" / "t1").mkdir(parents=True)
    (_known(project) / "_sablonlar" / "t1" / "sablon.pdf").write_bytes(b"%PDF template")

    result = project.backup()

    assert result.code == 0, result.text
    names = _archive_names(project)
    assert not [n for n in names if "/examples" in n or "/_egitim" in n or "/_referans" in n]
    assert "data/KnownDocuments/_sablonlar/t1/sablon.pdf" in names
    assert "data/Inbox/u_20260919_0001/Васильев.jpg" in names
    assert _manifest_material(project) == "excluded"


def test_manifest_file_count_matches_what_the_archive_holds(project: Project) -> None:
    _add_material(project)
    assert project.backup().code == 0, "backup failed"
    (archive,) = project.archives()
    with tarfile.open(archive) as handle:
        in_archive = sum(
            1 for m in handle.getmembers() if m.isfile() and m.name.startswith("data/")
        )
        member = handle.extractfile("MANIFEST.txt")
        assert member is not None
        manifest = dict(line.split("=", 1) for line in member.read().decode().splitlines())

    assert int(manifest["data_files"]) == in_archive


def test_include_flag_puts_the_material_back_into_the_archive(project: Project) -> None:
    _add_material(project)

    result = project.backup(BACKUP_INCLUDE_MATERIAL="1")

    assert result.code == 0, result.text
    names = _archive_names(project)
    assert "data/KnownDocuments/examples/russian_passport/ornek ğ.jpg" in names
    assert "data/KnownDocuments/_egitim/gelen/run1/item1.pdf" in names
    assert _manifest_material(project) == "included"


def test_restore_of_a_nightly_archive_says_the_material_is_not_in_it(project: Project) -> None:
    assert project.backup().code == 0
    (archive,) = project.archives()
    target = project.root / "geri"

    result = project.restore(
        archive,
        DATABASE_URL=f"sqlite:///{(target / 'belgeee.db').as_posix()}",
        DATA_DIR=(target / "data").as_posix(),
    )

    assert result.code == 0, result.text
    assert "backup-material.sh --restore" in result.text


# --- scripts/backup-material.sh (rsync gerekir) ------------------------------------------------


@pytest.fixture
def material(project: Project) -> Project:
    probe = project.run("backup-material.sh")
    if "rsync bulunamadı" in probe.text:
        pytest.skip("rsync yok")
    _add_material(project)
    return project


def test_material_is_copied_uncompressed_and_a_second_run_changes_nothing(
    material: Project, tmp_path: Path
) -> None:
    dest = tmp_path / "malzeme-yedegi"

    first = material.run("backup-material.sh", BACKUP_MATERIAL_DIR=dest.as_posix())

    assert first.code == 0, first.text
    for relative, content in MATERIAL.items():
        assert (dest / relative).read_bytes() == content
    stamp = (dest / "examples/russian_passport/ornek ğ.jpg").stat().st_mtime_ns
    second = material.run("backup-material.sh", BACKUP_MATERIAL_DIR=dest.as_posix())
    assert second.code == 0, second.text
    assert (dest / "examples/russian_passport/ornek ğ.jpg").stat().st_mtime_ns == stamp


def test_nothing_is_ever_deleted_from_the_backup_even_if_the_source_is_gone(
    material: Project, tmp_path: Path
) -> None:
    dest = tmp_path / "malzeme-yedegi"
    assert material.run("backup-material.sh", BACKUP_MATERIAL_DIR=dest.as_posix()).code == 0
    before = file_hashes(dest)
    shutil.rmtree(_known(material) / "examples")
    (_known(material) / "examples").mkdir()  # bağlanmamış hacim gibi boş
    (_known(material) / "_egitim" / "gelen" / "run1" / "item1.pdf").unlink()

    result = material.run("backup-material.sh", BACKUP_MATERIAL_DIR=dest.as_posix())

    assert result.code == 0, result.text
    assert "examples kaynağı yok ya da boş" in result.text
    assert file_hashes(dest) == before


def test_material_backup_needs_a_destination_and_refuses_one_inside_a_source(
    material: Project,
) -> None:
    assert "BACKUP_MATERIAL_DIR" in material.run("backup-material.sh").text
    inside = _known(material) / "examples" / "yedek"

    result = material.run("backup-material.sh", BACKUP_MATERIAL_DIR=inside.as_posix())

    assert result.code != 0 and "içinde olamaz" in result.text


def test_restore_puts_missing_files_back_but_never_overwrites_existing_ones(
    material: Project, tmp_path: Path
) -> None:
    dest = tmp_path / "malzeme-yedegi"
    assert material.run("backup-material.sh", BACKUP_MATERIAL_DIR=dest.as_posix()).code == 0
    lost = _known(material) / "_egitim/gelen/run1/item1.pdf"
    lost.unlink()
    kept = _known(material) / "examples/russian_passport/ornek ğ.jpg"
    kept.write_bytes(b"changed after the backup")

    result = material.run("backup-material.sh", "--restore", BACKUP_MATERIAL_DIR=dest.as_posix())

    assert result.code == 0, result.text
    assert lost.read_bytes() == MATERIAL["_egitim/gelen/run1/item1.pdf"]
    assert kept.read_bytes() == b"changed after the backup"
