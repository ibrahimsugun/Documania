"""Katalog YAML dosyası (§8.6) ve başlangıç tohumu (00.6.2, 00.6.3).

`data/KnownDocuments/catalog.yaml` hem tohum hem dışa aktarım dosyasıdır (§8.2). Veri dizini
git dışında olduğu için başlangıç tohumu paketin içinde durur (`seed_catalog.yaml`) ve
açılışta, veri dizininde katalog dosyası yoksa oraya yazılır; varsa dokunulmaz.

Dışa aktarım biçimi kanoniktir: `dump_catalog_yaml(parse_catalog_yaml(metin))` kanonik metni
değiştirmez. Tohum dosyası da bu biçimde tutulur.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from app.catalog.schema import Catalog, CatalogError, validate_catalog
from app.storage import DataLayout, StoredFile, replace_file, write_file

SEED_RESOURCE = "seed_catalog.yaml"

CATALOG_HEADER = """\
# belgeee — belge türü kataloğu (PRD §8.6).
# Tohum ve dışa aktarım dosyası. Veritabanına yükleme: `python -m app.catalog import`;
# veritabanından yeniden üretme: `python -m app.catalog export`.
# Dosya bütün olarak doğrulanır: tek kayıt geçersizse hiçbir kayıt yüklenmez.
# Direkt Belge kuralı: `direct: true` olan türde `allowed_conversions: []` olmalıdır.
# Ön/arka yüzlü türde (`sides: front_back`) `front_back_layouts` en az bir düzen taşır
# (`separate`: ayrı sayfalar, `combined`: tek sayfa); `expected_pages` düzenlerden türetilir.
"""

# Tek satırda yazılan alanlar (§8.6 örneğindeki gibi): `[pdf, jpeg]`, `{min: 1, max: 1}`.
_FLOW_LISTS = (
    "expected_file_types",
    "front_back_layouts",
    "required_fields",
    "allowed_conversions",
)
_FLOW_MAPS = ("expected_pages",)
# Uzun açıklamalar alt satıra bölünmesin; elle düzenlenen dosyada her alan tek satırdır.
_NO_LINE_WRAP = 1 << 30


class _FlowList(list[Any]):
    pass


class _FlowMap(dict[str, Any]):
    pass


class _CatalogLoader(yaml.SafeLoader):
    """Tekrarlanan anahtarı reddeden güvenli yükleyici.

    PyYAML aynı anahtarın ikinci değerini sessizce alır; yanlışlıkla iki kez yazılmış bir
    `direct:` satırı böylece fark edilmeden kuralı değiştiremez.
    """


def _construct_mapping(loader: _CatalogLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "kayıt okunurken",
                node.start_mark,
                f"tekrarlanan anahtar: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


_CatalogLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


class _CatalogDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        # Anahtar altındaki liste maddeleri girintili yazılsın (§8.6 örneğindeki gibi).
        return super().increase_indent(flow, False)

    def ignore_aliases(self, data: Any) -> bool:
        return True


_CatalogDumper.add_representer(
    _FlowList,
    lambda dumper, data: dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True),
)
_CatalogDumper.add_representer(
    _FlowMap,
    lambda dumper, data: dumper.represent_mapping("tag:yaml.org,2002:map", data, flow_style=True),
)


def parse_catalog_yaml(content: str | bytes) -> Catalog:
    """YAML metnini okur ve doğrular; okunamaz veya geçersizse `CatalogError`."""
    try:
        data = yaml.load(content, Loader=_CatalogLoader)  # SafeLoader alt sınıfı: nesne kurmaz
    except yaml.YAMLError as exc:
        raise CatalogError([f"YAML okunamadı: {exc}"]) from None
    return validate_catalog(data)


def dump_catalog_yaml(catalog: Catalog) -> str:
    """Kataloğu kanonik YAML metnine çevirir (alan sırası §8.6, tüm alanlar açık yazılır; yalnız
    `archived_at` arşivli türde yazılır)."""
    records = []
    for entry in catalog:
        record = entry.model_dump(mode="json")
        # Arşiv alanı (11.1.6) yalnız arşivli türde yazılır: arşivsiz kayıtların (tohum dahil)
        # kanonik metni alan eklenmeden önceki gibi kalır.
        if record["archived_at"] is None:
            del record["archived_at"]
        for key in _FLOW_LISTS:
            record[key] = _FlowList(record[key])
        for key in _FLOW_MAPS:
            if record[key] is not None:
                record[key] = _FlowMap(record[key])
        records.append(record)
    body = yaml.dump(
        records,
        Dumper=_CatalogDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=_NO_LINE_WRAP,
    )
    return CATALOG_HEADER + body


def read_catalog_file(path: Path) -> Catalog:
    return parse_catalog_yaml(path.read_bytes())


def write_catalog_file(path: Path, catalog: Catalog) -> StoredFile:
    """Dışa aktarım: dosyayı atomik olarak yeniden üretir (`replace_file`, 00.4.4)."""
    return replace_file(path, dump_catalog_yaml(catalog).encode("utf-8"))


def seed_catalog_bytes() -> bytes:
    """Paketle gelen başlangıç tohumunun baytları."""
    return resources.files(__package__).joinpath(SEED_RESOURCE).read_bytes()


def load_seed_catalog() -> Catalog:
    return parse_catalog_yaml(seed_catalog_bytes())


def install_seed_catalog(layout: DataLayout) -> bool:
    """Veri dizininde `catalog.yaml` yoksa tohumu oraya yazar; yazdıysa `True`.

    Var olan dosyaya dokunulmaz — İK'nın düzenlediği veya dışa aktarılmış katalog korunur.
    """
    if layout.catalog_path.exists():
        return False
    try:
        write_file(layout.catalog_path, seed_catalog_bytes())
    except FileExistsError:
        return False  # aynı anda açılan başka bir süreç yazdı
    return True
