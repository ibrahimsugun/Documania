"""13.4.2 — yedekleme prosedürü yazılıdır ve betiklerle çelişmez.

Betiklerin okuduğu her `BACKUP_*` ayarı `docs/YEDEKLEME.md`'de ve `.env.example`'da geçer; prosedür
iki betiği de adıyla anar ve denenmiş olduğunu kaydeder. Kabuk gerekmez.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = (ROOT / "docs" / "YEDEKLEME.md").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")


def _settings_read_by_the_scripts() -> set[str]:
    found: set[str] = set()
    for script in (ROOT / "scripts").glob("*.sh"):
        found |= set(re.findall(r"\bBACKUP_[A-Z_]+\b", script.read_text(encoding="utf-8")))
    return found


def test_every_backup_setting_is_documented() -> None:
    settings = _settings_read_by_the_scripts()

    assert settings >= {"BACKUP_DIR", "BACKUP_KEEP_DAYS", "BACKUP_COPY_DIR", "BACKUP_SCP_TARGET"}
    for setting in sorted(settings):
        assert f"`{setting}`" in DOC, f"{setting} docs/YEDEKLEME.md'de yok"
        assert re.search(rf"^# ?{setting}=", ENV_EXAMPLE, re.M), f"{setting} .env.example'da yok"


def test_procedure_names_both_scripts_and_records_the_drill() -> None:
    assert "scripts/backup.sh" in DOC and "scripts/restore.sh" in DOC
    assert "## Deneme kaydı" in DOC
    assert "test_restore_drill_into_a_fresh_location" in DOC
    assert "test_restore_drill_after_the_server_is_lost" in DOC
    # Sunucu dışı kopya ve gece zamanlaması prosedürde anlatılır.
    assert "cron" in DOC and "Sunucu dışı kopya" in DOC
    assert "alembic upgrade head" in DOC


def test_backups_are_never_committed() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "backups/" in ignored
