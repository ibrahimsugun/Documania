# PLAN arşivi — 2026-10-23

Kaynak: PLAN.md (K blokları, C ve D bölümleri; canlı dosyadan taşındı, birebir).

## K. Kanıt Geçmişi (arşiv)

#### K15.1 — 15.1.1, 15.1.2, 15.1.3, 15.1.4 · Hazır şablon deposu, incelemesi ve harita onayı
- ✅ Depo: göç 0031 (`output_templates`, boş `output_template_maps`, `generated_documents`; `access_log` `template_id`/`generated_document_id` + CHECK `target`), `_sablonlar/<id>/sablon.pdf` + `pages/`, `Uretilen/`; yükleme (PDF; JPEG/PNG img2pdf kayıpsız; Word/Excel 422; SHA-256 tekrarı 409 + uyarı; ad tekil), liste + durum süzgeci, arşiv/geri al, `TEMPLATE_UPLOADED/ARCHIVED/RESTORED`; parti/belge açmaz — `app/output_templates/service.py`, `app/web/routers/output_templates.py`, `app/storage/layout.py` · test `tests/web/test_output_templates.py` (9), `tests/storage/test_layout.py`, `tests/db/test_models.py` · tm 182


## K. Kanıt Geçmişi (arşiv)

#### K15.2 — 15.2.1, 15.2.2, 15.2.3 · Çıktıya hazırla ve üretilen belgeler
- ✅ Üretim (15.2.1): onaylı en yüksek harita sürümü şablon kopyasına PyMuPDF `insert_textbox` ile (gömülü Nimbus Sans: Latin, genişletilmiş Latin, Kiril; döndürülmüş sayfada `derotation_matrix`), yazı boyutu 0,5 adımla 6 pt'ye dek küçülür, yine sığmazsa kesilmeden yazılır + `truncated_fields`; değerler §D123 d (ad soyad, `GG.AA.YYYY`, uyruk İngilizce CLDR adı, pasaport numarası `employee_identifiers`'tan, güncel iletişim, `today`); boş profil alanı boş + `missing_fields`, imza/kaşe/"boş bırak" kutusu boş; `Uretilen/<Ad_Soyad>-<Etiket>[-n].pdf` (K8, `write_sequenced`), `generated_documents` satırı, `OUTPUT_GENERATED` (alan adları, değer yok); orijinal SHA-256 değişmez — `app/output_templates/generate.py`, `app/output_templates/labels.py`, `app/events.py` · test `tests/output_templates/test_generate.py` (7) · tm 185
- ✅ Profil ve erişim (15.2.1, 15.2.2): "Hazır şablonlar" (yalnız `ready`; "Çıktıya hazırla" yazma yetkisinde ve etkin çalışanda) ve "Üretilen belgeler" (şablon, dosya, tarih, üreten, harita sürümü, eksik alanlar, durum; yeni sekmede aç / indir, erişim kaydı `generated_document_id` ile önce yazılır); bildirim eksik ve taşan alan **adlarını** isteğin dilinde söyler (yeni `fields`/`overflow` parametre türü); üretilen belge `documents`'a, belge listesine ve paket hesabına girmez; üç dil — `app/web/routers/generated_documents.py`, `app/web/routers/employees.py`, `profile.html`, `app/web/feedback.py` · test `tests/web/test_outputs.py` (5), `tests/test_scenario_s29.py` (ilk yarı, 1), `test_access_log.py`, `test_profile.py`, `test_feedback.py`, `test_translation_sweep.py`, `test_ui_standard.py` · tm 185
- ✅ Kapı (tm 185): ruff check/format, compileall, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `python -m app.i18n check` exit 0; `pytest -q -m "not live" -n 6 --dist worksteal --cov=app --cov-fail-under=70` 7135 geçti, 6 atlandı, %98,76 — 2 kırmızı (`…plan_d58_verbatim`) önceki görevlerdeki gibi ilgisiz · tm 185
- ◐ 15.2.2'nin yeniden üretimde öncekini `superseded` yapması, arşiv/geri al ve `profil.md` "Üretilen belgeler" bölümü 15.2.3 ile birlikte tm 186'nın kapsamıdır; sıra numarası (`-2`) bu görevde verildi · tm 185

