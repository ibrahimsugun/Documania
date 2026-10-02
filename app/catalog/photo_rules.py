"""Profil fotoğrafı kural seti — katalogda tutulan, panelden açılıp kapatılan kurallar (11.6.1).

Kural seti `known_document_types.photo_rules` sütununda (§8.6, JSON) durur; şekli **bu modülün**
sözleşmesidir. Her kural kimliğiyle bir giriştir, girişte `enabled` bulunur; çözünürlük kuralı
ayrıca asgari piksel boyutlarını taşır:

    {"face_visible": {"enabled": true},
     "min_resolution": {"enabled": true, "min_width_px": 400, "min_height_px": 400}, ...}

Bu modül yalnız kuralları **tanımlar ve saklar**. Fotoğrafın kurallara göre değerlendirilmesi
(pass/fail/unsure, çözünürlüğün ölçülmesi, `fail` → Unresolved) 11.7'nin işidir; o iş etkin
kuralları `enabled_photo_rules`tan okur. Kural kapatılınca değerlendirilmez.

- **Okuma toleranslıdır** (`read_photo_rules`): kayıt boşsa (`None`), bir kuralın girişi yoksa ya da
  bozuksa (elle düzenlenmiş `catalog.yaml`) o kuralın varsayılanı kullanılır; tanımsız anahtarlar
  yok sayılır. Kural seti yüzünden katalog okunamaz olmaz — `CatalogEntry.photo_rules` serbest
  sözlük olarak kalır.
- **Yazma katıdır** (`build_photo_rules`): panelden gelen değerler doğrulanır, kayıt her zaman bütün
  kuralları açıkça yazar; bozuk giriş kaydedilmez.
- Kurallar yalnız `PHOTO_RULE_TYPES` türlerindedir (Profile Picture, K12'nin görsel türü).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.i18n import N_, Translatable

# Kural setinin geçerli olduğu türler; başka türe kural yazılmaz.
PHOTO_RULE_TYPES = frozenset({"profile_picture"})

RESOLUTION_RULE = "min_resolution"
# Asgari çözünürlüğün varsayılanı ve sınırları (piksel). Şirket kararıdır (PLAN.md §D35): panelden
# değişir; varsayılan yalnız ilk açılış değeridir.
DEFAULT_MIN_WIDTH_PX = 400
DEFAULT_MIN_HEIGHT_PX = 400
MAX_RESOLUTION_PX = 20000


@dataclass(frozen=True, slots=True)
class PhotoRuleSpec:
    """Katalogdaki bir kuralın tanımı: kimlik, panelde ve `fail` gerekçesinde görünen ad, açıklama.

    `default_enabled` kayıtta girişi olmayan kuralın durumudur. Şirket kararına bağlı kural
    (`company_decision`) varsayılan olarak kapalıdır: İK açana kadar hiçbir fotoğrafı elemez.
    """

    id: str
    label: str
    description: str
    default_enabled: bool = True
    company_decision: bool = False


PHOTO_RULE_SPECS: tuple[PhotoRuleSpec, ...] = (
    PhotoRuleSpec(
        "face_visible",
        N_("Yüz görünür"),
        N_("Yüz tam ve net görünmeli; kapalı ya da kesik olmamalı."),
    ),
    PhotoRuleSpec(
        "single_person", N_("Tek kişi"), N_("Fotoğrafta yalnız çalışanın kendisi bulunmalı.")
    ),
    PhotoRuleSpec(
        "neutral_expression",
        N_("Nötr ifade"),
        N_("Yüz ifadesi nötr olmalı; gülme, ağız açma ve göz kısma olmamalı."),
    ),
    PhotoRuleSpec(
        "plain_background",
        N_("Sade arka plan"),
        N_("Arka plan düz ve sade olmalı; desen, eşya ya da başka kişi görünmemeli."),
    ),
    PhotoRuleSpec(
        RESOLUTION_RULE,
        N_("Asgari çözünürlük"),
        N_("Görüntünün piksel boyutu asgari genişlik ve yüksekliğin altında olmamalı."),
    ),
    PhotoRuleSpec(
        "no_sunglasses",
        N_("Güneş gözlüğü yok"),
        N_("Gözler görünmeli; güneş gözlüğü ya da renkli cam olmamalı."),
    ),
    PhotoRuleSpec(
        "no_head_covering",
        N_("Baş örtüsü yok"),
        N_(
            "Baş örtüsü kabul edilmez. Bu şirket kararıdır; açılmadıkça fotoğraf bu yüzden elenmez."
        ),
        default_enabled=False,
        company_decision=True,
    ),
)

_SPECS_BY_ID = {spec.id: spec for spec in PHOTO_RULE_SPECS}


@dataclass(frozen=True, slots=True)
class PhotoRuleSetting:
    """Bir kuralın kayıtlı durumu; `min_*_px` yalnız çözünürlük kuralında dolu."""

    spec: PhotoRuleSpec
    enabled: bool
    min_width_px: int | None = None
    min_height_px: int | None = None

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def label(self) -> str:
        return self.spec.label

    def to_record(self) -> dict[str, Any]:
        """Kayıttaki (JSON) hâli."""
        record: dict[str, Any] = {"enabled": self.enabled}
        if self.min_width_px is not None:
            record["min_width_px"] = self.min_width_px
        if self.min_height_px is not None:
            record["min_height_px"] = self.min_height_px
        return record


class PhotoRulesError(ValueError):
    """Panelden gelen kural seti reddedildi; `problems` alan adı → mesajlar."""

    def __init__(self, problems: dict[str, list[str]]) -> None:
        self.problems = problems
        lines = [f"- {name}: {text}" for name, texts in problems.items() for text in texts]
        super().__init__("Fotoğraf kuralları reddedildi:\n" + "\n".join(lines))


@dataclass(frozen=True, slots=True)
class PhotoRulesForm:
    """Formun ham değerleri (doğrulanmamış); hata olursa sayfaya aynen geri yazılır."""

    enabled: tuple[str, ...] = ()
    min_width_px: str = str(DEFAULT_MIN_WIDTH_PX)
    min_height_px: str = str(DEFAULT_MIN_HEIGHT_PX)

    @classmethod
    def from_settings(cls, settings: Iterable[PhotoRuleSetting]) -> PhotoRulesForm:
        """Kayıtlı kural setinin form değerleri (formun açılışı)."""
        items = tuple(settings)
        resolution = next(item for item in items if item.id == RESOLUTION_RULE)
        return cls(
            enabled=tuple(item.id for item in items if item.enabled),
            min_width_px=str(resolution.min_width_px),
            min_height_px=str(resolution.min_height_px),
        )


def _pixels(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_RESOLUTION_PX:
        return value
    return default


def _setting(spec: PhotoRuleSpec, entry: object) -> PhotoRuleSetting:
    """Kayıttaki girişten kural durumu; giriş yok ya da bozuksa varsayılan."""
    given = entry if isinstance(entry, Mapping) else {}
    enabled = given.get("enabled")
    setting_enabled = enabled if isinstance(enabled, bool) else spec.default_enabled
    if spec.id != RESOLUTION_RULE:
        return PhotoRuleSetting(spec, setting_enabled)
    return PhotoRuleSetting(
        spec,
        setting_enabled,
        _pixels(given.get("min_width_px"), DEFAULT_MIN_WIDTH_PX),
        _pixels(given.get("min_height_px"), DEFAULT_MIN_HEIGHT_PX),
    )


def read_photo_rules(raw: Mapping[str, Any] | None) -> tuple[PhotoRuleSetting, ...]:
    """Kayıtlı `photo_rules`tan bütün kuralların durumu, katalogdaki sırayla.

    Kayıt `None` ya da sözlük dışıysa bütün kurallar varsayılanındadır; girişi eksik ya da bozuk
    kural varsayılanına döner; tanımsız anahtarlar yok sayılır.
    """
    given = raw if isinstance(raw, Mapping) else {}
    return tuple(_setting(spec, given.get(spec.id)) for spec in PHOTO_RULE_SPECS)


def enabled_photo_rules(raw: Mapping[str, Any] | None) -> tuple[PhotoRuleSetting, ...]:
    """Yalnız açık kurallar — 11.7 fotoğrafı bunlara göre değerlendirir; kapalı kural sorulmaz."""
    return tuple(setting for setting in read_photo_rules(raw) if setting.enabled)


def _form_pixels(text: str, field: str, problems: dict[str, list[str]]) -> int | None:
    text = text.strip()
    if not (text.isascii() and text.isdigit()) or not 1 <= int(text) <= MAX_RESOLUTION_PX:
        problems.setdefault(field, []).append(
            Translatable(
                N_("1 ile {limit} arasında bir piksel sayısı yazılmalı"), limit=MAX_RESOLUTION_PX
            )
        )
        return None
    return int(text)


def build_photo_rules(form: PhotoRulesForm) -> dict[str, Any]:
    """Formdan kaydedilecek `photo_rules` kaydı; her kural açıkça yazılır.

    İşaretli kural açık, işaretsiz kapalıdır. Tanımsız kural kimliği ve geçersiz piksel sayısı
    `PhotoRulesError` ile reddedilir; çözünürlük sınırları kural kapalıyken de denetlenir.
    """
    problems: dict[str, list[str]] = {}
    unknown = sorted(set(form.enabled) - set(_SPECS_BY_ID))
    if unknown:
        problems["enabled"] = [
            Translatable(N_("Tanımsız kural: {rules}"), rules=", ".join(unknown))
        ]
    width = _form_pixels(form.min_width_px, "min_width_px", problems)
    height = _form_pixels(form.min_height_px, "min_height_px", problems)
    if problems:
        raise PhotoRulesError(problems)
    chosen = set(form.enabled)
    return {
        spec.id: PhotoRuleSetting(
            spec,
            spec.id in chosen,
            width if spec.id == RESOLUTION_RULE else None,
            height if spec.id == RESOLUTION_RULE else None,
        ).to_record()
        for spec in PHOTO_RULE_SPECS
    }
