"""`scripts/backup.sh` ve `scripts/restore.sh` testleri için ortak kurulum.

Betikler gerçekten çalıştırılır (kabuk + tar + python); dış servis yoktur. Windows'ta Git for
Windows'un bash'i kullanılır (WSL'in bash'i Windows yollarını anlamaz): uygun bir bash bulunamazsa
bu dizindeki testler atlanır. Veri sentetiktir (`tests/fixtures/gen.py`).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    AccessAction,
    AccessLog,
    Base,
    Document,
    Employee,
    KnownDocumentType,
    User,
)
from app.db.session import create_db_engine
from app.storage import prepare_data_dir
from tests.fixtures.gen import make_pdf_bytes

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
CONFIG_KEYS = (
    "DATABASE_URL",
    "DATA_DIR",
    "BACKUP_DIR",
    "BACKUP_KEEP_DAYS",
    "BACKUP_COPY_DIR",
    "BACKUP_SCP_TARGET",
    "ENV_FILE",
    "PYTHON",
)


def _bash_candidates() -> Iterator[str]:
    found = shutil.which("bash")
    if found:
        yield found
    git = shutil.which("git")
    if git:
        root = Path(git).resolve().parent.parent
        for relative in ("bin/bash.exe", "usr/bin/bash.exe"):
            yield str(root / relative)


def _usable(bash: str) -> bool:
    """GNU tar'lı ve (Windows'ta) MSYS tabanlı bash: WSL'in bash'i Windows yollarını çözemez."""
    if not Path(bash).exists():
        return False
    try:
        probe = subprocess.run(
            [bash, "-c", "uname -s; tar --version | head -n 1"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    kernel, _, tar = probe.stdout.partition("\n")
    if probe.returncode != 0 or "GNU tar" not in tar:
        return False
    return os.name != "nt" or kernel.startswith(("MSYS", "MINGW", "CYGWIN"))


@pytest.fixture(scope="session")
def bash() -> str:
    for candidate in _bash_candidates():
        if _usable(candidate):
            return candidate
    pytest.skip("GNU tar'lı bir bash bulunamadı (Windows'ta Git for Windows gerekir)")


@dataclass
class Result:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err


@dataclass
class Project:
    """Yedeklenecek örnek kurulum: veri dizini + SQLite veritabanı (`root/data/belgeee.db`)."""

    root: Path
    bash: str
    extra_env: dict[str, str] = field(default_factory=dict)

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def db(self) -> Path:
        return self.data / "belgeee.db"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    def env(self, **overrides: str | None) -> dict[str, str]:
        # Geliştiricinin kendi PG* ortamı sahte araç günlüklerine karışmasın.
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in CONFIG_KEYS and not key.startswith("PG")
        }
        env.update(
            DATABASE_URL=f"sqlite:///{self.db.as_posix()}",
            DATA_DIR=self.data.as_posix(),
            BACKUP_DIR=self.backups.as_posix(),
            PYTHON=Path(sys.executable).as_posix(),
        )
        env.update(self.extra_env)
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env

    def run(self, script: str, *args: str, **overrides: str | None) -> Result:
        completed = subprocess.run(
            [self.bash, str(SCRIPTS / script), *args],
            cwd=self.root,
            env=self.env(**overrides),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            check=False,
        )
        return Result(completed.returncode, completed.stdout, completed.stderr)

    def backup(self, **overrides: str | None) -> Result:
        return self.run("backup.sh", **overrides)

    def restore(self, archive: Path, *args: str, **overrides: str | None) -> Result:
        return self.run("restore.sh", *args, str(archive), **overrides)

    def archives(self, directory: Path | None = None) -> list[Path]:
        return sorted((directory or self.backups).glob("belgeee-*.tar.gz"))


def file_hashes(directory: Path, *, skip: set[str] | None = None) -> dict[str, str]:
    """Dizindeki her dosyanın (göreli yol → SHA-256) haritası."""
    skip = skip or set()
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.relative_to(directory).as_posix() not in skip
    }


def seed_project(project: Project) -> None:
    """Örnek kurulumu yazar: çalışan, belge dosyası, Inbox özgün dosyası ve erişim logu satırı."""
    layout = prepare_data_dir(project.data)
    engine = create_db_engine(f"sqlite:///{project.db.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=1, username="ik-yonetici", password_hash="yok", role="admin"))
        session.add(
            KnownDocumentType(
                slug="russian_passport",
                name="Rus Pasaportu",
                file_label="Pasaport",
                sides="single",
                direct=True,
                analyze=True,
                output_format="pdf",
            )
        )
        session.add(
            Employee(
                id="E0001",
                folder_name="Dmitry_Vasiliev_E0001",
                given_names="Dmitry",
                surname="Vasiliev",
            )
        )
        folder = layout.ensure_employee_tree("Dmitry_Vasiliev_E0001")
        received = folder / "Hazir" / "Dmitry_Vasiliev-Pasaport.pdf"
        received.write_bytes(make_pdf_bytes(2))
        document = Document(
            employee_id="E0001",
            type_slug="russian_passport",
            path=layout.relative(received),
            format="pdf",
            sequence_no=1,
            source_refs_json=[],
            status="active",
        )
        session.add(document)
        session.flush()
        session.add(
            AccessLog(user_id=1, document_id=document.id, action=AccessAction.VIEW, channel="web")
        )
        session.commit()
    engine.dispose()
    # Kabuk tırnaklamasını sınayan adlar: boşluk, Türkçe ve Kiril harf.
    inbox = project.data / "Inbox" / "u_20260919_0001"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "özgün dosya ğ.pdf").write_bytes(make_pdf_bytes(3))
    (inbox / "Васильев.jpg").write_bytes(b"\xff\xd8\xff synthetic jpeg bytes")


@pytest.fixture
def project(tmp_path: Path, bash: str) -> Project:
    root = tmp_path / "kurulum"
    root.mkdir()
    built = Project(root=root, bash=bash)
    seed_project(built)
    return built
