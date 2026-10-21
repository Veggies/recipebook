"""Ingredient-line parsing and writing ingredient amounts into step text.

House rule: every step that uses an ingredient states how much of it, e.g.
"Stir in the cumin (1 tsp)". `annotate_steps` enforces that for recipes that
arrive without it (most scraped ones).
"""

import re

US_UNITS = {
    "teaspoon", "teaspoons", "tsp", "tsps", "t",
    "tablespoon", "tablespoons", "tbsp", "tbsps", "tbs", "tbl", "T",
    "cup", "cups", "c",
    "ounce", "ounces", "oz", "fl oz", "fluid ounce", "fluid ounces",
    "pound", "pounds", "lb", "lbs",
    "pint", "pints", "pt", "quart", "quarts", "qt", "gallon", "gallons", "gal",
}
METRIC_UNITS = {
    "gram", "grams", "g", "kilogram", "kilograms", "kg",
    "milliliter", "milliliters", "millilitre", "millilitres", "ml",
    "liter", "liters", "litre", "litres", "l",
}
COUNT_UNITS = {
    "pinch", "pinches", "dash", "dashes", "splash",
    "clove", "cloves", "can", "cans", "jar", "jars", "package", "packages", "pkg",
    "stick", "sticks", "slice", "slices", "sprig", "sprigs", "bunch", "bunches",
    "head", "heads", "handful", "handfuls", "piece", "pieces",
}
UNITS = US_UNITS | METRIC_UNITS | COUNT_UNITS

# Words that describe an ingredient rather than name it. A search term never
# ends in one of these ("packed light" is not an ingredient).
DESCRIPTORS = {
    "large", "medium", "small", "extra-large", "jumbo", "fresh", "freshly", "dried", "frozen",
    "packed", "light", "dark", "unsalted", "salted", "ground", "whole", "pure", "full-fat",
    "low-fat", "fat-free", "low-sodium", "reduced-sodium", "block", "plain", "raw", "ripe",
    "boneless", "skinless", "lean", "extra", "virgin", "extra-virgin", "organic", "good",
    "quality", "finely", "coarsely", "roughly", "thinly", "about", "optional", "and", "or",
    "of", "a", "the", "your", "any", "favorite", "favourite", "hot", "cold", "warm",
}
# Past-participle prep words ("diced", "softened"); 3+ letters before "ed" so "red" and "seed" stay ingredients.
PREP_WORD_RE = re.compile(r"^(?:\w{3,}ed|cut|and|or|into|at|to|room|temperature)$")
# Trailing words naming a form or container: "garlic cloves" is used as "garlic".
FORM_WORDS = {
    "clove", "cloves", "can", "cans", "stalk", "stalks", "sprig", "sprigs", "leaves", "leaf",
    "cube", "cubes", "fillet", "fillets", "slice", "slices", "piece", "pieces", "head", "heads",
    "bunch", "jar", "package", "pods", "pod", "wedges", "florets", "extract",
}

_FRACTIONS = "½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
_NUM = rf"(?:\d+\s+(?:and\s+)?\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?(?:\s*[{_FRACTIONS}])?|[{_FRACTIONS}])"
_QTY = rf"{_NUM}(?:\s*(?:-|–|to)\s*{_NUM})?"


def _alternation(words) -> str:
    return "|".join(sorted((re.escape(u) for u in words), key=len, reverse=True))


_UNIT = _alternation(UNITS)
_CONTAINER = r"(?:\s+(?:can|cans|jar|jars|package|packages|tin|tins|carton|cartons|bag|bags))"
_AMOUNT_RE = re.compile(
    rf"^\s*(?P<amount>{_QTY}(?:\s*\([^)]*\))?(?:\s*(?:{_UNIT})\.?(?![a-zA-Z])(?:\s*\([^)]*\))?{_CONTAINER}?)?)"
    rf"\s*(?:of\s+)?(?P<item>.*)$"
)
# "1 lb / 500g beef" or "800g / 28 oz can tomatoes": two systems for one amount.
_SIMPLE_AMOUNT = rf"{_QTY}\s*(?:{_UNIT})\.?(?![a-zA-Z]){_CONTAINER}?"
_DUAL_AMOUNT_RE = re.compile(rf"^\s*(?P<a>{_SIMPLE_AMOUNT})\s*/\s*(?P<b>{_SIMPLE_AMOUNT})\s*(?P<rest>.*)$")
_METRIC_RE = re.compile(rf"^{_QTY}\s*(?:{_alternation(METRIC_UNITS)})\.?(?![a-zA-Z])")
# A quantity sitting just before a matched ingredient means the step already
# states the amount ("add 2 cups flour"), so it shouldn't be annotated again.
_QTY_BEFORE_RE = re.compile(rf"(?:{_QTY})\s*(?:(?:{_UNIT})\.?\s*)?(?:of\s+)?(?:[\w-]+\s+)?$", re.IGNORECASE)
# "(2 cups)" right after the ingredient - already annotated, possibly with an older amount.
# "(Note 2)" doesn't count.
_AMOUNT_AFTER_RE = re.compile(r"\s*\((?!\s*(?:see\s+)?notes?\b)[^)]*\d", re.IGNORECASE)


def parse_ingredient(line: str) -> dict:
    """Split "2 1/4 cups all-purpose flour, sifted" into amount and item."""
    line = _prefer_us_amount(" ".join(line.split()))
    m = _AMOUNT_RE.match(line)
    if m and m.group("item"):
        return {"amount": m.group("amount").strip(), "item": tidy_item(m.group("item"))}
    return {"amount": "", "item": tidy_item(line)}


def _prefer_us_amount(line: str) -> str:
    m = _DUAL_AMOUNT_RE.match(line)
    if not m:
        return line
    a, b = m.group("a"), m.group("b")
    keep, other = (b, a) if _METRIC_RE.match(a) and not _METRIC_RE.match(b) else (a, b)
    container = re.search(rf"{_CONTAINER}$", other)
    if container and not re.search(rf"{_CONTAINER}$", keep):
        keep += container.group(0)  # "14 oz / 420g can" -> "14 oz can"
    return f"{keep} {m.group('rest')}".strip()


def tidy_item(item: str) -> str:
    """Fix the bracket soup some recipe plugins produce around ingredient notes.

    "garlic cloves (, minced)" -> "garlic cloves, minced"
    "red capsicum ((bell pepper), diced)" -> "red capsicum (bell pepper), diced"
    """
    item = item.strip()
    start = item.find(" (")
    if start != -1 and item.endswith(")") and _closing_paren(item, start + 1) == len(item) - 1:
        inner = item[start + 2:-1]
        if inner.startswith(","):
            item = item[:start] + inner
        elif inner.startswith("("):
            item = item[:start] + " " + inner
    return " ".join(item.split())


def _closing_paren(text: str, open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i
    return -1


def short_amount(amount: str) -> str:
    """Amount without asides, for use inside step text: "1/2 cup (8 Tbsp; 113g)" -> "1/2 cup"."""
    return " ".join(re.sub(r"\([^)]*\)", "", amount).split()) or amount


def core_name(item: str) -> str:
    """The ingredient itself, without prep notes.

    "onion, finely diced" -> "onion"; "peeled, shredded, and coarsely chopped carrots" -> "coarsely chopped carrots"
    """
    name = re.sub(r"\([^)]*\)|\*", "", item)
    name = re.split(r";| - | for | to taste| plus ", name, maxsplit=1)[0]
    parts = [p.strip() for p in name.split(",") if p.strip()]
    # Prep words can come first ("peeled, shredded, ..."); take the first part that names something.
    for part in parts:
        words = part.lower().split()
        if any(not PREP_WORD_RE.match(w) and w not in DESCRIPTORS for w in words):
            return " ".join(words)
    return " ".join(parts[0].lower().split()) if parts else ""


def match_terms(item: str) -> list[str]:
    """Phrases that a step might use for this ingredient, most specific first.

    Steps usually shorten names to their last word or two: "all-purpose flour" is
    "the flour", "extra-virgin olive oil" is "the olive oil", "garlic cloves" is
    "the garlic". So the candidates are the trailing word runs of each name,
    never a leading word alone ("chicken stock" must not match "the chicken").
    Ambiguous short terms are dropped later by `annotate_steps`, which can see
    the whole ingredient list.
    """
    terms: list[str] = []
    # "beef mince / ground beef", "cooking salt / kosher salt", "light or dark brown sugar"
    for name in re.split(r"\s*/\s*|\s+or\s+", core_name(item)):
        words = [w.strip(".:") for w in name.split() if w.strip(".:")]
        while words and words[-1] in FORM_WORDS and len(words) > 1:
            terms += _tails(words)
            words = words[:-1]
        terms += _tails(words)
    out = []
    for term in terms:
        for variant in (term, *_plural_variants(term)):
            if variant not in out:
                out.append(variant)
    return out


def _tails(words: list[str]) -> list[str]:
    tails = [" ".join(words[i:]) for i in range(len(words))]
    return [t for t in tails if t.split()[-1] not in DESCRIPTORS and not PREP_WORD_RE.match(t.split()[0])]


def _resolve_in_group(entries: list[tuple]) -> tuple | None:
    if len({e[2] for e in entries}) == 1:
        return entries[0]
    exact = [e for e in entries if e[3]]
    return exact[0] if len({e[2] for e in exact}) == 1 else None


def _plural_variants(term: str) -> list[str]:
    if term.endswith("ies"):
        return [term[:-3] + "y"]
    if term.endswith("oes"):
        return [term[:-2]]
    if term.endswith("s") and not term.endswith("ss"):
        return [term[:-1]]
    if term.endswith("y"):
        return [term[:-1] + "ies"]
    if term.endswith("o"):
        return [term + "es"]
    return [term + "s"]


def annotate_steps(ingredient_groups: list[dict], step_groups: list[dict]) -> list[dict]:
    """Return step_groups with "(amount)" written after each ingredient a step mentions.

    When the same ingredient appears in several groups (butter in both cake and
    frosting), prefer the group the steps are working on: the step group with the
    same name, else the group whose ingredients were mentioned most recently.
    """
    by_term: dict[str, list[tuple[str, int, int, bool]]] = {}  # term -> [(amount, group, ingredient, exact)]
    for gi, group in enumerate(ingredient_groups):
        for ii, ing in enumerate(group.get("items", [])):
            if ing.get("amount"):
                terms = match_terms(ing["item"])
                for term in terms:
                    exact = term in terms[:2]  # the full name or its plural/singular
                    by_term.setdefault(term, []).append((ing["amount"], gi, ii, exact))
    amounts_by_term = {}
    for term, entries in by_term.items():
        resolved = [_resolve_in_group([e for e in entries if e[1] == gi]) for gi in sorted({e[1] for e in entries})]
        # A term naming two ingredients in one group ("powder" for garlic powder and
        # onion powder) can't be resolved - unless one is called exactly that ("sugar"
        # vs "brown sugar") - so it isn't used.
        if all(resolved):
            amounts_by_term[term] = [(e[0], e[1], e[2]) for e in resolved]
    # Longest first, so "brown sugar" claims its words before "sugar" can.
    terms = sorted(amounts_by_term, key=len, reverse=True)
    group_names = [(g.get("name") or "").lower() for g in ingredient_groups]

    current_group = 0
    out = []
    for sg in step_groups:
        if (sg.get("name") or "").lower() in group_names and sg.get("name"):
            current_group = group_names.index(sg["name"].lower())
        new_steps = []
        for step in sg.get("steps", []):
            found: list[tuple[int, int, str]] = []
            for term in terms:
                for m in re.finditer(rf"\b{re.escape(term)}\b", step, re.IGNORECASE):
                    if not any(s < m.end() and m.start() < e for s, e, _ in found):
                        found.append((m.start(), m.end(), term))
                        break
            inserts = []
            seen_ingredients = set()  # each ingredient gets its amount once per step
            for start, end, term in sorted(found):  # reading order, so current_group tracks the text
                candidates = amounts_by_term[term]
                amount, current_group, ii = next((c for c in candidates if c[1] == current_group), candidates[0])
                if (current_group, ii) in seen_ingredients:
                    continue
                seen_ingredients.add((current_group, ii))
                if _AMOUNT_AFTER_RE.match(step, end) or _QTY_BEFORE_RE.search(step[:start]):
                    continue
                inserts.append((end, f" ({short_amount(amount)})"))
            for pos, text in reversed(inserts):
                step = step[:pos] + text + step[pos:]
            new_steps.append(step)
        out.append({**sg, "steps": new_steps})
    return out
