# PLAN arşivi — 2026-10-27

Kaynak: PLAN.md (K blokları, C ve D bölümleri; canlı dosyadan taşındı, birebir).

## D. Sapmalar

- **D124 — uygulama kararları (tm 189, 10.1.10).** **(a) Gizlilik:** `require_root` 404'ü Starlette'in `HTTPException`'ıyla atar — yanıt bilinmeyen yolunkiyle birebir (gövde, bildirim çerezi yok; FastAPI sınıfı yazma isteğine bildirim çerezi eklerdi). `app.main`'de sıra `require_root` → `panel_write_gate`: Kullanıcı'nın `POST`'u da 403 değil 404. `/ai-settings/{rest:path}` (`GET`, `POST`) herkese 404 döner; yoksa Starlette `/ai-settings/`'i 307 ile yönlendirip adresi ele verirdi. **(b) Form:** kartlar `main.content`'in çocuğudur, alanlar sondaki tek forma `form=` özniteliğiyle bağlıdır; anahtarı tanımsız sağlayıcının radyosu `disabled` (sunucu yine 422). Doğrulama hataları `N_` metinleriyle yönlendiricide (sağlayıcı adı parametre); `AiSettingsError` yalnız yedek, genel metinle. Listede olmayan model yalnız o sağlayıcının kayıtlı modeliyse kabul edilir. **(c) Olay ve bildirim:** `AI_SETTINGS_CHANGED` verisi `save_ai_settings`'in değişiklik sözlüğüdür; değişiklik yoksa olay yok (ilk kayıt değer değiştirmese de satırı açar ve "kaydedildi" der, aksi "değişiklik yok").


