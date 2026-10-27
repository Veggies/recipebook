import importlib
import re

import pytest
from fastapi.testclient import TestClient

HTML = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Recipe",
"name":"Test Chili","recipeYield":"4","recipeIngredient":["1 lb ground beef","2 tsp cumin"],
"recipeInstructions":[{"@type":"HowToStep","text":"Brown the ground beef."},{"@type":"HowToStep","text":"Add the cumin."}]}
</script></head></html>"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app.main
    main = importlib.reload(app.main)

    async def fake_fetch(url):
        return HTML, url
    monkeypatch.setattr("app.scrape.fetch_html", fake_fetch)
    with TestClient(main.app) as c:
        yield c


def test_pages_open_without_login(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/recipes").json() == []


def test_cross_site_writes_refused(client):
    r = client.post("/add", data={"url": "https://example.com/chili"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


def test_import_annotates_steps_and_dedupes(client):
    r = client.post("/api/import", json={"url": "https://example.com/chili"})
    assert r.status_code == 201
    recipe = r.json()
    assert recipe["status"] == "needs_review"
    assert recipe["step_groups"][0]["steps"][1] == "Add the cumin (2 tsp)."
    again = client.post("/api/import", json={"url": "https://example.com/chili"})
    assert again.status_code == 200 and again.json()["id"] == recipe["id"]
    page = client.get(f"/r/{recipe['id']}")
    assert '<span class="amt">2 tsp</span>' in page.text


def test_api_crud(client):
    body = {
        "title": "Toast",
        "ingredient_groups": [{"name": "", "items": [{"amount": "2 slices", "item": "bread"}]}],
        "step_groups": [{"name": "", "steps": ["Toast the bread."]}],
    }
    created = client.post("/api/recipes", json=body).json()
    assert created["step_groups"][0]["steps"] == ["Toast the bread (2 slices)."]
    body["status"] = "needs_review"
    client.put(f"/api/recipes/{created['id']}", json=body)
    assert [r["id"] for r in client.get("/api/recipes?status=needs_review").json()] == [created["id"]]
    assert client.delete(f"/api/recipes/{created['id']}").status_code == 204


def test_category_filter_on_home(client):
    def add(title, category):
        client.post("/api/recipes", json={"title": title, "category": category,
                                          "ingredient_groups": [], "step_groups": []})
    add("Brownies", "dessert")
    add("Chili", "Dinner")
    add("Aioli", "Sauces")
    home = client.get("/").text
    assert ">Desserts</a>" in home and ">Dinner</a>" in home and ">Salads</a>" not in home
    desserts = client.get("/?category=Desserts").text
    assert '<li data-category="Desserts">' in desserts and '<li data-category="Dinner" hidden>' in desserts
    assert "No recipes match" in client.get("/?category=Breakfast").text
    # Static files are cache-busted by content, not a hand-bumped number.
    assert re.search(r'/static/app\.js\?v=[0-9a-f]{10}"', home)
    assert [r["category"] for r in client.get("/api/recipes").json()] == ["", "Desserts", "Dinner"]


def test_step_sections_are_kept():
    from app.scrape import _sectioned_steps
    raw = [
        {"@type": "HowToStep", "text": "Mix the batter."},
        {"@type": "HowToStep", "name": "Make the frosting", "text": "Beat the butter."},
        {"@type": "HowToStep", "name": "Frost", "text": "Frost the cake."},
        {"@type": "HowToSection", "name": "To serve", "itemListElement": [{"@type": "HowToStep", "text": "Slice &amp; serve."}]},
    ]
    assert _sectioned_steps(raw) == [
        {"name": "", "steps": ["Mix the batter."]},
        {"name": "Make the frosting", "steps": ["Beat the butter.", "Frost the cake."]},
        {"name": "To serve", "steps": ["Slice & serve."]},
    ]


def test_blog_notes_not_imported_and_refs_stripped():
    from app.scrape import parse_recipe
    html = HTML.replace("Add the cumin.", "Add the cumin (Note 1). See Note 2 for options.").replace(
        '"recipeYield"', '"description":"Recipe video above. So good! See notes for toppings!","recipeYield"'
    ) + (
        '<div class="wprm-recipe-notes"><span>1. Cumin: Toast it first.</span></div>'
    )
    recipe = parse_recipe(html, "https://example.com/chili")
    assert recipe["step_groups"][0]["steps"][1] == "Add the cumin."
    assert recipe["notes"] == ""
    assert recipe["description"] == "So good!"


def test_add_note_from_recipe_page(client):
    created = client.post("/api/recipes", json={
        "title": "Toast", "status": "needs_review",
        "ingredient_groups": [{"name": "", "items": [{"amount": "2 slices", "item": "bread"}]}],
        "step_groups": [{"name": "", "steps": ["Toast the bread."]}],
    }).json()
    assert "Add a Note" in client.get(f"/r/{created['id']}").text
    r = client.post(f"/r/{created['id']}/notes", data={"notes": "Use sourdough.\r\n\r\nButter while hot.", "tab": "steps"},
                    follow_redirects=False)
    assert r.headers["location"].endswith("#steps-notes")
    saved = client.get(f"/api/recipes/{created['id']}").json()
    assert saved["notes"] == "Use sourdough.\n\nButter while hot."
    assert saved["status"] == "needs_review"
    assert "Edit Notes" in client.get(f"/r/{created['id']}").text


def test_shopping_list_pages(client):
    def make(title, *lines):
        return client.post("/api/recipes", json={
            "title": title,
            "ingredient_groups": [{"name": "", "items": [{"amount": a, "item": i} for a, i in lines]}],
            "step_groups": [{"name": "", "steps": ["Cook."]}],
        }).json()["id"]
    a = make("Lemon Bars", ("1", "lemon"), ("1 cup", "flour"))
    b = make("Lemonade", ("1", "lemon, juiced"), ("2 cups", "water"))
    assert client.get("/shop/list", follow_redirects=False).status_code == 303
    assert "Lemon Bars" in client.get("/shop").text
    page = client.get(f"/shop/list?r={a}&r={b}").text
    assert "<b>2</b> lemons" in page and "water" not in page
    assert client.get(f"/api/shopping-list?r={a}&r={b}").json()[0]["items"][0]["amount"] == "2"


def test_one_step_sections_are_step_titles():
    from app.scrape import _sectioned_steps
    raw = [{"@type": "HowToStep", "name": n, "text": t} for n, t in
           [("Slice", "Cut the onions."), ("Cook", "Fry them."), ("Season", "Add salt."), ("Serve", "Ladle it out.")]]
    raw.append({"@type": "HowToStep", "text": "Enjoy!"})
    assert _sectioned_steps(raw) == [
        {"name": "", "steps": ["Cut the onions.", "Fry them.", "Add salt.", "Ladle it out.", "Enjoy!"]}
    ]


def test_form_editor_round_trip(client):
    import json
    created = client.post("/api/recipes", json={
        "title": "Ranch Roast", "source_url": "https://example.com/r",
        "ingredient_groups": [{"name": "", "items": [{"amount": "1 (3 to 4 lb)", "item": "chuck roast"}]}],
        "step_groups": [{"name": "", "steps": ["Cook the roast."]}],
    }).json()
    assert 'value="1 (3 to 4 lb) chuck roast"' in client.get(f"/r/{created['id']}/edit").text
    form = {
        "title": "Ranch Roast", "description": "", "image_url": "/images/x.jpg", "servings": "8",
        "prep_time": "5", "cook_time": "480", "total_time": "", "category": "Dinner", "tags": "Beef, Slow Cooker", "notes": "",
        "needs_review": False,
        "ingredient_groups": [{"name": "", "items": [
            {"line": "1 (3 to 4 lb) chuck roast", "amount": "1 (3 to 4 lb)", "item": "chuck roast"},  # untouched
            {"line": "1 packet ranch dressing mix"},                                                  # new line
            {"line": "   "},                                                                          # blank row
        ]}],
        "step_groups": [{"name": "", "steps": ["Sprinkle the ranch dressing mix over the roast.", ""]}],
    }
    r = client.post(f"/r/{created['id']}/edit", data={"recipe": json.dumps(form)}, follow_redirects=False)
    assert r.status_code == 303
    saved = client.get(f"/api/recipes/{created['id']}").json()
    assert saved["ingredient_groups"][0]["items"] == [
        {"amount": "1 (3 to 4 lb)", "item": "chuck roast"}, {"amount": "1 packet", "item": "ranch dressing mix"},
    ]
    assert saved["step_groups"][0]["steps"] == ["Sprinkle the ranch dressing mix (1 packet) over the roast (1)."]
    assert saved["category"] == "Dinner" and saved["tags"] == ["beef", "slow cooker"] and saved["cook_time"] == 480 and saved["total_time"] is None
    assert saved["source_url"] == "https://example.com/r" and saved["image_url"] == "/images/x.jpg"


def test_new_recipe_from_form(client):
    import json
    form = {"title": "Toast", "ingredient_groups": [{"name": "", "items": [{"line": "2 slices bread"}]}],
            "step_groups": [{"name": "", "steps": ["Toast the bread."]}]}
    r = client.post("/new", data={"recipe": json.dumps(form)}, follow_redirects=False)
    assert r.status_code == 303 and "New Recipe" in client.get("/new").text


def test_image_upload(client):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), "orange").save(buf, "PNG")
    r = client.post("/api/images", files={"file": ("p.png", buf.getvalue(), "image/png")})
    assert r.status_code == 201
    url = r.json()["url"]
    img = client.get(url)
    assert img.status_code == 200 and Image.open(io.BytesIO(img.content)).size == (1600, 1067)
    bad = client.post("/api/images", files={"file": ("x.txt", b"not an image", "text/plain")})
    assert bad.status_code == 422
