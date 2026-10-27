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

## 196 — 11.9-i Önizleme ön yükleme: giriş sonrası küçükler, sayfaya girince o sayfanın büyükleri — done — 2026-10-27
- Yapıldı: `preview-prefetch.js` (yalnız girişli sayfada) boşta `/previews/thumbs` listesinden bütün küçük önizlemeleri 2 eşzamanlı + 150 ms arayla, `priority: "low"` ile HTTP önbelleğine indirir, bitince `localStorage`'a yalnız sürüm yazar; sayfadaki `data-preview-large` (tür, katalog örnekleri, `/uploads/<id>` sayfa görüntüleri) önce iner; tıklama/HTMX/çıkışta iptal, gizli sekme/saveData/2g'de durur, 429/503'te `Retry-After` geri çekilme. Sunucu: en çok 2 önizleme üretimi + tek üretim kilidi, ön yükleme beklemez (`503 Retry-After: 2`), liste ucu oturum başına 30/dk; sayfa görüntüsü `private, max-age=900` + ETag/304; çıkışta `Clear-Site-Data: "cache"`.
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check`, temiz SQLite'ta `alembic upgrade head` exit 0; tests/web + storage + scripts + i18n + training (-n 6) 2431 geçti, 4 atlandı; headless Chrome + CDP ile ağ günlüğü (en çok 2 eşzamanlı, orijinal yok, ikinci açılışta yalnız liste + sayfa büyükleri, tıklamada iptal). Tam kapı (`--cov`) koşulmadı (insan kuralı).
- Varsayımlar: liste yalnız eğitim tür sayfası adreslerini verir (`/training/known/<slug>/previews/small/…`); katalog sayfası küçükleri ayrı adreste olduğundan ısıtılmaz, büyükleri aşama 2 ile iner. İmleç sayısal sıra (belge adı saklanmaz). Ön yükleme isteği `X-Preview-Prefetch: 1` başlığıyla ayrılır; kullanıcı isteği sırasını bekler. `asyncio.Semaphore` yerine `threading` (uçlar eşzamanlı değil, Starlette iş parçacığı havuzunda koşar).
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. `Clear-Site-Data` yalnız HTTPS'te (belge.siyahkus.com) ya da localhost'ta etkilidir. Faz 1'de açık satır kalmadı; faz kapanışı (KF1 yeniden denetimi) ayrı iştir, tablo `AÇIK` bırakıldı.

## 195 — 11.9-h Örnek önizlemeleri: küçük türetilmiş önizleme, orijinal yalnız İndir — done — 2026-10-27
- Yapıldı: `app/storage/previews.py` örnekten bir kez 320/1280 px JPEG üretir (`cache/previews/<slug>/<anahtar>-<boyut>.jpg`; PDF'te ilk sayfa; EXIF/ICC yok; piksel sınırı/bomba/bozuk → yer tutucu); eğitim ve katalog sayfaları küçük resmi `…/previews/small/<ad>?v=<anahtar>` ile `loading=lazy decoding=async` alır, ad büyük önizlemeyi açar, orijinal yalnız "İndir" (`attachment`); önizleme `private, max-age=31536000, immutable` + ETag/304 + `nosniff`; `python -m app.training previews` toplu ısıtır; `backup.sh` `cache/previews`'ı hiç arşivlemez; YEDEKLEME, `.env.example`, i18n (en, sr).
- Doğrulama: ruff check/format, compileall, `import app.main`, temiz SQLite'ta `alembic upgrade head`, `python -m app.i18n check` exit 0; tests/web + storage + scripts + i18n + training (-n 6) yeşil. Tam kapı (`--cov`) koşulmadı (insan kuralı: uzun kapı beklenmez).
- Varsayımlar: anahtar içerik özeti yerine ad+boyut+mtime (§D130 izin verir; listeleme dosya okumaz); büyük önizleme yeni sekmede JPEG olarak açılır (iletişim kutusu/JS yok); sürümsüz ya da eski `?v=` isteği aynı baytları `private, no-cache` ile verir; eski anahtarlı önizleme dosyaları silinmez (önbellek, yedeğe girmez).
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. Dağıtımdan sonra `docker compose exec app python -m app.training previews` ile ~2.200 örneği önceden ısıtmak ilk açılış beklemesini önler. tm 196 (ön yükleme, §D131) bu uçların üzerine kurulur.

## 194 — 13.4-b Eğitim malzemesi ayrı hacimlerde ve gece arşivinin dışında — done — 2026-10-27
- Yapıldı: Compose `examples` ve `_egitim` için ayrı hacimler bağlar, `backup.sh` eğitim malzemesini gece arşivine almaz, yeni `scripts/backup-material.sh` onu rsync ile artımlı ve silmeden yedekler/geri koyar.
- Doğrulama: ruff check/format, `tests/scripts` + `tests/deploy` geçti (rsync'li 4 test geliştirme makinesinde rsync yok diye atlandı); tam kapı (`--cov`) koşulmadı (insan kuralı: 50 dk'lık kapıyı bekleme).
- Varsayımlar: §D129 — `_referans` data hacminde kalır ama arşivden çıkar; `--delete` yok; `gelen` tekilleştirme kapsam dışı.
- Sonraki pencereye not: YanPC'ye DAĞITILMADI. Geçiş (insan izni gerekir): uygulamayı durdur → imajı kur → `known_examples`/`known_training` hacimlerine kopyala (`cp -a`) → sayı/bayt doğrula → `data` hacmindeki eski `examples`/`_egitim`'i kaldır → `up -d`; sonra `BACKUP_MATERIAL_DIR` ve `MATERIAL_*_DIR` ile `backup-material.sh`'i bir kez çalıştır.

## 193 — 11.9-g Eğitimde çift inceleme (Sol + Sonnet 5.5) ve "AI kararı" yeniden inceleme komutu — done — 2026-10-27
- Yapıldı: iki anahtar tanımlıyken eğitim her belgeyi GPT-6.1 Sol ve Sonnet 5.5'e (`low`) ayrı sorar; ikisi aynı bilinen türü verirse örnek doğrudan `verified` (olay `review: pair`, aktör `system`), yoksa "AI kararı"; `python -m app.training recheck` mevcut "AI kararı" örneklerini aynı kuralla doğrular/taşır/bırakır ve model başına belirteç + tahmini maliyet yazar; `UsageTotals`, `TRAINING_AUTO_CONFIRM`, i18n (en, sr).
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check` exit 0; tests/training + ai + i18n + worker + config + ui_standard 1543 geçti, 4 atlandı. Tam kapı (`--cov`) koşulmadı (insan kuralı). Yerel kuru koşu (5 örnek, gerçek sağlayıcılar): 4 doğrulanır, 1 belirsiz, ~0,25 $.
- Varsayımlar: §D128 — aynı ama farklı türü veren iki model örneği o türe taşır (`move_example`); Yerleştirilemedi/Başarısız öğeler kapsam dışı; çift panelden seçilemez (sabit).
- Sonraki pencereye not: kod YanPC'ye dağıtılmadı ve canlıdaki 405 "AI kararı" örneği henüz incelenmedi (dağıtım izni bekliyor). Dağıtımdan sonra sunucuda `docker compose exec app python -m app.training recheck --limit 10` ile pilot, sonra tamamı (yaklaşık 20 $).

## 192 — 03.3-b OpenAI sağlayıcısı Responses API'ye, GPT-6.1 Sol — done — 2026-10-26
- Yapıldı: `OpenAIProvider` Chat Completions yerine Responses API (`instructions`, `input_image`/`input_text`, düz işlev aracı, `reasoning.effort` yalnız seçilince, `max_output_tokens` ≥ 16000, `incomplete`/ret reddi); model listesinde `gpt-6.1-sol` (`low`–`max`, varsayılan `medium`), `gpt-6-luna` çıktı; varsayılan `OPENAI_MODEL=gpt-6.1-sol`; `TrainingClassification.notes` 250 karakter (istem dahil). Anthropic sağlayıcısı değişmedi.
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check` exit 0; `tests/ai` + `tests/web/test_ai_settings_page.py` + `tests/test_config.py` + `tests/test_events.py` + `tests/web/test_ui_standard.py` + `tests/db/test_migrations.py` 962 geçti, 4 atlandı. Tam kapı (`--cov`) koşulmadı: değişiklik OpenAI sağlayıcısı ve model listesiyle sınırlı, göç yok (insan kuralı: uzun kapı beklenmez). Gerçek sağlayıcıyla sonda: Sol `low` 4 belge, Sonnet 5.5 (önceden `notes` > 200 ile reddedilen belge) geçti.
- Varsayımlar: §D127'ye yazıldı — ölçüm 14 belge (Luna `none` 9/14 + 3 yanlış; Sonnet 5.5 ve Sol 11/14 + 0 yanlış); `.env`'de `gpt-6-luna` kalan kurulum listede olmayan model olarak çalışmaya devam eder; Terra/Astra eklenmedi.
- Sonraki pencereye not: YanPC'de `ai_settings` satırı ya da `.env` hâlâ `gpt-6-luna` diyorsa kalıcı değişiklik için panelden `/ai-settings`ta OpenAI modelini Sol seçip kaydetmek gerekir (veritabanına dokunulmadı).

