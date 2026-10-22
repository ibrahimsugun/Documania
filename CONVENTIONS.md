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
| 4–5 | `pytest -q -m "not live" -n 12 --dist worksteal --cov=app --cov-fail-under=70` | Tüm testler yeşil (unit + entegrasyon) ve kapsam eşiği, tek paralel koşuda (~10 dk) |
| 6 | `alembic upgrade head` (temiz geçici SQLite üzerinde) | Göç zinciri kırılmamış |
| 7 | `python -c "import app.main"` | Uygulama içe aktarılabiliyor |
| 8 | Görevin **kendi kabul kriteri** (PRD'deki satır) | İşin gerçekten yapıldığı |
| 9 | Yeni kod için **test yazılmış olması** (hafif, §1.4) | Kapsam iddiası değil, dosya kanıtı |
| 10 | `PLAN.md` gereksinim satırının güncellenmiş olması | Plan bayatlamıyor |

Ek koşullu kapılar:

| Koşul | Ek komut |
|---|---|
| `Dockerfile` veya `docker-compose.yml` değiştiyse | `docker compose config` exit 0 |
| Panel şablonu değiştiyse | İlgili yol için istek testi (`TestClient`) exit 0 |
| Yapay zekâ promptu değiştiyse | Kayıtlı yanıt testleri yeşil (`pytest -q tests/ai`) |

### 1.1 Kapıyı kuran görevler istisnadır

Faz 0'ın ilk görevleri (`00.1.1` … `00.1.4`) kapının kendisini kurar; kapı o görevlerde kurulduğu kadarıyla
koşulur. Faz 0 bitti, pencereler için geçerli değil. Gerekçe/ölçümler: docs/conventions-gerekce.md §1.1.

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

Canlı dosyada en fazla son 3 madde kalır (açık görevlere ait maddeler dahil); fazlası **aynı commit'te**
`docs/archive/plan-kanit/` altına birebir taşınır, blokta `_Önceki maddeler: docs/archive/plan-kanit/ (#### K<kod>)_`
satırı bırakılır. Taşıma: `node scripts/arsiv-dondur.mjs --apply` (çalıştırmadan önce `node scripts/arsiv-dondur.mjs`
ne taşıyacağını söyler). Eski kanıt gerekiyorsa baştan okuma, `grep -rn 'tm <id>' docs/archive/plan-kanit` ile ara.
Yeni madde kalıbı (kısa tut): `- ✅ <ne> — <dosya:satır> · test <dosya> (n) · tm <id>`.
`C` ve `D` bölümlerinde de canlıda son 5 madde kalır; aynı betik taşır. Bir bloğun canlı kalan maddesinde kapanışsız
"**Kalan" / "henüz yapılmadı" bırakma (panel `suspicious-done` açar); gerekirse `Durum: KAPANDI (tm <id>)` satırı ekle.
Sebep (ölçüm): docs/conventions-gerekce.md §1.2.

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

- Testler **arka planda** koşulur (`run_in_background: true`); zaman aşımı sınırına takılmaz,
  sonuç gelmeden pencere sırasını bitirmez (`Monitor`/bitiş bildirimiyle bekler; yoksa koşu oturumla ölür). Çıktı dosyaya yazılır
  (`> <scratch>/pytest.log 2>&1`), sonuç exit code + son satırlardan okunur. Aynı anda tek
  tam suite koşar.
- **Testler hafif yazılır.** Her davranış için tek, odaklı test yeterlidir: mutlu yol + en
  önemli bir kenar durum. Aynı şeyi tekrar eden parametre patlaması, büyük gerçek boyutlu
  belge üretimi, uzun döngüler, `sleep` ve gereksiz uçtan uca tekrarlar yazılmaz. Tek test
  1 sn'yi geçiyorsa küçültülür (daha küçük sentetik belge, daha az sayfa, mock). Kapsam eşiği
  (%70) korunur; amaç sağlamlık, dayanıklılık testi değil.
- `-n 12` yalnız tam kapı komutundadır, `addopts`'a konmaz (tek dosya koşusunu yavaşlatır).
- **Kararsızlık kuralı:** paralel koşuda düşüp seri koşuda geçen test "paralel yüzünden" denip
  geçilmez. Ortak durum aranır ve test tarafında düzeltilir; `-p no:randomly`, yeniden deneme
  ya da skip kullanılmaz. Parametre kimlikleri süreçten sürece aynıdır (gerekirse `ids=`).
  Ayrıntı: docs/conventions-gerekce.md §1.4.
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

**Canlı dosya sınırı.** `HANDOFF.md` en fazla son 5 görev bloğu + açık (pending/in-progress/blocked/review)
görevlerin bloklarını tutar. Kapanışta yeni blok eklenince en alttaki fazla bloklar **aynı commit'te**
`docs/archive/handoff/` altındaki arşiv dosyasına (`HANDOFF-arsiv-<YYYY-MM-DD>.md`, blokların başına,
newest-first) birebir taşınır: `node scripts/arsiv-dondur.mjs --apply`. Eski kayıt gerekirse
`grep -rn 'tm <id>' docs/archive/handoff` ile ara; arşivi baştan okuma.

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
