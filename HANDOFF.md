# HANDOFF — pencereler arası köprü

Her görev penceresi kapanırken buraya bir blok ekler. Bloklar **newest-first** sıralıdır:
en yeni blok `## Task log (newest-first)` başlığının hemen altındadır.

**Bu dosyayı baştan sona okuma.** Sana gereken en üstteki birkaç bloktur: `head -60 HANDOFF.md`.
Eski bir işi arıyorsan hedefli ara: `grep -n 'tm <id>' HANDOFF.md | head -5`.

Blok biçimi `CONVENTIONS.md` §3'te tanımlıdır:

```markdown
## <tm-id> — <başlık> — <done|blocked> — <YYYY-MM-DD>
- Yapıldı: <tek cümle>
- Doğrulama: <hangi kapılar yeşil, kaç test>
- Varsayımlar: <yoksa "yok">
- Sonraki pencereye not: <bir sonraki işin bilmesi gereken tek şey>
```

## Task log (newest-first)

## 0 — kurulum — done — 2026-09-05
- Yapıldı: Belge sözleşmesi kuruldu (PRD, MASTER-PROMPT, CONVENTIONS, CLAUDE, TASK-RUNNER-PROMPT,
  run-loop.sh, PLAN.md, görev ağacı). Henüz kod yazılmadı.
- Doğrulama: PLAN.md panel biçimine uygun (145 gereksinim satırı); `.taskmaster/tasks/tasks.json`
  91 görev; §G düz tablosu ile görev başlıkları birebir eşleşiyor. Kararlar PRD §12'ye
  karar tablosu olarak yazıldı; [OPUS-MAX] görev sayısı 4.
- Varsayımlar: C1 (geliştirmede SQLite), C2 (uzak git deposu yok, push atlanır) — PLAN §C.
- Sonraki pencereye not: İlk iş **tm 1 — `00.1` Uygulama iskeleti**. DoD kapısını kuran görev
  odur; `CONVENTIONS.md` §1.1'e göre kapı o görevde kurulduğu kadarıyla koşulur.
