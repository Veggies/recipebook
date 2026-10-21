"""Ingredient-line parsing and writing ingredient amounts into step text.

House rule: every step that uses an ingredient states how much of it, e.g.
"Stir in the cumin (1 tsp)". `annotate_steps` enforces that for recipes that
arrive without it (most scraped ones).
"""

import re

UNITS = {
    "teaspoon", "teaspoons", "tsp", "tsps", "t",
    "tablespoon", "tablespoons", "tbsp", "tbsps", "tbs", "tbl", "T",
    "cup", "cups", "c",
    "ounce", "ounces", "oz", "fl oz", "fluid ounce", "fluid ounces",
    "pound", "pounds", "lb", "lbs",
    "gram", "grams", "g", "kilogram", "kilograms", "kg",
    "milliliter", "milliliters", "millilitre", "millilitres", "ml",
    "liter", "liters", "litre", "litres", "l",
    "pint", "pints", "pt", "quart", "quarts", "qt", "gallon", "gallons", "gal",
    "pinch", "pinches", "dash", "dashes", "splash",
    "clove", "cloves", "can", "cans", "jar", "jars", "package", "packages", "pkg",
    "stick", "sticks", "slice", "slices", "sprig", "sprigs", "bunch", "bunches",
    "head", "heads", "handful", "handfuls", "piece", "pieces",
}

_FRACTIONS = "½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
_NUM = rf"(?:\d+\s+(?:and\s+)?\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?(?:\s*[{_FRACTIONS}])?|[{_FRACTIONS}])"
_QTY = rf"{_NUM}(?:\s*(?:-|–|to)\s*{_NUM})?"
_UNIT = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
_AMOUNT_RE = re.compile(
    rf"^\s*(?P<amount>{_QTY}(?:\s*\([^)]*\))?(?:\s*(?:{_UNIT})\.?(?![a-zA-Z])(?:\s*\([^)]*\))?)?)\s*(?:of\s+)?(?P<item>.*)$"
)
# A quantity sitting just before a matched ingredient means the step already
# states the amount ("add 2 cups flour"), so it shouldn't be annotated again.
_QTY_BEFORE_RE = re.compile(rf"(?:{_QTY})\s*(?:(?:{_UNIT})\.?\s*)?(?:of\s+)?(?:[\w-]+\s+)?$", re.IGNORECASE)

# "(2 cups)" right after the ingredient - already annotated, possibly with an older amount.
_AMOUNT_AFTER_RE = re.compile(r"\s*\([^)]*\d")


def parse_ingredient(line: str) -> dict:
    """Split "2 1/4 cups all-purpose flour, sifted" into amount and item."""
    line = " ".join(line.split())
    m = _AMOUNT_RE.match(line)
    if m and m.group("item"):
        return {"amount": m.group("amount").strip(), "item": m.group("item").strip()}
    return {"amount": "", "item": line}


def short_amount(amount: str) -> str:
    """Amount without asides, for use inside step text: "1/2 cup (8 Tbsp; 113g)" -> "1/2 cup"."""
    return " ".join(re.sub(r"\([^)]*\)", "", amount).split()) or amount


def core_name(item: str) -> str:
    """The ingredient itself, without prep notes: "onion, finely diced" -> "onion"."""
    name = re.sub(r"\([^)]*\)", "", item)
    name = re.split(r",|;| - | for | to taste| plus ", name, maxsplit=1)[0]
    return " ".join(name.split()).lower()


def match_terms(item: str) -> list[str]:
    """Phrases to search for in step text to detect that a step uses this ingredient.

    Return them most-specific first; the first one found in a step wins.
    `item` is the ingredient text without its amount, e.g.
    "all-purpose flour, sifted" or "large eggs, at room temperature".
    """
    name = core_name(item)
    # TODO(ryan): placeholder - only matches the full name, so a step saying
    # "whisk the flour" never matches "all-purpose flour". See tests/test_ingredients.py.
    return [name] if name else []


def annotate_steps(ingredient_groups: list[dict], step_groups: list[dict]) -> list[dict]:
    """Return step_groups with "(amount)" written after each ingredient a step mentions.

    When the same ingredient appears in several groups (butter in both cake and
    frosting), prefer the group whose ingredients the recipe was most recently
    using - steps usually work through the groups in order.
    """
    amounts_by_term: dict[str, list[tuple[str, int]]] = {}
    for gi, group in enumerate(ingredient_groups):
        for ing in group.get("items", []):
            if ing.get("amount"):
                for term in match_terms(ing["item"]):
                    amounts_by_term.setdefault(term.lower(), []).append((ing["amount"], gi))
    # Longest first, so "brown sugar" claims its words before "sugar" can.
    terms = sorted(amounts_by_term, key=len, reverse=True)

    current_group = 0
    out = []
    for sg in step_groups:
        new_steps = []
        for step in sg.get("steps", []):
            found: list[tuple[int, int, str]] = []
            for term in terms:
                for m in re.finditer(rf"\b{re.escape(term)}\b", step, re.IGNORECASE):
                    if not any(s < m.end() and m.start() < e for s, e, _ in found):
                        found.append((m.start(), m.end(), term))
                        break
            inserts = []
            for start, end, term in sorted(found):  # reading order, so current_group tracks the text
                candidates = amounts_by_term[term]
                amount, current_group = next((c for c in candidates if c[1] == current_group), candidates[0])
                if _AMOUNT_AFTER_RE.match(step, end) or _QTY_BEFORE_RE.search(step[:start]):
                    continue
                inserts.append((end, f" ({short_amount(amount)})"))
            for pos, text in reversed(inserts):
                step = step[:pos] + text + step[pos:]
            new_steps.append(step)
        out.append({**sg, "steps": new_steps})
    return out
