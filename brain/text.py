"""Text primitives for the clusterer.

Deliberately dependency-free: no numpy, no scikit-learn, no spaCy. TF-IDF over a few
hundred short news items is a few dozen lines of Python, and the interesting part of this
system is the *blend* of signals in `scoring.py`, not the vector maths. Keeping this pure
also means it can be imported and tested without Django or a database.
"""

from __future__ import annotations

import math
import re
import unicodedata

# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------

# Standard English function words, plus newsroom filler that appears in almost every
# item and therefore carries no signal about *which* event an item is about.
STOPWORDS: frozenset[str] = frozenset(
    """
    a about above across after again against all almost also although always am among an and
    another any are around as at back be became because been before being below between both
    but by came can cannot could did do does doing done down during each either else enough
    even ever every few for from further get got had has have having he her here hers herself
    him himself his how however i if in inside into is it its itself just least less like made
    make many may me might mine more most much must my myself near neither never new next no
    nor not now of off on once one only onto or other others otherwise our ours ourselves out
    outside over own per perhaps rather same she should since so some still such than that the
    their theirs them themselves then there these they this those though through thus to too
    under until up upon us use used very was we well were what when where whether which while
    who whom whose why will with within without would yet you your yours yourself
    monday tuesday wednesday thursday friday saturday sunday today yesterday tomorrow
    said says say told adding added according reported report reports statement spokesperson
    officials official told-reporters pti ani
    """.split()
)

# Runs of capitals that are grammar, not names.
_ENTITY_BLOCKLIST: frozenset[str] = frozenset(
    """
    the a an and but or if so then this that these those it he she they we i you
    in on at by for from to of with without over under after before during
    there here what when where which who whose why how
    mr mrs ms dr shri smt update updates note new
    january february march april may june july august september october november december
    jan feb mar apr jun jul aug sept sep oct nov dec
    monday tuesday wednesday thursday friday saturday sunday
    """.split()
)

# Lowercase words allowed *inside* a multi-word name ("Ministry of Industry & Commerce",
# "Board of Secondary Education").
_ENTITY_CONNECTORS: frozenset[str] = frozenset({"of", "and", "for", "de", "the", "&", "-"})

NUMBER_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}

# ---------------------------------------------------------------------------
# Boilerplate stripping
# ---------------------------------------------------------------------------

# Real desks strip this before they read anything. Leaving it in would also make the two
# pharma press releases look far more alike than they are — they share every line of it.
_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.MULTILINE)
    for p in (
        r"^\s*for immediate release\s*$",
        r"^\s*press (?:note|release)\s*$",
        r"^\s*media (?:note|advisory)\s*$",
        r"^\s*embargoed.*$",
        r"this (?:press )?release contains forward-looking statements.*",
        r"actual results may differ materially.*",
        r"^\s*(?:for )?media (?:queries|contact)s?\s*:.*$",
        r"^\s*for media queries\s*:.*$",
        r"^\s*unsubscribe\s*\|.*$",
        r"^\s*(?:disclosure|disclaimer)\s*:.*$",
        r"^\s*automated post\..*$",
        r"^\s*(?:dyor|nfa)\b.*$",
        r"^\s*(?:jump to|print) recipe.*$",
        r"^\s*—\s*district police.*$",
        r"^\s*p\.?s\.?\s.*$",
    )
)

_WS = re.compile(r"[ \t]+")
_MULTINEWLINE = re.compile(r"\n{3,}")


def strip_boilerplate(text: str) -> str:
    """Remove wrapper text that says nothing about which event this is."""
    out = text
    for pattern in _BOILERPLATE_PATTERNS:
        out = pattern.sub("", out)
    out = _MULTINEWLINE.sub("\n\n", out)
    return out.strip()


def normalize(text: str) -> str:
    """Fold to comparable lowercase text. Keeps digits, % and currency marks."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = text.lower()
    text = re.sub(r"[^a-z0-9%₹$'.,\- \n]", " ", text)
    return _WS.sub(" ", text)


# ---------------------------------------------------------------------------
# Tokens and n-grams
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z][a-z'\-]*|\d[\d,.]*%?")


def tokenize(text: str) -> list[str]:
    """Content tokens from already-normalized text."""
    tokens = []
    for raw in _TOKEN.findall(normalize(text)):
        token = raw.strip("'-.,")
        if not token or token in STOPWORDS:
            continue
        if len(token) == 1 and not token.isdigit():
            continue
        tokens.append(token)
    return tokens


def ngrams(tokens: list[str]) -> list[str]:
    """Unigrams plus bigrams. Bigrams are what separate 'purple line' from 'line'."""
    grams = list(tokens)
    grams += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    return grams


# ---------------------------------------------------------------------------
# Dateline
# ---------------------------------------------------------------------------

# Wire style: "PALANPUR: Four people were killed..."
_DATELINE_COLON = re.compile(r"^\s*([A-Z][A-Z .'-]{2,30}?)\s*:\s")
# Release style: "HYDERABAD — Zydan Therapeutics today announced..."
_DATELINE_DASH = re.compile(r"^\s*([A-Z][A-Z .'-]{2,30}?)\s*[-–—]\s")

_DATELINE_NON_PLACES = frozenset(
    {"press note", "for immediate release", "bulletin no", "notice no", "update", "market close"}
)


def extract_dateline(body: str) -> str | None:
    """The place a piece of copy is filed from, if it declares one.

    Only wires and formal releases carry datelines; blogs and social posts don't. That
    asymmetry matters — the dateline veto in `scoring.py` may only fire when *both*
    items have one, or it would wrongly split a wire report from the blog post about
    the same event.
    """
    for line in body.split("\n"):
        if not line.strip():
            continue
        for pattern in (_DATELINE_COLON, _DATELINE_DASH):
            match = pattern.match(line)
            if match:
                place = " ".join(match.group(1).split()).strip(" .'-")
                if len(place) < 3 or place.lower() in _DATELINE_NON_PLACES:
                    continue
                if any(ch.isdigit() for ch in place):
                    continue
                return place.lower()
        return None  # only ever the first non-blank line
    return None


# ---------------------------------------------------------------------------
# Entities — cheap NER, no model
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_CAP_TOKEN = re.compile(r"^[A-Z][a-zA-Z'&.\-]*$")
_ALLCAPS_TOKEN = re.compile(r"^[A-Z][A-Z'&.\-]{1,}$")

# Above this share of capitalized content words, the line is Title Case (or all-caps) and
# capitalization is the house style rather than a claim that anything is a name.
_TITLE_CASE_SHARE = 0.8
_TITLE_CASE_MIN_WORDS = 4


def _is_title_cased(words: list[str]) -> bool:
    """Whether capitalization in this line carries any information.

    Wire and press-release headlines are sentence case, so a capital is a signal:
    "Purple Line metro services disrupted at Halasuru" capitalizes three words out of ten
    and every one of them is a name. Blogspam headlines are Title Case, where every
    content word is capitalized and none of it means anything — "10 Best Budget
    Smartphones Under ₹15,000" yielded "Best Budget Smartphones" as a proper noun, and a
    filter-coffee recipe yielded "Best Coffee Powders". Sharing `best` and `india` then
    read as 59% name agreement between a recipe and a phone listicle.
    """
    content = [w for w in words if w[:1].isalpha() and w.lower() not in STOPWORDS]
    if len(content) < _TITLE_CASE_MIN_WORDS:
        return False
    capitalized = sum(
        1 for w in content if _CAP_TOKEN.match(w) or _ALLCAPS_TOKEN.match(w)
    )
    return capitalized / len(content) >= _TITLE_CASE_SHARE


def extract_entities(text: str) -> set[str]:
    """Capitalized runs that aren't just sentence-initial capitalization.

    Good enough to tell "Zydan Therapeutics / ZT-441 / ASCEND-3" apart from
    "Verakine Biosciences / VK-208 / HORIZON-2", which is the whole job here.
    """
    entities: set[str] = set()
    for sentence in _SENTENCE_SPLIT.split(text):
        words = [w.strip("(),;:\"'“”") for w in sentence.split()]
        words = [w for w in words if w]
        if _is_title_cased(words):
            continue
        run: list[str] = []
        run_start = 0
        for index, word in enumerate(words):
            capitalized = bool(_CAP_TOKEN.match(word)) or bool(_ALLCAPS_TOKEN.match(word))
            connector = word.lower() in _ENTITY_CONNECTORS and bool(run)
            if capitalized and word.lower() not in _ENTITY_BLOCKLIST:
                if not run:
                    run_start = index
                run.append(word)
            elif connector and index + 1 < len(words):
                if _CAP_TOKEN.match(words[index + 1]) or _ALLCAPS_TOKEN.match(words[index + 1]):
                    run.append(word)
                else:
                    _flush_entity(entities, run, run_start)
                    run = []
            else:
                _flush_entity(entities, run, run_start)
                run = []
        _flush_entity(entities, run, run_start)
    return entities


def _flush_entity(sink: set[str], run: list[str], start: int) -> None:
    if not run:
        return
    # A single capitalized word at the start of a sentence is grammar, not a name.
    if start == 0 and len(run) == 1:
        return
    phrase = " ".join(run).strip(" .-&")
    if len(phrase) < 3:
        return
    if all(word.lower() in _ENTITY_BLOCKLIST or word.lower() in STOPWORDS for word in run):
        return
    sink.add(phrase)


def entity_tokens(entities: set[str]) -> set[str]:
    """Lowercased word set from entity phrases.

    Compared at token level so "Fernandes" in an all-caps social post still matches
    "Neil Fernandes" in wire copy.
    """
    tokens: set[str] = set()
    for phrase in entities:
        for word in re.split(r"[\s.&-]+", phrase.lower()):
            word = word.strip("'")
            if len(word) > 2 and word not in STOPWORDS and word not in _ENTITY_BLOCKLIST:
                tokens.add(word)
    return tokens


# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------

# Abbreviations matter: a blog writes "₹18.4 crore" and a social post writes "₹18.4cr"
# for the same figure. Without "cr" here the two are read as 1.84e8 and 18.4, look
# irreconcilable, and the money veto wrongly splits a real pair.
_MULTIPLIERS: tuple[tuple[str, float], ...] = (
    ("lakh crore", 1e12),
    ("thousand crore", 1e10),
    ("crore", 1e7),
    ("cr", 1e7),
    ("lakh", 1e5),
    ("trillion", 1e12),
    ("billion", 1e9),
    ("bn", 1e9),
    ("million", 1e6),
    ("mn", 1e6),
    ("thousand", 1e3),
    ("lpa", 1e5),
)

_MONEY = re.compile(
    r"(?P<sym>[₹$])\s?(?P<num>\d[\d,.]*)\s*"
    r"(?P<mult>lakh crore|thousand crore|crore|cr|lakh|trillion|billion|bn|million|mn|thousand|lpa)?\b",
    re.IGNORECASE,
)

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|per cent|percent)")

_NUM_OR_WORD = r"(?:\d[\d,]*|" + "|".join(NUMBER_WORDS) + r")"
# Number, then up to five words that are not "the", then a casualty word. Two guards:
#   * the "the" barrier stops "Three of the dead were passengers" being read as a second,
#     conflicting death toll — which would have masked the real conflict between the two
#     NH-48 crashes and let them merge
#   * the gap may not cross a line break, so a headline ending in a number cannot bind to
#     a casualty word opening the body
_CASUALTY = re.compile(
    r"\b(?P<num>" + _NUM_OR_WORD + r")[^\S\n]+"
    r"(?P<gap>(?:(?!the\b)[a-z'\-]+[,]?[^\S\n]+){0,5})"
    r"(?P<word>killed|dead|died|deaths|fatalities|injured|hurt|wounded)\b",
    re.IGNORECASE,
)

_DEAD_WORDS = frozenset({"killed", "dead", "died", "deaths", "fatalities"})

# Only these units may veto a pair. A conflicting death toll or rupee figure means two
# different events; a mismatch in "six stations" vs "four stations" does not, and using
# every noun-attached number as a veto would tear the metro cluster apart.
VETO_UNITS: frozenset[str] = frozenset({"dead", "injured", "money"})


def extract_quantities(text: str) -> dict[str, set[float]]:
    """Numbers keyed by unit. Sets, not scalars: one item may carry several figures."""
    quantities: dict[str, set[float]] = {}

    for match in _MONEY.finditer(text):
        value = _parse_number(match.group("num"))
        if value is None:
            continue
        multiplier = 1.0
        if match.group("mult"):
            key = match.group("mult").lower()
            multiplier = next((m for name, m in _MULTIPLIERS if name == key), 1.0)
        quantities.setdefault("money", set()).add(round(value * multiplier, 2))

    for match in _PERCENT.finditer(text):
        value = _parse_number(match.group(1))
        if value is not None:
            quantities.setdefault("percent", set()).add(value)

    for match in _CASUALTY.finditer(text):
        value = _parse_number(match.group("num"))
        if value is None or value > 100000:
            continue
        unit = "dead" if match.group("word").lower() in _DEAD_WORDS else "injured"
        quantities.setdefault(unit, set()).add(value)

    # Large bare figures ("60,000 commuters", "44,286 households", "1,142 adults") are
    # strong same-event evidence but never a veto.
    #
    # Bare years are excluded. A four-digit number in this range is a date, not a
    # measurement, and it is the least distinctive number in a news corpus — every item
    # in a day's intake carries the same one. Left in, a listicle saying "2026" and a
    # recipe saying "2026" agreed on 100% of their figures and were put up for review.
    for raw in re.findall(r"\b\d[\d,]{3,}\b", text):
        value = _parse_number(raw)
        if value is None or value < 1000:
            continue
        if "," not in raw and _looks_like_year(value):
            continue
        quantities.setdefault("figure", set()).add(value)

    return quantities


def _parse_number(raw: str) -> float | None:
    token = raw.strip().lower().replace(",", "")
    if token in NUMBER_WORDS:
        return float(NUMBER_WORDS[token])
    try:
        return float(token)
    except ValueError:
        return None


def _looks_like_year(value: float) -> bool:
    """A plain four-digit number in calendar range. Written unseparated, "2026" is a
    year; "2,026" would be a count, which is why the caller checks for the comma."""
    return value.is_integer() and 1900 <= value <= 2100


def quantities_conflict(left: dict[str, set[float]], right: dict[str, set[float]]) -> str | None:
    """Two items disagree irreconcilably on a high-signal unit.

    Only a *disjoint* pair of non-empty sets counts. Sharing one figure out of five is
    normal — two reports of the same budget quote different line items. Sharing none,
    on a death toll or a rupee amount, means two different events.
    """
    for unit in VETO_UNITS:
        a, b = left.get(unit), right.get(unit)
        if not a or not b:
            continue
        if unit == "money":
            if any(_close(x, y) for x in a for y in b):
                continue
            return f"conflicting money figures ({_fmt(a)} vs {_fmt(b)})"
        if a.isdisjoint(b):
            return f"conflicting {unit} count ({_fmt(a)} vs {_fmt(b)})"
    return None


def _close(x: float, y: float, tolerance: float = 0.01) -> bool:
    if x == y:
        return True
    scale = max(abs(x), abs(y)) or 1.0
    return abs(x - y) / scale <= tolerance


def _fmt(values: set[float]) -> str:
    return ", ".join(f"{v:g}" for v in sorted(values))


def jaccard(left: set, right: set) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def overlap_coefficient(left: set, right: set) -> float:
    """Szymkiewicz-Simpson. Fairer than Jaccard when one item is far longer."""
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))
