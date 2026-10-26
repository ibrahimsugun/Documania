# HANDOFF arşivi — 2026-10-26

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

## 184 — 15.1-c Alan haritası önizleme ve onay — done — 2026-10-23
- Yapıldı: `app/output_templates/approve.py` (`approve_map`: son sürüme onay, atama doğrulama, değişen atama `store_map` ile yeni sürüm, `ready`, `TEMPLATE_MAP_APPROVED`; `approved_map`), şablon sayfasında SVG kutulu önizleme + atama tablosu (`select`/"Boş bırak", imza/kaşe seçimsiz), `POST /output-templates/{id}/maps/{version}/approve` düz form, Kullanıcı'ya yalnız onaylı harita salt okunur; `panel.css` + ARAYUZ-STANDARDI §3/§4, dört bildirim, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7122 geçti, 6 atlandı, kapsam %98,83 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) tm 180–183'teki gibi bu görevle ilgisiz.
- Varsayımlar: §D123 (m)'ye yazıldı — onay yalnız son sürüme (eski sürüm 409), atama değişmezse yerinde onay, değişirse yeni sürüm (`model` kutuları önerenin), zaten onaylıysa yazma yok; üretim onaylı en yüksek sürümü kullanır; kutular `style=` yasağı yüzünden SVG.
- Sonraki pencereye not: tm 185 haritayı `app.output_templates.approve.approved_map(template)` ile alır (`json["fields"]`, `source` = `unassigned` boş kalır); `generated_documents.map_id` o satırın `id`'si. D58 testleri için ayrı küçük görev hâlâ gerekli.

## 185 — 15.2-a Çıktıya hazırla ve üretilen belgeler — done — 2026-10-23
- Yapıldı: `app/output_templates/generate.py` (onaylı harita → şablon kopyasına PyMuPDF `insert_textbox`, gömülü Nimbus Sans ile Latin/Kiril, döndürülmüş sayfa, küçültme + kesmeden taşma `truncated_fields`, §D123 d değer biçimleri, eksik alan boş, imza/kaşe/"boş bırak" boş; `Uretilen/` K8 adı, `generated_documents`, `OUTPUT_GENERATED`), `app/web/routers/generated_documents.py` (`POST /employees/{id}/outputs`, aç/indir + erişim kaydı), profilde "Hazır şablonlar" ve "Üretilen belgeler", bildirimde alan adları (`fields`/`overflow` parametresi), üç dil; S29 ilk yarı.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7135 geçti, 6 atlandı, kapsam %98,76 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) tm 180–184'teki gibi bu görevle ilgisiz.
- Varsayımlar: §D123 (n)'ye yazıldı — yerleşik Nimbus Sans gömülür (yeni bağımlılık yok), 6 pt alt sınır, taşan metin kutunun başından tek parça, `max_chars` kullanılmaz, uyruk İngilizce CLDR adı, pasif/birleştirilmiş çalışan ve hazır olmayan şablon 409. 15.2.2 ◐: `superseded`, arşiv/geri al ve `profil.md` tm 186'da.
- Sonraki pencereye not: tm 186 yeniden üretimde öncekini `superseded` yapmalı (`generate_document` sırayı zaten veriyor), `OUTPUT_ARCHIVED/RESTORED` olaylarını ekleyip yeni POST yollarını `REVIEWED_MUTATING_ROUTES` ve `tests/web/test_profile.py` yol listesine yazmalı; S29 ikinci yarısı `tests/test_scenario_s29.py`'ye. Test fikstürü `tests/output_templates/factory.py:ready_template`. Testte conftest modülü içe aktarılmaz (fikstür kaydı bozulur) — S29 s01_s05 fikstürlerini kullanır.
