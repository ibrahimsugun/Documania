"""Çeviri kataloğu komutu (PRD 10.10.3; PLAN.md §D92 e).

    python -m app.i18n extract   # işaretli metinler → app/i18n/locales/messages.pot
    python -m app.i18n update    # messages.pot → en, sr messages.po (yeni metin boş çeviriyle)
    python -m app.i18n compile   # messages.po → messages.mo (çalışma zamanı bunu okur)
    python -m app.i18n check     # bütünlük; sorun varsa listeler ve 1 ile çıkar

Ayrıntı `app.i18n.tools`'ta. Depo kökünden çalıştırılır (`babel.cfg` oradadır).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from app.i18n import tools

COMMANDS = {
    "extract": "işaretli metinleri kaynaktan messages.pot'a çıkarır",
    "update": "her dilin messages.po'sunu messages.pot'a eşitler",
    "compile": "messages.po'ları messages.mo'ya derler",
    "check": "kataloğun bütünlüğünü denetler (boş, bulanık, eksik, yer tutucu, eski .mo)",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.i18n", description="Arayüz çevirileri")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        commands.add_parser(name, help=help_text)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Çıktı yönlendirildiğinde konsol kodlaması Sırpça/Türkçe harfi yazamayabilir.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    command = _parser().parse_args(argv).command
    if command == "extract":
        changed = tools.extract()
        print(f"{tools.TEMPLATE_NAME}: {'güncellendi' if changed else 'değişiklik yok'}")
        return 0
    if command == "update":
        paths = tools.update()
        print("\n".join(f"güncellendi: {path}" for path in paths) or "değişiklik yok")
        return 0
    if command == "compile":
        paths = tools.compile_catalogs()
        print("\n".join(f"derlendi: {path}" for path in paths) or "değişiklik yok")
        return 0
    problems = tools.check()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} sorun.", file=sys.stderr)
        return 1
    print("katalog temiz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
