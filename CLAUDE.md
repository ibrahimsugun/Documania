# CLAUDE.md — Documania (her Claude Code penceresi bunu otomatik okur)

Bu depo, çalışan belgelerini içeriğinden anlayıp doğru çalışana yerleştiren **akıllı belge
yönetim sisteminin** otonom yapımıdır. Her pencere — interaktif olsun, `run-loop.sh` ile
açılmış olsun — aşağıdaki kurallara uyar.

## Her zaman geçerli

- **Kilitli kararlar + yığın + sınırlar:** `MASTER-PROMPT.md`. Ürün kuralları K1–K18 orada.
- **"Bitti" tanımı + git + handoff:** `CONVENTIONS.md`. Bir iş bu kapıdan (exit code'larla)
  geçmeden bitmiş değildir.
- **Ne yapılacak, kabul kriteri ne:** `urun-gereksinim-dokumani-PRD.md`. Kimliksiz iş yapılmaz.
- **Neredeyiz:** `PLAN.md`. Baştan sona okuma — hedef satırı `grep -n` ile bul.
- **Tarihsel kaynak:** `docs/UYGULAMA-PLANI-KAYNAK.md` — ilk uygulama planı. Taşınmaz, silinmez.
- **Tek orkestratör:** implementasyon subagent'a dağıtılmaz; pencere kendi araçlarıyla çalışır.

## Otonom döngüde

- Pencere protokolü: `TASK-RUNNER-PROMPT.md` (bootstrap → resume → build → verify → kapanış).
- Yalnız hedef görev yapılır; `done` ancak DoD kapısı yeşilse + commit + push + Task Master done.
- Bağlam hafızadan değil, Task Master + git + `HANDOFF.md`'den kurulur.

## Cloud'da (Claude Code web, Linux)

- Ortamı `scripts/cloud-setup.sh` kurar (SessionStart kancası): `.venv` `uv.lock`'tan, `.venv/bin`
  PATH'te, `task-master` kurulu. Kurulumu elle tekrarlama; `python`, `pytest`, `ruff`, `alembic`
  doğrudan çağrılır. `.env` ve `data/` cloud'da yoktur — DoD kapısı ikisine de ihtiyaç duymaz.
- Bir cloud oturumu = bir görev penceresi: `TASK-RUNNER-PROMPT.md` aynen uygulanır.
- Git: oturumun kendi dalında çalışılır, kapanışta o dala push edilir ve `main`'e PR açılır; görev
  dalı adı (CONVENTIONS §2) bu durumda oturumun dalıdır. `main`'e doğrudan push edilmez, PR'ı insan
  birleştirir. Task Master `done`, PLAN ve HANDOFF aynı PR'dadır.
- Aynı anda tek görev: her görev `tasks.json`, `PLAN.md`, `HANDOFF.md`'ye yazar. Önceki görevin PR'ı
  birleşmeden yenisi başlatılmaz.

## Bu ürünün değişmez kuralı

Sistem belgeyi **anlar**, **değiştirmez**. İçerik üretilmez, yazı değiştirilmez, form
doldurulmaz, görüntü kırpılmaz. Yalnız fiziksel düzenleme yapılır: sayfa çıkar, sayfa birleştir,
kayıpsız sar, yeniden adlandır, taşı. Emin olunamayan belge kuyruğa alınır, tahmin edilmez.

## Sınırlar

Production deploy / DNS / TLS / gerçek secret / ödeme YOK. **Gerçek kimlik belgesi depoya
girmez** — testler sentetik belgelerle çalışır. force-push, history rewrite, DB drop, başka
repoya dokunma YOK. İzleme panelinin klasörüne (`Claude_Loop_Controller-main`) dokunulmaz.
Kapsam dışına çıkılmaz: yan düzeltme yeni görev olarak açılır.
