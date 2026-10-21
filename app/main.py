import hashlib
import hmac
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from pydantic import BaseModel, Field, HttpUrl

from . import db, textformat
from .ingredients import annotate_steps, short_amount
from .scrape import ScrapeError, scrape

log = logging.getLogger("recipebook")

APP_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
API_TOKEN = os.environ.get("API_TOKEN", "")
SESSION_COOKIE = "rb_session"
PUBLIC_PATHS = ("/login", "/static/", "/manifest.webmanifest", "/healthz")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init(DATA_DIR / "recipes.db")
    if not APP_PASSWORD:
        log.warning("APP_PASSWORD is not set - the site is open to anyone who can reach it.")
    yield


app = FastAPI(title="Recipe Book", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


# --- auth -------------------------------------------------------------------

def _secret() -> bytes:
    # Kept in the data volume so sessions survive image updates.
    path = DATA_DIR / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip().encode()


def _session_value() -> str:
    # Derived from the password, so changing APP_PASSWORD signs everyone out.
    return hmac.new(_secret(), APP_PASSWORD.encode(), hashlib.sha256).hexdigest()


def _is_authed(request: Request) -> bool:
    if not APP_PASSWORD:
        return True
    auth = request.headers.get("authorization", "")
    if API_TOKEN and auth.startswith("Bearer ") and hmac.compare_digest(auth[7:], API_TOKEN):
        return True
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return hmac.compare_digest(cookie, _session_value())


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith(PUBLIC_PATHS) or _is_authed(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    next_url = path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/login?next={quote(next_url)}", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": None})


@app.post("/login")
def login(request: Request, password: str = Form(...), next: str = Form("/")):
    if not hmac.compare_digest(password, APP_PASSWORD):
        return templates.TemplateResponse(
            request, "login.html", {"next": next, "error": "Wrong password"}, status_code=401
        )
    resp = RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE, _session_value(), max_age=60 * 60 * 24 * 365, httponly=True,
        samesite="lax", secure=request.url.scheme == "https",
    )
    return resp


@app.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# --- shared -----------------------------------------------------------------

def normalize(recipe: dict) -> dict:
    """Enforce house rules on every save, whatever the recipe's origin."""
    recipe["step_groups"] = annotate_steps(recipe.get("ingredient_groups", []), recipe.get("step_groups", []))
    recipe["title"] = (recipe.get("title") or "").strip() or "Untitled recipe"
    return recipe


async def import_url(url: str) -> tuple[dict, bool]:
    """Scrape and save a recipe. Returns (recipe, created); re-sharing a link returns the existing one."""
    if existing := db.find_by_source(url):
        return existing, False
    recipe = await scrape(url)
    if recipe["source_url"] != url and (existing := db.find_by_source(recipe["source_url"])):
        return existing, False
    return db.create(normalize(recipe)), True


_PAREN_RE = re.compile(r"\(([^()]+)\)")


def highlight_amounts(step: str, recipe: dict) -> Markup:
    """Render ingredient amounts in step text, e.g. "(2 cups)", as highlighted; leave "(177°C)" alone."""
    amounts = {
        str(escape(a)).lower()
        for g in recipe.get("ingredient_groups", []) for i in g["items"] if i.get("amount")
        for a in (i["amount"], short_amount(i["amount"]))
    }
    return Markup(_PAREN_RE.sub(
        lambda m: f'<span class="amt">{m.group(1)}</span>' if m.group(1).lower() in amounts else m.group(0),
        str(escape(step)),
    ))


def fmt_minutes(minutes) -> str:
    if not minutes:
        return ""
    h, m = divmod(int(minutes), 60)
    return f"{h} hr {m} min" if h and m else f"{h} hr" if h else f"{m} min"


templates.env.filters["amounts"] = highlight_amounts
templates.env.filters["minutes"] = fmt_minutes
templates.env.globals["auth_enabled"] = bool(APP_PASSWORD)


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
    all_tags = sorted({t for r in recipes for t in r.get("tags", [])})
    if tag:
        recipes = [r for r in recipes if tag in r.get("tags", [])]
    return templates.TemplateResponse(
        request, "index.html", {"recipes": recipes, "q": q, "tag": tag, "tags": all_tags}
    )


@app.get("/r/{recipe_id}", response_class=HTMLResponse)
def view(request: Request, recipe_id: int):
    recipe = db.get(recipe_id) or _not_found()
    return templates.TemplateResponse(request, "recipe.html", {"r": recipe})


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


@app.post("/api/import")
async def api_import(body: ImportIn):
    try:
        recipe, created = await import_url(str(body.url))
    except ScrapeError as e:
        raise HTTPException(422, str(e)) from e
    return JSONResponse(recipe, status_code=201 if created else 200)
