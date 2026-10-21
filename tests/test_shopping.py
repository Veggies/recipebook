import pytest

from app.ingredients import parse_ingredient
from app.shopping import aisle_for, build_shopping_list, parse_amount


def recipe(title, *lines):
    return {"title": title, "ingredient_groups": [{"name": "", "items": [parse_ingredient(l) for l in lines]}]}


def flat(shopping_list):
    return {i["name"]: i for g in shopping_list for i in g["items"]}


def test_same_ingredient_across_recipes_is_added_up():
    items = flat(build_shopping_list([recipe("A", "1 lemon, juiced"), recipe("B", "1 lemon")]))
    assert items["lemons"]["amount"] == "2"
    assert items["lemons"]["sources"] == ["A", "B"]


def test_volumes_convert_and_add():
    items = flat(build_shopping_list([
        recipe("Cake", "1 cup unsalted butter, softened"),
        recipe("Frosting", "2 tbsp unsalted butter"),
    ]))
    assert items["unsalted butter"]["amount"] == "1 1/8 cups"


def test_small_volumes_stay_small():
    items = flat(build_shopping_list([recipe("A", "1 tsp cumin"), recipe("B", "1/2 teaspoon cumin")]))
    assert items["cumin"]["amount"] == "1 1/2 tsp"


def test_incompatible_amounts_shown_side_by_side():
    items = flat(build_shopping_list([recipe("A", "1 cup butter"), recipe("B", "1 stick butter")]))
    assert items["butter"]["amount"] == "1 cup + 1 stick"


def test_descriptions_that_dont_change_the_purchase_merge():
    items = flat(build_shopping_list([recipe("A", "2 large eggs, at room temperature"), recipe("B", "1 egg")]))
    assert items["eggs"]["amount"] == "3"


def test_descriptions_that_change_the_purchase_stay_separate():
    items = flat(build_shopping_list([recipe("A", "1 tsp dried oregano"), recipe("B", "1 tbsp fresh oregano")]))
    assert set(items) == {"dried oregano", "oregano"}


def test_prep_words_before_the_name_are_dropped():
    items = flat(build_shopping_list([recipe("A", "1 1/2 cups peeled, shredded, and coarsely chopped carrots*")]))
    assert set(items) == {"carrots"}


def test_garlic_cloves_either_way_round():
    items = flat(build_shopping_list([recipe("A", "3 garlic cloves, minced"), recipe("B", "2 cloves garlic")]))
    assert items["garlic"]["amount"] == "5 cloves"


def test_cans_counted_by_size():
    items = flat(build_shopping_list([recipe("A", "28 oz can crushed tomatoes"), recipe("B", "28 oz can crushed tomatoes")]))
    assert items["crushed tomatoes"]["amount"] == "2 cans (28 oz)"


def test_water_skipped_and_unquantified_kept():
    items = flat(build_shopping_list([recipe("A", "2 cups water", "salt and pepper, to taste")]))
    assert "water" not in items
    assert items["salt and pepper"]["amount"] == ""


def test_optional_items_flagged():
    items = flat(build_shopping_list([recipe("A", "optional add-in: 3/4 cup chopped walnuts")]))
    assert items["walnuts"]["optional"] and items["walnuts"]["amount"] == "3/4 cup"


def test_grouped_by_aisle_in_store_order():
    groups = build_shopping_list([recipe("A", "1 lemon", "1 lb ground beef", "2 cups flour", "1 cup milk")])
    assert [g["aisle"] for g in groups] == ["Produce", "Meat & Seafood", "Dairy & Eggs", "Baking"]


@pytest.mark.parametrize("key, aisle", [
    ("ground beef", "Meat & Seafood"), ("ground cumin", "Spices"), ("baking powder", "Baking"),
    ("garlic powder", "Spices"), ("unsalted butter", "Dairy & Eggs"), ("peanut butter", "Pantry"),
    ("beef bouillon cube", "Pantry"), ("red kidney bean", "Pantry"), ("eggplant", "Produce"),
    ("semisweet chocolate chip", "Baking"), ("salted butter", "Dairy & Eggs"), ("garlic", "Produce"),
])
def test_aisles(key, aisle):
    assert aisle_for(key) == aisle


@pytest.mark.parametrize("amount, expected", [
    ("1 1/2 cups (200g)", (1.5, "cup")), ("1 and 1/3 cups", (4 / 3, "cup")), ("½ tsp", (0.5, "tsp")),
    ("8 Tbsp", (8, "tbsp")), ("1 T", (1, "tbsp")), ("1 t", (1, "tsp")), ("1 - 2 tsp", (2, "tsp")),
    ("3", (3, "")), ("2 cloves", (2, "clove")), ("28 oz can", (1, "can (28 oz)")),
])
def test_parse_amount(amount, expected):
    qty, unit = parse_amount(amount)
    assert (round(qty, 3), unit) == (round(expected[0], 3), expected[1])


def test_hyphenated_prep_and_olive_oil_grades_merge():
    items = flat(build_shopping_list([
        recipe("A", "1 large carrot, diced", "1 tbsp extra virgin olive oil"),
        recipe("B", "3 cups medium-diced carrots", "1/4 cup olive oil"),
    ]))
    assert items["carrot"]["amount"] == "1 + 3 cups"
    assert items["olive oil"]["amount"] == "1/3 cup"  # 5 tbsp, rounded to a measuring cup


def test_canned_produce_goes_to_pantry_and_quarts():
    groups = build_shopping_list([recipe("A", "1 (14.5 oz) can diced fire-roasted tomatoes", "3 quarts chicken stock")])
    pantry = {i["name"]: i for g in groups if g["aisle"] == "Pantry" for i in g["items"]}
    assert "fire-roasted tomatoes" in pantry
    assert pantry["chicken stock"]["amount"] == "3 quarts"
