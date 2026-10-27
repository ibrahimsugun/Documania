"""Önizleme ön yükleme listesi (PRD 11.9.8; PLAN.md §D131 b, f).

`GET /previews/thumbs?after=<imleç>&limit=<n>` bilinen türlerin bütün örneklerinin küçük önizleme
adreslerini sayfalı verir; `preview-prefetch.js` bunları boşta, düşük öncelikle ister ve tarayıcı
önbelleğini ısıtır. Adresler tür sayfasının (`/training/known/<slug>`) gösterdiği adreslerin
aynısıdır: sayfa açılınca görüntüler ağa gitmez.

- **Yeni yetki yoktur:** uç panelin oturum ve rol kapısının arkasındadır (`app.main`); verdiği
  her adres zaten aynı oturumun açabildiği önizleme ucudur. Orijinal dosya adresi listede yoktur.
- **Yalnız adres ve sürüm:** `version` listenin özetidir (örnek eklenince, çıkınca ya da
  değişince değişir); istemci yalnız bunu ve sayısal imleci (`after`, sıra numarası) saklar —
  belge adı ya da içerik saklamaz.
- **Üst sınır:** sayfa başına en çok `THUMBS_LIMIT` adres; oturum başına hız sınırı aşılırsa
  `429 Retry-After`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.storage import DataLayout
from app.storage.examples import list_examples
from app.training.known_types import load_known_types
from app.web.auth import SESSION_COOKIE
from app.web.previews import ListRateLimit, preview_url
from app.web.routers.training import KNOWN_PATH
from app.web.routers.uploads import get_layout

router = APIRouter(tags=["previews"])

THUMBS_PATH = "/previews/thumbs"
THUMBS_LIMIT = 200
# ~2.200 örnek = 11 sayfa; bir dakikada 30 istek gerçek kullanımı hiç durdurmaz.
LIST_RATE = ListRateLimit(limit=30, window=60.0)


@router.get(THUMBS_PATH)
def preview_thumbs(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    layout: Annotated[DataLayout, Depends(get_layout)],
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=THUMBS_LIMIT)] = THUMBS_LIMIT,
) -> Any:
    """`{"version", "items": [adres…], "next": imleç | null}` — `after` sıradaki ilk öğenin
    numarasıdır; `next` boşsa liste bitti."""
    retry = LIST_RATE.retry_after(request.cookies.get(SESSION_COOKIE, ""))
    if retry is not None:
        return Response(
            status_code=429, headers={"Retry-After": str(retry), "Cache-Control": "no-store"}
        )
    response.headers["Cache-Control"] = "private, no-store"
    try:
        slugs = [known.slug for known in load_known_types(session)]
    finally:
        session.rollback()
    urls = list(_thumb_urls(layout, slugs))
    version = hashlib.sha256("\n".join(urls).encode("utf-8")).hexdigest()[:20]
    end = after + limit
    return {
        "version": version,
        "items": urls[after:end],
        "next": end if end < len(urls) else None,
    }


def _thumb_urls(layout: DataLayout, slugs: list[str]) -> Iterator[str]:
    """Türlerin örneklerinin küçük önizleme adresleri, tür ve ad sırasıyla (tür sayfasıyla aynı)."""
    for slug in slugs:
        try:
            examples = list_examples(layout, slug)
        except ValueError:  # yol parçası olamayan slug
            continue
        base = f"{KNOWN_PATH}/{quote(slug)}"
        directory = layout.type_examples_dir(slug)
        for example in examples:
            try:
                yield preview_url(base, directory / example.name, "small")
            except FileNotFoundError:  # listelenip silindi
                continue
