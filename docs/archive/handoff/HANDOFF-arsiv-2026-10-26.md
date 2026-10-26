# HANDOFF arşivi — 2026-10-26

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

## 184 — 15.1-c Alan haritası önizleme ve onay — done — 2026-10-23
- Yapıldı: `app/output_templates/approve.py` (`approve_map`: son sürüme onay, atama doğrulama, değişen atama `store_map` ile yeni sürüm, `ready`, `TEMPLATE_MAP_APPROVED`; `approved_map`), şablon sayfasında SVG kutulu önizleme + atama tablosu (`select`/"Boş bırak", imza/kaşe seçimsiz), `POST /output-templates/{id}/maps/{version}/approve` düz form, Kullanıcı'ya yalnız onaylı harita salt okunur; `panel.css` + ARAYUZ-STANDARDI §3/§4, dört bildirim, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7122 geçti, 6 atlandı, kapsam %98,83 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) tm 180–183'teki gibi bu görevle ilgisiz.
- Varsayımlar: §D123 (m)'ye yazıldı — onay yalnız son sürüme (eski sürüm 409), atama değişmezse yerinde onay, değişirse yeni sürüm (`model` kutuları önerenin), zaten onaylıysa yazma yok; üretim onaylı en yüksek sürümü kullanır; kutular `style=` yasağı yüzünden SVG.
- Sonraki pencereye not: tm 185 haritayı `app.output_templates.approve.approved_map(template)` ile alır (`json["fields"]`, `source` = `unassigned` boş kalır); `generated_documents.map_id` o satırın `id`'si. D58 testleri için ayrı küçük görev hâlâ gerekli.
