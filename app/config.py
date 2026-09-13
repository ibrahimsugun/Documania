"""Ortam değişkeni tabanlı yapılandırma (PRD 00.2.1, 00.2.2).

Tüm ayarlar `.env` (veya gerçek ortam değişkenleri) ile değişir. Kodda sabit
yol/model adı bulunmaz — yeni ayara ihtiyaç duyan modül burada bir alan açar.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production"] = "development"
    database_url: str
    data_dir: Path = Path("data")


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
