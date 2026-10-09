"""Panel kullanıcısı komutları (PRD 10.1.3, 10.1.8; PLAN.md §D115 b).

    python -m app.web create-user --username AD --role hr          # İK; parola iki kez sorulur
    python -m app.web create-user --username AD --role user        # salt okunur Kullanıcı
    python -m app.web create-root --username AD                    # tek root; ikincisi reddedilir
    echo "$PAROLA" | python -m app.web create-user --username AD --role hr --password-stdin

Root yalnız buradan açılır (panel root üretmez ve atamaz); sistemde root varsa `create-root` hata
verir. Parola komut satırı argümanı olarak alınmaz (kabuk geçmişine ve süreç listesine düşmesin); ya
terminalden gizli sorulur ya da standart girdinin ilk satırından okunur. Bağlantı dizesi
`app.config` ayarlarından gelir; şema önceden `alembic upgrade head` ile kurulmuş olmalıdır.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db.models import UserRole
from app.db.session import create_db_engine, create_session_factory
from app.web.auth import ASSIGNABLE_ROLES, UserCreationError, create_root, create_user

ROOT_EXISTS = "Sistemde zaten bir root var; ikinci root açılamaz."
USERNAME_RACE = "Kullanıcı adı aynı anda başka bir işlemle alındı; başka bir ad deneyin."
CREATED = {
    UserRole.HR: "İK kullanıcısı oluşturuldu",
    UserRole.USER: "Kullanıcı (salt okunur) oluşturuldu",
    UserRole.ROOT: "Root oluşturuldu",
}


def _add_common(command: argparse.ArgumentParser) -> None:
    command.add_argument("--username", required=True, help="giriş adı")
    command.add_argument(
        "--password-stdin",
        action="store_true",
        help="parolayı terminalden sormak yerine standart girdinin ilk satırından okur",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.web", description="Panel kullanıcıları")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="İK ya da salt okunur Kullanıcı oluşturur")
    _add_common(create)
    create.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in ASSIGNABLE_ROLES],
        help="hr: İK, bütün yazma işlemleri; user: Kullanıcı, panel salt okunur",
    )
    root = commands.add_parser("create-root", help="tek root'u oluşturur (root varsa reddeder)")
    _add_common(root)
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

    role = UserRole.ROOT if args.command == "create-root" else UserRole(args.role)
    engine = create_db_engine(get_settings().database_url)
    try:
        with create_session_factory(engine)() as session:
            if role is UserRole.ROOT:
                user = create_root(session, args.username, password)
            else:
                user = create_user(session, args.username, password, role=role)
            session.commit()
    except UserCreationError as exc:
        print(exc, file=sys.stderr)
        return 1
    except IntegrityError:
        # Yarış: aynı anda iki `create-root`'un ikincisini `uq_users_single_root`, aynı adı
        # `users.username` tekilliği reddeder.
        print(ROOT_EXISTS if role is UserRole.ROOT else USERNAME_RACE, file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(f"{CREATED[role]}: {user.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
