import pytest

from app.ingredients import annotate_steps, match_terms, parse_ingredient


@pytest.mark.parametrize("line, amount, item", [
    ("2 cups all-purpose flour", "2 cups", "all-purpose flour"),
    ("2 1/4 cups flour, sifted", "2 1/4 cups", "flour, sifted"),
    ("1½ tsp ground cumin", "1½ tsp", "ground cumin"),
    ("1 (14 oz) can diced tomatoes", "1 (14 oz) can", "diced tomatoes"),
    ("3 large eggs", "3", "large eggs"),
    ("2-3 cloves garlic, minced", "2-3 cloves", "garlic, minced"),
    ("1 tbsp. olive oil", "1 tbsp.", "olive oil"),
    ("Salt and pepper, to taste", "", "Salt and pepper, to taste"),
    ("2 tomatoes", "2", "tomatoes"),
    ("1 and 1/3 cups (166g) all-purpose flour", "1 and 1/3 cups (166g)", "all-purpose flour"),
    ("8 ounces (224g) cream cheese, softened", "8 ounces (224g)", "cream cheese, softened"),
])
def test_parse_ingredient(line, amount, item):
    assert parse_ingredient(line) == {"amount": amount, "item": item}


def _annotate(ingredients, steps, groups=None):
    ingredient_groups = groups or [{"name": "", "items": [parse_ingredient(i) for i in ingredients]}]
    return annotate_steps(ingredient_groups, [{"name": "", "steps": steps}])[0]["steps"]


def test_amount_written_after_ingredient():
    assert _annotate(["1 tsp cumin"], ["Stir in the cumin."]) == ["Stir in the cumin (1 tsp)."]


def test_step_annotation_drops_metric_aside():
    assert _annotate(["1/2 cup (8 Tbsp; 113g) butter"], ["Melt the butter."]) == ["Melt the butter (1/2 cup)."]


def test_step_that_already_states_amount_is_left_alone():
    steps = ["Add 1 tsp cumin.", "Add the cumin (1 tsp)."]
    assert _annotate(["1 tsp cumin"], steps) == steps


def test_longer_name_wins_over_shorter_overlap():
    out = _annotate(["1 cup sugar", "1/2 cup brown sugar"], ["Beat in the brown sugar, then the sugar."])
    assert out == ["Beat in the brown sugar (1/2 cup), then the sugar (1 cup)."]


def test_same_ingredient_in_two_groups_follows_the_current_group():
    groups = [
        {"name": "Cake", "items": [parse_ingredient("1 cup butter"), parse_ingredient("2 cups flour")]},
        {"name": "Frosting", "items": [parse_ingredient("1/2 cup butter"), parse_ingredient("3 cups powdered sugar")]},
    ]
    out = _annotate(None, ["Cream the butter, then add the flour.", "Beat the powdered sugar into the butter."], groups)
    assert out == [
        "Cream the butter (1 cup), then add the flour (2 cups).",
        "Beat the powdered sugar (3 cups) into the butter (1/2 cup).",
    ]


# --- match_terms: the step-matching heuristic -------------------------------

@pytest.mark.parametrize("item, step", [
    ("all-purpose flour, sifted", "Whisk the flour and salt."),
    ("ground cumin", "Add the cumin."),
    ("large eggs, at room temperature", "Beat in the eggs one at a time."),
    ("unsalted butter, softened", "Cream the butter."),
    ("extra-virgin olive oil", "Heat the olive oil in a pan."),
])
def test_match_terms_finds_ingredient_by_its_common_name(item, step):
    terms = match_terms(item)
    assert any(t in step.lower() for t in terms), f"{terms} not found in {step!r}"


@pytest.mark.parametrize("item, step", [
    ("baking powder", "Add the baking soda."),
    ("chicken stock", "Season the chicken."),
])
def test_match_terms_avoids_false_matches(item, step):
    terms = match_terms(item)
    assert not any(t in step.lower() for t in terms), f"{terms} wrongly matched {step!r}"
