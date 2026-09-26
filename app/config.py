"""Ortam değişkeni tabanlı yapılandırma (PRD 00.2.1, 00.2.2).

Tüm ayarlar `.env` (veya gerçek ortam değişkenleri) ile değişir. Kodda sabit
yol/model adı bulunmaz — yeni ayara ihtiyaç duyan modül burada bir alan açar.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPrice(BaseModel):
    """Bir modelin token fiyatı: bir milyon token başına USD (PRD 13.1.1).

    `cached_input_per_mtok` sağlayıcının önbellekten okuduğu girdi tokenının fiyatıdır; yoksa o
    tokenlar da `input_per_mtok` ile hesaplanır.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_per_mtok: Decimal = Field(ge=0, allow_inf_nan=False)
    output_per_mtok: Decimal = Field(ge=0, allow_inf_nan=False)
    cached_input_per_mtok: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


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
    # PRD 13.2.2 — metin katmanı olan PDF sayfası analize bu uzun kenar sınırıyla render edilir:
    # yazının kendisi istekte metin olarak gider, görüntü düzen ve görünüm içindir. Genel sınırdan
    # (`page_render_max_long_edge_px`) büyükse genel sınır geçerlidir (bkz. PLAN.md §C71).
    page_render_text_layer_max_long_edge_px: int = Field(default=1024, gt=0)
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
    # PRD 13.2.1 — ucuz model ön elemesi: tanımlıysa her sayfa önce bu modele sorulur, kolay sayfa
    # ölçütünü karşılamayan yanıt atılır ve sayfa ana modele (`*_MODEL`) sorulur
    # (`app.pipeline.analyze`). Boş ya da ana modelle aynıysa ön eleme yapılmaz (bkz. PLAN.md §C71).
    anthropic_prescreen_model: str | None = None
    # PRD 03.3.1 — ikincil sağlayıcı; anahtar yalnız `AI_PROVIDER=openai` iken zorunludur.
    openai_api_key: SecretStr | None = None
    openai_model: str = Field(default="gpt-6-luna", min_length=1)
    openai_prescreen_model: str | None = None
    # PRD 13.1.1 — maliyet paneli token fiyatlarını yerleşik fiyat tablosundan okur
    # (`app/ai/model_prices.yaml`, `app.ai.pricing`); bu ayar aynı model için onun önüne geçer
    # (JSON: `{"<model>": {"input_per_mtok": 5, "output_per_mtok": 25,
    # "cached_input_per_mtok": 0.5}}`, birim USD / milyon token, önbellek fiyatı isteğe bağlı).
    # İkisinde de olmayan modelin tokenları sayılır, maliyeti hesaplanmaz (bkz. PLAN.md §C77).
    ai_model_prices: dict[str, ModelPrice] = Field(default_factory=dict)
    # PRD 13.3.1 — kalıcı işçi kuyruğu ayrı `python -m app.worker` sürecinde çalışır; APP yalnız
    # HTTP sunar. İşi alan worker kirasını (`WORKER_LEASE_SECONDS`) her geçişte ve kiranın üçte
    # birinde bir yeniler; kirası dolan iş sahipsiz sayılır ve yeniden alınır. Kirası
    # `WORKER_MAX_ATTEMPTS` kez dolan işten vazgeçilir, parti `failed` olur. Kuyruk
    # `WORKER_POLL_SECONDS` aralıkla taranır (bkz. PLAN.md §D57).
    worker_lease_seconds: int = Field(default=120, ge=10)
    worker_max_attempts: int = Field(default=3, ge=1)
    worker_poll_seconds: float = Field(default=5.0, gt=0)
    # PRD 13.6.1 — izleme ve uyarı (`app.worker.monitor`). Hata, disk doluluğu ve kuyruk uzunluğu
    # eşiği aşınca uyarı üretilir: panel ve bot süreçlerinin logu ile Telegram bildirimi. Son
    # `ALERT_ERROR_WINDOW_MINUTES` dakikada `ALERT_ERROR_COUNT` parti işlenemediyse hata; veri
    # diski `ALERT_DISK_USED_PERCENT` yüzde dolduysa disk; işlenmeyi bekleyen parti sayısı
    # `ALERT_JOB_QUEUE_LENGTH`'e, karar bekleyen kuyruk öğesi sayısı `ALERT_REVIEW_QUEUE_LENGTH`'e
    # vardıysa kuyruk uyarısı çıkar. Ölçüm `ALERT_CHECK_SECONDS` aralıkla yapılır; süren uyarı
    # `ALERT_REPEAT_MINUTES` dakikada bir hatırlatılır (bkz. PLAN.md §C76).
    alert_error_count: int = Field(default=3, ge=1)
    alert_error_window_minutes: int = Field(default=60, ge=1)
    alert_disk_used_percent: float = Field(default=85.0, gt=0, le=100)
    alert_job_queue_length: int = Field(default=20, ge=1)
    alert_review_queue_length: int = Field(default=50, ge=1)
    alert_check_seconds: float = Field(default=60.0, gt=0)
    alert_repeat_minutes: int = Field(default=360, ge=1)
    # PRD 10.1.2 — panel oturumunun ömrü (saniye); süre dolunca yeniden giriş istenir. PRD süre
    # vermez, varsayılan bir iş günü (bkz. PLAN.md §C45).
    session_max_age_seconds: int = Field(default=12 * 60 * 60, gt=0)
    # PRD 11.9.5 — eğitim modunun "Harita yükle"si: CSV haritasının bayt sınırı ve satır sınırı
    # (haritanın çözdüğü dosya sayısına da uygulanır). Haritanın `source_collection_path` sütunu
    # yalnız `TRAINING_COLLECTION_DIR` ayarlıysa o kökün altında çözülür; ayar isteğe bağlıdır,
    # boşsa (varsayılan) o sütunun satırları atlanır (bkz. PLAN.md §C87).
    training_map_max_bytes: int = Field(default=8 * 1024 * 1024, gt=0)
    training_map_max_rows: int = Field(default=20_000, gt=0)
    training_collection_dir: Path | None = None
    # PRD 12.1.1 — Telegram botu (K13: yalnız İK). Bot ayrı süreç olarak koşar (`python -m
    # app.telegram.bot`): geliştirmede polling, üretimde (`APP_ENV=production`) webhook. Değerler
    # yalnız bot başlarken okunur ve doğrulanır (bkz. PLAN.md §C66).
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_webhook_listen: str = Field(default="127.0.0.1", min_length=1)
    telegram_webhook_port: int = Field(default=8443, ge=1, le=65535)

    @field_validator("training_collection_dir", mode="before")
    @classmethod
    def _blank_collection_dir_is_unset(cls, value: object) -> object:
        # `TRAINING_COLLECTION_DIR=` (boş) ayarsızdır; `Path("")` çalışma dizinini gösterirdi.
        if isinstance(value, str) and not value.strip():
            return None
        return value


def load_settings(**overrides: object) -> Settings:
    """`Settings` oluşturur; zorunlu bir değişken eksikse anlaşılır hata verir (00.2.2)."""
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        # Yalnız üst düzey alanın kendisi eksikse "eksik değişken"; iç içe bir değerin
        # (ör. `AI_MODEL_PRICES` içindeki bir fiyat) eksikliği asıl doğrulama hatasıdır.
        missing = sorted(
            {
                str(error["loc"][0]).upper()
                for error in exc.errors()
                if error["type"] == "missing" and len(error["loc"]) == 1
            }
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
