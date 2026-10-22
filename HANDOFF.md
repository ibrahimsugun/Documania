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

## 180, 181, 182, 183, 184, 185, 186, 187 — FR-MOD-15 Hazır şablonlar, çıktı hazırlama ve ek profil alanları açıldı — pending — 2026-10-23 (interaktif oturum: insan isteği)
- Yapıldı: İnsan isteği (2026-10-23, PLAN §D123'te birebir) PRD FR-MOD-15 (15.1.1–15.3.3, 10 satır), §3 R3/R12 notları, §4 sözlük, §5.2 kapsam, 10.1.1 menü sırası, §8.1 üç tablo + `employees` sütunları, §8.2 `Uretilen/` ve `_sablonlar/`, §8.3 olaylar, §8.4 `person` alanları, §8.7 alan haritası şeması, §9 S29, §10 kapsam dışı; MASTER-PROMPT K11/K16/K17 istisnası (insan kararı); PLAN §0 (Faz 1: 82 ✅ · 10 ⬜, 41/49 Must, Kapanış AÇIK), §2 matris, §4.4 tablo, §D123 sözleşme, §G 8 satır; tasks.json tm 180–187 (15.3-a/b, 15.1-a/b/c, 15.2-a/b, §5.2 kapanış), bağımlılıklar ve etiketler. Kod değişmedi.
- Doğrulama: PRD §20.6 tablosu değişmedi (`tests/web/test_confirm.py` okur) — test yeşil; `tests/web/test_ui_standard.py`, `tests/i18n` yeşil; sayım komutları (CONVENTIONS §1.3) §0 ile eşit; `node scripts/arsiv-dondur.mjs` dry-run sonucu HANDOFF'un altında.
- Varsayımlar: (1) R3/R12/K11/K17 daraltması insan tarafından 2026-10-23'te açıkça onaylandı (§D123 a, "Onay" cümlesi); veto ihtimali kapandı. (2) Word/Excel şablonu, kutu çizme, toplu üretim, e-imza kapsam dışı bırakıldı (ayrı insan isteği). (3) Pasaport numarası ayrı sütun değil, `employee_identifiers`'tan gösterim. (4) Onay ve üretim tek adımlı (§D61 geri alınabilirlik), §20.6'ya satır yok. (5) Sıra: önce tm 180 (alanlar) ve tm 182 (depo) paralel açılabilir; 181 → 180; 183 → 182; 184 → 183; 185 → 184+180; 186 → 185; 187 → 181+186.
- Sonraki pencereye not: `task-master next` tm 180 ya da 182'yi verir; `[OPUS-XHIGH]`. Her görev `docs/ARAYUZ-STANDARDI.md`'ye uyar ve `test_ui_standard`'ı yeşil tutar. D58 testleri (tm yok) hâlâ `PLAN.md`'de olmayan D58 bloğunu arıyor — ayrı küçük görev önerisi: testler `docs/archive/plan-kanit/`'ten okusun.
