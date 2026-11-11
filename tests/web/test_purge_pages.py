"""11.9.10 — `purge-originals --apply` sonrası panel (PLAN.md §D135 c, d).

Ham örnek ve `done` çalıştırmanın yükleme kopyası silindikten sonra eğitim sayfaları, çalıştırmanın
öğe listesi, eğitim ve katalog tür sayfaları açılır; örnek adı ve önizlemesiyle görünür, "İndir"
yerine "Ham dosya silindi" yazar. Veri sentetiktir; yalnız `TestClient`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.db.models import (
    TrainingItem,
    TrainingItemStatus,
    TrainingRun,
    TrainingRunKind,
    TrainingRunStatus,
)
from app.storage import DataLayout
from app.storage.examples import store_example
from app.storage.filetype import FileKind
from app.training.cleanup import record_uploaded_example
from app.training.purge import purge_originals
from tests.fixtures.gen import make_half_filled_image_bytes

SLUG = "russian_passport"


@pytest.fixture
def purged(session_factory: sessionmaker[Session], layout: DataLayout) -> tuple[str, int]:
    content = make_half_filled_image_bytes("JPEG", (900, 600))
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        stored = store_example(layout, SLUG, "ornek.jpg", content, FileKind.JPEG, session=session)
        record_uploaded_example(session, SLUG, stored)
        run = TrainingRun(
            kind=TrainingRunKind.UPLOAD.value, created_by="ik", status=TrainingRunStatus.DONE.value
        )
        session.add(run)
        session.flush()
        item = TrainingItem(
            run_id=run.id,
            original_name="yuklenen.jpg",
            status=TrainingItemStatus.UNPLACED.value,
            file_kind="jpeg",
        )
        session.add(item)
        session.flush()
        staged = layout.training_staged_path(run.id, item.id, "jpg")
        staged.parent.mkdir(parents=True)
        staged.write_bytes(content)
        item.staged_path = layout.relative(staged)
        session.commit()
        run_id = run.id
    report = purge_originals(session_factory, layout, apply=True)
    assert report.deleted["examples"].files == 1 and report.deleted["gelen"].files == 1
    return stored.name, run_id


def test_pages_open_after_purge(client: TestClient, purged: tuple[str, int]) -> None:
    name, run_id = purged
    for page in ("/training", f"/training/items?run={run_id}", "/training/known"):
        assert client.get(page).status_code == 200, page
    for page in (f"/training/known/{SLUG}", f"/document-types/{SLUG}"):
        response = client.get(page)
        assert response.status_code == 200, page
        assert name in response.text and "Ham dosya silindi" in response.text
    assert client.get(f"/training/known/{SLUG}/previews/large/{name}").status_code == 200
    assert client.get(f"/training/known/{SLUG}/examples/{name}").status_code == 404
