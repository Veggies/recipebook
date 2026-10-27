"""House-style cleanup applied to every recipe on save, whatever its source."""

import re

from .ingredients import annotate_steps

# "350°F (177°C)", "350°F / 180°C", "180°C / 350°F", "(160°C fan)", "gas mark 4": US kitchens use °F only.
_C = r"-?\d+(?:\.\d+)?\s*(?:°\s*|degrees?\s+)C\b(?:\s*fan(?:[- ]forced)?)?"
_CELSIUS_RES = [
    re.compile(rf"\s*\(\s*{_C}[^)]*\)"),
    re.compile(rf"\s*/\s*{_C}"),
    re.compile(rf"{_C}\s*/\s*(?=\d)"),
    re.compile(r"\s*[/,]?\s*\(?gas mark \d+\)?", re.IGNORECASE),
]
# Broad, one-per-recipe shelves for browsing; finer detail goes in tags.
CATEGORIES = ["Breakfast", "Dinner", "Soups", "Salads", "Sides", "Desserts", "Snacks", "Drinks", "Sauces"]
_STOPWORDS = {"the", "and", "for", "make", "making", "meanwhile", "with", "your", "to", "of", "a"}


def strip_celsius(text: str) -> str:
    for pattern in _CELSIUS_RES:
        text = pattern.sub("", text)
    return text


def tidy_recipe(recipe: dict) -> dict:
    recipe["title"] = (recipe.get("title") or "").strip() or "Untitled recipe"
    recipe["category"] = _category(recipe.get("category"))
    for key in ("description", "notes"):
        recipe[key] = strip_celsius(recipe.get(key) or "")
    ingredient_groups = recipe.get("ingredient_groups", [])
    step_groups = recipe.get("step_groups", [])
    for group in ingredient_groups + step_groups:
        name = (group.get("name") or "").strip().rstrip(":").strip()
        group["name"] = name[:1].upper() + name[1:]
    for group in step_groups:
        group["steps"] = [strip_celsius(s) for s in group["steps"]]
    _match_step_group_names(ingredient_groups, step_groups)
    _name_unnamed_groups(recipe["title"], ingredient_groups)
    _name_unnamed_groups(recipe["title"], step_groups)
    recipe["step_groups"] = annotate_steps(ingredient_groups, step_groups)
    return recipe


def _category(value: str | None) -> str:
    """Case-insensitive match to a known category ("dessert" -> "Desserts"); anything else is dropped."""
    key = (value or "").strip().lower().rstrip("s")
    return next((c for c in CATEGORIES if c.lower().rstrip("s") == key), "")


def _match_step_group_names(ingredient_groups: list[dict], step_groups: list[dict]) -> None:
    """"Meanwhile, make the frosting" -> "Cream Cheese Frosting", so both lists read the same."""
    for sg in step_groups:
        words = _keywords(sg["name"])
        if not words:
            continue
        for ig in ingredient_groups:
            if ig["name"] and words & _keywords(ig["name"]):
                sg["name"] = ig["name"]
                break


def _name_unnamed_groups(title: str, groups: list[dict]) -> None:
    """When a recipe has several components, every list gets a heading - the main one is named after the dish."""
    if len(groups) > 1:
        for group in groups:
            if not group["name"]:
                group["name"] = title


def _keywords(name: str) -> set[str]:
    words = {w for w in re.findall(r"[a-z]+", name.lower()) if w not in _STOPWORDS and len(w) > 2}
    return {w[:-1] if w.endswith("s") else w for w in words}
