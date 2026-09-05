# CONVENTIONS — Definition of Done, Git ve Handoff Kuralları

Bu dosya **"bitti" kelimesinin objektif tanımıdır**. Her madde çalıştırılabilir bir komut ve
beklenen bir exit code'dur. "Kod gözden geçirildi", "sanırım çalışıyor", "mantıken doğru"
gibi öznel ifadeler kanıt sayılmaz.

---

## 1) Definition of Done (DoD) kapısı

Bir görev `done` sayılmadan önce aşağıdaki komutların **hepsi** çalıştırılır ve **hepsi
exit 0** döner. Biri bile kırmızıysa görev `done` değildir.

| # | Komut | Ne doğrular |
|---|---|---|
| 1 | `ruff check .` | Lint temiz |
| 2 | `ruff format --check .` | Biçim tutarlı |
| 3 | `python -m compileall -q app tests` | Sözdizimi hatası yok |
| 4 | `pytest -q -m "not live"` | Tüm testler yeşil (unit + entegrasyon) |
| 5 | `pytest -q -m "not live" --cov=app --cov-fail-under=70` | Kapsam eşiği (Faz 0 sonundan itibaren zorunlu) |
| 6 | `alembic upgrade head` (temiz geçici SQLite üzerinde) | Göç zinciri kırılmamış |
| 7 | `python -c "import app.main"` | Uygulama içe aktarılabiliyor |
| 8 | Görevin **kendi kabul kriteri** (PRD'deki satır) | İşin gerçekten yapıldığı |
| 9 | Yeni kod için **test yazılmış olması** | Kapsam iddiası değil, dosya kanıtı |
| 10 | `PLAN.md` gereksinim satırının güncellenmiş olması | Plan bayatlamıyor |

Ek koşullu kapılar:

| Koşul | Ek komut |
|---|---|
| `Dockerfile` veya `docker-compose.yml` değiştiyse | `docker compose config` exit 0 |
| Panel şablonu değiştiyse | İlgili yol için istek testi (`TestClient`) exit 0 |
| Yapay zekâ promptu değiştiyse | Kayıtlı yanıt testleri yeşil (`pytest -q tests/ai`) |

### 1.1 Kapıyı kuran görevler istisnadır

Faz 0'ın ilk görevleri (`00.1.1` … `00.1.4`) kapının kendisini kurar. O görevlerde kapı,
**o görevin kurduğu kadarıyla** koşulur: `pytest` henüz test yokken "0 test" ile geçerse
bu kabul edilir, ama `00.1.2` bittiğinde en az bir gerçek test bulunmak zorundadır.
`00.1.4` bittikten sonra 1–4 arası maddeler her görevde koşulur, 5. madde Faz 0 kapanışından
itibaren zorunludur.

### 1.2 PLAN.md kanıt disiplini: hücrede damga, dipnotta geçmiş

Gereksinim tablosundaki `Durum` hücresi **yalnız** şu iki biçimden birini taşır:

```
✅ → K04.1
◐ → K04.1
```

Hücreye kanıt metni, dosya adı, test sayısı, tarih veya açıklama **YAZILMAZ**. Kanıt,
`PLAN.md` sonundaki `## K. Kanıt Geçmişi` bölümünde ilgili `#### K<kod>` bloğuna **madde
olarak eklenir**:

```
#### K04.1 — 04.1 · Dosya içi gruplama
- ✅ ardışık sayfa gruplama — `app/pipeline/group.py` · test `tests/test_group.py` (11) · tm 24
```

Var olan maddeler silinmez, üzerine yazılmaz — bu bir geçmiş kaydıdır, ekleyerek büyür.

**Sebebi ölçümdür.** Kanıt hücrede biriktiğinde tablo satırı on binlerce karaktere çıkar;
sonraki her pencerenin `grep`'i o tek satırı okurken bağlam bütçesinin önemli bir kısmını
yakar. Ayrıca kanıt metnindeki kaçırılmamış `|` karakterleri satırı yanlış sütunlara böler
ve panel durumu yanlış okur.

### 1.3 Sayım kuralı

`PLAN.md`'nin en üstündeki faz özet tablosundaki `✅ / ◐ / ⬜` sayıları **tablolardan
sayılarak** yazılır, tahminle değil. Elle yazılmış sayı paneldeki `plan-count-drift`
bulgusunu doğurur. Sayım komutu:

```bash
# Gereksinim satırı üç parçalı kimlikle başlar (00.1.1); §G düz tablosunun satırları
# iki parçalıdır (00.1) ve SAYILMAZ — deseni gevşetirsen §G'yi de sayar, sayım şişer.
grep -cE '^\| [0-9]{2}\.[0-9]+\.[0-9]+ ' PLAN.md              # toplam gereksinim satırı
grep -cE '^\| [0-9]{2}\.[0-9]+\.[0-9]+ .*✅' PLAN.md           # tamamlanan
grep -cE '^\| [0-9]{2}\.[0-9]+\.[0-9]+ .*⬜' PLAN.md           # açık
```

Faz bazında saymak için önce faz bölümünün satır aralığını bul
(`grep -n '^## .*FAZ' PLAN.md`), sonra `sed -n '<baş>,<son>p'` ile o aralığı yukarıdaki
desene ver.

### 1.4 Kapının önkoşulları

- Testler **ön planda** koşulur. `run_in_background` ile başlatılan test/build komutu, pencere
  sırasını bitirdiği anda oturumla birlikte ölür ve sonuç asla gelmez. Uzun süren suite için
  yeterli `timeout` ver (tam suite için 900000 ms).
- Testler ağ erişimi olmadan geçmelidir. Canlı yapay zekâ çağrısı yapan testler `live`
  işaretlidir ve kapıda `-m "not live"` ile dışarıda bırakılır.
- Test veritabanı her koşuda geçici ve izoledir; paylaşılan bir veritabanına karşı koşulmaz.

---

## 2) Git kuralları

- Ana dal `main`. Görev dalı: `task/<tm-id>-<kısa-slug>`.
- Commit biçimi Conventional Commits:
  `feat(<alan>): <özet>` · `fix(<alan>): <özet>` · `test(<alan>): ...` · `refactor(...)` ·
  `chore: ...` · `docs: ...`
- Commit gövdesinde görev ve gereksinim kimliği geçer:
  ```
  feat(matching): MRZ TD3 ayrıştırma ve kontrol hanesi doğrulaması

  PRD 05.3.1, 05.3.2 — tm 31
  ```
- `PLAN.md` ve `HANDOFF.md` güncellemesi **görevin kendi commit'inin içindedir**.
- **Uzak depo (remote) kuralı.** Bu depoda başlangıçta remote **tanımlı değildir**. Kapanış
  adımı şudur: `git remote` çıktısı boşsa push **atlanır** ve commit yeterlidir; remote
  tanımlıysa push zorunludur. Pencere kendiliğinden remote **eklemez** — remote tanımlamak
  insanın işidir. Push'un atlandığı durum kapanış notunda ayrıca belirtilmez, normaldir.
- Kapanışta `git status` temiz olmalıdır. Kalan değişiklik varsa ya commit'lenir ya da neden
  bırakıldığı `HANDOFF.md`'ye yazılır.
- **Yasak:** force-push, history rewrite, `main` üzerinde doğrudan deneysel commit,
  gerçek secret commit'i, başka repoya push.

---

## 3) Handoff notu formatı

Her görev kapanışında `HANDOFF.md`'nin `## Task log (newest-first)` başlığının **hemen
altına** şu blok eklenir. En fazla dört madde; uzun anlatım yazılmaz.

```markdown
## <tm-id> — <başlık> — <done|blocked> — <YYYY-MM-DD>
- Yapıldı: <tek cümle, ne inşa edildi>
- Doğrulama: <hangi kapılar yeşil, kaç test>
- Varsayımlar: <onay beklemeden yapılan varsayım; yoksa "yok">
- Sonraki pencereye not: <bir sonraki işin bilmesi gereken tek şey>
```

Blocked kapanışında `Yapıldı` yerine `Nerede kaldı`, `Doğrulama` yerine `Son hata` yazılır ve
denenen çözümler kısaca listelenir.

---

## 4) Task Master durum akışı

| Durum | Ne zaman |
|---|---|
| `pending` | Açık, henüz başlanmadı |
| `in-progress` | Pencere işi devraldı — **tespit biter bitmez işaretlenir**, opsiyonel değildir |
| `done` | DoD kapısı yeşil + commit yapıldı (remote varsa push da) |
| `blocked` | Kapı geçilemedi; HANDOFF'a BLOCKED notu yazıldı |
| `deferred` | Bilinçli olarak sonraki faza bırakıldı |
| `cancelled` | Kapsam dışı kaldı |

`in-progress` damgası kritiktir: pencere beklenmedik şekilde ölürse (kota, çökme, elle
durdurma) görev `pending` göründüğü sürece hiçbir denetim onu yarım kalmış saymaz ve iş
sessizce kaybolur.

Alt görevi olan bir üst görev, **tüm** alt görevleri `done` olduğunda `done` işaretlenir.
Üst görevin kendisi kod yazmaz.

### 4.1 Öncelik seviyeleri — `critical` rezervedir

| Seviye | Kim atar | Ne zaman |
|---|---|---|
| `high` | Planlama | Faz 0 ve v1 Must |
| `medium` | Planlama | v1 Should |
| `low` | Planlama | v2 / v3 |
| `critical` | **YALNIZ** panelin "düzeltmeye gönder" penceresi | Sağlık taraması bulgusundan doğan düzeltme |

Planlama sırasında (PRD aktarımı, bootstrap, §G toplu aktarımı, elle açılan görevler)
**yalnız `high` / `medium` / `low`** kullanılır. `critical` sıralamada `high`'ın da önüne
geçer; planlama sırasında dağıtılırsa gerçek düzeltmelerin önüne geçer ve seviye anlamını
yitirir.

Serbest yazım kullanılmaz. Tam olarak bu dört kelimeden biri yazılır — tanınmayan bir değer
(`"very high"` gibi) sıralamada `low`'un bile altına düşer.

---

## 5) Kapsam disiplini

- Bir pencere **yalnız kendi görevini** yapar. Başka görevin işine girmez.
- Yolda görülen kusur düzeltilmez; yeni görev olarak açılır ve `HANDOFF.md`'ye not düşülür.
  İstisna: değişikliğin kendi testini kırdığı durumlar — o zaman düzeltmek görevin parçasıdır.
- PRD'de olmayan özellik **eklenmez**. İhtiyaç görülüyorsa `PLAN.md` §D'ye sapma olarak yazılır
  ve karar insana bırakılır.
- Kilitli teknik karar (`MASTER-PROMPT.md` §4) değiştirilmez. Karar yanlış görünüyorsa uygulanır
  ve §D'ye yazılır.

---

## 6) Gizlilik kuralı — bu projeye özgü

Bu sistem kimlik belgesi işler. Bu yüzden:

- **Gerçek kişisel belge deponun hiçbir yerine girmez.** Ne test verisi, ne örnek, ne ekran
  görüntüsü olarak.
- Testler `tests/fixtures/gen.py` ile üretilen **sentetik** belgeleri kullanır.
- `data/` dizini `.gitignore`'dadır ve orada kalır.
- Log ve hata mesajlarına belge numarası, ad-soyad gibi alanlar **açık** yazılmaz; olay
  logunda kimlik alanları veritabanı kaydına referansla tutulur.
- Yapay zekâ sağlayıcısına yalnız işlenmekte olan sayfa gönderilir; başka çalışanın verisi
  aynı isteğe konmaz.
