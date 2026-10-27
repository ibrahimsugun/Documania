"""Örnek önizlemesi ve indirme yanıtları (PRD 11.9.7; PLAN.md §D130) — eğitim ve katalog uçları
ortak kullanır.

Önizleme adresi içeriğe bağlıdır (`?v=<anahtar>`, `app.storage.previews.preview_key`): adresteki
sürüm güncelse yanıt `private, max-age=31536000, immutable` ile uzun önbelleklenir — `private`
paylaşılan ve uç önbelleğe (Cloudflare) girmesini engeller; yanıtlar oturumun arkasındadır. Sürüm
yoksa ya da eskiyse aynı baytlar `no-cache` ile döner. `ETag` her yanıttadır, `If-None-Match`
tutarsa 304. Üretilemeyen önizlemede yer tutucu döner ve önbelleklenmez. Orijinal dosya yalnız
indirilir (`Content-Disposition: attachment`); satır içi gösterilmez.

Ön yükleme (PRD 11.9.8; PLAN.md §D131): `preview-prefetch.js` önizleme isteğine `PREFETCH_HEADER`
koyar; üretim yeri doluysa ön yükleme beklemez, `503 Retry-After: 2` alır ve geri çekilir
(`busy_response`). Kullanıcının kendi isteği sırasını bekler. Liste ucu (`/previews/thumbs`) oturum
başına hız sınırlıdır (`ListRateLimit`).

Genel önizleme katmanı (PRD 11.9.9; PLAN.md §D132 c): her belge kaynağı (`PreviewSource`) aynı
yanıtı alır (`source_preview_response`), önbellek iki kademelidir. Kademe 1 (`Tier.SPECIMEN`: örnek,
şablon — çalışan verisi yok) yukarıdaki gibi `immutable`; kademe 2 (`Tier.PERSONAL`: çalışan
belgesi, yükleme/kuyruk/geçmiş sayfası, üretilen belge, fotoğraf) adres sürümünden bağımsız
`private, max-age=900` + `ETag`/304 — çıkışta `Clear-Site-Data: "cache"` bunları da temizler.
Görüntü uçları erişim logu yazmaz; "görüntüleme" kaydı önizleme sayfasındadır (çağıran uç).
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from app.storage.layout import DataLayout
from app.storage.previews import (
    PREVIEW_MAX_PAGES,
    Preview,
    PreviewBusy,
    PreviewSource,
    document_page_count,
    ensure_source_preview,
    placeholder_jpeg,
    preview_key,
)

IMMUTABLE = "private, max-age=31536000, immutable"
REVALIDATE = "private, no-cache"
# Gerçek çalışan belgesi görüntüsü: tarayıcıda 15 dakika, paylaşılan önbellekte hiç (§D131 f3).
PERSONAL = "private, max-age=900"
NOSNIFF = {"X-Content-Type-Options": "nosniff"}
# Ön yükleme isteğinin işareti (yalnız aynı kökenli `fetch`; içerik değiştirmez, yalnız beklemeyi).
PREFETCH_HEADER = "x-preview-prefetch"
BUSY_RETRY_AFTER = 2


class Tier(Enum):
    """Önbellek kademesi (11.9.9): çalışan verisi taşımayan örnek/şablon ya da gerçek belge."""

    SPECIMEN = "specimen"
    PERSONAL = "personal"


def is_prefetch(request: Request) -> bool:
    return request.headers.get(PREFETCH_HEADER) == "1"


def busy_response() -> Response:
    """Üretim yerleri dolu: ön yükleme `Retry-After` kadar geri çekilir."""
    return Response(
        status_code=503,
        headers={**NOSNIFF, "Retry-After": str(BUSY_RETRY_AFTER), "Cache-Control": "no-store"},
    )


class ListRateLimit:
    """Oturum başına kayan pencere: `window` saniyede en çok `limit` istek. Anahtar oturum
    belirtecinin özetidir (belirteç bellekte tutulmaz). `retry_after` boşsa istek geçer."""

    def __init__(self, limit: int, window: float, *, capacity: int = 1000) -> None:
        self.limit = limit
        self.window = window
        self.capacity = capacity
        self._hits: dict[str, deque[float]] = {}
        self._guard = threading.Lock()

    def retry_after(self, token: str, now: float | None = None) -> int | None:
        moment = time.monotonic() if now is None else now
        key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._guard:
            if key not in self._hits and len(self._hits) >= self.capacity:
                self._prune(moment)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= moment - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, int(hits[0] + self.window - moment) + 1)
            hits.append(moment)
            return None

    def _prune(self, moment: float) -> None:
        stale = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= moment - self.window
        ]
        for key in stale:
            del self._hits[key]
        if len(self._hits) >= self.capacity:  # hepsi etkin: en eskisi düşer
            del self._hits[min(self._hits, key=lambda key: self._hits[key][-1])]


def preview_url(base: str, source: Path, size: str) -> str:
    """`<base>/previews/<boyut>/<ad>?v=<anahtar>` — `base` türün örnek yolunun öncesidir."""
    return f"{base}/previews/{size}/{quote(source.name)}?v={preview_key(source)}"


def preview_response(request: Request, preview: Preview, size: str) -> Response:
    if preview.path is None:
        return Response(
            placeholder_jpeg(),
            media_type="image/jpeg",
            headers={**NOSNIFF, "Cache-Control": "no-store"},
        )
    etag = f'"{preview.key}-{size}"'
    cache = IMMUTABLE if request.query_params.get("v") == preview.key else REVALIDATE
    headers = {**NOSNIFF, "Cache-Control": cache, "ETag": etag}
    if etag in request_etags(request.headers.get("if-none-match", "")):
        return Response(status_code=304, headers=headers)
    return FileResponse(preview.path, media_type="image/jpeg", headers=headers)


def source_preview_url(base: str, source: PreviewSource, size: str) -> str:
    """`<base>/previews/<boyut>?page=<n>&v=<anahtar>` — `base` kaynağın adresidir; `page` 1
    tabanlıdır ve ilk sayfada yazılmaz. Dosya yoksa `v` boştur (uç 404 döner)."""
    try:
        version = source.key()
    except OSError:
        version = ""
    page = f"page={source.page + 1}&" if source.page else ""
    return f"{base}/previews/{size}?{page}v={version}"


@dataclass(frozen=True, slots=True)
class PreviewPage:
    number: int  # 1 tabanlı
    url: str  # büyük önizleme


@dataclass(frozen=True, slots=True)
class DocumentPreview:
    """Önizleme sayfası (`document_preview.html`, 11.9.9): belgenin büyük önizlemeleri sayfa sayfa,
    en çok `PREVIEW_MAX_PAGES`; `page_count` belgenin bütün sayfalarıdır (fazlası İndir ile)."""

    file_name: str
    back_url: str
    back_label: str  # veri (çalışan ya da şablon adı); çevrilmez
    download_url: str
    pages: list[PreviewPage]
    page_count: int


def document_preview(
    source: PreviewSource,
    base: str,
    *,
    file_name: str,
    back_url: str,
    back_label: str,
    download_url: str,
    previewable: bool = True,
) -> DocumentPreview:
    """`source`'un (ilk sayfa) önizleme sayfası görünümü; `base` kaynağın önizleme adresinin
    öncesidir (`source_preview_url`). Önizlenemeyen biçimde (Word/Excel) sayfa yoktur."""
    count = document_page_count(source.path) if previewable else 0
    pages = [
        PreviewPage(
            index + 1,
            source_preview_url(
                base, PreviewSource(source.kind, source.ident, source.path, index), "large"
            ),
        )
        for index in range(min(count, PREVIEW_MAX_PAGES))
    ]
    return DocumentPreview(file_name, back_url, back_label, download_url, pages, count)


def source_preview_response(
    request: Request,
    layout: DataLayout,
    source: PreviewSource | None,
    size: str,
    *,
    tier: Tier,
    not_found: str,
) -> Response:
    """Kaynağın önizlemesi (11.9.9). `source` boşsa (yetkisiz, kayıt ya da dosya yok), boyut
    tanımsızsa ya da sayfa sınır dışındaysa 404 (`not_found`) — belgenin varlığı sızmaz. Ön
    yükleme üretim yeri bulamazsa 503."""
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, not_found)
    try:
        preview = ensure_source_preview(layout, source, size, wait=not is_prefetch(request))
    except PreviewBusy:
        return busy_response()
    if preview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, not_found)
    if tier is Tier.SPECIMEN:
        return preview_response(request, preview, size)
    if preview.path is None:
        return Response(
            placeholder_jpeg(),
            media_type="image/jpeg",
            headers={**NOSNIFF, "Cache-Control": "no-store"},
        )
    etag = f'"{preview.key}-{size}"'
    headers = {**NOSNIFF, "Cache-Control": PERSONAL, "ETag": etag}
    if etag in request_etags(request.headers.get("if-none-match", "")):
        return Response(status_code=304, headers=headers)
    return FileResponse(preview.path, media_type="image/jpeg", headers=headers)


def download_response(path: Path) -> FileResponse:
    """Orijinal baytlar, yalnız indirme olarak."""
    return FileResponse(
        path, filename=path.name, content_disposition_type="attachment", headers=NOSNIFF
    )


def request_etags(value: str) -> set[str]:
    """`If-None-Match` başlığındaki etiketler (zayıf işaret atılır)."""
    return {part.strip().removeprefix("W/") for part in value.split(",") if part.strip()}
