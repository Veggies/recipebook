"""Shopping list: combine several recipes' ingredients, adding up amounts that can be added up.

Two recipes needing "1 lemon" each -> "2 lemons"; "1 cup butter" + "2 tbsp butter" -> "1 1/8 cups".
Amounts that can't be converted into each other stay side by side: "1 cup + 1 stick".
"""

import re

from .ingredients import core_name, parse_ingredient, short_amount

_FRACTION_CHARS = {
    "½": 1 / 2, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 1 / 4, "¾": 3 / 4, "⅕": 1 / 5, "⅖": 2 / 5, "⅗": 3 / 5,
    "⅘": 4 / 5, "⅙": 1 / 6, "⅚": 5 / 6, "⅛": 1 / 8, "⅜": 3 / 8, "⅝": 5 / 8, "⅞": 7 / 8,
}
_FR = "".join(_FRACTION_CHARS)
_NUM = rf"(?:\d+\s+(?:and\s+)?\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?\s*[{_FR}]?|[{_FR}])"
_QTY_RE = re.compile(rf"^\s*(?P<a>{_NUM})(?:\s*(?:-|–|to)\s*(?P<b>{_NUM}))?\s*")

# canonical unit -> (dimension, size in the dimension's base unit)
UNITS = {
    "tsp": ("volume", 1), "tbsp": ("volume", 3), "cup": ("volume", 48), "fl oz": ("volume", 6),
    "pint": ("volume", 96), "quart": ("volume", 192), "gallon": ("volume", 768),
    "oz": ("weight", 1), "lb": ("weight", 16),
    "ml": ("metric volume", 1), "l": ("metric volume", 1000),
    "g": ("metric weight", 1), "kg": ("metric weight", 1000),
}
_ALIASES = {
    "teaspoons": "tsp", "teaspoon": "tsp", "tsps": "tsp", "tsp": "tsp", "t": "tsp",
    "tablespoons": "tbsp", "tablespoon": "tbsp", "tbsps": "tbsp", "tbsp": "tbsp", "tbs": "tbsp", "tbl": "tbsp", "T": "tbsp",
    "cups": "cup", "cup": "cup", "c": "cup",
    "fluid ounces": "fl oz", "fluid ounce": "fl oz", "fl oz": "fl oz",
    "ounces": "oz", "ounce": "oz", "oz": "oz", "pounds": "lb", "pound": "lb", "lbs": "lb", "lb": "lb",
    "pints": "pint", "pint": "pint", "pt": "pint", "quarts": "quart", "quart": "quart", "qt": "quart",
    "gallons": "gallon", "gallon": "gallon", "gal": "gallon",
    "milliliters": "ml", "milliliter": "ml", "millilitres": "ml", "millilitre": "ml", "ml": "ml",
    "liters": "l", "liter": "l", "litres": "l", "litre": "l", "l": "l",
    "grams": "g", "gram": "g", "g": "g", "kilograms": "kg", "kilogram": "kg", "kg": "kg",
}
# Counted things: "3 cloves garlic". Singular form is the key.
COUNT_UNITS = {
    "clove", "can", "jar", "package", "pkg", "stick", "slice", "sprig", "bunch", "head", "handful",
    "piece", "pinch", "dash", "splash", "bag", "box", "carton", "tin", "bottle", "stalk",
}
CONTAINERS = {"can", "jar", "package", "bag", "box", "carton", "tin", "bottle"}
_UNIT_RE = re.compile(
    r"^(?P<unit>" + "|".join(sorted((re.escape(a) for a in [*_ALIASES, *COUNT_UNITS]), key=len, reverse=True))
    + r")(?:e?s)?\.?(?![A-Za-z])"
)

# Words that don't change what you buy. Kept on purpose: dried, ground, crushed, smoked,
# unsalted... ("dried oregano" and "fresh oregano" are different purchases).
_IGNORED_WORDS = {
    "large", "medium", "small", "extra-large", "jumbo", "fresh", "freshly", "packed", "lightly", "firmly",
    "chopped", "finely", "coarsely", "roughly", "thinly", "diced", "minced", "sliced", "grated", "shredded",
    "softened", "melted", "cold", "warm", "hot", "boiling", "lukewarm", "room", "temperature", "peeled",
    "halved", "cubed", "trimmed", "rinsed", "drained", "beaten", "sifted", "divided", "about",
    "approximately", "heaping", "level", "scant", "good", "quality",
}
_NOT_BOUGHT = {"water", "ice", "ice water"}
_SERVING_NOTES_RE = re.compile(r",?\s*\b(?:to taste|as needed|for serving|for garnish|to serve)\b", re.IGNORECASE)

# (aisle, words) checked in order, first match wins - so exceptions come before the general
# word they contain ("ground beef" before Spices' "ground", "baking powder" before "powder").
# Words are singular; matching allows a plural ending.
AISLES = [
    ("Meat & Seafood", ["ground beef", "ground turkey", "ground chicken", "ground pork", "ground lamb", "beef mince"]),
    ("Baking", ["baking powder", "baking soda", "cocoa powder", "chocolate chip", "powdered sugar"]),
    ("Produce", ["eggplant", "butternut squash", "green bean", "sweet potato", "fresh ginger"]),
    ("Pantry", ["peanut butter", "corn chip", "tortilla chip", "coconut milk", "crushed tomato", "tomato paste",
                "tomato sauce", "diced tomato", "canned", "bouillon", "stock", "broth", "applesauce"]),
    ("Frozen", ["frozen"]),
    ("Spices", ["ground", "dried", "powder", "seasoning", "spice", "cumin", "paprika", "oregano", "cinnamon",
                "nutmeg", "cayenne", "chili flake", "red pepper flake", "salt", "black pepper", "peppercorn",
                "bay leaf", "bay leave", "allspice", "turmeric", "cardamom"]),
    ("Baking", ["flour", "sugar", "yeast", "vanilla", "cocoa", "cornstarch", "corn starch", "chocolate",
                "sprinkle", "molasse"]),
    ("Dairy & Eggs", ["milk", "butter", "cream", "cheese", "yogurt", "yoghurt", "egg", "buttermilk", "parmesan",
                      "mozzarella", "cheddar", "ricotta", "feta"]),
    ("Meat & Seafood", ["beef", "chicken", "pork", "turkey", "lamb", "bacon", "sausage", "ham", "steak", "mince",
                        "salmon", "shrimp", "prawn", "fish", "cod", "tilapia", "chorizo"]),
    ("Bakery", ["bread", "bun", "tortilla", "roll", "pita", "baguette", "naan"]),
    ("Produce", ["lemon", "lime", "orange", "apple", "banana", "berry", "berrie", "onion", "garlic", "shallot",
                 "scallion", "potato", "tomato", "carrot", "celery", "bell pepper", "capsicum", "jalapeño",
                 "jalapeno", "lettuce", "spinach", "kale", "cabbage", "broccoli", "cauliflower", "zucchini",
                 "cucumber", "mushroom", "avocado", "cilantro", "coriander", "parsley", "basil", "mint", "thyme",
                 "rosemary", "dill", "ginger", "leek", "squash", "corn", "pear", "peach", "grape"]),
    ("Pantry", ["oil", "vinegar", "sauce", "paste", "bean", "rice", "pasta", "noodle", "honey", "syrup",
                "walnut", "pecan", "almond", "peanut", "cashew", "raisin", "oat", "soy", "mustard", "mayo",
                "ketchup", "lentil", "chickpea", "chip", "salsa", "nut"]),
]
AISLE_ORDER = ["Produce", "Meat & Seafood", "Dairy & Eggs", "Bakery", "Baking", "Pantry", "Spices", "Frozen", "Other"]


def build_shopping_list(recipes: list[dict]) -> list[dict]:
    """[{"aisle", "items": [{key, name, amount, sources, optional}]}] in store-walk order."""
    items: dict[str, dict] = {}
    for recipe in recipes:
        for group in recipe.get("ingredient_groups", []):
            for ing in group.get("items", []):
                entry = _shopping_entry(ing)
                if not entry:
                    continue
                key = entry["key"]
                item = items.setdefault(key, {
                    "key": key, "name": entry["name"], "totals": {}, "loose": [], "sources": [],
                    "optional": True, "aisle": aisle_for(key),
                })
                item["optional"] &= entry["optional"]
                if recipe["title"] not in item["sources"]:
                    item["sources"].append(recipe["title"])
                _add_amount(item, entry["amount"], entry["unit_hint"])
    groups: dict[str, list[dict]] = {}
    for item in items.values():
        groups.setdefault(item["aisle"], []).append({
            "key": item["key"], "name": _display_name(item), "amount": _format_amount(item),
            "sources": item["sources"], "optional": item["optional"],
        })
    return [
        {"aisle": aisle, "items": sorted(groups[aisle], key=lambda i: i["name"])}
        for aisle in AISLE_ORDER if aisle in groups
    ]


def _shopping_entry(ing: dict) -> dict | None:
    item, amount = ing.get("item", ""), ing.get("amount", "")
    optional = bool(re.match(r"\s*optional\b", item, re.IGNORECASE))
    if optional:
        # "optional add-in: 3/4 cup chopped walnuts or pecans"
        item = re.sub(r"^\s*optional\b[^:]*:\s*", "", item, flags=re.IGNORECASE)
        if not amount:
            parsed = parse_ingredient(item)
            item, amount = parsed["item"], parsed["amount"]
    if amount:
        name = core_name(item)
    else:
        # Unquantified lines are often lists ("Rice, corn chips, tortillas") - keep them whole.
        name = " ".join(_SERVING_NOTES_RE.sub("", re.sub(r"\([^)]*\)|\*", "", item)).split()).lower()
    name = name.split(" / ")[-1]  # "beef mince / ground beef": the American name is usually last
    words = [w for w in name.replace("’", "'").split() if w not in _IGNORED_WORDS]
    while words and words[0] in ("and", "or", "&"):  # "peeled, shredded, and coarsely chopped carrots"
        words.pop(0)
    # "3 garlic cloves" is 3 cloves of garlic, same as "3 cloves garlic".
    unit_hint = ""
    if len(words) > 1 and _singular_phrase(words[-1]) in COUNT_UNITS:
        unit_hint = _singular_phrase(words.pop())
    name = " ".join(words).strip(" ,.;:")
    if not name or name in _NOT_BOUGHT:
        return None
    return {"key": _singular_phrase(name), "name": name, "amount": amount, "optional": optional, "unit_hint": unit_hint}


def _add_amount(item: dict, amount: str, unit_hint: str = "") -> None:
    qty, unit = parse_amount(amount)
    unit = unit or unit_hint
    if qty is None:
        if amount and amount not in item["loose"]:
            item["loose"].append(amount)
        return
    dimension, size = UNITS.get(unit, (unit, 1))
    item["totals"][dimension] = item["totals"].get(dimension, 0) + qty * size


def parse_amount(amount: str) -> tuple[float | None, str]:
    """"1 1/2 cups (200g)" -> (1.5, "cup"); "2" -> (2, ""); "28 oz can" -> (1, "can (28 oz)")."""
    text = short_amount(amount)
    m = _QTY_RE.match(text)
    if not m:
        return None, ""
    qty = max(_to_number(m.group("a")), _to_number(m.group("b") or "0"))
    rest = text[m.end():]
    # Case matters only for T (tbsp) vs t (tsp); otherwise "Tbsp" and "tbsp" are the same.
    um = _UNIT_RE.match(rest) or _UNIT_RE.match(rest.lower())
    if not um:
        return qty, ""
    unit = um.group("unit")
    unit = _ALIASES.get(unit, _ALIASES.get(unit.lower(), unit.lower()))
    container = re.match(r"\s*(" + "|".join(CONTAINERS) + r")s?\b", rest[um.end():])
    if container and unit in UNITS:
        # A container size: buy one 28 oz can, not 28 ounces.
        return 1, f"{container.group(1)} ({_fmt_number(qty)} {unit})"
    return qty, unit


def aisle_for(key: str) -> str:
    for aisle, words in AISLES:
        if any(re.search(rf"\b{re.escape(w)}(?:e?s)?\b", key) for w in words):
            return aisle
    return "Other"


def _format_amount(item: dict) -> str:
    parts = []
    for dimension, total in item["totals"].items():
        if dimension == "volume":
            parts.append(_fmt_volume(total))
        elif dimension == "weight":
            parts.append(_fmt_unit(total / 16, "lb") if total >= 16 else _fmt_unit(total, "oz", step=0.5))
        elif dimension == "metric volume":
            parts.append(_fmt_unit(total / 1000, "l", step=0.1) if total >= 1000 else _fmt_unit(total, "ml", step=1))
        elif dimension == "metric weight":
            parts.append(_fmt_unit(total / 1000, "kg", step=0.1) if total >= 1000 else _fmt_unit(total, "g", step=1))
        elif dimension:  # counted unit: clove, stick, can (28 oz)...
            parts.append(_fmt_unit(total, dimension))
        else:  # bare count - the number goes with the name ("2 lemons")
            parts.append(_fmt_number(total))
    parts += item["loose"]
    return " + ".join(parts)


def _fmt_volume(tsp: float) -> str:
    if tsp >= 12:
        return _fmt_unit(tsp / 48, "cup")
    if tsp >= 3:
        return _fmt_unit(tsp / 3, "tbsp", step=0.5)
    return _fmt_unit(tsp, "tsp")


def _fmt_unit(qty: float, unit: str, step: float | None = None) -> str:
    number = _fmt_number(qty, step)
    if unit in ("cup", "pint", "quart", "gallon") or unit.split()[0] in COUNT_UNITS:
        if qty > 1:
            first, _, rest = unit.partition(" ")
            unit = f"{_plural(first)} {rest}".strip()
    return f"{number} {unit}"


_NICE_FRACTIONS = [(0, ""), (1 / 8, "1/8"), (1 / 4, "1/4"), (1 / 3, "1/3"), (3 / 8, "3/8"), (1 / 2, "1/2"),
                   (5 / 8, "5/8"), (2 / 3, "2/3"), (3 / 4, "3/4"), (7 / 8, "7/8"), (1, "")]


def _fmt_number(x: float, step: float | None = None) -> str:
    if step:
        x = round(x / step) * step
        if step >= 1:
            return str(int(round(x)))
        if step < 0.5:  # metric: decimals read naturally ("1.2 kg")
            return f"{x:g}"
    whole = int(x)
    value, text = min(_NICE_FRACTIONS, key=lambda f: abs(x - whole - f[0]))
    if value == 1:
        whole, text = whole + 1, ""
    if whole and text:
        return f"{whole} {text}"
    return text or str(whole)


def _display_name(item: dict) -> str:
    name = item["name"]
    bare = item["totals"].get("")
    if bare and bare > 1 and not item["loose"] and len(item["totals"]) == 1:
        return _plural_phrase(name)
    return name


def _to_number(text: str) -> float:
    total = 0.0
    for part in re.findall(rf"\d+/\d+|\d+(?:[.,]\d+)?|[{_FR}]", text):
        if "/" in part:
            n, d = part.split("/")
            total += int(n) / int(d) if int(d) else 0
        elif part in _FRACTION_CHARS:
            total += _FRACTION_CHARS[part]
        else:
            total += float(part.replace(",", "."))
    return total


def _singular_phrase(phrase: str) -> str:
    *head, last = phrase.split()
    if last.endswith("ies") and len(last) > 4:
        last = last[:-3] + "y"
    elif last.endswith(("oes", "ches", "shes", "sses")):
        last = last[:-2]
    elif last.endswith("s") and not last.endswith(("ss", "us")):
        last = last[:-1]
    return " ".join([*head, last])


def _plural_phrase(phrase: str) -> str:
    *head, last = phrase.split()
    return " ".join([*head, _plural(last)])


def _plural(word: str) -> str:
    if word.endswith("s"):
        return word
    if word.endswith("y") and word[-2:-1] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("o", "ch", "sh")):
        return word + "es"
    return word + "s"
