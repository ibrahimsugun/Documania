"""Örnek önizlemesi ve indirme yanıtları (PRD 11.9.7; PLAN.md §D130) — eğitim ve katalog uçları
ortak kullanır.

Önizleme adresi içeriğe bağlıdır (`?v=<anahtar>`, `app.storage.previews.preview_key`): adresteki
sürüm güncelse yanıt `private, max-age=31536000, immutable` ile uzun önbelleklenir — `private`
paylaşılan ve uç önbelleğe (Cloudflare) girmesini engeller; yanıtlar oturumun arkasındadır. Sürüm
yoksa ya da eskiyse aynı baytlar `no-cache` ile döner. `ETag` her yanıttadır, `If-None-Match`
tutarsa 304. Üretilemeyen önizlemede yer tutucu döner ve önbelleklenmez. Orijinal dosya yalnız
indirilir (`Content-Disposition: attachment`); satır içi gösterilmez.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import Request, Response
from fastapi.responses import FileResponse

from app.storage.previews import Preview, placeholder_jpeg, preview_key

IMMUTABLE = "private, max-age=31536000, immutable"
REVALIDATE = "private, no-cache"
NOSNIFF = {"X-Content-Type-Options": "nosniff"}


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
    if etag in _etags(request.headers.get("if-none-match", "")):
        return Response(status_code=304, headers=headers)
    return FileResponse(preview.path, media_type="image/jpeg", headers=headers)


def download_response(path: Path) -> FileResponse:
    """Orijinal baytlar, yalnız indirme olarak."""
    return FileResponse(
        path, filename=path.name, content_disposition_type="attachment", headers=NOSNIFF
    )


def _etags(value: str) -> set[str]:
    return {part.strip().removeprefix("W/") for part in value.split(",") if part.strip()}
