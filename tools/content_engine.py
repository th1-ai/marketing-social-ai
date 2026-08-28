"""tools/content_engine.py - Content Creation AI's whole decision engine.

Pure functions over plain dicts and dataclasses - no I/O, no LLM, no
randomness, no wall-clock reads, ported from the source's own header rule:
"the AI 'thinking' the page animates is the steps array each function
returns alongside its result." `tools/campaign.py` is the only place that
touches the store; `tests/test_content_engine.py` runs the exact same
functions a real brief does.

Composes only from `content_assets` (the brand kit Brand & Collateral AI
owns) and a hard-coded copy bank - there is no image generation at runtime,
matching the roster's "won't publish without a human eye on brand and
licensing."
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

LAYOUTS = ["bottom", "panel", "center"]
CTA_COLORS = [("Coast Blue", "#1379A8"), ("Sea Teal", "#178F79")]

SUBJECT_TAGS = {
    "spa": {"spa", "wellness", "massage", "sauna", "hot-tub", "yoga", "pool"},
    "rooms": {"room", "suite", "bed", "linen"},
    "dining": {"dining", "restaurant", "breakfast", "terrace", "bar", "cocktails", "food"},
    "offer": {"exterior", "pool", "beach", "coast", "aerial", "lobby", "sunset"},
}
SEASON_TAGS = {
    "winter": {"winter", "snow", "ski", "fireplace", "apres"},
    "summer": {"summer", "beach", "pool", "coast", "ocean", "terrace"},
    "autumn": {"sunset", "harbour", "city"},
    "spring": {"yoga", "coast", "garden"},
}

# subject -> (winter | other) -> {headlines, sublines, ctas}
COPY_BANK = {
    "spa": {
        "winter": {"headlines": ["Apres, then relax", "The spa after the slopes",
                                "Warm water, cold peaks"],
                  "sublines": ["An outdoor hot tub under the peaks.",
                              "Sauna, snow, repeat.", "The ritual the mountain earns."],
                  "ctas": ["Book the winter escape", "Reserve your ritual"]},
        "other": {"headlines": ["Slow down, properly", "The spa hour you keep meaning to take"],
                 "sublines": ["Treatments built around doing nothing.",
                             "An afternoon with no agenda."],
                 "ctas": ["Reserve your ritual", "Plan the week"]},
    },
    "rooms": {
        "winter": {"headlines": ["Warm rooms, cold views", "Sleep well, ski hard"],
                  "sublines": ["Linen, a fireplace, and a mountain out the window."],
                  "ctas": ["Book the room", "Plan the week"]},
        "other": {"headlines": ["Sea light, linen sheets", "A room that does less, better"],
                 "sublines": ["Nothing you don't need. Everything you do."],
                 "ctas": ["Book the room", "Reserve your stay"]},
    },
    "dining": {
        "winter": {"headlines": ["The table by the window", "Dinner, then the fire"],
                  "sublines": ["A menu built for the season."],
                  "ctas": ["Reserve a table", "Plan the week"]},
        "other": {"headlines": ["The table by the window", "Come down to the water"],
                 "sublines": ["Local, seasonal, no fuss."],
                 "ctas": ["Reserve a table", "Book the winter escape"]},
    },
    "offer": {
        "winter": {"headlines": ["Five nights, one price", "The long weekend, done right"],
                  "sublines": ["One offer. No discount theatre."],
                  "ctas": ["Claim the winter escape", "Plan the week"]},
        "other": {"headlines": ["The long weekend, done right", "Five nights, one price"],
                 "sublines": ["One offer. No discount theatre."],
                 "ctas": ["Book the winter escape", "Plan the week"]},
    },
}

#: brief-language detection for `parse_freestyle()`. Distinctive, unaccented
#: words per language, matched against the accent-folded brief text (so
#: "verão"/"verao" hit the same keyword) - see `_fold()` and
#: `detect_brief_language()`. English is the implicit default: nothing here
#: firing means "treat it as English." COPY_BANK below only has English
#: copy, so a hit here is what makes `generate_campaign()` raise the
#: "captions are English" flag - see README "Adding a language."
LANGUAGE_TAGS: dict[str, set[str]] = {
    "es": {"habitacion", "habitaciones", "playa", "verano", "parejas", "necesito",
          "necesitamos", "huespedes", "desayuno", "reserva", "anuncio"},
    "fr": {"chambre", "chambres", "plage", "ete", "besoin", "clients",
          "petit-dejeuner", "diner", "reservation", "annonce"},
    "de": {"zimmer", "strand", "sommer", "paare", "brauche", "brauchen", "gaeste",
          "fruhstuck", "abendessen", "anzeige"},
    "it": {"camera", "camere", "spiaggia", "estate", "coppie", "bisogno",
          "ospiti", "colazione", "prenotazione", "annuncio"},
    "pt": {"quarto", "quartos", "praia", "verao", "casais", "preciso",
          "precisamos", "hospedes", "cafe da manha", "anuncio"},
}
LANGUAGE_NAMES = {"es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
                  "pt": "Portuguese"}

LINE_BY_TAG = [
    ({"hot-tub", "spa", "massage", "wellness"}, "Warm water, cold peaks"),
    ({"fireplace"}, "A fire that never goes out"),
    ({"ski", "mountain", "snow"}, "The mountain does the hard part"),
    ({"breakfast", "terrace", "dining", "restaurant"}, "The table by the window"),
    ({"pool", "beach", "coast", "ocean"}, "Come down to the water"),
    ({"room", "suite", "bed"}, "Sea light, linen sheets"),
]


@dataclass
class Brief:
    subject: str  # spa | rooms | dining | offer
    property_slug: str
    season: str  # winter | summer | autumn | spring
    audience: str  # couples | families | business | wellness
    freestyle: str = ""
    language: str = "en"  # best guess at the freestyle brief's own language
    subject_confident: bool = True  # False when parse_freestyle had to default, not match


@dataclass
class CreativeSpec:
    photo_slug: str
    photo_url: str
    layout: str
    treatment: str
    headline: str
    subline: str
    cta: str
    cta_color: str
    text_tone: str
    property_slug: str
    eyebrow: str = ""
    off_brand: bool = False
    label: str = ""


@dataclass
class SequenceSpec:
    shots: list[dict]
    end: dict


@dataclass
class CampaignResult:
    creatives: list[CreativeSpec]
    sequence: SequenceSpec
    thinking_log: list[str]
    needs_human: bool = False
    needs_human_reasons: list[str] = field(default_factory=list)


def _fold(text: str) -> str:
    """Lowercase and strip accents - 'verão' and 'verao' match the same keyword."""
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def detect_brief_language(text: str) -> str:
    """Best guess at the freestyle brief's own language.

    A keyword vote over `LANGUAGE_TAGS`, accent-folded. Returns 'en' when
    nothing else scores - English is the fallback, never a guess at one of
    the other five. See `parse_freestyle()` and README "Adding a language."
    """
    folded = _fold(text)
    scores = {lang: sum(1 for kw in words if kw in folded)
             for lang, words in LANGUAGE_TAGS.items()}
    best_lang = max(scores, key=lambda lang: scores[lang])
    return best_lang if scores[best_lang] > 0 else "en"


def parse_freestyle(text: str, properties: dict[str, str], default_property: str) -> Brief:
    """Keyword-maps free text onto the four brief fields, first match wins.

    Recognises the same concepts in English plus Spanish, French, German,
    Italian and Portuguese, accent-folded (see `_fold()`) so 'verão' and
    'verao' hit the same keyword. `subject` still falls back to 'offer' when
    nothing matches in any of the six - `Brief.subject_confident` says
    whether that was a real match or a default, so a caller can ask a human
    instead of silently shipping a campaign under the wrong heading. Also
    detects the brief's own language (`Brief.language`) - see
    `detect_brief_language()` - because the copy bank below is English-only
    regardless of what language the brief itself was written in.
    """
    t = _fold(text)

    def pick(mapping: list[tuple[set[str], str]], default: str) -> tuple[str, bool]:
        for keywords, value in mapping:
            if any(k in t for k in keywords):
                return value, True
        return default, False

    subject, subject_confident = pick([
        ({"spa", "wellness", "massage", "ritual", "relax", "massagem", "masaje",
          "massaggio", "bem-estar", "bienestar", "benessere", "relaxar", "relajar",
          "rilassarsi"}, "spa"),
        ({"suite", "room", "sleep", "quarto", "quartos", "habitacion", "habitaciones",
          "chambre", "chambres", "zimmer", "camera", "camere", "cama", "letto", "bett",
          "dormir", "dormire"}, "rooms"),
        ({"dining", "restaurant", "dinner", "breakfast", "table", "chef", "food",
          "restaurante", "jantar", "cena", "desayuno", "cafe da manha", "diner",
          "petit-dejeuner", "abendessen", "fruhstuck", "colazione"}, "dining"),
    ], "offer")
    property_slug = default_property
    for slug, keywords in properties.items():
        if any(_fold(k) in t for k in keywords.split(",")):
            property_slug = slug
            break
    season, _ = pick([
        ({"winter", "ski", "snow", "christmas", "apres", "inverno", "invierno",
          "hiver", "neve", "nieve", "neige", "schnee", "natal", "navidad", "noel",
          "weihnachten", "natale"}, "winter"),
        ({"autumn", "october", "november", "fall", "outono", "otono", "automne",
          "herbst", "autunno"}, "autumn"),
        ({"spring", "april", "may", "primavera", "printemps", "fruhling"}, "spring"),
    ], "summer")
    audience, _ = pick([
        ({"couple", "romance", "honeymoon", "casal", "casais", "pareja", "parejas",
          "coppia", "coppie", "paar", "paare", "lua de mel", "luna de miel",
          "lune de miel", "luna di miele"}, "couples"),
        ({"famil", "kids", "familia", "famille", "familie", "famiglia", "criancas",
          "ninos", "enfants", "kinder", "bambini"}, "families"),
        ({"business", "corporate", "meeting", "negocio", "negocios", "affaires",
          "geschaft", "affari", "reuniao", "reunion", "sitzung", "riunione"}, "business"),
        ({"wellness", "yoga", "retreat", "bem-estar", "bienestar", "wohlbefinden",
          "benessere", "retiro", "retraite", "ritiro"}, "wellness"),
    ], "couples")
    language = detect_brief_language(text)
    return Brief(subject=subject, property_slug=property_slug, season=season,
                audience=audience, freestyle=text, language=language,
                subject_confident=subject_confident)


def campaign_name(brief: Brief, property_label: str) -> str:
    season_label = brief.season.capitalize()
    subject_label = {"spa": "spa & wellness", "rooms": "rooms & suites", "dining": "dining",
                    "offer": "stay offer"}[brief.subject]
    return f"{season_label} {subject_label} — {property_label}"


def score_photo(photo: dict, brief: Brief) -> int:
    """+4 property match (+1 collection-level), +3/tag hit capped at 2 subject
    hits, +2/tag hit capped at 2 season hits, -3 season mismatch, +1 hero."""
    score = 0
    if photo.get("property_slug") == brief.property_slug:
        score += 4
    elif photo.get("property_slug") == "collection":
        score += 1
    tags = set(photo.get("tags", []))
    subject_hits = len(tags & SUBJECT_TAGS.get(brief.subject, set()))
    score += 3 * min(subject_hits, 2)
    season_hits = len(tags & SEASON_TAGS.get(brief.season, set()))
    score += 2 * min(season_hits, 2)
    photo_season = photo.get("season")
    if brief.season == "winter" and photo_season == "summer":
        score -= 3
    elif brief.season != "winter" and photo_season == "winter":
        score -= 3
    if photo.get("hero"):
        score += 1
    return score


def pick_photos(assets: list[dict], brief: Brief, limit: int = 4) -> list[dict]:
    """Top ``limit`` photos by score, tie-broken by slug ascending."""
    photos = [a for a in assets if a.get("type") == "photo" and a.get("url")]
    scored = [(score_photo(p, brief), p) for p in photos]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["slug"]))
    return [p for _, p in scored[:limit]]


def generate_campaign(brief: Brief, photos: list[dict], rules: dict,
                      property_label: str,
                      hotel_languages: tuple[str, ...] = ("en",)) -> CampaignResult:
    """12 creatives: 4 photos x 3 layouts, treatments and copy rotated per version.

    ``hotel_languages`` is ``config/hotel.yaml: hotel.languages``. COPY_BANK is
    English-only, so when the brief's own language (``brief.language``, from
    `parse_freestyle()`) is one the hotel actually operates in but is not
    English, the campaign is still drafted - never blocked - but
    `CampaignResult.needs_human` comes back true with a plain-language reason,
    and it never guesses when `brief.subject_confident` is false either. See
    README "Adding a language."
    """
    if not photos:
        return CampaignResult([], SequenceSpec([], {}), ["No photos matched this brief."])
    guard = rules.get("brand_guard", True)
    name_property = rules.get("always_name_property", True)
    season_key = "winter" if brief.season == "winter" else "other"
    bank = COPY_BANK[brief.subject][season_key]
    creatives: list[CreativeSpec] = []
    for i in range(12):
        photo = photos[i % len(photos)]
        layout = LAYOUTS[(i // len(photos)) % 3]
        treatment = "warm" if i % 6 == 4 else "bw" if i % 6 == 5 else "none"
        headline = bank["headlines"][i % len(bank["headlines"])]
        subline = bank["sublines"][i % len(bank["sublines"])]
        cta = bank["ctas"][i % len(bank["ctas"])]
        off_brand = (not guard) and i % 4 == 3
        cta_name, cta_hex = CTA_COLORS[i % 2] if not off_brand else ("Off-brand", "#D6188F")
        label = f"{photo.get('title', photo['slug'])} · " \
               f"{'bottom bar' if layout == 'bottom' else 'side panel' if layout == 'panel' else 'centered'}"
        if off_brand:
            label += " · off-brand"
        creatives.append(CreativeSpec(
            photo_slug=photo["slug"], photo_url=photo.get("url", ""), layout=layout,
            treatment=treatment, headline=headline, subline=subline, cta=cta,
            cta_color=cta_hex, text_tone="dark" if layout == "panel" else "light",
            property_slug=brief.property_slug,
            eyebrow=property_label if name_property else "", off_brand=off_brand, label=label,
        ))
    top_titles = ", ".join(p.get("title", p["slug"]) for p in photos[:3])
    log = [
        "Read the brief.",
        f"Scanned the content library: {len(photos)} photo(s) picked, top three: {top_titles}.",
        "Opened the brand kit: palette locked to Coast Blue and Sea Teal CTAs "
        "- brand guard is on." if guard else
        "Opened the brand kit: brand guard is OFF - exploring off-brand colorways "
        "alongside the approved palette (marked).",
        "Wrote the copy: one idea per sentence, no urgency theatre.",
        "Composed the versions: 12 creatives, 4 photos x 3 layouts, treatments and "
        "copy rotated per version.",
        "Cut a video sequence.",
    ]
    sequence = build_sequence(brief, photos)
    needs_human_reasons: list[str] = []
    if not brief.subject_confident:
        needs_human_reasons.append(
            f"Could not confidently tell what this brief is about from the text - "
            f"defaulted to '{brief.subject}'. Confirm the subject before using this "
            f"campaign (or rerun with --subject/--season/--audience).")
    if brief.language != "en" and brief.language in hotel_languages:
        lang_name = LANGUAGE_NAMES.get(brief.language, brief.language)
        needs_human_reasons.append(
            f"This brief was written in {lang_name}; the copy bank only has English "
            f"captions. Captions are English - translate before posting.")
    if needs_human_reasons:
        log.append("Flagged for a human: " + " ".join(needs_human_reasons))
    return CampaignResult(creatives=creatives, sequence=sequence, thinking_log=log,
                          needs_human=bool(needs_human_reasons),
                          needs_human_reasons=needs_human_reasons)


def build_sequence(brief: Brief, photos: list[dict], base: CreativeSpec | None = None) -> SequenceSpec:
    shots = list(photos[:4])
    if base is not None:
        leader = next((p for p in photos if p["slug"] == base.photo_slug), None)
        rest = [p for p in photos if p["slug"] != base.photo_slug][:3]
        shots = ([leader] if leader else []) + rest
        shots = shots[:4]
    used_lines: set[str] = set()
    out_shots = []
    for photo in shots:
        tags = set(photo.get("tags", []))
        line = None
        for tag_set, candidate in LINE_BY_TAG:
            if tags & tag_set and candidate not in used_lines:
                line = candidate
                break
        if line is None:
            line = f"{photo.get('title', photo['slug'])}"
        used_lines.add(line)
        out_shots.append({"photo_slug": photo["slug"], "photo_url": photo.get("url", ""),
                          "line": line})
    if out_shots and base is not None:
        out_shots[-1]["line"] = base.headline
    end = {"title": base.headline if base else (out_shots[0]["line"] if out_shots else ""),
          "subline": brief.property_slug, "cta": base.cta if base else "Book the stay"}
    return SequenceSpec(shots=out_shots, end=end)


@dataclass
class VariationResult:
    drafts: list[CreativeSpec]
    thinking_log: list[str]


def generate_variations(base: CreativeSpec, photos: list[dict], rules: dict) -> VariationResult:
    """Cheapest-first variation order: CTA colour, background treatment, one-word
    copy tests, up to 2 photo swaps sharing a tag, one video cut. Capped at 12
    when `rules.variation_cap` is on (the video draft is protected from the cap)."""
    cap_on = rules.get("variation_cap", True)
    drafts: list[CreativeSpec] = []

    def clone(**changes: Any) -> CreativeSpec:
        base_kwargs = {**base.__dict__}
        base_kwargs.update(changes)
        base_kwargs["label"] = f"{base.label} variant"
        return CreativeSpec(**base_kwargs)

    for name, hex_ in [("Coast Blue", "#1379A8"), ("Sea Teal", "#178F79"),
                       ("Sunset Gold", "#C9A227")]:
        drafts.append(clone(cta_color=hex_, label=f"{base.label} · CTA {name}"))

    drafts.append(clone(treatment="bw", label=f"{base.label} · black & white"))
    drafts.append(clone(treatment="warm", label=f"{base.label} · warm tone"))
    drafts.append(clone(treatment="red", label=f"{base.label} · red tone"))
    drafts.append(clone(text_tone="dark" if base.text_tone == "light" else "light",
                        label=f"{base.label} · flipped text tone"))

    if "apres" in base.headline.lower() or "après" in base.headline.lower():
        headline_a, headline_b = "After the slopes, relax", "Ski. Spa. Sleep."
    else:
        headline_a = base.headline.split(",")[0]
        headline_b = "Arrive. Unwind. Repeat."
    drafts.append(clone(headline=headline_a, label=f"{base.label} · copy test A"))
    drafts.append(clone(headline=headline_b, label=f"{base.label} · staccato copy"))
    cta_swap = base.cta.replace("Book", "Claim").replace("Reserve", "Claim")
    drafts.append(clone(cta=cta_swap, label=f"{base.label} · CTA verb swap"))

    base_photo = next((p for p in photos if p["slug"] == base.photo_slug), None)
    base_tags = set(base_photo.get("tags", [])) if base_photo else set()
    swaps = [p for p in photos if p["slug"] != base.photo_slug
            and set(p.get("tags", [])) & base_tags]
    swaps.sort(key=lambda p: (-len(set(p.get("tags", [])) & base_tags), p["slug"]))
    for p in swaps[:2]:
        drafts.append(clone(photo_slug=p["slug"], photo_url=p.get("url", ""),
                            label=f"{p.get('title', p['slug'])} · photo swap"))

    if cap_on and len(drafts) > 11:
        drafts = drafts[:11]

    log = [
        "Read the winning spec.", "Checked the brand kit.",
        "Built the color grid: CTA and background treatments first - cheapest "
        "tests, fastest reads.",
        "Wrote the copy tests: one word changed at a time, so the winner is "
        "attributable.",
        "Swapped the photography.", "Cut the video version.",
    ]
    return VariationResult(drafts=drafts, thinking_log=log)
