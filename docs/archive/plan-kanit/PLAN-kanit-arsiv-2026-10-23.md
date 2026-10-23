# PLAN arşivi — 2026-10-23

Kaynak: PLAN.md (K blokları, C ve D bölümleri; canlı dosyadan taşındı, birebir).

## K. Kanıt Geçmişi (arşiv)

#### K15.1 — 15.1.1, 15.1.2, 15.1.3, 15.1.4 · Hazır şablon deposu, incelemesi ve harita onayı
- ✅ Depo: göç 0031 (`output_templates`, boş `output_template_maps`, `generated_documents`; `access_log` `template_id`/`generated_document_id` + CHECK `target`), `_sablonlar/<id>/sablon.pdf` + `pages/`, `Uretilen/`; yükleme (PDF; JPEG/PNG img2pdf kayıpsız; Word/Excel 422; SHA-256 tekrarı 409 + uyarı; ad tekil), liste + durum süzgeci, arşiv/geri al, `TEMPLATE_UPLOADED/ARCHIVED/RESTORED`; parti/belge açmaz — `app/output_templates/service.py`, `app/web/routers/output_templates.py`, `app/storage/layout.py` · test `tests/web/test_output_templates.py` (9), `tests/storage/test_layout.py`, `tests/db/test_models.py` · tm 182

