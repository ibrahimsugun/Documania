"""11.8.1 testleri için: saklı fotoğraf kontrolü (`pages.photo_check_json`) taşıyan çıktı belgeleri.

Boru hattını koşmadan, planın ve uygulayıcının yazacağı satırları doğrudan kurar: parti, dosya,
sayfalar (kontrolleriyle), çalışanın Hazir klasöründe dosya ve `documents` satırı. Fotoğraflar
`tests/fixtures/gen.py`'nin sentetik siluetleridir (gerçek kişi yok). Uçtan uca akış
`tests/test_scenarios_s01_s05.py`'dedir.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.catalog import enabled_photo_rules
from app.db.models import Document, DocumentStatus, Employee, Page, Upload, UploadFile, UploadStatus
from app.storage import DataLayout
from tests.fixtures.gen import make_portrait_image_bytes

PHOTO = "profile_picture"
EMPLOYEE_ID = "E0001"
FOLDER = "Test_Ornek_E0001"
# Varsayılan kural setinde açık kurallar (kayıt `null`), katalog sırasıyla.
OPEN_RULES = tuple(rule.id for rule in enabled_photo_rules(None))
FIRST_DAY = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def stored_check(
    results: Mapping[str, str] | None = None, *, rules: Sequence[str] = OPEN_RULES
) -> dict[str, Any]:
    """Sayfaya saklanan kontrol (`PhotoCheck` biçimi): `rules`'un her biri, verilmeyen `pass`."""
    given = dict(results or {})
    return {
        "rules": [
            {
                "rule": rule,
                "result": given.get(rule, "pass"),
                "note": None if given.get(rule, "pass") == "pass" else "Sentetik not.",
            }
            for rule in rules
        ]
    }


class PhotoRows:
    """Tek çalışanın çıktı belgelerini sırayla kurar; her belge ayrı bir partidendir. Oturum
    commit edilmez, `flush` edilir."""

    def __init__(self, session: Session, layout: DataLayout) -> None:
        self.session = session
        self.layout = layout
        self.count = 0
        session.add(
            Employee(id=EMPLOYEE_ID, folder_name=FOLDER, given_names="Test", surname="Ornek")
        )
        session.flush()
        layout.ensure_employee_tree(FOLDER)

    def add(
        self,
        checks: Sequence[Mapping[str, Any] | None] = (),
        *,
        status: DocumentStatus = DocumentStatus.ACTIVE,
        type_slug: str = PHOTO,
        pages: Sequence[int] | None = None,
        refs: object = None,
        content: bytes | None = None,
        extension: str = "jpeg",
        created_at: datetime | None = None,
    ) -> Document:
        """Bir çıktı belgesi: kaynak dosyanın sayfaları `checks` sırasıyla (kontrol `None` ise
        boş). Köken (`source_refs_json`) `refs` verilmişse odur, yoksa dosyanın `pages`'i (boş
        liste bütün dosya), o da yoksa sayfaların hepsi tek tek. Varsayılan kontrol her açık kuralda
        `pass`, varsayılan dosya sentetik vesikalık, zaman her belgede bir gün sonrası."""
        self.count += 1
        number = self.count
        upload = Upload(
            id=f"u_20260919_{number:04d}", channel="web", status=UploadStatus.DONE.value
        )
        upload_file = UploadFile(
            upload=upload,
            original_name=f"foto-{number}.jpg",
            stored_path=f"Inbox/{upload.id}/foto-{number}.jpg",
            sha256=f"{number:064x}",
            mime="image/jpeg",
        )
        self.session.add_all([upload, upload_file])
        self.session.flush()
        checks = list(checks) or [stored_check()]
        for index, check in enumerate(checks):
            self.session.add(
                Page(
                    file_id=upload_file.id,
                    index=index,
                    analysis_status="done",
                    photo_check_json=None if check is None else dict(check),
                )
            )
        output = self.layout.ready_dir(FOLDER) / f"Test_Ornek-Profile-Picture-{number}.{extension}"
        output.write_bytes(make_portrait_image_bytes() if content is None else content)
        if refs is None:
            listed = list(range(len(checks))) if pages is None else list(pages)
            refs = [{"file_id": upload_file.id, "pages": listed}]
        document = Document(
            employee_id=EMPLOYEE_ID,
            type_slug=type_slug,
            path=self.layout.relative(output),
            format=extension,
            sequence_no=number,
            source_refs_json=refs,
            status=status.value,
            created_at=created_at or FIRST_DAY + timedelta(days=number),
        )
        self.session.add(document)
        self.session.flush()
        return document
