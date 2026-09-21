"""Çalışan profili yönetici komutları.

    python -m app.profiles repair-latin-names [--dry-run] [--actor AD]

`repair-latin-names` (PRD 05.2.2, PLAN.md §C81): ad, soyad ya da diğer isimler alanında Latin
olmayan harf taşıyan çalışanları onarır (`app.profiles.latin_names`). Tekrar çalıştırılabilir:
ikinci çalıştırma değişiklik yapmaz. Onarılan çalışanın klasörü varsa `profil.md`'si güncel
kayıttan yeniden üretilir (09.1.1); klasör adı değişmez (K8). `--dry-run` yalnız ne yapılacağını
yazar. Çıktı yalnız E numarası ve alan adı taşır, kişisel değer taşımaz (CONVENTIONS §6).
Bağlantı dizesi ve veri dizini `app.config` ayarlarından gelir; şema önceden `alembic upgrade
head` ile kurulmuş olmalıdır.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.config import get_settings
from app.db.models import Employee
from app.db.session import create_db_engine, create_session_factory
from app.profiles.latin_names import LatinRepair, repair_latin_names
from app.profiles.render import write_profile
from app.storage import DataLayout


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.profiles", description="Çalışan profili")
    commands = parser.add_subparsers(dest="command", required=True)
    repair = commands.add_parser(
        "repair-latin-names",
        help="Latin alanlarında Latin olmayan yazım taşıyan çalışanları onarır (05.2.2)",
    )
    repair.add_argument(
        "--dry-run", action="store_true", help="yalnız ne yapılacağını yazar, kaydetmez"
    )
    repair.add_argument("--actor", default="system", help="olay logundaki kullanıcı adı")
    return parser


def _describe(repair: LatinRepair) -> str:
    filled = ", ".join(f"{name} ({source.value})" for name, source in repair.filled) or "yok"
    line = f"{repair.employee_id}: yazılan {filled}"
    if repair.latin_missing:
        line += f"; Latin yazım eksik: {', '.join(repair.latin_missing)}"
    return line


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    layout = DataLayout(settings.data_dir)
    engine = create_db_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            repairs = repair_latin_names(session, actor=args.actor, dry_run=args.dry_run)
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
                for repair in repairs:
                    employee = session.get_one(Employee, repair.employee_id)
                    if repair.filled and layout.employee_dir(employee.folder_name).is_dir():
                        write_profile(session, layout, employee)
    finally:
        engine.dispose()
    for repair in repairs:
        print(_describe(repair))
    verb = "onarılacak" if args.dry_run else "onarıldı"
    print(f"Latin ad onarımı: {len(repairs)} çalışan {verb}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
