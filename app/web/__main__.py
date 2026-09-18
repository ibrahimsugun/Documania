"""Panel kullanıcısı komutu (PRD 10.1.3): komut satırından ilk yönetici oluşturulur.

    python -m app.web create-admin --username AD                   # parola iki kez sorulur
    echo "$PAROLA" | python -m app.web create-admin --username AD --password-stdin

Parola komut satırı argümanı olarak alınmaz (kabuk geçmişine ve süreç listesine düşmesin); ya
terminalden gizli sorulur ya da standart girdinin ilk satırından okunur. Bağlantı dizesi
`app.config` ayarlarından gelir; şema önceden `alembic upgrade head` ile kurulmuş olmalıdır.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence

from app.config import get_settings
from app.db.models import UserRole
from app.db.session import create_db_engine, create_session_factory
from app.web.auth import UserCreationError, create_user


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.web", description="Panel kullanıcıları")
    commands = parser.add_subparsers(dest="command", required=True)
    create_admin = commands.add_parser("create-admin", help="panel yöneticisi oluşturur")
    create_admin.add_argument("--username", required=True, help="giriş adı")
    create_admin.add_argument(
        "--password-stdin",
        action="store_true",
        help="parolayı terminalden sormak yerine standart girdinin ilk satırından okur",
    )
    return parser


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass("Parola: ")
    if getpass.getpass("Parola (tekrar): ") != password:
        raise UserCreationError("Parolalar eşleşmiyor.")
    return password


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        password = _read_password(args.password_stdin)
    except UserCreationError as exc:
        print(exc, file=sys.stderr)
        return 1

    engine = create_db_engine(get_settings().database_url)
    try:
        with create_session_factory(engine)() as session:
            user = create_user(session, args.username, password, role=UserRole.ADMIN)
            session.commit()
    except UserCreationError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(f"Yönetici oluşturuldu: {user.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
