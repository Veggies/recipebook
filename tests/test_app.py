import importlib

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
    client.post(f"/r/{created['id']}/notes", data={"notes": "Use sourdough.\r\n\r\nButter while hot."})
    saved = client.get(f"/api/recipes/{created['id']}").json()
    assert saved["notes"] == "Use sourdough.\n\nButter while hot."
    assert saved["status"] == "needs_review"
    assert "Edit Notes" in client.get(f"/r/{created['id']}").text
