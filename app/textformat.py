"""Plain-text editing format for a recipe, so it can be edited from a phone in one textarea.

    Title: Chocolate Cake
    Servings: 8
    Category: Desserts
    Tags: cake

    == Ingredients: Cake batter ==
    2 1/4 cups | all-purpose flour
    salt, to taste

    == Steps: Cake ==
    Whisk the flour (2 1/4 cups) and salt together.

    == Notes ==
    Freezes well.

Ingredient lines are "amount | item"; a line without "|" is parsed automatically.
"""

import re

from .ingredients import parse_ingredient

FIELDS = {
    "title": "Title", "servings": "Servings", "prep_time": "Prep minutes",
    "cook_time": "Cook minutes", "total_time": "Total minutes", "source_url": "Source",
    "image_url": "Image", "category": "Category", "tags": "Tags", "description": "Description",
}
_LABEL_TO_FIELD = {v.lower(): k for k, v in FIELDS.items()}
_SECTION_RE = re.compile(r"^==\s*(ingredients|steps|notes)\s*(?::\s*(.*?))?\s*==$", re.IGNORECASE)
_STEP_NUMBER_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")


def to_text(recipe: dict) -> str:
    lines = []
    for field, label in FIELDS.items():
        value = recipe.get(field)
        if field == "tags":
            value = ", ".join(value or [])
        if value not in (None, ""):
            lines.append(f"{label}: {value}")
    for group in recipe.get("ingredient_groups", []):
        lines += ["", _header("Ingredients", group.get("name"))]
        for ing in group["items"]:
            lines.append(f"{ing['amount']} | {ing['item']}" if ing.get("amount") else ing["item"])
    for group in recipe.get("step_groups", []):
        lines += ["", _header("Steps", group.get("name"))]
        lines += group["steps"]
    # Always present, so there's an obvious place to add your own.
    lines += ["", "== Notes =="] + ([recipe["notes"]] if recipe.get("notes") else [])
    return "\n".join(lines) + "\n"


def from_text(text: str) -> dict:
    recipe = {"tags": [], "ingredient_groups": [], "step_groups": [], "notes": ""}
    section = None
    notes = []
    for raw in text.splitlines():
        line = raw.strip()
        if m := _SECTION_RE.match(line):
            section = m.group(1).lower()
            name = (m.group(2) or "").strip()
            if section == "ingredients":
                recipe["ingredient_groups"].append({"name": name, "items": []})
            elif section == "steps":
                recipe["step_groups"].append({"name": name, "steps": []})
            continue
        if section == "notes":
            notes.append(raw.rstrip())
        elif not line:
            continue
        elif section == "ingredients":
            if "|" in line:
                amount, item = (p.strip() for p in line.split("|", 1))
                ing = {"amount": amount, "item": item}
            else:
                ing = parse_ingredient(line)
            recipe["ingredient_groups"][-1]["items"].append(ing)
        elif section == "steps":
            recipe["step_groups"][-1]["steps"].append(_STEP_NUMBER_RE.sub("", line))
        elif ":" in line:
            label, value = (p.strip() for p in line.split(":", 1))
            field = _LABEL_TO_FIELD.get(label.lower())
            if field == "tags":
                recipe["tags"] = [t.strip().lower() for t in value.split(",") if t.strip()]
            elif field in ("prep_time", "cook_time", "total_time"):
                recipe[field] = int(value) if value.isdigit() else None
            elif field:
                recipe[field] = value
    recipe["notes"] = "\n".join(notes).strip()
    return recipe


def _header(kind: str, name: str | None) -> str:
    return f"== {kind}: {name} ==" if name else f"== {kind} =="
