"""Inbox'a değişmez yazma (PRD 01.5.1, K10).

Inbox, yüklenen orijinal dosyanın ilk ve tek yazıldığı yerdir. `write_file`'ın sabit bağ
(`os.link`) garantisi sayesinde aynı yol ikinci kez yazılmaya çalışılırsa `FileExistsError`
fırlatılır — orijinal bir daha değiştirilemez, üzerine yazılamaz.
"""

from __future__ import annotations

from app.storage.atomic import Content, StoredFile, write_file
from app.storage.layout import DataLayout


def write_to_inbox(layout: DataLayout, upload_id: str, name: str, content: Content) -> StoredFile:
    """Dosyayı `Inbox/<upload_id>/<name>` altına yazar; aynı ada ikinci yazma reddedilir."""
    target = layout.upload_inbox_dir(upload_id) / name
    return write_file(target, content)
