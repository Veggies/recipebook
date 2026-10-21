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
    ("1 lb / 500g beef mince / ground beef", "1 lb", "beef mince / ground beef"),
    ("800g / 28 oz can crushed tomato", "28 oz can", "crushed tomato"),
    ("14 oz / 420g can red kidney beans", "14 oz can", "red kidney beans"),
    ("3 garlic cloves (, minced)", "3", "garlic cloves, minced"),
    ("1 red capsicum ((bell pepper), diced)", "1", "red capsicum (bell pepper), diced"),
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
    ("garlic cloves, minced", "Add the garlic and onion."),
    ("peeled, shredded, and coarsely chopped carrots*", "Whisk in the carrots."),
    ("beef mince / ground beef", "Add the beef."),
    ("packed light or dark brown sugar", "Whisk the oil and brown sugar."),
    ("ripe tomatoes, chopped", "Add the tomato."),
    ("pure vanilla extract", "Stir in vanilla."),
])
def test_match_terms_finds_ingredient_by_its_common_name(item, step):
    terms = match_terms(item)
    assert any(t in step.lower() for t in terms), f"{terms} not found in {step!r}"


@pytest.mark.parametrize("item, step", [
    ("baking powder", "Add the baking soda."),
    ("chicken stock", "Season the chicken."),
    ("packed light or dark brown sugar", "Use a light touch."),
])
def test_match_terms_avoids_false_matches(item, step):
    terms = match_terms(item)
    assert not any(t in step.lower() for t in terms), f"{terms} wrongly matched {step!r}"


def test_term_shared_by_two_ingredients_in_one_group_is_not_used():
    out = _annotate(["2 tsp garlic powder", "1 tsp onion powder"], ["Add the garlic powder, then the rest of the powder."])
    assert out == ["Add the garlic powder (2 tsp), then the rest of the powder."]


def test_step_group_named_like_ingredient_group_uses_its_amounts():
    groups = [
        {"name": "Cake", "items": [parse_ingredient("1 cup butter")]},
        {"name": "Frosting", "items": [parse_ingredient("1/2 cup butter")]},
    ]
    steps = [{"name": "Cake", "steps": ["Melt the butter."]}, {"name": "Frosting", "steps": ["Beat the butter."]}]
    out = annotate_steps(groups, steps)
    assert [g["steps"] for g in out] == [["Melt the butter (1 cup)."], ["Beat the butter (1/2 cup)."]]


def test_note_reference_after_ingredient_does_not_block_amount():
    assert _annotate(["1 tsp cayenne pepper"], ["Add cayenne pepper (Note 2)."]) == ["Add cayenne pepper (1 tsp) (Note 2)."]


def test_ingredient_annotated_once_per_step():
    out = _annotate(["8 oz cream cheese"], ["Beat the cream cheese. Cold cream cheese holds its shape."])
    assert out == ["Beat the cream cheese (8 oz). Cold cream cheese holds its shape."]


def test_dish_name_and_headings_not_annotated():
    out = _annotate(["2 tbsp butter", "6 chicken thighs"],
                    ["Make Butter Chicken Sauce: melt the butter.", "Brown Chicken Thighs: brown the chicken thighs."])
    assert out == ["Make Butter Chicken Sauce: melt the butter (2 tbsp).",
                   "Brown Chicken Thighs: brown the chicken thighs (6)."]


def test_amount_with_metric_aside_already_stated():
    assert _annotate(["2 tbsp garam masala"], ["Add 2 tbsp (24g) garam masala."]) == ["Add 2 tbsp (24g) garam masala."]


def test_generic_word_alone_not_matched():
    assert _annotate(["1 tbsp lemon juice"], ["Add the meat juice."]) == ["Add the meat juice."]


def test_to_taste_not_annotated():
    assert _annotate(["1 tbsp kosher salt"], ["Season to taste with salt."]) == ["Season to taste with salt."]
    out = _annotate(["2 tbsp sugar", "1 tsp salt"], ["Adjust with more salt, sugar, and lemon to taste. Add the sugar."])
    assert out == ["Adjust with more salt, sugar, and lemon to taste. Add the sugar (2 tbsp)."]


def test_fraction_in_alternative_is_not_a_term():
    terms = match_terms("fresh thyme (sprigs) OR 1/2 teaspoon dried thyme")
    assert "1" not in terms and "thyme" in terms


def test_canned_is_not_a_can():
    assert parse_ingredient("4 to 8 ounces canned tomato sauce") == {"amount": "4 to 8 ounces", "item": "canned tomato sauce"}


def test_amount_stated_under_another_name_counts():
    out = _annotate(["2 tbsp ghee or unsalted butter"], ["Add the ghee or butter (2 tbsp)."])
    assert out == ["Add the ghee or butter (2 tbsp)."]
