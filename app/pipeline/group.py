"""Dosya içi ve dosyalar arası gruplama, ön/arka yüz eşleşmesi, ardışıklık güvenlik kuralı,
belirsiz eşleştirmenin reddi, beklenen sayfa sayısı kontrolü, bilinmeyen tür ve Word/Excel eki
yolu — PRD 04.1.1, 04.1.2, 04.2.1, 04.3.1, 04.3.2, 04.5.1, 04.6.1, 04.7.1.

Bir dosyanın analiz edilmiş sayfaları `pages.index` sırasıyla **belge adaylarına** ayrılır (§4:
karar motorunun aynı belgeye ait olduğuna hükmettiği sayfa grubu). Sayfa açık adaya ancak aşağıdaki
koşulların hepsi sağlanırsa katılır; biri bile sağlanmazsa yeni aday başlatır:

1. **Ardışık:** adayın son sayfası, bu sayfadan hemen önce analize gönderilen sayfadır. Boş sayfa
   (02.4.1) analize gönderilmez ve başka belgeye ait sayfa değildir: zinciri kırmaz, adaya da girmez
   (S8 "atlanır"; dupleks taramada kartın iki yüzü arasına girer). Analizi başarısız ya da hiç
   yapılmamış sayfanın içeriği bilinmez — başka bir belge olabilir (K5) — zinciri kırar. Analizcinin
   boş dediği ve hiçbir şey okumadığı sayfa da zinciri kırar: sonraki sayfanın devam işareti o boş
   sayfaya göre verilmiştir. Bu sayfalar aday olmaz.
2. **Devam:** sayfanın `continues_previous_page` değeri `true`. Aynı kişinin art arda taranmış iki
   aynı tür belgesini (ör. eski ve yeni pasaport) ayıran işaret budur; `false` bölmek demektir
   (C14).
3. **Aynı tür:** aynı katalog slug'ı; katalog dışı sayfada aynı aday tür adı (harf büyüklüğü ve
   boşluk farkı yok sayılır). Türü belirlenemeyen sayfa hiçbir sayfayla gruplanmaz.
4. **Yüz yapısı (04.1.2):** katalogda `sides: front_back` olan türde ön yüz ve onu izleyen arka yüz
   sırayla eşleşir — aday yalnız ön yüzden oluşuyorsa ve sayfa arka yüzse katılır. Tamamlanmış çift
   başka sayfa almaz; arka yüzden sonra gelen ön yüz ve `single`/`unknown` yüzlü sayfa eşleşmez.
   İki yüzü birlikte taşıyan (`front_and_back`) sayfa, türü ne olursa olsun, tek başına tamamlanmış
   adaydır: önceki adaya katılmaz, sonraki sayfayı almaz; türün bu düzeni kabul edip etmediği
   doğrulayıcının (`sides`) işidir. Tek yüzlü ve katalog dışı türde öteki yüzler sınır değildir.
   Sayfa sayısı sınırı gruplamada uygulanmaz:
   sınırda bölmek geçerli görünen yanlış belgeler üretirdi; aralık dışı aday 04.5'te Unresolved
   olur. Katalogda bulunmayan slug'ın yüz yapısı bilinmediği için gruplanmaz.
5. **Aynı kişi:** iki sayfada da yazılı hiçbir kimlik değeri çelişmez — belge numarası (§20.2.1
   normalizasyonu), doğum tarihi, soyad, ad ve orijinal yazım. İsimlerde harf büyüklüğü, aksan,
   noktalama ve kelime sırası farkı yok sayılır; kelime kümelerinden biri ötekini kapsamıyorsa
   çelişkidir (ikinci adı yazılmamış sayfa çelişmez). Değeri olmayan sayfa (ör. kartın arka yüzü)
   çelişmez. Katılacak sayfa adayın her sayfasıyla karşılaştırılır.

Aday eksik olabilir (yalnız ön ya da yalnız arka yüz, beklenen sayfa sayısı dışında); gruplama onu
tamamlamaz. Başka dosyadaki eş 04.3'ün, sayfa sayısı 04.5'in işidir.

**Ardışıklık güvenlik kuralı (04.2.1, R6/K5):** aynı dosyadaki iki aday aynı belgenin parçaları
olabiliyor ve aralarına başka bir belge girmişse parçalar birleştirilmez; her biri
`contiguity_violation` taşır ve Unresolved'a gider. Adaylar, sıraları ve aradaki belgeler değişmez.
İki aday şu koşulların hepsinde aynı belgenin parçası olabilir:

- **Aynı katalog türü.** Katalog dışı ve türü belirlenemeyen adayın yüz ve sayfa yapısı bilinmez;
  parça olup olmadığına hükmedilmez (rotası 04.6'nın).
- **Tek belgede birleşebilir.** `front_back` türde biri yalnız ön, öteki yalnız arka yüzdür — sıra
  fark etmez, arka yüzü önce taranmış kart da aynı karttır. İki yüzü birlikte taşıyan
  (`front_and_back`) aday tamamlanmıştır, hiçbir parçayla birleşmez. Tek yüzlü türde toplam
  sayfa sayısı türün en fazla sayfa sayısını aşmaz (aralık yoksa sınır yoktur); iki parçanın her
  biri tek başına aralıkta olsa da iki belge mi tek belge mi olduğu bilinemez, kuyruğa gider (R7).
- **Aynı kişi.** 5. koşuldaki kimlik değerleri iki parçanın hiçbir sayfa çiftinde çelişmez.
- **Araya belge girmiş.** İki parça arasında başka bir aday (türü ne olursa olsun) ya da analizi
  olmayan, içeriği bilinmediği için başka belge olabilecek sayfa vardır. Boş sayfa belge değildir:
  yalnız boş sayfayla ayrılmış ya da bitişik eksik parçalar bu kuralın konusu değildir.

Gerekçe (`ContiguityViolation.reason`) kuralı, parçanın ve öteki parçaların sayfalarını ve araya
girenleri kullanıcının gördüğü sayfa numarasıyla (1'den) yazar; kişisel değer taşımaz.

**Dosyalar arası gruplama (04.3.1, K4):** partinin ayrı dosyalarındaki ön ve arka yüz yalnız
katalogda `sides: front_back` ve `direct: false` olan türde tek adayda — önce ön, sonra arka yüz —
eşleşir. Direkt Belge'ye başka dosyadan sayfa eklenmez (K3); tek yüzlü, katalog dışı ve türü
belirlenemeyen adayın dosyalar arası yapısı bilinmez. Dosyaların yükleme sırası belge yapısı
değildir (arka yüz önce yüklenebilir). Ardışıklık dosya içidir: kuralına takılan parça eşleşmez,
eşi aynı dosyada araya belge girmiş hâlde durur. Eşleşme yalnız **tek anlamlıysa** yapılır: türün
partide eşi olmayan tam bir ön ve bir arka yüzü vardır (tamamlanmış çift sayılmaz, ardışıklık
kuralına takılan parça sayılır), ikisi ayrı dosyalardadır, 5. koşuldaki kimlik değerleri çelişmez
ve partide başka yüz olabilecek sayfa yoktur. İki yüzü birlikte taşıyan (`front_and_back`) aday
tamamlanmış çift gibidir: eş beklemez, eşleşmeye girmez ve engel sayılmaz. Engeller:

- türün yüzü ön ya da arka okunmamış (`single`/`unknown`) sayfası;
- analizi olmayan sayfa — içeriği bilinmez;
- katalog türü verilmemiş (türü belirlenemeyen, aday tür adlı ya da slug'ı katalogda olmayan) ve
  tek yüzlü ya da iki yüzü birlikte taşıyan okunmamış sayfa — analizci emin olmadığı türü aday tür
  adıyla yazar (03.4), kartın emin olunmayan yüzü böyle görünür.

Başka katalog türü, tek yüzlü katalog dışı belge ve boş sayfa engel değildir.

**Belirsiz eşleştirmenin reddi (04.3.2):** ayrı dosyalarda eşleşebilecek bir ön ve arka yüz varken
eşleşme tek anlamlı değilse — türün birden fazla ön ya da arka yüzü veya başka yüz olabilecek sayfa
varsa — eşleştirme yapılmaz; türün ardışıklık kuralına takılmamış bütün eksik yüzleri
`ambiguous_pairing` taşır ve Unresolved'a gider (ardışıklık kuralına takılanlar zaten oradadır).
Gerekçe (`AmbiguousPairing.reason`) yüzleri ve engelleri dosya kimliği ve 1'den başlayan sayfa
numarasıyla yazar. Kimlik değerleri çelişen tek ön ve tek arka yüz aynı belge değildir, işaretsiz
ayrı kalır. Eşleşebilecek yüz yoksa (ör. yalnız ön yüzler) hüküm verilmez; eksik yüz 04.5'in
işidir.

**Beklenen sayfa sayısı kontrolü (04.5.1):** dosya içi ve dosyalar arası gruplama bittikten sonra,
başka bir kuralla (04.2.1/04.3.2) zaten işaretlenmemiş ve katalogda türü belirlenmiş her adayın
sayfa sayısı türün `expected_pages` aralığıyla (§8.6) karşılaştırılır — `direct: false` türde
eşleşememiş tek ön ya da tek arka yüz (04.3.2'nin hüküm vermediği, eşleşebilecek karşı yüzün hiç
olmadığı durum) tam burada yakalanır. Aralık tanımlı değilse (`expected_pages: null`) sınır yoktur.
Dışındaysa aday `page_count_violation` taşır ve Unresolved'a gider; aday bölünmez ya da otomatik
tamamlanmaz. Gerekçe (`PageCountViolation.reason`) sayfa sayısını ve beklenen aralığı yazar; kişisel
değer taşımaz. Katalog dışı ve türü belirlenemeyen aday (04.6.1'in) yargılanmaz.

**Bilinmeyen tür (04.6.1, R7):** türü güncel katalogda olmayan her dosya adayı — analizcinin aday
tür adı yazdığı, türünü hiç belirleyemediği ya da analizde yazılan slug'ı katalogdan kalkmış olan —
`unknown_type` taşır ve Unknown'a gider. Aday katalogdaki bir türe zorla atanmaz: benzer adlı
katalog türüne, aday tür adına ya da en yakın türe eşlenmez, slug'ı boş kalır. Yukarıdaki kurallar
katalog türünün yapısına dayandığı için bu adayı yargılamaz; hüküm tektir. Gerekçe
(`UnknownDocumentType.reason`) sayfaları ve önerilen aday tür adını yazar; kişisel değer taşımaz.

**Word/Excel eki (04.7.1, K2):** hiç sayfası olmayan dosya (K2: Word/Excel render/analiz
edilmez) içerik imzasından (`detect_file_kind`) tespit edilir; katalogda `analyze: false` olan ve
o içerik türünü `expected_file_types`'ta taşıyan kayıtla (tohumda yalnız `attachment`) eşleşirse
`AttachmentFile` üretilir. Sayfalara ayrılmaz, kişi/kabul kriteri değerlendirilmez, dönüştürülmez
(K2). Partinin bağlam çalışanı (`Upload.context_employee_id`) doluysa belge olduğu gibi Hazir'a
kaydedilecek şekilde `unresolved` boş kalır; boşsa sahibi belirsiz olduğu için `unresolved` dolar
ve gerekçesiyle Unresolved'a gider — fiziksel kopyalama sonraki görevin (07.x) işidir. Eşleşen bir
`analyze: false` kayıt yoksa (K2 dışı içerik) dosya sayfasız ve adaysız kalır; bu görevin kapsamı
yalnız Word/Excel'dir.

`group_upload` partinin tekrar olmayan dosyalarını ayrı ayrı gruplar, ayrı dosyalardaki yüzleri
eşleştirir ve her aday için bir olay yazar: katalog türünde `DOC_TYPE_DETERMINED`, değilse
`DOC_TYPE_UNKNOWN` (veri: slug veya aday tür adı, sayfalar, yüzler — kişisel değer yok). Dosyalar
arası adayın olayı ilk sayfasının (ön yüz) dosyasına yazılır ve kaynaklarını `sources` olarak taşır.
Ardışıklık kuralına, belirsiz eşleştirmeye, beklenen sayfa sayısı kontrolüne ya da bilinmeyen türe
takılan adayın olayı ayrıca kuralın verisini ve gerekçeyi taşır. Aday tür adı olan bilinmeyen tür
adayında önerilen tür `candidate_document_types`'a aday tür olarak kaydedilir
(`record_candidate_type_sighting`) ve görülme sayıldıysa `CANDIDATE_TYPE_PROPOSED` yazılır. Word/
Excel eki de kendi dosyasına `DOC_TYPE_DETERMINED` yazar (veri: slug, bağlam yoksa `unresolved`).
Oturum commit edilmez; işlem sınırı çağıranındır.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import ClassVar

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis, PagePerson, Side
from app.catalog import Catalog, CatalogEntry, FileType, Sides
from app.db.models import (
    Page,
    QueueKind,
    Upload,
    UploadFile,
    normalize_candidate_type_name,
    record_candidate_type_sighting,
)
from app.events import EventType, event_context, record_event
from app.pipeline.analyze import PageAnalysisStatus
from app.storage import DataLayout, UnsupportedFileTypeError, detect_file_kind

# §20.2.1: belge numarası büyük harfe çevrilir; boşluk, tire, nokta ve eğik çizgi silinir.
_NUMBER_SEPARATORS = re.compile(r"[\s./-]+")
_NON_WORD = re.compile(r"[\W_]+")
_NAME_FIELDS = ("surname", "given_names", "original_script_name")
# Eş beklemeyen, tamamlanmış yüz yapıları (04.1.2): sırayla ön ve arka, ya da iki yüz tek sayfada.
_COMPLETE_FACES = frozenset({(Side.FRONT, Side.BACK), (Side.FRONT_AND_BACK,)})
# Başka dosyadaki bir kartın eksik yüzü olamayan yüzler: tek yüzlü ve iki yüzü birlikte taşıyan.
_NOT_A_MISSING_FACE = frozenset({Side.SINGLE, Side.FRONT_AND_BACK})
# Adayın partideki yeri: (dosya sırası, dosyadaki aday sırası).
_Slot = tuple[int, int]


class StoredAnalysisError(ValueError):
    """Saklanan `pages.analysis_json` §8.4 şemasına uymuyor; mesaj gelen değeri tekrarlamaz."""


@dataclass(frozen=True, slots=True)
class GroupingPage:
    """Gruplamanın okuduğu sayfa; `analysis` yalnız analizi tamamlanmış sayfada doludur."""

    index: int
    is_blank: bool = False
    analysis: PageAnalysis | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CandidatePage:
    """Belge adayındaki tek sayfa: kaynak dosyası, dosyadaki sırası ve analizi."""

    file_id: int
    index: int
    analysis: PageAnalysis = field(repr=False)


@dataclass(frozen=True, slots=True, order=True)
class PageRef:
    """Partideki bir sayfa: kaynak dosya (`upload_files.id`) ve dosyadaki sıra (`pages.index`)."""

    file_id: int
    index: int


@dataclass(frozen=True, slots=True)
class ContiguityViolation:
    """R6 (K5): aday, aynı dosyada araya başka belge girmiş bir belgenin parçası olabilir (04.2.1).

    Parça otomatik birleştirilmez ve Unresolved'a gider. Alanlar dosyadaki sayfa sıralarıdır
    (`pages.index`): `pages` bu parçanın, `counterparts` aynı belgeye ait olabilecek öteki
    parçaların (dosya sırasıyla) sayfaları; `intervening_pages` aradaki başka belgelerin,
    `unanalyzed_pages` aradaki analizi olmayan sayfalardır. Boş sayfa ikisinde de yer almaz.
    """

    rule: ClassVar[str] = "R6"
    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    pages: tuple[int, ...]
    counterparts: tuple[tuple[int, ...], ...]
    intervening_pages: tuple[int, ...] = ()
    unanalyzed_pages: tuple[int, ...] = ()

    @property
    def reason(self) -> str:
        """Değer taşımayan gerekçe; sayfa numarası kullanıcının gördüğü gibi 1'den başlar."""
        between: list[str] = []
        if self.intervening_pages:
            between.append(f"başka belgeye ait sayfa ({_page_numbers(self.intervening_pages)})")
        if self.unanalyzed_pages:
            between.append(
                "analizi yapılamamış, başka belgeye ait olabilecek sayfa "
                f"({_page_numbers(self.unanalyzed_pages)})"
            )
        others = "; ".join(_page_numbers(pages) for pages in self.counterparts)
        piece = "parça" if len(self.counterparts) == 1 else "parçalar"
        return (
            f"Ardışıklık güvenlik kuralı ({self.rule}): bu parça ({_page_numbers(self.pages)}) "
            f"ile aynı belgeye ait olabilecek {piece} ({others}) arasında {' ve '.join(between)} "
            "var; parçalar otomatik birleştirilmez."
        )


@dataclass(frozen=True, slots=True)
class AmbiguousPairing:
    """04.3.2: yüz, partinin ayrı dosyalarındaki yüzlerle tek anlamlı eşleştirilemiyor.

    Eşleştirme yapılmaz; yüz Unresolved'a gider. `face` bu adayın sayfasıdır; `fronts` ve `backs`
    türün partide eşi olmayan bütün ön ve arka yüzleri (bu yüz ve ardışıklık kuralına takılanlar
    dahil), `unoriented_pages` türün yüzü ön ya da arka okunmamış sayfaları, `unanalyzed_pages`
    partide analizi olmayan, `uncertain_type_pages` katalog türü verilmemiş ve tek yüzlü okunmamış
    sayfalardır. Hepsi partideki sırasıyladır.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    face: PageRef
    fronts: tuple[PageRef, ...]
    backs: tuple[PageRef, ...]
    unoriented_pages: tuple[PageRef, ...] = ()
    unanalyzed_pages: tuple[PageRef, ...] = ()
    uncertain_type_pages: tuple[PageRef, ...] = ()

    @property
    def reason(self) -> str:
        """Değer taşımayan gerekçe; dosyadaki sayfa numarası kullanıcının gördüğü gibi 1'den."""
        sentences = [
            f"Belirsiz ön/arka yüz eşleştirmesi: bu yüz ({_page_refs((self.face,))}) partide tek "
            "anlamlı bir eşle eşleştirilemiyor.",
            f"Eşleşmemiş ön yüzler: {_page_refs(self.fronts)}.",
            f"Eşleşmemiş arka yüzler: {_page_refs(self.backs)}.",
        ]
        for label, refs in (
            ("Aynı türün yüzü ön ya da arka okunmamış sayfaları", self.unoriented_pages),
            ("Analizi yapılamamış sayfalar", self.unanalyzed_pages),
            ("Türü kesin belirlenemeyen sayfalar", self.uncertain_type_pages),
        ):
            if refs:
                sentences.append(f"{label}: {_page_refs(refs)}.")
        sentences.append("Yüzler dosyalar arasında otomatik eşleştirilmez.")
        return " ".join(sentences)


@dataclass(frozen=True, slots=True)
class PageCountViolation:
    """04.5.1: adayın sayfa sayısı türün `expected_pages` aralığı (§8.6) dışında.

    Aday otomatik tamamlanmaz ya da bölünmez; gerekçesiyle Unresolved'a gider. `pages` adayın
    sayfalarıdır (dosya kimliği ve dosyadaki sırasıyla, adaydaki sırayla); `expected_min`/
    `expected_max` türün kataloğundaki aralıktır.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    pages: tuple[PageRef, ...]
    expected_min: int
    expected_max: int

    @property
    def reason(self) -> str:
        """Değer taşımayan gerekçe; sayfa sayısı ve beklenen aralık."""
        expected = (
            f"{self.expected_min} sayfa"
            if self.expected_min == self.expected_max
            else f"{self.expected_min}-{self.expected_max} sayfa"
        )
        return (
            f"Beklenen sayfa sayısı kontrolü (04.5.1): bu aday {len(self.pages)} sayfa "
            f"({_page_refs(self.pages)}) taşıyor, tür {expected} bekliyor."
        )


@dataclass(frozen=True, slots=True)
class UnknownDocumentType:
    """04.6.1 (R7): adayın türü güncel katalogda yok; zorla bir türe atanmaz, Unknown'a gider.

    `pages` adayın sayfalarıdır (dosya kimliği ve dosyadaki sırasıyla, adaydaki sırayla).
    `candidate_type_name` analizcinin önerdiği aday tür adıdır (ilk sayfada yazıldığı gibi);
    `document_type_slug` analizde yazılmış ama katalogda bulunmayan slug'dır (katalog analizden
    sonra değişmiş). İkisi de boşsa türü belirlenemedi. `candidate_type_id` önerilen türün aday tür
    kaydıdır (`candidate_document_types.id`); yalnız `group_upload` kaydı yazdıktan sonra dolar.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNKNOWN

    pages: tuple[PageRef, ...]
    candidate_type_name: str | None = None
    document_type_slug: str | None = None
    candidate_type_id: int | None = None

    @property
    def reason(self) -> str:
        """Değer taşımayan gerekçe; sayfalar dosya kimliği ve 1'den başlayan sayfa numarasıyla."""
        subject = f"Bilinmeyen belge türü (04.6.1): bu adayın ({_page_refs(self.pages)})"
        if self.candidate_type_name is not None:
            name = " ".join(self.candidate_type_name.split())
            finding = f'türü katalogda yok; önerilen aday tür: "{name}".'
        elif self.document_type_slug is not None:
            finding = f"analizde yazılan türü ({self.document_type_slug}) güncel katalogda yok."
        else:
            finding = "türü belirlenemedi."
        return f"{subject} {finding} Belge katalogdaki bir türe zorla atanmaz."


@dataclass(frozen=True, slots=True)
class AttachmentWithoutContext:
    """04.7.1 (K2): Word/Excel eki bir çalışan bağlamı olmadan yüklendi, sahibi belirsiz.

    Belge analiz edilmez, dönüştürülmez, olduğu gibi saklanır (K2); yalnız sahibi bilinmediği
    için Unresolved'a gider. `reason` kişisel değer taşımaz.
    """

    queue: ClassVar[QueueKind] = QueueKind.UNRESOLVED

    file_id: int
    document_type_slug: str

    @property
    def reason(self) -> str:
        return (
            "Word/Excel eki (04.7.1): parti bir çalışan bağlamıyla yüklenmedi, sahibi "
            "belirlenemedi; belge analiz edilmez, dönüştürülmez, gerekçesiyle kuyruğa alınır."
        )


@dataclass(frozen=True, slots=True)
class AttachmentFile:
    """04.7.1 (K2): Word/Excel eki — analiz edilmeden, dönüştürülmeden bütün dosya taşınır.

    PDF/JPEG/PNG'nin aksine sayfa render/analiz adımından hiç geçmez; sayfalara ayrılmaz.
    `document_type_slug` katalogda içerik türünü (`expected_file_types`) taşıyan `analyze: false`
    kayıttır (`Catalog.unanalyzed_entry_for`). `unresolved` doluysa parti bağlam çalışanı olmadan
    yüklendi (`Upload.context_employee_id` boş) ve belge Unresolved'a gider; boşsa bağlam çalışanı
    bilindiği için belge olduğu gibi Hazir'a kaydedilir — kişi eşleştirme veya kabul kriteri
    değerlendirmesinden geçmez (K2).
    """

    file_id: int
    document_type_slug: str
    unresolved: AttachmentWithoutContext | None = None


@dataclass(frozen=True, slots=True)
class DocumentCandidate:
    """Aynı belgeye ait olduğuna hükmedilen sayfalar, belgedeki sırasıyla.

    Sayfalar tek dosyadan dosyadaki sırasıyla ya da dosyalar arası eşleşmede (04.3.1) iki dosyadan
    önce ön, sonra arka yüz olarak gelir. `contiguity_violation` doluysa aday, araya başka belge
    girmiş bir belgenin parçasıdır (04.2.1); `ambiguous_pairing` doluysa yüz partide tek anlamlı bir
    eşle eşleştirilemedi (04.3.2); `page_count_violation` doluysa sayfa sayısı türün beklenen
    aralığı dışındadır (04.5.1, yalnız öteki ikisi boşken değerlendirilir). Bu üçünde gerekçesiyle
    Unresolved'a gider. `unknown_type` doluysa türü katalogda yoktur ve Unknown'a gider (04.6.1);
    öteki üç hüküm yalnız katalog türüne verildiği için onlarla birlikte bulunmaz. Hiçbirinde çıktı
    üretilmez.
    """

    pages: tuple[CandidatePage, ...]
    contiguity_violation: ContiguityViolation | None = None
    ambiguous_pairing: AmbiguousPairing | None = None
    page_count_violation: PageCountViolation | None = None
    unknown_type: UnknownDocumentType | None = None

    @property
    def file_ids(self) -> tuple[int, ...]:
        """Adayın kaynak dosyaları, sayfa sırasında ilk görüldükleri sırayla."""
        return tuple(dict.fromkeys(page.file_id for page in self.pages))

    @property
    def document_type_slug(self) -> str | None:
        return self.pages[0].analysis.document_type_slug

    @property
    def candidate_type_name(self) -> str | None:
        """Katalog dışı adayın tür adı, ilk sayfada yazıldığı gibi."""
        return self.pages[0].analysis.candidate_type_name

    @property
    def sides(self) -> tuple[Side, ...]:
        return tuple(page.analysis.side for page in self.pages)


@dataclass(frozen=True, slots=True)
class FileGrouping:
    """Tek dosyanın gruplaması; boş ve analizsiz sayfalar hiçbir adaya girmez.

    Başka dosyadaki yüzle eşleşen yüz (04.3.1) dosyanın adaylarından çıkar, partinin dosyalar arası
    adayına girer.
    """

    file_id: int
    candidates: tuple[DocumentCandidate, ...]
    blank_pages: tuple[int, ...] = ()
    unanalyzed_pages: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class UploadGrouping:
    """Parti gruplaması: tekrar olmayan dosyalar (dosya sırasıyla), dosyalar arası adaylar ve
    Word/Excel ekleri (04.7.1, dosya sırasıyla)."""

    files: tuple[FileGrouping, ...]
    cross_file_candidates: tuple[DocumentCandidate, ...] = ()
    attachments: tuple[AttachmentFile, ...] = ()

    @property
    def candidates(self) -> tuple[DocumentCandidate, ...]:
        """Bütün adaylar: dosyaların adayları dosya sırasıyla, ardından dosyalar arası adaylar."""
        return (
            *(candidate for grouping in self.files for candidate in grouping.candidates),
            *self.cross_file_candidates,
        )


def group_upload(
    session: Session, upload: Upload, *, catalog: Catalog, layout: DataLayout
) -> UploadGrouping:
    """Partinin her dosyasını ayrı gruplar (04.1, 04.2, 04.6), ayrı dosyalardaki yüzleri
    eşleştirir (04.3), sayfa sayısını denetler (04.5), Word/Excel eklerini sınıflar (04.7) ve
    her adayı olay loguna yazar.

    Tekrar dosyası (01.4.1) gruplanmaz: analiz edilmemiştir ve çıktı üretmez. `catalog`, türlerin
    yüz yapısının okunduğu güncel katalogdur (`export_catalog(session)`). Hiç sayfası olmayan
    dosya (K2: Word/Excel render edilmez) `layout`taki içeriğinden Word/Excel eki olup olmadığı
    için sınanır (04.7.1); eşleşmezse gruplamaya girmez (bu görevin kapsamı dışı). Bilinmeyen tür
    adayının önerdiği tür aday tür olarak kaydedilir; dönen gruplamada
    `unknown_type.candidate_type_id` doludur. Kayıtlar ve olaylar bütün dosyalar gruplandıktan
    sonra yazılır: şemaya uymayan saklı analiz hiçbir şey yazılmadan durdurur.
    """
    non_duplicates = [
        upload_file for upload_file in upload.files if upload_file.is_duplicate_of is None
    ]
    grouping = group_across_files(
        (
            group_file_pages(upload_file.id, _grouping_pages(upload_file), catalog=catalog)
            for upload_file in non_duplicates
        ),
        catalog=catalog,
    )
    attachments = [
        attachment
        for upload_file in non_duplicates
        if not upload_file.pages
        and (attachment := _classify_attachment(layout, upload_file, catalog)) is not None
    ]
    page_ids = {
        (page.file_id, page.index): page.id
        for upload_file in upload.files
        for page in upload_file.pages
    }
    with event_context(upload_id=upload.id):
        files = tuple(
            replace(
                file_grouping,
                candidates=tuple(
                    _record_candidate(session, upload.id, candidate, page_ids)
                    for candidate in file_grouping.candidates
                ),
            )
            for file_grouping in grouping.files
        )
        cross_file = tuple(
            _record_candidate(session, upload.id, candidate, page_ids)
            for candidate in grouping.cross_file_candidates
        )
        attached = tuple(
            _record_attachment(session, upload, attachment) for attachment in attachments
        )
    return UploadGrouping(files, cross_file, attached)


def group_file_pages(
    file_id: int, pages: Iterable[GroupingPage], *, catalog: Catalog
) -> FileGrouping:
    """Tek dosyanın sayfalarını belge adaylarına ayırır; kurallar modül açıklamasındadır.

    Araya başka belge girmiş parçalar `contiguity_violation` (04.2.1), türü katalogda olmayan
    adaylar `unknown_type` (04.6.1) ile işaretlenir.
    """
    ordered = sorted(pages, key=lambda page: page.index)
    if len({page.index for page in ordered}) != len(ordered):
        raise ValueError("Aynı dosyada bir sayfa sırası birden fazla kez verildi")
    candidates: list[DocumentCandidate] = []
    blank: list[int] = []
    unanalyzed: list[int] = []
    current: list[CandidatePage] = []
    for page in ordered:
        if page.is_blank:
            blank.append(page.index)
            continue
        analysis = page.analysis
        if analysis is not None and current and _joins(current, analysis, catalog):
            current.append(CandidatePage(file_id, page.index, analysis))
            continue
        if current:
            candidates.append(DocumentCandidate(tuple(current)))
            current = []
        if analysis is None:
            unanalyzed.append(page.index)
        elif _reads_as_blank(analysis):
            blank.append(page.index)
        else:
            current = [CandidatePage(file_id, page.index, analysis)]
    if current:
        candidates.append(DocumentCandidate(tuple(current)))
    return FileGrouping(
        file_id,
        _mark_unknown_types(_mark_contiguity_violations(candidates, unanalyzed, catalog), catalog),
        tuple(blank),
        tuple(unanalyzed),
    )


def group_across_files(groupings: Iterable[FileGrouping], *, catalog: Catalog) -> UploadGrouping:
    """Partinin dosya gruplamalarında ayrı dosyalardaki ön ve arka yüzü eşleştirir (04.3.1).

    Tek anlamlı olmayan eşleştirme yapılmaz, yüzler `ambiguous_pairing` ile işaretlenir (04.3.2);
    kurallar modül açıklamasındadır. Dosyalar `file_id` (yükleme) sırasıyla döner.
    """
    files = sorted(groupings, key=lambda grouping: grouping.file_id)
    if len({grouping.file_id for grouping in files}) != len(files):
        raise ValueError("Aynı partide bir dosya birden fazla kez verildi")
    # Türden bağımsız olarak partide başka bir yüz olabilecek sayfalar.
    unanalyzed = tuple(
        PageRef(grouping.file_id, index)
        for grouping in files
        for index in grouping.unanalyzed_pages
    )
    uncertain_type = tuple(
        _page_ref(page)
        for grouping in files
        for candidate in grouping.candidates
        if _catalog_entry(candidate, catalog) is None
        for page in candidate.pages
        if page.analysis.side not in _NOT_A_MISSING_FACE
    )
    cross_file: list[DocumentCandidate] = []
    paired: set[_Slot] = set()
    ambiguous: dict[_Slot, AmbiguousPairing] = {}
    for faces in _unpaired_faces(files, catalog):
        open_fronts, open_backs = _open_faces(faces.fronts), _open_faces(faces.backs)
        if not any(front[0] != back[0] for front in open_fronts for back in open_backs):
            continue
        unambiguous = len(faces.fronts) == len(faces.backs) == 1 and not (
            faces.unoriented or unanalyzed or uncertain_type
        )
        if unambiguous:
            ((front_slot, front),) = faces.fronts.items()
            ((back_slot, back),) = faces.backs.items()
            if not _identity_conflict(
                front.pages[0].analysis.person, back.pages[0].analysis.person
            ):
                cross_file.append(DocumentCandidate((*front.pages, *back.pages)))
                paired.update((front_slot, back_slot))
            continue
        fronts = tuple(_page_ref(candidate.pages[0]) for candidate in faces.fronts.values())
        backs = tuple(_page_ref(candidate.pages[0]) for candidate in faces.backs.values())
        for slot, candidate in (*open_fronts.items(), *open_backs.items()):
            ambiguous[slot] = AmbiguousPairing(
                face=_page_ref(candidate.pages[0]),
                fronts=fronts,
                backs=backs,
                unoriented_pages=tuple(faces.unoriented),
                unanalyzed_pages=unanalyzed,
                uncertain_type_pages=uncertain_type,
            )
    return UploadGrouping(
        tuple(
            replace(
                grouping,
                candidates=_mark_page_count_violations(
                    _remaining_candidates(position, grouping, paired, ambiguous), catalog
                ),
            )
            for position, grouping in enumerate(files)
        ),
        _mark_page_count_violations(
            sorted(cross_file, key=lambda candidate: _page_ref(candidate.pages[0])), catalog
        ),
    )


def _joins(candidate: Sequence[CandidatePage], analysis: PageAnalysis, catalog: Catalog) -> bool:
    key = _type_key(analysis)
    return (
        analysis.continues_previous_page
        and key is not None
        and key == _type_key(candidate[0].analysis)
        and _faces_match(candidate, analysis, catalog)
        and not any(_identity_conflict(page.analysis.person, analysis.person) for page in candidate)
    )


def _type_key(analysis: PageAnalysis) -> tuple[str, str] | None:
    if analysis.document_type_slug is not None:
        return ("slug", analysis.document_type_slug)
    if analysis.candidate_type_name is not None:
        # Aday tür kaydının tekillik anahtarıyla aynı: aynı adayın sayfaları tek kayda iner.
        return ("candidate", normalize_candidate_type_name(analysis.candidate_type_name))
    return None


def _faces_match(
    candidate: Sequence[CandidatePage], analysis: PageAnalysis, catalog: Catalog
) -> bool:
    # İki yüzü birlikte taşıyan sayfa tek başına tam belgedir: katılmaz, sonrakini almaz (04.1.2).
    if Side.FRONT_AND_BACK in (analysis.side, candidate[-1].analysis.side):
        return False
    slug = analysis.document_type_slug
    if slug is None:
        return True
    entry = catalog.get(slug)
    if entry is None:
        return False
    if entry.sides == Sides.FRONT_BACK:
        faces = [page.analysis.side for page in candidate]
        return faces == [Side.FRONT] and analysis.side == Side.BACK
    return True


def _identity_conflict(first: PagePerson, second: PagePerson) -> bool:
    numbers = (
        _document_number_key(first.document_number),
        _document_number_key(second.document_number),
    )
    if all(numbers) and numbers[0] != numbers[1]:
        return True
    births = first.date_of_birth, second.date_of_birth
    if None not in births and births[0] != births[1]:
        return True
    for name in _NAME_FIELDS:
        words = _name_words(getattr(first, name)), _name_words(getattr(second, name))
        if all(words) and not (words[0] <= words[1] or words[1] <= words[0]):
            return True
    return False


def _document_number_key(value: str | None) -> str:
    return "" if value is None else _NUMBER_SEPARATORS.sub("", value.upper())


def _name_words(value: str | None) -> frozenset[str]:
    if value is None:
        return frozenset()
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    letters = "".join(char for char in decomposed if not unicodedata.combining(char))
    # Noktasız `ı`nın ayrışmış biçimi yok; `I`nın küçük harfiyle (`i`) aynı anahtara iner.
    return frozenset(_NON_WORD.sub(" ", letters.replace("ı", "i")).split())


def _mark_contiguity_violations(
    candidates: Sequence[DocumentCandidate], unanalyzed: Sequence[int], catalog: Catalog
) -> tuple[DocumentCandidate, ...]:
    # Adaylar dosya sırasındadır ve sayfa aralıkları örtüşmez: iki adayın arasındaki adaylar
    # listede de aralarındadır.
    positions_by_type: dict[str, list[int]] = {}
    for position, candidate in enumerate(candidates):
        if candidate.document_type_slug is not None:
            positions_by_type.setdefault(candidate.document_type_slug, []).append(position)
    counterparts: dict[int, list[int]] = {}
    for slug, positions in positions_by_type.items():
        entry = catalog.get(slug)
        if entry is None:
            continue
        for first, second in combinations(positions, 2):
            if _separated(candidates, unanalyzed, first, second) and _may_be_one_document(
                candidates[first], candidates[second], entry
            ):
                counterparts.setdefault(first, []).append(second)
                counterparts.setdefault(second, []).append(first)
    marked = list(candidates)
    for position, others in counterparts.items():
        marked[position] = replace(
            candidates[position],
            contiguity_violation=_violation(candidates, unanalyzed, position, sorted(others)),
        )
    return tuple(marked)


def _separated(
    candidates: Sequence[DocumentCandidate], unanalyzed: Sequence[int], first: int, second: int
) -> bool:
    # Aradaki aday başka belgedir; aday yoksa aradaki analizsiz sayfa başka belge olabilir (K5).
    # Boş sayfa belge değildir.
    if second - first > 1:
        return True
    after, before = candidates[first].pages[-1].index, candidates[second].pages[0].index
    return any(after < index < before for index in unanalyzed)


def _may_be_one_document(
    first: DocumentCandidate, second: DocumentCandidate, entry: CatalogEntry
) -> bool:
    if (Side.FRONT_AND_BACK,) in (first.sides, second.sides):
        return False  # tamamlanmış belge, parça değil (04.1.2)
    if entry.sides == Sides.FRONT_BACK:
        fits = {first.sides, second.sides} == {(Side.FRONT,), (Side.BACK,)}
    else:
        limit = entry.expected_pages
        fits = limit is None or len(first.pages) + len(second.pages) <= limit.max
    return fits and not any(
        _identity_conflict(page.analysis.person, other.analysis.person)
        for page in first.pages
        for other in second.pages
    )


def _violation(
    candidates: Sequence[DocumentCandidate],
    unanalyzed: Sequence[int],
    position: int,
    others: Sequence[int],
) -> ContiguityViolation:
    between: set[int] = set()
    unanalyzed_between: set[int] = set()
    for other in others:
        low, high = sorted((position, other))
        between.update(range(low + 1, high))
        after, before = candidates[low].pages[-1].index, candidates[high].pages[0].index
        unanalyzed_between.update(index for index in unanalyzed if after < index < before)
    # Öteki parça, daha uzaktaki bir parçayla arada kalsa da "başka belge" diye ayrıca sayılmaz.
    between.difference_update(others)
    return ContiguityViolation(
        pages=_indexes(candidates[position]),
        counterparts=tuple(_indexes(candidates[other]) for other in others),
        intervening_pages=tuple(
            sorted(page.index for inner in between for page in candidates[inner].pages)
        ),
        unanalyzed_pages=tuple(sorted(unanalyzed_between)),
    )


def _indexes(candidate: DocumentCandidate) -> tuple[int, ...]:
    return tuple(page.index for page in candidate.pages)


def _page_numbers(indexes: Iterable[int]) -> str:
    return "sayfa " + ", ".join(str(index + 1) for index in indexes)


@dataclass(slots=True)
class _TypeFaces:
    """Bir türün partide eşi olmayan ön/arka yüzleri ve yüzü ön ya da arka okunmamış sayfaları."""

    fronts: dict[_Slot, DocumentCandidate] = field(default_factory=dict)
    backs: dict[_Slot, DocumentCandidate] = field(default_factory=dict)
    unoriented: list[PageRef] = field(default_factory=list)


def _unpaired_faces(files: Sequence[FileGrouping], catalog: Catalog) -> list[_TypeFaces]:
    # Yalnız dosyalar arası eşleşebilen türler: katalogda `front_back`, Direkt Belge değil (K3).
    # Tamamlanmış çift ve iki yüzü birlikte taşıyan sayfa eş beklemez; öteki yüz yapıları türün
    # yüzü belirsiz sayfalarıdır.
    by_type: dict[str, _TypeFaces] = {}
    for file_position, grouping in enumerate(files):
        for position, candidate in enumerate(grouping.candidates):
            entry = _catalog_entry(candidate, catalog)
            if entry is None or entry.direct or entry.sides != Sides.FRONT_BACK:
                continue
            faces = by_type.setdefault(entry.slug, _TypeFaces())
            if candidate.sides == (Side.FRONT,):
                faces.fronts[file_position, position] = candidate
            elif candidate.sides == (Side.BACK,):
                faces.backs[file_position, position] = candidate
            elif candidate.sides not in _COMPLETE_FACES:
                faces.unoriented.extend(_page_ref(page) for page in candidate.pages)
    return list(by_type.values())


def _open_faces(faces: dict[_Slot, DocumentCandidate]) -> dict[_Slot, DocumentCandidate]:
    # Ardışıklık kuralına takılan parça dosyalar arası eşleşmez: eşi aynı dosyada durur (K5).
    return {
        slot: candidate
        for slot, candidate in faces.items()
        if candidate.contiguity_violation is None
    }


def _remaining_candidates(
    file_position: int,
    grouping: FileGrouping,
    paired: set[_Slot],
    ambiguous: dict[_Slot, AmbiguousPairing],
) -> tuple[DocumentCandidate, ...]:
    remaining: list[DocumentCandidate] = []
    for position, candidate in enumerate(grouping.candidates):
        slot = (file_position, position)
        if slot in ambiguous:
            remaining.append(replace(candidate, ambiguous_pairing=ambiguous[slot]))
        elif slot not in paired:
            remaining.append(candidate)
    return tuple(remaining)


def _mark_page_count_violations(
    candidates: Iterable[DocumentCandidate], catalog: Catalog
) -> tuple[DocumentCandidate, ...]:
    """04.5.1: türün `expected_pages` aralığı dışındaki adayı işaretler.

    Başka bir kuralla (04.2.1/04.3.2) zaten Unresolved'a giden aday atlanır — gerekçe oradadır.
    """
    marked: list[DocumentCandidate] = []
    for candidate in candidates:
        if candidate.contiguity_violation is not None or candidate.ambiguous_pairing is not None:
            marked.append(candidate)
            continue
        entry = _catalog_entry(candidate, catalog)
        limit = entry.expected_pages if entry is not None else None
        count = len(candidate.pages)
        if limit is not None and not (limit.min <= count <= limit.max):
            marked.append(
                replace(
                    candidate,
                    page_count_violation=PageCountViolation(
                        pages=tuple(_page_ref(page) for page in candidate.pages),
                        expected_min=limit.min,
                        expected_max=limit.max,
                    ),
                )
            )
        else:
            marked.append(candidate)
    return tuple(marked)


def _mark_unknown_types(
    candidates: Iterable[DocumentCandidate], catalog: Catalog
) -> tuple[DocumentCandidate, ...]:
    """04.6.1: türü katalogda olmayan adayı işaretler; aday hiçbir türe atanmaz."""
    return tuple(
        candidate
        if _catalog_entry(candidate, catalog) is not None
        else replace(
            candidate,
            unknown_type=UnknownDocumentType(
                pages=tuple(_page_ref(page) for page in candidate.pages),
                candidate_type_name=candidate.candidate_type_name,
                document_type_slug=candidate.document_type_slug,
            ),
        )
        for candidate in candidates
    )


def _catalog_entry(candidate: DocumentCandidate, catalog: Catalog) -> CatalogEntry | None:
    slug = candidate.document_type_slug
    return None if slug is None else catalog.get(slug)


def _page_ref(page: CandidatePage) -> PageRef:
    return PageRef(page.file_id, page.index)


def _page_refs(refs: Iterable[PageRef]) -> str:
    return "; ".join(f"dosya {ref.file_id}, sayfa {ref.index + 1}" for ref in refs)


def _reads_as_blank(analysis: PageAnalysis) -> bool:
    # Çelişkili yanıt (boş denmiş ama tür, kişi değeri veya okunaklı alan var) boş sayılmaz.
    person = analysis.person.model_dump()
    contact = person.pop("contact")
    return (
        analysis.is_blank
        and _type_key(analysis) is None
        and all(value is None for value in (*person.values(), *contact.values()))
        and not any(reading.legible for reading in analysis.fields.values())
    )


def _grouping_pages(upload_file: UploadFile) -> list[GroupingPage]:
    return [
        GroupingPage(index=page.index, is_blank=page.is_blank, analysis=_stored_analysis(page))
        for page in upload_file.pages
    ]


def _stored_analysis(page: Page) -> PageAnalysis | None:
    if page.analysis_status != PageAnalysisStatus.DONE or page.analysis_json is None:
        return None
    try:
        # Saklanan analiz katalogsuz okunur (C12): katalog analizden sonra değişmiş olabilir.
        return PageAnalysis.model_validate(page.analysis_json)
    except ValidationError as exc:
        # Gelen değer mesaja konmaz (CONVENTIONS §6); yalnız alan konumu ve kural.
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'yanıt'}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False, include_context=False)
        )
        raise StoredAnalysisError(
            f"Saklanan sayfa analizi §8.4 şemasına uymuyor (dosya {page.file_id}, "
            f"sayfa {page.index}): {problems}"
        ) from None


def _record_candidate(
    session: Session,
    upload_id: str,
    candidate: DocumentCandidate,
    page_ids: dict[tuple[int, int], int],
) -> DocumentCandidate:
    unknown = candidate.unknown_type
    first = candidate.pages[0]
    sighting = None
    if unknown is not None and unknown.candidate_type_name is not None:
        # 04.6.1: önerilen tür aday tür olarak kaydedilir; belge o türe de atanmaz.
        sighting = record_candidate_type_sighting(
            session,
            proposed_name=unknown.candidate_type_name,
            upload_id=upload_id,
            page_id=page_ids[first.file_id, first.index],
        )
        candidate = replace(
            candidate, unknown_type=replace(unknown, candidate_type_id=sighting.candidate_type.id)
        )
    _record_type_event(session, candidate)
    if sighting is not None and sighting.counted:
        record_event(
            session,
            EventType.CANDIDATE_TYPE_PROPOSED,
            file_id=first.file_id,
            page_index=first.index,
            data={
                "candidate_type_id": sighting.candidate_type.id,
                "candidate_type_name": candidate.candidate_type_name,
                "pages": [page.index for page in candidate.pages],
                "created": sighting.created,
                "seen_count": sighting.candidate_type.seen_count,
            },
        )
    return candidate


def _record_type_event(session: Session, candidate: DocumentCandidate) -> None:
    # Olay verisi kişisel değer taşımaz (CONVENTIONS §6); değerler `pages.analysis_json`'dadır.
    data: dict[str, object] = {}
    event_type = (
        EventType.DOC_TYPE_DETERMINED
        if candidate.unknown_type is None
        else EventType.DOC_TYPE_UNKNOWN
    )
    if candidate.document_type_slug is not None:
        data["document_type_slug"] = candidate.document_type_slug
    else:
        data["candidate_type_name"] = candidate.candidate_type_name
    if len(candidate.file_ids) == 1:
        data["pages"] = [page.index for page in candidate.pages]
    else:
        # Dosyalar arası aday (04.3.1): olay ilk sayfanın dosyasına yazılır, kaynaklar veridedir.
        data["sources"] = [
            {
                "file_id": file_id,
                "pages": [page.index for page in candidate.pages if page.file_id == file_id],
            }
            for file_id in candidate.file_ids
        ]
    data["sides"] = [side.value for side in candidate.sides]
    # §8.3'te ardışıklık, belirsiz eşleştirme ve sayfa sayısı hükmüne ayrı olay türü yok; hüküm
    # adayın kendi olayına yazılır. Kuyruk kaydı ve `QUEUED_UNRESOLVED`/`QUEUED_UNKNOWN`
    # planlamadan sonra kuyruğun işidir (08.1).
    reasons: list[str] = []
    violation = candidate.contiguity_violation
    if violation is not None:
        data["contiguity_violation"] = {
            "rule": violation.rule,
            "queue": violation.queue.value,
            "counterparts": [list(pages) for pages in violation.counterparts],
            "intervening_pages": list(violation.intervening_pages),
            "unanalyzed_pages": list(violation.unanalyzed_pages),
        }
        reasons.append(violation.reason)
    ambiguity = candidate.ambiguous_pairing
    if ambiguity is not None:
        data["ambiguous_pairing"] = {
            "queue": ambiguity.queue.value,
            "fronts": _page_ref_data(ambiguity.fronts),
            "backs": _page_ref_data(ambiguity.backs),
            "unoriented_pages": _page_ref_data(ambiguity.unoriented_pages),
            "unanalyzed_pages": _page_ref_data(ambiguity.unanalyzed_pages),
            "uncertain_type_pages": _page_ref_data(ambiguity.uncertain_type_pages),
        }
        reasons.append(ambiguity.reason)
    page_count = candidate.page_count_violation
    if page_count is not None:
        data["page_count_violation"] = {
            "queue": page_count.queue.value,
            "pages": _page_ref_data(page_count.pages),
            "expected_min": page_count.expected_min,
            "expected_max": page_count.expected_max,
        }
        reasons.append(page_count.reason)
    unknown = candidate.unknown_type
    if unknown is not None:
        data["unknown_type"] = {
            "queue": unknown.queue.value,
            "candidate_type_id": unknown.candidate_type_id,
        }
        reasons.append(unknown.reason)
    first = candidate.pages[0]
    record_event(
        session,
        event_type,
        file_id=first.file_id,
        page_index=first.index,
        message=" ".join(reasons) or None,
        data=data,
    )


def _page_ref_data(refs: Iterable[PageRef]) -> list[dict[str, int]]:
    return [{"file_id": ref.file_id, "page_index": ref.index} for ref in refs]


def _classify_attachment(
    layout: DataLayout, upload_file: UploadFile, catalog: Catalog
) -> AttachmentFile | None:
    """04.7.1: dosya içeriği Word/Excel imzasıysa ve katalogda `analyze: false` bir tür
    eşleşiyorsa `AttachmentFile` döner; eşleşmiyorsa `None` (bu görevin kapsamı dışı)."""
    content = layout.resolve(upload_file.stored_path).read_bytes()
    try:
        kind = detect_file_kind(content)
    except UnsupportedFileTypeError:
        return None
    entry = catalog.unanalyzed_entry_for(FileType(kind.value))
    if entry is None:
        return None
    return AttachmentFile(file_id=upload_file.id, document_type_slug=entry.slug)


def _record_attachment(
    session: Session, upload: Upload, attachment: AttachmentFile
) -> AttachmentFile:
    """04.7.1: bağlam çalışanı yoksa `unresolved`i doldurur ve `DOC_TYPE_DETERMINED` yazar."""
    if upload.context_employee_id is None:
        attachment = replace(
            attachment,
            unresolved=AttachmentWithoutContext(
                file_id=attachment.file_id, document_type_slug=attachment.document_type_slug
            ),
        )
    data: dict[str, object] = {"document_type_slug": attachment.document_type_slug}
    message = None
    if attachment.unresolved is not None:
        data["unresolved"] = {"queue": attachment.unresolved.queue.value}
        message = attachment.unresolved.reason
    record_event(
        session,
        EventType.DOC_TYPE_DETERMINED,
        file_id=attachment.file_id,
        message=message,
        data=data,
    )
    return attachment
