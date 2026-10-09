"""10.1.3, 10.1.8 — komut satırından İK, Kullanıcı ve tek root açılır: `python -m app.web
create-user --role hr|user` ve `create-root` (ikinci root reddedilir)."""

import io
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import create_db_engine, create_session_factory, get_session
from app.main import create_app
from app.storage import prepare_data_dir
from app.web.__main__ import main
from app.web.routers.uploads import get_layout

REPO_ROOT = Path(__file__).resolve().parents[2]
USERNAME = "yonetici"
PASSWORD = "ilk-yonetici-parolasi"
CREATE_HR = ["create-user", "--username", USERNAME, "--role", "hr", "--password-stdin"]


@pytest.fixture
def environment(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _users(session_factory: sessionmaker[Session]) -> list[User]:
    with session_factory() as session:
        return list(session.scalars(select(User).order_by(User.id)))


def _stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def _typed(monkeypatch: pytest.MonkeyPatch, *answers: str) -> list[str]:
    prompts: list[str] = []
    replies = iter(answers)

    def _getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        return next(replies)

    monkeypatch.setattr("getpass.getpass", _getpass)
    return prompts


def test_create_user_reads_the_password_from_stdin(
    environment: None,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stdin(monkeypatch, f"{PASSWORD}\r\n")

    assert main(CREATE_HR) == 0

    (user,) = _users(session_factory)
    assert (user.username, user.role) == (USERNAME, "hr")
    assert user.password_hash.startswith("$argon2id$")
    assert PasswordHasher().verify(user.password_hash, PASSWORD)
    output = capsys.readouterr()
    assert output.out.strip() == f"İK kullanıcısı oluşturuldu: {USERNAME}"
    assert PASSWORD not in output.out + output.err


def test_create_user_asks_for_the_password_twice_without_echo(
    environment: None,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = _typed(monkeypatch, PASSWORD, PASSWORD)

    assert main(["create-user", "--username", USERNAME, "--role", "user"]) == 0

    assert prompts == ["Parola: ", "Parola (tekrar): "]
    (user,) = _users(session_factory)
    assert user.role == "user"
    assert PasswordHasher().verify(user.password_hash, PASSWORD)


def test_create_user_refuses_mismatched_passwords(
    environment: None,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _typed(monkeypatch, PASSWORD, PASSWORD + "x")

    assert main(["create-user", "--username", USERNAME, "--role", "hr"]) == 1

    assert "Parolalar eşleşmiyor." in capsys.readouterr().err
    assert _users(session_factory) == []


@pytest.mark.parametrize(
    ("username", "password", "message"),
    [
        (USERNAME, PASSWORD, "zaten kullanılıyor"),
        ("ikinci", "kisa", "en az 12"),
        ("ikinci", "on-bir-harf", "en az 12"),
        ("ab", PASSWORD, "en az 3"),
        ("ad soyad", PASSWORD, "boşluk"),
    ],
)
def test_create_user_reports_invalid_input_and_writes_nothing(
    environment: None,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    username: str,
    password: str,
    message: str,
) -> None:
    _stdin(monkeypatch, f"{PASSWORD}\n")
    assert main(CREATE_HR) == 0
    capsys.readouterr()

    _stdin(monkeypatch, f"{password}\n")
    assert main(["create-user", "--username", username, "--role", "hr", "--password-stdin"]) == 1

    assert message in capsys.readouterr().err
    assert [user.username for user in _users(session_factory)] == [USERNAME]


@pytest.mark.parametrize(
    "arguments",
    [
        ["create-user", "--role", "hr"],
        ["create-user", "--username", USERNAME],
        ["create-user", "--username", USERNAME, "--role", "root"],
        ["create-user", "--username", USERNAME, "--role", "admin"],
        ["create-root"],
        ["create-admin", "--username", USERNAME],
    ],
    ids=["no-username", "no-role", "root-role", "admin-role", "root-no-username", "old"],
)
def test_the_command_requires_a_username_and_an_assignable_role(arguments: list[str]) -> None:
    # 10.1.8: root yalnız create-root ile açılır; create-user rolü yalnız hr ya da user.
    with pytest.raises(SystemExit) as caught:
        main(arguments)

    assert caught.value.code == 2


def test_create_root_opens_the_single_root_and_refuses_a_second_one(
    environment: None,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stdin(monkeypatch, f"{PASSWORD}\n")
    assert main(["create-root", "--username", "Zvz", "--password-stdin"]) == 0
    assert capsys.readouterr().out.strip() == "Root oluşturuldu: Zvz"

    _stdin(monkeypatch, f"{PASSWORD}\n")
    assert main(["create-root", "--username", "ikinci-root", "--password-stdin"]) == 1

    assert "ikinci root açılamaz" in capsys.readouterr().err
    assert [(user.username, user.role) for user in _users(session_factory)] == [("Zvz", "root")]


def test_admin_created_from_the_command_line_can_sign_in_and_open_the_panel(
    tmp_path: Path,
) -> None:
    # Uçtan uca: göçlü temiz veritabanı → komut satırı (ayrı süreç) → panel girişi.
    database_url = f"sqlite:///{(tmp_path / 'panel.db').as_posix()}"
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")

    arguments = CREATE_HR
    result = subprocess.run(
        [sys.executable, "-m", "app.web", *arguments],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": database_url, "PYTHONIOENCODING": "utf-8"},
        input=f"{PASSWORD}\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert f"İK kullanıcısı oluşturuldu: {USERNAME}" in result.stdout

    engine = create_db_engine(database_url)
    factory = create_session_factory(engine)
    layout = prepare_data_dir(tmp_path / "data")
    application = create_app()

    def _override_get_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    application.dependency_overrides[get_session] = _override_get_session
    application.dependency_overrides[get_layout] = lambda: layout
    application.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url=database_url
    )
    try:
        client = TestClient(application)
        assert client.get("/upload", follow_redirects=False).status_code == 303

        response = client.post(
            "/login",
            data={"username": USERNAME, "password": PASSWORD, "next": "/upload"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/upload"
        for path in ("/upload", "/employees", "/queues", "/document-types", "/uploads"):
            assert client.get(path, follow_redirects=False).status_code == 200, path
    finally:
        engine.dispose()
