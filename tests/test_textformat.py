from app.textformat import from_text, to_text

RECIPE = {
    "title": "Carrot Cake",
    "servings": "12",
    "prep_time": 30,
    "tags": ["dessert", "cake"],
    "ingredient_groups": [
        {"name": "Cake", "items": [{"amount": "2 cups", "item": "flour"}, {"amount": "", "item": "pinch of salt"}]},
        {"name": "Frosting", "items": [{"amount": "8 oz", "item": "cream cheese, softened"}]},
    ],
    "step_groups": [
        {"name": "Cake", "steps": ["Whisk the flour (2 cups).", "Bake."]},
        {"name": "Frosting", "steps": ["Beat the cream cheese (8 oz)."]},
    ],
    "notes": "Keeps 3 days.\nFreezes well.",
}


def test_round_trip():
    parsed = from_text(to_text(RECIPE))
    for key, value in RECIPE.items():
        assert parsed[key] == value


def test_lenient_input():
    parsed = from_text("Title: Toast\n\n== Ingredients ==\n2 slices bread\n\n== Steps ==\n1. Toast the bread.\n2) Eat.\n")
    assert parsed["ingredient_groups"] == [{"name": "", "items": [{"amount": "2 slices", "item": "bread"}]}]
    assert parsed["step_groups"] == [{"name": "", "steps": ["Toast the bread.", "Eat."]}]
