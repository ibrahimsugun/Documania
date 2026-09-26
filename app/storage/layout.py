"""Veri dizini düzeni — PRD §8.2 (00.4.1).

Dosya yolu üreten tek yer `app/storage/`'dır (MASTER-PROMPT §4 yol kuralı): başka modül dizge
birleştirerek yol kurmaz, `DataLayout` yöntemlerini çağırır.

```
data/
  Inbox/<upload_id>/              orijinaller, değişmez
  Employees/<Ad_Soyad_E0001>/
      Alinan/  Hazir/  profil.md
  Unknown/<upload_id>/            kaynak kopyası + reason.json
  Unreadable/<upload_id>/         kaynak kopyası + reason.json
  Unresolved/<upload_id>/         kaynak kopyası + reason.json
  Archive/<yyyy-mm>/              arşive taşınanlar
  KnownDocuments/
      catalog.yaml  examples/<tur_slug>/
      _ornek_envanteri.csv            örnek envanteri; harici toplayıcının ürünü (11.9.2)
      _egitim/gelen/<run>/            eğitim modunda yüklenen dosyaların kopyası (11.9)
      _egitim/haritalar/              yüklenen harita CSV'leri (11.9.5)
      _egitim/cikarilan/<tur_slug>/   örneklerden çıkarılanlar; silinmez (11.9.4)
  cache/pages/<file_id>/          analiz için üretilmiş sayfa görüntüleri
```

Açılışta sabit dizinler kurulur (`prepare_data_dir`); `<…>` kimlikli dizinler ilgili adım
çalışınca açılır. Kimlikten gelen her yol parçası `[A-Za-z0-9_-]` kümesinde olmalıdır —
`..`, `/` veya boş parça veri dizininin dışına çıkamaz.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.storage.atomic import remove_partial_writes

INBOX = "Inbox"
EMPLOYEES = "Employees"
RECEIVED = "Alinan"
READY = "Hazir"
PROFILE_FILE = "profil.md"
UNKNOWN = "Unknown"
UNREADABLE = "Unreadable"
UNRESOLVED = "Unresolved"
REASON_FILE = "reason.json"
ARCHIVE = "Archive"
KNOWN_DOCUMENTS = "KnownDocuments"
CATALOG_FILE = "catalog.yaml"
EXAMPLE_INVENTORY_FILE = "_ornek_envanteri.csv"
EXAMPLES = "examples"
TRAINING = "_egitim"
TRAINING_INCOMING = "gelen"
TRAINING_MAPS = "haritalar"
TRAINING_REMOVED = "cikarilan"
CACHE = "cache"
PAGES = "pages"
PAGE_IMAGE_EXTENSION = "jpg"

# Plan JSON `route` / `queue_items.kind` değeri → kuyruk dizini (PRD §8.5).
_QUEUE_DIRS = {"unknown": UNKNOWN, "unreadable": UNREADABLE, "unresolved": UNRESOLVED}

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,254}")


class DataLayout:
    """Veri kökünden §8.2 yollarını üretir; dizin açan yöntemler adında `ensure_` taşır."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # --- sabit dizinler ---------------------------------------------------------------------

    @property
    def inbox(self) -> Path:
        return self.root / INBOX

    @property
    def employees(self) -> Path:
        return self.root / EMPLOYEES

    @property
    def archive(self) -> Path:
        return self.root / ARCHIVE

    @property
    def known_documents(self) -> Path:
        return self.root / KNOWN_DOCUMENTS

    @property
    def examples(self) -> Path:
        return self.known_documents / EXAMPLES

    @property
    def training(self) -> Path:
        """`KnownDocuments/_egitim/` — eğitim modunun dosyaları (11.9). Örnek değildir: türlerin
        örnek klasörleri `examples/` altındadır."""
        return self.known_documents / TRAINING

    @property
    def training_maps(self) -> Path:
        return self.training / TRAINING_MAPS

    @property
    def page_cache(self) -> Path:
        return self.root / CACHE / PAGES

    @property
    def catalog_path(self) -> Path:
        return self.known_documents / CATALOG_FILE

    @property
    def example_inventory_path(self) -> Path:
        """`KnownDocuments/_ornek_envanteri.csv` — örneklerin kaynak ve SHA-256 envanteri; harici
        toplayıcı aracının ürünüdür, sistem yazmaz (mekanik tanıma okur, 11.9.2)."""
        return self.known_documents / EXAMPLE_INVENTORY_FILE

    def static_dirs(self) -> tuple[Path, ...]:
        """Açılışta var olması gereken dizinlerin tamamı."""
        queues = tuple(self.root / name for name in _QUEUE_DIRS.values())
        return (
            self.inbox,
            self.employees,
            *queues,
            self.archive,
            self.known_documents,
            self.examples,
            self.page_cache,
        )

    def ensure_tree(self) -> None:
        for directory in self.static_dirs():
            directory.mkdir(parents=True, exist_ok=True)

    # --- kimlikli yollar --------------------------------------------------------------------

    def upload_inbox_dir(self, upload_id: str) -> Path:
        return self.inbox / _segment(upload_id, "upload_id")

    def employee_dir(self, folder_name: str) -> Path:
        return self.employees / _segment(folder_name, "folder_name")

    def received_dir(self, folder_name: str) -> Path:
        """`Alinan/` — bu çalışana ait orijinallerin kopyası (K10)."""
        return self.employee_dir(folder_name) / RECEIVED

    def ready_dir(self, folder_name: str) -> Path:
        """`Hazir/` — çıktı belgeleri ve Attachment dosyaları."""
        return self.employee_dir(folder_name) / READY

    def profile_path(self, folder_name: str) -> Path:
        return self.employee_dir(folder_name) / PROFILE_FILE

    def ensure_employee_tree(self, folder_name: str) -> Path:
        """Çalışan klasörünü `Alinan/` ve `Hazir/` ile açar; klasör yolunu döndürür."""
        self.received_dir(folder_name).mkdir(parents=True, exist_ok=True)
        self.ready_dir(folder_name).mkdir(parents=True, exist_ok=True)
        return self.employee_dir(folder_name)

    def queue_dir(self, kind: str, upload_id: str) -> Path:
        """`Unknown/`, `Unreadable/` veya `Unresolved/` altında partinin dizini."""
        try:
            queue = _QUEUE_DIRS[kind]
        except KeyError:
            raise ValueError(f"Geçersiz kuyruk türü: {kind!r}") from None
        return self.root / queue / _segment(upload_id, "upload_id")

    def queue_reason_path(self, kind: str, upload_id: str) -> Path:
        return self.queue_dir(kind, upload_id) / REASON_FILE

    def archive_dir(self, day: date) -> Path:
        """`Archive/<yyyy-mm>/` — ay, taşımanın yapıldığı günden alınır."""
        return self.archive / f"{day:%Y-%m}"

    def type_examples_dir(self, type_slug: str) -> Path:
        return self.examples / _segment(type_slug, "type_slug")

    def training_incoming_dir(self, run_id: int | str) -> Path:
        """`_egitim/gelen/<run>/` — eğitim çalıştırmasında yüklenen dosyaların kopyası."""
        return self.training / TRAINING_INCOMING / _segment(str(run_id), "run_id")

    def training_staged_path(self, run_id: int | str, item_id: int | str, extension: str) -> Path:
        """`_egitim/gelen/<run>/<item>.<ext>` — eğitim öğesinin içeriği (uzantı içerikten gelir)."""
        name = f"{_segment(str(item_id), 'item_id')}.{_segment(extension, 'extension')}"
        return self.training_incoming_dir(run_id) / name

    def training_map_path(self, run_id: int | str) -> Path:
        """`_egitim/haritalar/<run>.csv` — toplu taramanın (11.9.5) yüklendiği haliyle haritası."""
        return self.training_maps / f"{_segment(str(run_id), 'run_id')}.csv"

    def training_removed_dir(self, type_slug: str) -> Path:
        """`_egitim/cikarilan/<tur_slug>/` — örneklerden çıkarılanlar; silinmez (11.9.4)."""
        return self.training / TRAINING_REMOVED / _segment(type_slug, "type_slug")

    def page_cache_dir(self, file_id: int | str) -> Path:
        return self.page_cache / _segment(str(file_id), "file_id")

    def page_image_path(
        self, file_id: int | str, page_index: int, extension: str = PAGE_IMAGE_EXTENSION
    ) -> Path:
        """`cache/pages/<file_id>/0000.<extension>` — 0 tabanlı sayfa sırasıyla analiz görüntüsü.

        `extension` varsayılanı PDF sayfa render'ının her zaman ürettiği `jpg`'dir; görüntü
        dosyası analiz kopyası (02.3.1) kaynağın kendi biçimini (`jpg`/`png`) kullanır.
        """
        if page_index < 0:
            raise ValueError(f"Geçersiz sayfa sırası: {page_index!r}")
        return self.page_cache_dir(file_id) / f"{page_index:04d}.{extension}"

    # --- veritabanında saklanan göreli yollar -----------------------------------------------

    def resolve(self, relative_path: str) -> Path:
        """Veri köküne göreli saklanan yolu (`stored_path`, `image_path`) mutlak yola çevirir.

        Mutlak yol, `..`/`.` parçası, ters bölü veya kökten kaçan (ör. Windows sürücü) parça
        reddedilir — veritabanındaki bir değer veri dizininin dışını gösteremez.
        """
        parts = relative_path.split("/")
        if "\\" in relative_path or any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"Geçersiz göreli yol: {relative_path!r}")
        path = self.root.joinpath(*parts)
        if not path.is_relative_to(self.root) or path.relative_to(self.root).parts != tuple(parts):
            raise ValueError(f"Geçersiz göreli yol: {relative_path!r}")
        return path

    def relative(self, path: Path) -> str:
        """Veri kökü altındaki yolu veritabanında saklanan göreli biçime çevirir (`resolve`'un
        tersi).

        Kökün dışındaki ya da kökün kendisi olan yol `ValueError`; dönen değer `resolve`'dan geçer.
        """
        relative_path = Path(path).relative_to(self.root).as_posix()
        self.resolve(relative_path)
        return relative_path


def prepare_data_dir(root: Path) -> DataLayout:
    """Uygulama açılışı: §8.2 ağacını kurar, öldürülmüş yazmalardan kalanları temizler."""
    layout = DataLayout(root)
    layout.ensure_tree()
    remove_partial_writes(layout.root)
    return layout


def _segment(value: str, name: str) -> str:
    if not _SEGMENT.fullmatch(value):
        raise ValueError(f"Geçersiz yol parçası ({name}): {value!r}")
    return value
