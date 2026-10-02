"""12.1.5 — yerel başlatıcıda bot (tm 150, PLAN.md §D87 (e), §D90).

`baslat.bat` `.env`'de `TELEGRAM_BOT_TOKEN` doluysa botu panelle birlikte ayrı pencerede açar, boşsa
"Telegram botu kapalı" der ve botsuz devam eder. Token değeri ekrana asla yazılmaz. Üç katman:
dosyanın içeriği (CRLF, sıra, `>nul`), denetimin Python ifadesi (her platformda, gerçek `.env`
dosyalarıyla) ve Windows'ta bat bloğunun kendisi (gerçek `cmd`; bot yerine `echo`). Token
sentetiktir; ağ ve gerçek bot yoktur.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BAT = ROOT / "baslat.bat"
FAKE_TOKEN = "123456:SENTETIK-sahte-token"
CLOSED_MESSAGE = "Telegram botu kapali: .env'de TELEGRAM_BOT_TOKEN yok"


def _lines() -> list[str]:
    return BAT.read_bytes().decode("ascii").split("\r\n")


def _index(prefix: str) -> int:
    return next(i for i, line in enumerate(_lines()) if line.lstrip().startswith(prefix))


def _check_line() -> str:
    return next(line for line in _lines() if "get_secret_value" in line)


def _check_snippet() -> str:
    """Bat satırındaki `-c "..."` ifadesi, olduğu gibi."""
    match = re.search(r'-c "(?P<code>[^"]+)"', _check_line())
    assert match is not None
    return match.group("code")


def test_launcher_keeps_crlf_and_plain_ascii() -> None:
    raw = BAT.read_bytes()

    assert raw.count(b"\n") == raw.count(b"\r\n") > 0, "çıplak LF var: cmd.exe CRLF bekler"
    raw.decode("ascii")  # chcp 65001 altında çok baytlı karakter bat ayrıştırmasını bozar
    assert "*.bat text eol=crlf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")


def test_bot_starts_in_its_own_window_with_the_bot_module() -> None:
    start = next(line for line in _lines() if line.lstrip().startswith('start "Documania bot"'))

    assert "-m app.telegram.bot" in start
    assert "%PY%" in start, "bot, panelle aynı sanal ortamın Python'uyla açılır"
    assert "cmd /k" in start, "bot hata verip kapanırsa pencere nedeniyle birlikte kaybolmaz"


def test_bot_starts_only_after_migration_and_before_the_server() -> None:
    migrate = _index('"%PY%" -m alembic upgrade head')
    check = next(i for i, line in enumerate(_lines()) if "get_secret_value" in line)
    start = _index('start "Documania bot"')
    server = _index('"%PY%" -m uvicorn')

    assert migrate < check < start < server


def test_missing_token_says_so_and_goes_on_without_the_bot() -> None:
    lines = _lines()
    closed = next(i for i, line in enumerate(lines) if CLOSED_MESSAGE in line)
    start = _index('start "Documania bot"')

    assert lines[closed - 1].strip() == "if errorlevel 1 (", "boşsa bot kolu atlanır"
    assert lines[closed + 1].strip() == ") else (", "bot yalnız token doluyken açılır"
    assert closed + 1 < start < _index("echo [3/4]")
    assert "exit" not in "".join(lines[closed - 1 : start + 2]), (
        "botsuz açılış panelin açılışını bozmaz"
    )


def test_the_token_value_is_never_printed() -> None:
    lines = _lines()

    # Denetim çıktısı atılır: yalnız çıkış kodu okunur.
    assert _check_line().rstrip().endswith(">nul 2>&1")
    assert "print" not in _check_snippet()
    for line in lines:
        assert not re.search(r"[%!]TELEGRAM_BOT_TOKEN[%!]", line, re.I), line
        # .env'i ekrana basabilecek komutlar (findstr/type/more) bat'ta hiç yok.
        assert not re.search(r"\b(findstr|type|more|set /p)\b", line, re.I), line


def test_readme_explains_how_to_get_the_token_and_open_the_bot() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    note = next(par for par in readme.split("\n- ") if "baslat.bat` ile açılır" in par)

    for needle in ("TELEGRAM_BOT_TOKEN", "BotFather", "/newbot", ".env", "baslat.bat", "yeniden"):
        assert needle in note, needle


def _run_check(tmp_path: Path, env_file: str | None, env: dict[str, str] | None = None):
    if env_file is not None:
        (tmp_path / ".env").write_text(env_file, encoding="utf-8")
    clean = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("TELEGRAM_", "DATABASE_URL"))
    }
    clean["PYTHONPATH"] = str(
        ROOT
    )  # `app` temp dizinden de bulunur; .env yine temp dizinden okunur
    return subprocess.run(
        [sys.executable, "-c", _check_snippet()],
        cwd=tmp_path,
        env={**clean, **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize(
    ("env_file", "env"),
    [
        pytest.param(None, None, id="env-yok"),
        pytest.param("DATABASE_URL=sqlite:///x.db\n", None, id="satir-yok"),
        pytest.param("DATABASE_URL=sqlite:///x.db\nTELEGRAM_BOT_TOKEN=\n", None, id="bos"),
        pytest.param("DATABASE_URL=sqlite:///x.db\nTELEGRAM_BOT_TOKEN=   \n", None, id="bosluk"),
        # Tırnak içindeki boşluk dotenv'de kırpılmaz; botun denetimi (`_reveal`) onu boş sayar.
        pytest.param(
            'DATABASE_URL=sqlite:///x.db\nTELEGRAM_BOT_TOKEN="   "\n', None, id="tirnakli-bosluk"
        ),
        pytest.param(
            'DATABASE_URL=sqlite:///x.db\nTELEGRAM_BOT_TOKEN=""\n', None, id="tirnakli-bos"
        ),
    ],
)
def test_check_reports_a_missing_token(
    tmp_path: Path, env_file: str | None, env: dict[str, str] | None
) -> None:
    result = _run_check(tmp_path, env_file, {"DATABASE_URL": "sqlite:///x.db", **(env or {})})

    assert result.returncode == 1
    assert result.stdout == "" and result.stderr == ""


@pytest.mark.parametrize(
    ("env_file", "env"),
    [
        pytest.param(
            f"DATABASE_URL=sqlite:///x.db\nTELEGRAM_BOT_TOKEN={FAKE_TOKEN}\n", None, id="env"
        ),
        pytest.param(
            f'DATABASE_URL=sqlite:///x.db\nTELEGRAM_BOT_TOKEN="{FAKE_TOKEN}"\n', None, id="tirnakli"
        ),
        pytest.param(
            None, {"DATABASE_URL": "sqlite:///x.db", "TELEGRAM_BOT_TOKEN": FAKE_TOKEN}, id="ortam"
        ),
    ],
)
def test_check_accepts_a_filled_token_and_prints_nothing(
    tmp_path: Path, env_file: str | None, env: dict[str, str] | None
) -> None:
    result = _run_check(tmp_path, env_file, env)

    assert result.returncode == 0
    assert result.stdout == "" and result.stderr == ""


@pytest.mark.skipif(sys.platform != "win32", reason="bat bloğu yalnız Windows'ta çalışır")
@pytest.mark.parametrize(("token", "expected"), [("", "closed"), (FAKE_TOKEN, "opens")])
def test_the_bat_block_runs_in_a_real_cmd(tmp_path: Path, token: str, expected: str) -> None:
    lines = _lines()
    begin, end = _index("echo [2/4]"), _index("echo [3/4]")
    block = [
        # Gerçek bot (sahte token, ağ) açılmasın: start satırı yalnız yazdırılır.
        "  echo BASLATILIR: " + line.strip() if line.lstrip().startswith("start ") else line
        for line in lines[begin : end - 1]
    ]
    runner = f'@echo off\r\nset "PY={sys.executable}"\r\n' + "\r\n".join(block) + "\r\n"
    (tmp_path / "run.bat").write_bytes(runner.encode("ascii"))
    (tmp_path / ".env").write_text(
        f"DATABASE_URL=sqlite:///x.db\nTELEGRAM_BOT_TOKEN={token}\n", encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("TELEGRAM_")}
    env["PYTHONPATH"] = str(ROOT)

    result = subprocess.run(
        ["cmd.exe", "/c", str(tmp_path / "run.bat")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert FAKE_TOKEN not in result.stdout + result.stderr
    if expected == "closed":
        assert CLOSED_MESSAGE in result.stdout
        assert "BASLATILIR" not in result.stdout
    else:
        assert CLOSED_MESSAGE not in result.stdout
        assert "BASLATILIR: start" in result.stdout
        assert "-m app.telegram.bot" in result.stdout
