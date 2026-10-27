from app.prep import before_you_start
from app.tidy import strip_celsius, tidy_recipe


def test_strip_celsius():
    assert strip_celsius("Preheat the oven to 350°F (177°C).") == "Preheat the oven to 350°F."
    assert strip_celsius("Bake at 350°F / 180°C for 20 min.") == "Bake at 350°F for 20 min."
    assert strip_celsius("Heat oven to 180°C / 350°F.") == "Heat oven to 350°F."
    assert strip_celsius("Oven at 400°F (200°C fan-forced), gas mark 6.") == "Oven at 400°F."
    assert strip_celsius("Preheat the oven to 350 degrees F (175 degrees C).") == "Preheat the oven to 350 degrees F."


def test_group_headings():
    recipe = tidy_recipe({
        "title": "Carrot Cupcakes",
        "ingredient_groups": [
            {"name": "", "items": [{"amount": "2 cups", "item": "flour"}]},
            {"name": "Cream Cheese Frosting:", "items": [{"amount": "8 oz", "item": "cream cheese"}]},
        ],
        "step_groups": [
            {"name": "", "steps": ["Mix the flour."]},
            {"name": "Meanwhile, make the frosting", "steps": ["Beat the cream cheese."]},
        ],
    })
    assert [g["name"] for g in recipe["ingredient_groups"]] == ["Carrot Cupcakes", "Cream Cheese Frosting"]
    assert [g["name"] for g in recipe["step_groups"]] == ["Carrot Cupcakes", "Cream Cheese Frosting"]


def test_category_matches_known_list():
    def category(value):
        return tidy_recipe({"title": "Toast", "category": value, "ingredient_groups": [], "step_groups": []})["category"]
    assert category("dessert") == "Desserts"
    assert category(" SOUP ") == "Soups"
    assert category("Dinner") == "Dinner"
    assert category("Brunch") == ""
    assert category(None) == ""


def test_single_group_stays_unnamed():
    recipe = tidy_recipe({"title": "Toast", "ingredient_groups": [{"name": "", "items": []}], "step_groups": []})
    assert recipe["ingredient_groups"][0]["name"] == ""


def test_before_you_start():
    before = before_you_start({"ingredient_groups": [{"name": "", "items": [
        {"amount": "8 ounces (224g)", "item": "cream cheese, softened to room temperature"},
        {"amount": "2", "item": "large eggs, at room temperature"},
        {"amount": "1", "item": "onion, diced"},
        {"amount": "2 cups", "item": "flour"},
    ]}]})
    assert len(before["ahead"]) == 1 and before["ahead"][0]["tip"].startswith("Set out")
    assert before["ahead"][0]["items"] == [
        {"amount": "8 ounces", "item": "cream cheese, softened to room temperature"},
        {"amount": "2", "item": "large eggs, at room temperature"},
    ]
    assert before["prep"] == [{"amount": "1", "item": "onion, diced"}]
