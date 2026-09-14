"""Katalog eşitleme komutu (00.6.3).

    python -m app.catalog import [--file YOL]   # YAML → veritabanı
    python -m app.catalog export [--file YOL]   # veritabanı → YAML

`--file` verilmezse veri dizinindeki `KnownDocuments/catalog.yaml` kullanılır; içe aktarmada o
dosya yoksa önce başlangıç tohumu oraya yazılır. Bağlantı dizesi ve veri dizini `app.config`
ayarlarından gelir; şema önceden `alembic upgrade head` ile kurulmuş olmalıdır.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.catalog.schema import CatalogError
from app.catalog.sync import export_catalog, import_catalog
from app.catalog.yaml_io import install_seed_catalog, read_catalog_file, write_catalog_file
from app.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.storage import DataLayout


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.catalog", description="Belge türü kataloğu YAML ↔ veritabanı"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("import", "YAML kataloğunu doğrulayıp veritabanına yazar"),
        ("export", "veritabanındaki kataloğu YAML dosyasına yazar"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--file", type=Path, help="katalog dosyası (varsayılan: veri dizini)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    layout = DataLayout(settings.data_dir)
    path: Path = args.file or layout.catalog_path

    engine = create_db_engine(settings.database_url)
    try:
        if args.command == "import":
            if args.file is None and install_seed_catalog(layout):
                print(f"Başlangıç tohumu yazıldı: {path}")
            catalog = read_catalog_file(path)
            with create_session_factory(engine)() as session:
                result = import_catalog(session, catalog)
                session.commit()
            print(
                f"Katalog yüklendi ({len(catalog)} tür): {len(result.created)} yeni, "
                f"{len(result.updated)} güncellendi, {len(result.unchanged)} aynı."
            )
            if result.not_in_catalog:
                print(f"Dosyada olmayan, dokunulmayan türler: {', '.join(result.not_in_catalog)}")
        else:
            with create_session_factory(engine)() as session:
                catalog = export_catalog(session)
            write_catalog_file(path, catalog)
            print(f"Katalog dışa aktarıldı ({len(catalog)} tür): {path}")
    except CatalogError as exc:
        print(exc, file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Katalog dosyası bulunamadı: {exc.filename}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
