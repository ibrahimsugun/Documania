"""13.4.2 — gece yedeği alınır; geri yükleme prosedürü denenmiştir.

`scripts/backup.sh` ve `scripts/restore.sh` gerçekten çalıştırılır. **Geri yükleme provası** bu
dosyadadır (`test_restore_drill_*`): yedek alınır, veri ve veritabanı yok edilir ya da yeni bir yere
geri yüklenir, her dosya bayt bayt ve her veritabanı satırı aynı çıkmalıdır. PostgreSQL yolu bu
makinede gerçek sunucuyla değil, komut satırını ve ortamı kaydeden sahte `pg_dump`/`pg_restore`/
`psql` ile sınanır. Veri sentetiktir; gerçek kimlik belgesi ya da ağ çağrısı yoktur.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import sqlite3
import subprocess
import tarfile
import time
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AccessLog, Document, Employee
from app.db.session import create_db_engine
from tests.scripts.conftest import SCRIPTS, Project, file_hashes

DB_NAME = "belgeee.db"


def _members(archive: Path) -> list[str]:
    with tarfile.open(archive) as handle:
        return handle.getnames()


def _manifest(archive: Path) -> dict[str, str]:
    with tarfile.open(archive) as handle:
        member = handle.extractfile("MANIFEST.txt")
        assert member is not None
        lines = member.read().decode().splitlines()
    return dict(line.split("=", 1) for line in lines)


def _counts(db: Path) -> dict[str, int]:
    """Uygulamanın kendi motoruyla açılan veritabanındaki satır sayıları."""
    engine = create_db_engine(f"sqlite:///{db.as_posix()}")
    with Session(engine) as session:
        counts = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
            for model in (Employee, Document, AccessLog)
        }
    engine.dispose()
    return counts


def _make_archive(project: Project) -> Path:
    result = project.backup()
    assert result.code == 0, result.text
    (archive,) = project.archives()
    return archive


def _targets(root: Path) -> dict[str, str]:
    return {
        "DATABASE_URL": f"sqlite:///{(root / 'yeni' / DB_NAME).as_posix()}",
        "DATA_DIR": (root / "yeni-data").as_posix(),
    }


# --- yedek alma ------------------------------------------------------------------------------


def test_backup_writes_archive_checksum_and_manifest(project: Project) -> None:
    result = project.backup()

    assert result.code == 0, result.text
    (archive,) = project.archives()
    assert archive.name.startswith("belgeee-") and archive.name.endswith("Z.tar.gz")
    sidecar = Path(f"{archive}.sha256").read_text().split()
    assert sidecar == [hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name]

    members = _members(archive)
    assert "MANIFEST.txt" in members
    assert "db/belgeee.sqlite" in members
    assert "data/Inbox/u_20260919_0001/özgün dosya ğ.pdf" in members
    assert "data/Inbox/u_20260919_0001/Васильев.jpg" in members
    assert "data/Employees/Dmitry_Vasiliev_E0001/Hazir/Dmitry_Vasiliev-Pasaport.pdf" in members
    manifest = _manifest(archive)
    assert manifest["db_kind"] == "sqlite"
    assert manifest["db_file"] == "db/belgeee.sqlite"
    assert manifest["belgeee-backup"] == "1"


def test_live_database_file_is_not_copied_raw_into_the_data_tree(project: Project) -> None:
    """Veritabanı veri dizininde durur; arşive canlı dosya değil tutarlı anlık görüntü girer."""
    archive = _make_archive(project)

    assert not [name for name in _members(archive) if name.startswith(f"data/{DB_NAME}")]
    on_disk = sum(1 for name in file_hashes(project.data) if name != DB_NAME)
    with tarfile.open(archive) as handle:
        in_archive = sum(
            1 for m in handle.getmembers() if m.isfile() and m.name.startswith("data/")
        )
    assert int(_manifest(archive)["data_files"]) == on_disk == in_archive


def test_snapshot_includes_committed_rows_still_waiting_in_the_wal(project: Project) -> None:
    """WAL kipinde işlenmiş satırlar ana dosyada değil `-wal`'dadır: dosya kopyası onları kaçırır,
    SQLite'ın yedekleme arayüzü kaçırmaz."""
    holder = sqlite3.connect(project.db)
    holder.execute("PRAGMA journal_mode=WAL")
    holder.execute("PRAGMA wal_autocheckpoint=0")
    holder.execute(
        "insert into users (id, username, password_hash, role) values (9, 'wal', 'x', 'hr')"
    )
    holder.commit()
    assert Path(f"{project.db}-wal").stat().st_size > 0
    try:
        archive = _make_archive(project)
    finally:
        holder.close()

    target = project.root / "geri"
    result = project.restore(archive, **_targets(target))
    assert result.code == 0, result.text
    restored = sqlite3.connect(target / "yeni" / DB_NAME)
    assert restored.execute("select username from users where id = 9").fetchone() == ("wal",)
    restored.close()


def test_backup_dir_inside_the_data_dir_is_refused(project: Project) -> None:
    result = project.backup(BACKUP_DIR=(project.data / "yedek").as_posix())

    assert result.code != 0
    assert "veri dizininin" in result.err
    assert not any(project.data.rglob("belgeee-*.tar.gz"))


def test_backup_fails_clearly_without_configuration(project: Project, tmp_path: Path) -> None:
    missing_url = project.backup(DATABASE_URL=None)
    missing_dir = project.backup(DATA_DIR=(tmp_path / "yok").as_posix())
    missing_db = project.backup(DATABASE_URL=f"sqlite:///{(tmp_path / 'yok.db').as_posix()}")
    bad_keep = project.backup(BACKUP_KEEP_DAYS="on dört")
    in_memory = project.backup(DATABASE_URL="sqlite://")
    other = project.backup(DATABASE_URL="mysql://u:p@h/db")

    assert "DATABASE_URL tanımlı değil" in missing_url.err
    assert "veri dizini yok" in missing_dir.err
    assert "SQLite anlık görüntüsü alınamadı" in missing_db.err
    assert "BACKUP_KEEP_DAYS" in bad_keep.err
    assert "DATABASE_URL ayrıştırılamadı" in in_memory.err
    assert "desteklenmeyen veritabanı: mysql" in other.err
    assert all(
        r.code != 0 for r in (missing_url, missing_dir, missing_db, bad_keep, in_memory, other)
    )
    # Hiçbir başarısız çalışma yarım arşiv ya da kalıntı bırakmaz.
    assert not list(project.backups.glob("*"))
    assert not (tmp_path / "yok.db").exists()


def test_settings_fall_back_to_the_env_file_but_the_environment_wins(
    project: Project, tmp_path: Path
) -> None:
    env_file = project.root / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# yorum",
                f'DATABASE_URL="sqlite:///{project.db.as_posix()}"',
                f"DATA_DIR={project.data.as_posix()}",
                f"BACKUP_DIR={(tmp_path / 'env-dizini').as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = project.backup(
        DATABASE_URL=None, DATA_DIR=None, BACKUP_DIR=None, ENV_FILE=env_file.as_posix()
    )
    assert result.code == 0, result.text
    assert len(project.archives(tmp_path / "env-dizini")) == 1

    override = project.backup(
        DATABASE_URL=None,
        DATA_DIR=None,
        ENV_FILE=env_file.as_posix(),
        BACKUP_DIR=project.backups.as_posix(),
    )
    assert override.code == 0, override.text
    assert len(project.archives()) == 1


# --- sunucu dışı kopya ve budama ------------------------------------------------------------------


def test_offsite_copy_is_written_and_matches_the_archive(project: Project, tmp_path: Path) -> None:
    offsite = tmp_path / "sunucu-disi"

    result = project.backup(BACKUP_COPY_DIR=offsite.as_posix())

    assert result.code == 0, result.text
    (local,) = project.archives()
    (copy,) = project.archives(offsite)
    assert copy.read_bytes() == local.read_bytes()
    assert Path(f"{copy}.sha256").read_text() == Path(f"{local}.sha256").read_text()
    assert "UYARI: sunucu dışı hedef tanımlı değil" not in result.out
    assert not list(offsite.glob(".*"))


def test_without_an_offsite_target_the_run_warns(project: Project) -> None:
    result = project.backup()

    assert result.code == 0
    assert "UYARI: sunucu dışı hedef tanımlı değil" in result.out


def test_failed_offsite_copy_fails_the_run_and_keeps_the_local_archive(
    project: Project, tmp_path: Path
) -> None:
    blocker = tmp_path / "dosya"
    blocker.write_text("dizin değil")

    result = project.backup(BACKUP_COPY_DIR=(blocker / "altinda").as_posix())

    assert result.code != 0
    assert len(project.archives()) == 1


def test_old_backups_are_pruned_after_a_successful_run_only(project: Project) -> None:
    project.backups.mkdir()
    old = project.backups / "belgeee-20200101T000000Z.tar.gz"
    old_sum = project.backups / "belgeee-20200101T000000Z.tar.gz.sha256"
    unrelated = project.backups / "notlar.txt"
    for path in (old, old_sum, unrelated):
        path.write_text("eski")
        long_ago = time.time() - 40 * 86400
        os.utime(path, (long_ago, long_ago))

    failed = project.backup(DATABASE_URL=f"sqlite:///{(project.root / 'yok.db').as_posix()}")
    assert failed.code != 0
    assert old.exists() and old_sum.exists()  # başarısız gece eskiler korunur

    ok = project.backup(BACKUP_KEEP_DAYS="14")
    assert ok.code == 0, ok.text
    assert not old.exists() and not old_sum.exists()
    assert unrelated.exists()  # yalnız yedek adlı dosyalar budanır
    assert len(project.archives()) == 1  # yeni yedek korunur


def test_keep_days_zero_never_prunes(project: Project) -> None:
    project.backups.mkdir()
    old = project.backups / "belgeee-20200101T000000Z.tar.gz"
    old.write_text("eski")
    os.utime(old, (0, 0))

    result = project.backup(BACKUP_KEEP_DAYS="0")

    assert result.code == 0, result.text
    assert old.exists()


# --- geri yükleme provası ---------------------------------------------------------------------


def test_restore_drill_into_a_fresh_location_reproduces_files_and_database(
    project: Project, tmp_path: Path
) -> None:
    """Yedek yeni bir yere geri yüklenir: her dosya bayt bayt, her satır aynı."""
    original_files = file_hashes(project.data, skip={DB_NAME})
    original_counts = _counts(project.db)
    assert original_counts == {"employees": 1, "documents": 1, "access_log": 1}
    archive = _make_archive(project)
    target = tmp_path / "prova"
    env = _targets(target)

    result = project.restore(archive, **env)

    assert result.code == 0, result.text
    restored_data = target / "yeni-data"
    assert file_hashes(restored_data) == original_files
    assert _counts(target / "yeni" / DB_NAME) == original_counts
    check = sqlite3.connect(target / "yeni" / DB_NAME)
    assert check.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    check.close()
    assert "geri yükleme tamam" in result.out
    assert "alembic upgrade head" in result.out
    # Yedeğin kendisi restore'la değişmedi.
    assert archive.exists()


def test_restore_drill_after_the_server_is_lost_rebuilds_it_in_place(project: Project) -> None:
    """Felaket senaryosu: veri dizini ve veritabanı tamamen kaybolur; yedekten aynı yola dönülür."""
    original_files = file_hashes(project.data, skip={DB_NAME})
    original_counts = _counts(project.db)
    archive = _make_archive(project)
    kept = project.root / "yedek-kopyasi"
    kept.mkdir()
    shutil.copy2(archive, kept / archive.name)
    shutil.copy2(f"{archive}.sha256", kept / f"{archive.name}.sha256")
    shutil.rmtree(project.data)
    assert not project.db.exists()

    result = project.restore(kept / archive.name)

    assert result.code == 0, result.text
    assert file_hashes(project.data, skip={DB_NAME}) == original_files
    assert _counts(project.db) == original_counts


def test_restore_refuses_a_nonempty_target_and_writes_nothing(
    project: Project, tmp_path: Path
) -> None:
    archive = _make_archive(project)
    before = file_hashes(project.data)

    result = project.restore(archive)

    assert result.code != 0
    assert "veri dizini dolu" in result.err
    assert "SQLite dosyası var" in result.err
    assert "--force" in result.err
    assert file_hashes(project.data) == before
    assert not list(tmp_path.rglob("*.before-restore-*"))
    assert not list(tmp_path.rglob("*.restoring"))


def test_force_sets_existing_data_aside_instead_of_deleting_it(project: Project) -> None:
    archive = _make_archive(project)
    extra = project.data / "Inbox" / "sonradan.pdf"
    extra.write_bytes(b"yedekten sonra gelen dosya")
    with closing(sqlite3.connect(project.db)) as connection:
        connection.execute("delete from access_log")
        connection.commit()

    result = project.restore(archive, "--force")

    assert result.code == 0, result.text
    (aside,) = project.root.glob("data.before-restore-*")
    assert (aside / "Inbox" / "sonradan.pdf").read_bytes() == b"yedekten sonra gelen dosya"
    assert not (project.data / "Inbox" / "sonradan.pdf").exists()
    assert _counts(project.db)["access_log"] == 1
    # Kendi konumundaki eski veritabanı da veri dizininin yanına çekilmiştir, içinde değil.
    assert (aside / DB_NAME).exists()


def test_tampered_archive_is_rejected_before_the_target_is_touched(
    project: Project, tmp_path: Path
) -> None:
    archive = _make_archive(project)
    raw = bytearray(archive.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    archive.write_bytes(bytes(raw))
    target = tmp_path / "prova"

    result = project.restore(archive, **_targets(target))

    assert result.code != 0
    assert "SHA-256" in result.err
    assert not target.exists()


def test_tampered_database_dump_is_rejected_even_without_the_checksum_file(
    project: Project, tmp_path: Path
) -> None:
    archive = _make_archive(project)
    forged = tmp_path / "sahte.tar.gz"
    with tarfile.open(archive) as source, tarfile.open(forged, "w:gz") as target_archive:
        for member in source.getmembers():
            content = source.extractfile(member) if member.isfile() else None
            if member.name == "db/belgeee.sqlite":
                assert content is not None
                data = content.read() + b"\x00"
                member.size = len(data)
                content = io.BytesIO(data)
            target_archive.addfile(member, content)
    target = tmp_path / "prova"

    result = project.restore(forged, **_targets(target))

    assert result.code != 0
    assert "özeti doğrulanamadı" in result.out  # sağlama dosyası yok: yalnız uyarı
    assert "veritabanı dökümünün özeti tutmuyor" in result.err
    assert not target.exists()


def test_restore_rejects_bad_invocations(project: Project, tmp_path: Path) -> None:
    archive = _make_archive(project)
    not_ours = tmp_path / "baska.tar.gz"
    with tarfile.open(not_ours, "w:gz") as handle:
        handle.add(project.data / "Inbox", arcname="rastgele")

    no_archive = project.run("restore.sh")
    missing = project.restore(tmp_path / "yok.tar.gz")
    unknown_flag = project.run("restore.sh", "--sil", str(archive))
    two = project.run("restore.sh", str(archive), str(archive))
    foreign = project.restore(not_ours)

    assert all(r.code != 0 for r in (no_archive, missing, unknown_flag, two, foreign))
    assert "kullanım" in no_archive.err
    assert "arşiv yok" in missing.err
    assert "bilinmeyen seçenek" in unknown_flag.err
    assert "tek bir arşiv" in two.err
    assert "MANIFEST.txt" in foreign.err


def test_restore_refuses_a_backup_of_the_other_database_kind(
    project: Project, tmp_path: Path
) -> None:
    archive = _make_archive(project)

    result = project.restore(
        archive,
        DATABASE_URL="postgresql://u:p@localhost/belgeee",
        DATA_DIR=(tmp_path / "x").as_posix(),
    )

    assert result.code != 0
    assert "yedek sqlite veritabanından, hedef DATABASE_URL postgres" in result.err
    assert not (tmp_path / "x").exists()


# --- PostgreSQL (sahte istemci araçlarıyla) ---------------------------------------------

PG_URL = "postgresql+psycopg://belgeee:s3cret%21@db.example:5433/belgeee_db?sslmode=require"


def _stub_tools(project: Project, *, tables: str = "0") -> dict[str, str]:
    """`pg_dump`, `pg_restore` ve `psql` yerine geçen betikler; komut satırını ve `PG*` ortamını
    kaydeder. Ortam değişkenlerini döner (PATH başa eklenmiş)."""
    stubs = project.root / "stubs"
    logs = project.root / "stub-logs"
    stubs.mkdir(exist_ok=True)
    logs.mkdir(exist_ok=True)
    (stubs / "pg_dump").write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$@" > "$STUB_LOGS/pg_dump.args"\n'
        'env | grep "^PG" | sort > "$STUB_LOGS/pg_dump.env"\n'
        'for a in "$@"; do case "$a" in --file=*) '
        'printf "SYNTHETIC-DUMP" > "${a#--file=}";; esac; done\n',
        newline="\n",
    )
    (stubs / "pg_restore").write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$@" > "$STUB_LOGS/pg_restore.args"\n'
        'env | grep "^PG" | sort > "$STUB_LOGS/pg_restore.env"\n',
        newline="\n",
    )
    (stubs / "psql").write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$STUB_LOGS/psql.args"\necho {tables}\n',
        newline="\n",
    )
    for tool in stubs.iterdir():
        tool.chmod(0o755)
    return {
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "STUB_LOGS": logs.as_posix(),
        "DATABASE_URL": PG_URL,
    }


def _log(project: Project, name: str) -> str:
    return (project.root / "stub-logs" / name).read_text()


def test_postgres_backup_dumps_with_pg_dump_and_keeps_the_password_out_of_the_command_line(
    project: Project,
) -> None:
    env = _stub_tools(project)

    result = project.backup(**env)

    assert result.code == 0, result.text
    (archive,) = project.archives()
    manifest = _manifest(archive)
    assert manifest["db_kind"] == "postgres"
    assert manifest["db_file"] == "db/belgeee.pgdump"
    assert "db/belgeee.pgdump" in _members(archive)
    assert "db/belgeee.sqlite" not in _members(archive)
    with tarfile.open(archive) as handle:
        dump = handle.extractfile("db/belgeee.pgdump")
        assert dump is not None and dump.read() == b"SYNTHETIC-DUMP"
    arguments = _log(project, "pg_dump.args")
    assert "--format=custom" in arguments and "--no-owner" in arguments
    assert "s3cret" not in arguments  # parola `ps` çıktısında görünmez
    assert sorted(_log(project, "pg_dump.env").splitlines()) == [
        "PGDATABASE=belgeee_db",
        "PGHOST=db.example",
        "PGPASSWORD=s3cret!",
        "PGPORT=5433",
        "PGSSLMODE=require",
        "PGUSER=belgeee",
    ]
    # SQLite veritabanı postgres yedeğine girmez, ama veri dizini eksiksiz girer; canlı `.db` dahil.
    assert f"data/{DB_NAME}" in _members(archive)


@pytest.mark.skipif(shutil.which("pg_dump") is not None, reason="bu makinede pg_dump kurulu")
def test_postgres_backup_without_pg_dump_fails_clearly(project: Project) -> None:
    result = project.backup(DATABASE_URL=PG_URL)

    assert result.code != 0
    assert "pg_dump bulunamadı" in result.err
    assert not project.archives()


def test_postgres_restore_into_an_empty_database_runs_pg_restore(
    project: Project, tmp_path: Path
) -> None:
    env = _stub_tools(project)
    assert project.backup(**env).code == 0
    (archive,) = project.archives()
    target = tmp_path / "pg-hedef"

    result = project.restore(archive, **env, DATA_DIR=target.as_posix())

    assert result.code == 0, result.text
    arguments = _log(project, "pg_restore.args").splitlines()
    assert "--no-owner" in arguments and "--exit-on-error" in arguments
    assert "--dbname=belgeee_db" in arguments
    assert "--clean" not in arguments
    assert "s3cret" not in _log(project, "pg_restore.args")
    assert "PGPASSWORD=s3cret!" in _log(project, "pg_restore.env")
    assert arguments[-1].endswith("belgeee.pgdump")
    assert file_hashes(target)  # veri dizini de geri geldi


def test_postgres_restore_refuses_a_populated_database_unless_forced(
    project: Project, tmp_path: Path
) -> None:
    assert project.backup(**_stub_tools(project)).code == 0
    (archive,) = project.archives()
    populated = _stub_tools(project, tables="7")
    target = tmp_path / "pg-hedef"

    refused = project.restore(archive, **populated, DATA_DIR=target.as_posix())
    assert refused.code != 0
    assert "PostgreSQL veritabanında 7 tablo var" in refused.err
    assert not target.exists()
    assert not (project.root / "stub-logs" / "pg_restore.args").exists()

    forced = project.restore(archive, "--force", **populated, DATA_DIR=target.as_posix())
    assert forced.code == 0, forced.text
    arguments = _log(project, "pg_restore.args").splitlines()
    assert "--clean" in arguments and "--if-exists" in arguments


# --- betiklerin kendisi ------------------------------------------------------------------------


def test_scripts_are_lf_only_bash_with_valid_syntax(bash: str) -> None:
    scripts = sorted(SCRIPTS.glob("*.sh"))

    assert {script.name for script in scripts} >= {"backup.sh", "restore.sh", "backup-lib.sh"}
    for script in scripts:
        raw = script.read_bytes()
        assert raw.startswith(b"#!/usr/bin/env bash\n"), script.name
        assert b"\r" not in raw, f"{script.name}: CRLF bash'i bozar"
        checked = subprocess.run([bash, "-n", str(script)], capture_output=True, check=False)
        assert checked.returncode == 0, (script.name, checked.stderr)
