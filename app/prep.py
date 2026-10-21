"""'Before you start' list: what needs doing ahead of time, and the knife work, read off the ingredients."""

import re

from .ingredients import short_amount

# (pattern in the ingredient text, heads-up shown to the cook). First match wins.
AHEAD = [
    (r"room temp|softened", "Set out about 1 hour ahead to come to room temperature"),
    (r"thawed|defrosted", "Thaw ahead - overnight in the fridge"),
    (r"melted and cooled|cooled", "Prepare ahead so it has time to cool"),
    (r"\bsoaked\b|soaked overnight", "Soak ahead"),
    (r"chilled|very cold|ice[- ]cold|\bcold\b", "Keep in the fridge until you need it"),
    (r"\bcooked\b|leftover", "Cook ahead"),
    (r"marinated", "Marinate ahead"),
]
KNIFE_WORK = re.compile(
    r"\b(chopped|diced|minced|sliced|grated|shredded|zested|julienned|cubed|crushed|crumbled|"
    r"peeled|trimmed|halved|quartered|cut into|torn|pitted|seeded|deveined|rinsed|drained)\b",
    re.IGNORECASE,
)


def before_you_start(recipe: dict) -> dict:
    """{"ahead": [{tip, items: [{amount, item}]}], "prep": [{amount, item}]} - each ingredient listed at most once."""
    ahead: dict[str, list[dict]] = {}
    prep = []
    for group in recipe.get("ingredient_groups", []):
        for ing in group.get("items", []):
            text = ing["item"].lower()
            entry = {"amount": short_amount(ing.get("amount", "")), "item": ing["item"]}
            tip = next((tip for pattern, tip in AHEAD if re.search(pattern, text)), None)
            if tip:
                ahead.setdefault(tip, []).append(entry)
            elif KNIFE_WORK.search(text) and not text.startswith("optional"):
                prep.append(entry)
    return {"ahead": [{"tip": tip, "items": items} for tip, items in ahead.items()], "prep": prep}
