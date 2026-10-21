import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from pydantic import BaseModel, Field, HttpUrl

from . import db, textformat
from .ingredients import short_amount
from .prep import before_you_start
from .tidy import tidy_recipe
from .scrape import ScrapeError, scrape
from .shopping import build_shopping_list

APP_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init(DATA_DIR / "recipes.db")
    yield


app = FastAPI(title="Recipe Book", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


# Sign-in is handled in front of the app (Cloudflare Access), so there's no login here.
# What remains is refusing changes triggered from other websites, which would ride
# along on the browser's Cloudflare session.

@app.middleware("http")
async def block_cross_site_writes(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    return await call_next(request)


# --- shared -----------------------------------------------------------------

def normalize(recipe: dict) -> dict:
    """Enforce house rules on every save, whatever the recipe's origin."""
    return tidy_recipe(recipe)


async def import_url(url: str) -> tuple[dict, bool]:
    """Scrape and save a recipe. Returns (recipe, created); re-sharing a link returns the existing one."""
    if existing := db.find_by_source(url):
        return existing, False
    recipe = await scrape(url)
    if recipe["source_url"] != url and (existing := db.find_by_source(recipe["source_url"])):
        return existing, False
    return db.create(normalize(recipe)), True


_PAREN_RE = re.compile(r"\(([^()]+)\)")


def render_step(step: str, recipe: dict) -> Markup:
    """Highlight ingredient amounts like "(2 cups)" in step text."""
    amounts = {
        str(escape(a)).lower()
        for g in recipe.get("ingredient_groups", []) for i in g["items"] if i.get("amount")
        for a in (i["amount"], short_amount(i["amount"]))
    }
    html = _PAREN_RE.sub(
        lambda m: f'<span class="amt">{m.group(1)}</span>' if m.group(1).lower() in amounts else m.group(0),
        str(escape(step)),
    )
    return Markup(html)


def note_paragraphs(notes: str) -> list[str]:
    return [p.strip() for p in (notes or "").split("\n\n") if p.strip()]


def fmt_minutes(minutes) -> str:
    if not minutes:
        return ""
    h, m = divmod(int(minutes), 60)
    return f"{h} hr {m} min" if h and m else f"{h} hr" if h else f"{m} min"


templates.env.filters["step"] = render_step
templates.env.filters["note_paragraphs"] = note_paragraphs
templates.env.filters["minutes"] = fmt_minutes
templates.env.filters["serves"] = lambda v: re.sub(r"\s*(servings?|serves|people|portions)$", "", str(v), flags=re.IGNORECASE)


# --- pages ------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(
        {
            "name": "Recipe Book", "short_name": "Recipes", "start_url": "/", "display": "standalone",
            "background_color": "#f2f2f7", "theme_color": "#f2f2f7",
            "icons": [
                {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        },
        media_type="application/manifest+json",
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = "", tag: str = ""):
    recipes = db.list_recipes(q)
    if tag:
        recipes = [r for r in recipes if tag in r.get("tags", [])]
    return templates.TemplateResponse(request, "index.html", {"recipes": recipes, "q": q, "tag": tag})


@app.get("/r/{recipe_id}", response_class=HTMLResponse)
def view(request: Request, recipe_id: int):
    recipe = db.get(recipe_id) or _not_found()
    return templates.TemplateResponse(request, "recipe.html", {"r": recipe, "before": before_you_start(recipe)})


@app.get("/r/{recipe_id}/edit", response_class=HTMLResponse)
def edit_page(request: Request, recipe_id: int):
    recipe = db.get(recipe_id) or _not_found()
    return templates.TemplateResponse(
        request, "edit.html", {"r": recipe, "text": textformat.to_text(recipe), "error": None}
    )


@app.post("/r/{recipe_id}/edit")
def edit(request: Request, recipe_id: int, text: str = Form(...), needs_review: bool = Form(False)):
    recipe = textformat.from_text(text)
    recipe["status"] = "needs_review" if needs_review else "ready"
    saved = db.update(recipe_id, normalize(recipe)) or _not_found()
    return RedirectResponse(f"/r/{saved['id']}", status_code=303)


@app.post("/r/{recipe_id}/notes")
def save_notes(recipe_id: int, notes: str = Form(""), tab: str = Form("")):
    recipe = db.get(recipe_id) or _not_found()
    recipe["notes"] = notes.replace("\r\n", "\n").strip()
    db.update(recipe_id, normalize(recipe))
    # Back to the tab the note was written from, scrolled to the notes.
    return RedirectResponse(f"/r/{recipe_id}#{'steps-' if tab == 'steps' else ''}notes", status_code=303)


@app.post("/r/{recipe_id}/delete")
def delete(recipe_id: int):
    db.delete(recipe_id) or _not_found()
    return RedirectResponse("/", status_code=303)


@app.get("/new", response_class=HTMLResponse)
def new_page(request: Request):
    blank = {"title": "", "ingredient_groups": [{"name": "", "items": []}], "step_groups": [{"name": "", "steps": []}]}
    return templates.TemplateResponse(
        request, "edit.html", {"r": None, "text": textformat.to_text(blank), "error": None}
    )


@app.post("/new")
def new(text: str = Form(...)):
    saved = db.create(normalize(textformat.from_text(text)))
    return RedirectResponse(f"/r/{saved['id']}", status_code=303)


@app.get("/add", response_class=HTMLResponse)
def add_page(request: Request, url: str = ""):
    # The iOS Shortcut opens /add?url=...; the page auto-submits the import.
    return templates.TemplateResponse(request, "add.html", {"url": url, "error": None})


@app.post("/add")
async def add(request: Request, url: str = Form(...)):
    url = _extract_url(url)
    try:
        recipe, _ = await import_url(url)
    except ScrapeError as e:
        return templates.TemplateResponse(request, "add.html", {"url": url, "error": str(e)}, status_code=422)
    return RedirectResponse(f"/r/{recipe['id']}", status_code=303)


@app.get("/shop", response_class=HTMLResponse)
def shop_pick(request: Request, r: list[int] = Query(default=[])):
    """Step 1 of the shopping list: choose what you're cooking."""
    return templates.TemplateResponse(request, "shop_pick.html", {"recipes": db.list_recipes(), "chosen": set(r)})


@app.get("/shop/list", response_class=HTMLResponse)
def shop_list(request: Request, r: list[int] = Query(default=[])):
    """Steps 2 and 3: tick off what you already have, then the final list to share."""
    recipes = [recipe for recipe in (db.get(i) for i in r) if recipe]
    if not recipes:
        return RedirectResponse("/shop", status_code=303)
    return templates.TemplateResponse(request, "shop_list.html", {
        "recipes": recipes, "groups": build_shopping_list(recipes),
        "list_id": ",".join(str(x["id"]) for x in sorted(recipes, key=lambda x: x["id"])),
        "shop_back": "/shop?" + "&".join(f"r={x['id']}" for x in recipes),
    })


def _extract_url(text: str) -> str:
    # Share sheets sometimes send "Recipe title https://..." rather than a bare URL.
    m = re.search(r"https?://\S+", text)
    return m.group(0) if m else text.strip()


def _not_found():
    raise HTTPException(404, "Recipe not found")


# --- JSON API (iOS Shortcut, Claude Code, scripts) --------------------------

class Ingredient(BaseModel):
    amount: str = ""
    item: str


class IngredientGroup(BaseModel):
    name: str = ""
    items: list[Ingredient]


class StepGroup(BaseModel):
    name: str = ""
    steps: list[str]


class RecipeIn(BaseModel):
    title: str
    description: str = ""
    source_url: str = ""
    image_url: str = ""
    servings: str = ""
    prep_time: int | None = None
    cook_time: int | None = None
    total_time: int | None = None
    tags: list[str] = Field(default_factory=list)
    ingredient_groups: list[IngredientGroup]
    step_groups: list[StepGroup]
    notes: str = ""
    status: str = Field("ready", pattern="^(ready|needs_review)$")


class ImportIn(BaseModel):
    url: HttpUrl


@app.get("/api/recipes")
def api_list(q: str = "", status: str | None = None):
    return [
        {"id": r["id"], "title": r["title"], "status": r["status"], "source_url": r.get("source_url", ""),
         "tags": r.get("tags", []), "updated_at": r["updated_at"]}
        for r in db.list_recipes(q, status)
    ]


@app.get("/api/recipes/{recipe_id}")
def api_get(recipe_id: int):
    return db.get(recipe_id) or _not_found()


@app.post("/api/recipes", status_code=201)
def api_create(recipe: RecipeIn):
    return db.create(normalize(recipe.model_dump()))


@app.put("/api/recipes/{recipe_id}")
def api_update(recipe_id: int, recipe: RecipeIn):
    return db.update(recipe_id, normalize(recipe.model_dump())) or _not_found()


@app.delete("/api/recipes/{recipe_id}", status_code=204)
def api_delete(recipe_id: int):
    db.delete(recipe_id) or _not_found()


@app.get("/api/shopping-list")
def api_shopping_list(r: list[int] = Query(default=[])):
    return build_shopping_list([recipe for recipe in (db.get(i) for i in r) if recipe])


@app.post("/api/import")
async def api_import(body: ImportIn):
    try:
        recipe, created = await import_url(str(body.url))
    except ScrapeError as e:
        raise HTTPException(422, str(e)) from e
    return JSONResponse(recipe, status_code=201 if created else 200)
