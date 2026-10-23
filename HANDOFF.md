# HANDOFF — pencereler arası köprü

Her görev penceresi kapanırken buraya bir blok ekler. Bloklar **newest-first** sıralıdır:
en yeni blok `## Task log (newest-first)` başlığının hemen altındadır.

**Bu dosyayı baştan sona okuma.** Sana gereken en üstteki birkaç bloktur: `head -60 HANDOFF.md`.
Eski bir işi arıyorsan hedefli ara: `grep -n 'tm <id>' HANDOFF.md | head -5`.

Eski kayıtlar: `docs/archive/handoff/` (`grep -rn 'tm <id>' docs/archive/handoff`). Bu dosyada yalnız son 5 görev + açık görevler durur (CONVENTIONS §3).

Blok biçimi `CONVENTIONS.md` §3'te tanımlıdır:

```markdown
## <tm-id> — <başlık> — <done|blocked> — <YYYY-MM-DD>
- Yapıldı: <tek cümle>
- Doğrulama: <hangi kapılar yeşil, kaç test>
- Varsayımlar: <yoksa "yok">
- Sonraki pencereye not: <bir sonraki işin bilmesi gereken tek şey>
```

## Task log (newest-first)

## 186 — 15.2-b Üretilen belge yaşam döngüsü — done — 2026-10-23
- Yapıldı: yeniden üretim aynı şablonun etkin belgesini `superseded` yapar; `app/output_templates/lifecycle.py` arşivle/geri al (tek adım, `OUTPUT_ARCHIVED/RESTORED`, `POST …/outputs/{id}/archive|restore`, profilde katlanmış `details.archived-outputs`); 10.5.6 `Uretilen/` K8 yeniden adlandırma (`app/storage/rename.py`), 10.5.9 kalanın `Uretilen/`'ine taşıma (`app/storage/merge.py`), 10.5.13 dosya silme + `deleted` satır + `EMPLOYEE_DELETED.outputs`; `profil.md` "Üretilen belgeler"; üç dil; S29 tam.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7143 geçti, 6 atlandı, kapsam %98,77 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) tm 180–185'teki gibi ilgisiz.
- Varsayımlar: §D123 (o)'ya yazıldı — geri alınan belge daha yeni belge varsa `superseded`; yeniden adlandırmada `Uretilen/`'in bütün belgeleri (eski sürüm dahil) K8 adı alır; birleştirmede durum korunur, sıra kalanınkinden devam eder; olay verilerine `outputs` / `superseded` anahtarları eklendi; silme onayının `<N>`'i değişmedi.
- Sonraki pencereye not: FR-MOD-15'in on satırı ✅ (Faz 1: 92 ✅, 49/49 Must; Kapanış AÇIK — kapanış denetimi görevi yeniden açılmalı). Yeni yol parametresi `generated_document_id` `tests/web/test_roles.py` `WORLD_PARAMS`'tadır. D58 testleri için ayrı küçük görev hâlâ gerekli.

## 185 — 15.2-a Çıktıya hazırla ve üretilen belgeler — done — 2026-10-23
- Yapıldı: `app/output_templates/generate.py` (onaylı harita → şablon kopyasına PyMuPDF `insert_textbox`, gömülü Nimbus Sans ile Latin/Kiril, döndürülmüş sayfa, küçültme + kesmeden taşma `truncated_fields`, §D123 d değer biçimleri, eksik alan boş, imza/kaşe/"boş bırak" boş; `Uretilen/` K8 adı, `generated_documents`, `OUTPUT_GENERATED`), `app/web/routers/generated_documents.py` (`POST /employees/{id}/outputs`, aç/indir + erişim kaydı), profilde "Hazır şablonlar" ve "Üretilen belgeler", bildirimde alan adları (`fields`/`overflow` parametresi), üç dil; S29 ilk yarı.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7135 geçti, 6 atlandı, kapsam %98,76 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) tm 180–184'teki gibi bu görevle ilgisiz.
- Varsayımlar: §D123 (n)'ye yazıldı — yerleşik Nimbus Sans gömülür (yeni bağımlılık yok), 6 pt alt sınır, taşan metin kutunun başından tek parça, `max_chars` kullanılmaz, uyruk İngilizce CLDR adı, pasif/birleştirilmiş çalışan ve hazır olmayan şablon 409. 15.2.2 ◐: `superseded`, arşiv/geri al ve `profil.md` tm 186'da.
- Sonraki pencereye not: tm 186 yeniden üretimde öncekini `superseded` yapmalı (`generate_document` sırayı zaten veriyor), `OUTPUT_ARCHIVED/RESTORED` olaylarını ekleyip yeni POST yollarını `REVIEWED_MUTATING_ROUTES` ve `tests/web/test_profile.py` yol listesine yazmalı; S29 ikinci yarısı `tests/test_scenario_s29.py`'ye. Test fikstürü `tests/output_templates/factory.py:ready_template`. Testte conftest modülü içe aktarılmaz (fikstür kaydı bozulur) — S29 s01_s05 fikstürlerini kullanır.

## 184 — 15.1-c Alan haritası önizleme ve onay — done — 2026-10-23
- Yapıldı: `app/output_templates/approve.py` (`approve_map`: son sürüme onay, atama doğrulama, değişen atama `store_map` ile yeni sürüm, `ready`, `TEMPLATE_MAP_APPROVED`; `approved_map`), şablon sayfasında SVG kutulu önizleme + atama tablosu (`select`/"Boş bırak", imza/kaşe seçimsiz), `POST /output-templates/{id}/maps/{version}/approve` düz form, Kullanıcı'ya yalnız onaylı harita salt okunur; `panel.css` + ARAYUZ-STANDARDI §3/§4, dört bildirim, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7122 geçti, 6 atlandı, kapsam %98,83 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) tm 180–183'teki gibi bu görevle ilgisiz.
- Varsayımlar: §D123 (m)'ye yazıldı — onay yalnız son sürüme (eski sürüm 409), atama değişmezse yerinde onay, değişirse yeni sürüm (`model` kutuları önerenin), zaten onaylıysa yazma yok; üretim onaylı en yüksek sürümü kullanır; kutular `style=` yasağı yüzünden SVG.
- Sonraki pencereye not: tm 185 haritayı `app.output_templates.approve.approved_map(template)` ile alır (`json["fields"]`, `source` = `unassigned` boş kalır); `generated_documents.map_id` o satırın `id`'si. D58 testleri için ayrı küçük görev hâlâ gerekli.

## 183 — 15.1-b Şablon incelemesi (alan haritası) — done — 2026-10-23
- Yapıldı: `TemplateFieldMap` §8.7 şeması (`app/ai/schemas.py`), talimat `template_map.md`, `examine_template` (Anthropic/OpenAI/kayıtlı yanıt), göç 0032 (`examine_requested_at` + boş-zaman sahiplenme alanları), `app/output_templates/examine.py` (kuyruk, `TemplateExaminationJob`, harita sürümü + `map_hash`, `examine_error` kodu, `TEMPLATE_EXAMINED`), yüklemede kuyruğa alma, "Yeniden incele" (`POST …/examine`), listede/sayfada sebep, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7115 geçti, 6 atlandı, kapsam %98,84 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) önceki görevlerdeki gibi bu görevle ilgisiz.
- Varsayımlar: §D123 (l)'ye yazıldı — yanıt yalnız `fields`+`notes`, `text`/`date`'te `source`/`font_size`/`max_chars` zorunlu, `examine_error` kod, şema hatası yeniden sorulmaz, sağlayıcı ayarı panelde denetlenir, yeniden inceleme durumu değiştirmez, 0032 öncesi şablonlar kendiliğinden kuyruğa girmez.
- Sonraki pencereye not: tm 184 son sürümü `template.maps[-1]` (`json["fields"]`) üzerinden önizler; onay `approved_at`/`approved_by` yazar ve `map_hash`'i yeniden hesaplamaz (sürüm değişmezse aynıdır), düzenleme `store_map` ile yeni sürüm açmalı. Yeni POST yolları `REVIEWED_MUTATING_ROUTES`'a eklenmeli; web testleri `provider_available`'ı override eder.

## 182 — 15.1-a Hazır şablon deposu — done — 2026-10-23
- Yapıldı: göç 0031 (`output_templates`, boş `output_template_maps`, `generated_documents`; `access_log` `template_id`/`generated_document_id` + CHECK), `app/output_templates/` (yükleme PDF/JPEG/PNG img2pdf kayıpsız, Word/Excel 422, SHA-256 ve ad tekrarı 409, arşiv/geri al, `TEMPLATE_UPLOADED/ARCHIVED/RESTORED`), `_sablonlar/<id>/sablon.pdf` + `pages/`, `Uretilen/` çalışan klasöründe; `/output-templates` liste/süzgeç/şablon sayfası, orijinali aç/indir erişim kaydıyla, menü "Hazır Şablonlar" simgeli, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0031), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7085 geçti, 6 atlandı, kapsam %98,86 — 2 kırmızı (`…plan_d58_verbatim`) HEAD'de de kırmızı (D58 bloğu PLAN'da yok), bu görevle ilgisiz.
- Varsayımlar: §D123 (k)'ye yazıldı — erişim kaydı ayrı sütunlarla (`action` genişlemedi), önizleme görüntüsü kayda girmez, `sha256` saklanan PDF'in, "Etkin" süzgeci = `draft` + `ready`, `_sablonlar/` `static_dirs`'e girmez (yedek kapsamında).
- Sonraki pencereye not: tm 183 haritayı `output_template_maps`'e yazar; liste "alan sayısı" son sürümün `text`/`date` alanlarını sayar (`field_count`), geri alınan şablon onaylı harita varsa `ready`'ye döner. Yeni POST yolları `tests/web/test_access_log.py` `REVIEWED_MUTATING_ROUTES`'a eklenmeli. D58 testleri için ayrı küçük görev hâlâ gerekli.

## 180, 181, 182, 183, 184, 185, 186 — FR-MOD-15 Hazır şablonlar, çıktı hazırlama ve ek profil alanları açıldı — pending — 2026-10-23 (interaktif oturum: insan isteği)
- Yapıldı: İnsan isteği (2026-10-23, PLAN §D123'te birebir) PRD FR-MOD-15 (15.1.1–15.3.3, 10 satır), §3 R3/R12 notları, §4 sözlük, §5.2 kapsam, 10.1.1 menü sırası, §8.1 üç tablo + `employees` sütunları, §8.2 `Uretilen/` ve `_sablonlar/`, §8.3 olaylar, §8.4 `person` alanları, §8.7 alan haritası şeması, §9 S29, §10 kapsam dışı; MASTER-PROMPT K11/K16/K17 istisnası (insan kararı); PLAN §0 (Faz 1: 82 ✅ · 10 ⬜, 41/49 Must, Kapanış AÇIK), §2 matris, §4.4 tablo, §D123 sözleşme, §G 8 satır; tasks.json tm 180–186 (15.3-a/b, 15.1-a/b/c, 15.2-a/b), bağımlılıklar ve etiketler. Kod değişmedi.
- Doğrulama: PRD §20.6 tablosu değişmedi (`tests/web/test_confirm.py` okur) — test yeşil; `tests/web/test_ui_standard.py`, `tests/i18n` yeşil; sayım komutları (CONVENTIONS §1.3) §0 ile eşit; `node scripts/arsiv-dondur.mjs` dry-run sonucu HANDOFF'un altında.
- Varsayımlar: (1) R3/R12/K11/K17 daraltması insan tarafından 2026-10-23'te açıkça onaylandı (§D123 a, "Onay" cümlesi); veto ihtimali kapandı. (2) Word/Excel şablonu, kutu çizme, toplu üretim, e-imza kapsam dışı bırakıldı (ayrı insan isteği). (3) Pasaport numarası ayrı sütun değil, `employee_identifiers`'tan gösterim. (4) Onay ve üretim tek adımlı (§D61 geri alınabilirlik), §20.6'ya satır yok. (5) Sıra: önce tm 180 (alanlar) ve tm 182 (depo) paralel açılabilir; 181 → 180; 183 → 182; 184 → 183; 185 → 184+180; 186 → 185; (tm 187 kapanış denetimi insan isteğiyle silindi, 2026-10-23; Faz 1 kapanışı yeniden açılacak görevle yapılır).
- Sonraki pencereye not: `task-master next` tm 180 ya da 182'yi verir; `[OPUS-XHIGH]`. Her görev `docs/ARAYUZ-STANDARDI.md`'ye uyar ve `test_ui_standard`'ı yeşil tutar. D58 testleri (tm yok) hâlâ `PLAN.md`'de olmayan D58 bloğunu arıyor — ayrı küçük görev önerisi: testler `docs/archive/plan-kanit/`'ten okusun.
