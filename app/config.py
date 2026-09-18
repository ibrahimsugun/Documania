"""Ortam değişkeni tabanlı yapılandırma (PRD 00.2.1, 00.2.2).

Tüm ayarlar `.env` (veya gerçek ortam değişkenleri) ile değişir. Kodda sabit
yol/model adı bulunmaz — yeni ayara ihtiyaç duyan modül burada bir alan açar.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production"] = "development"
    database_url: str
    data_dir: Path = Path("data")
    # PRD 01.3.1 sayı vermez; MB/sayfa sınırları burada varsayılan olarak sabitlenir
    # (bkz. PLAN.md §C8), ortam değişkeniyle ortama göre değiştirilebilir.
    max_upload_file_size_bytes: int = 20 * 1024 * 1024
    max_upload_pdf_pages: int = 30
    # PRD 02.1.1 — analiz için sayfa görüntüsü: bu DPI'da render edilir, uzun kenar sınırı
    # aşılırsa küçültülür; önbellek JPEG kalitesi (bkz. PLAN.md §C10).
    page_render_dpi: int = Field(default=200, gt=0)
    page_render_max_long_edge_px: int = Field(default=1568, gt=0)
    page_render_jpeg_quality: int = Field(default=90, ge=1, le=100)
    # PRD 07.6.1, §20.5 — `render_image` çıktısı: bu DPI'da rasterleştirilir, bu JPEG kalitesiyle
    # kaydedilir. Analiz önbelleğinin (`page_render_*`) ayarından bağımsızdır (bkz. PLAN.md §C10):
    # o bir analiz kopyası, bu yayınlanan çıktı belgesidir.
    render_image_dpi: int = Field(default=200, gt=0)
    render_image_jpeg_quality: int = Field(default=90, ge=1, le=100)
    # PRD 03.2.1 — sayfa analizi sağlayıcısı adıyla seçilir (`app.ai.provider.create_provider`);
    # sağlayıcıya özgü anahtar/model yalnız o sağlayıcı kurulurken okunur (bkz. PLAN.md §C13).
    ai_provider: str = Field(default="anthropic", pattern=r"^[a-z][a-z0-9_]*$")
    ai_max_output_tokens: int = Field(default=4096, gt=0)
    ai_request_timeout_seconds: float = Field(default=120.0, gt=0)
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = Field(default="claude-opus-5", min_length=1)
    # PRD 10.1.2 — panel oturumunun ömrü (saniye); süre dolunca yeniden giriş istenir. PRD süre
    # vermez, varsayılan bir iş günü (bkz. PLAN.md §C45).
    session_max_age_seconds: int = Field(default=12 * 60 * 60, gt=0)


def load_settings(**overrides: object) -> Settings:
    """`Settings` oluşturur; zorunlu bir değişken eksikse anlaşılır hata verir (00.2.2)."""
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        missing = sorted(
            {str(error["loc"][0]).upper() for error in exc.errors() if error["type"] == "missing"}
        )
        if missing:
            raise RuntimeError(
                "Eksik zorunlu ortam değişkeni: "
                f"{', '.join(missing)}. Bkz. .env.example dosyasındaki açıklama."
            ) from exc
        raise


@lru_cache
def get_settings() -> Settings:
    """Süreç boyunca paylaşılan tek `Settings` örneği (test dışı kullanım için)."""
    return load_settings()
