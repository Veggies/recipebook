"""Turn a recipe URL into a recipe dict in the house format."""

import html as htmllib
import re
from types import SimpleNamespace

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import RequestException
from recipe_scrapers import scrape_html

from .ingredients import parse_ingredient

# Recipe-card plugins that most food blogs use (WP Recipe Maker, Tasty Recipes, Mediavine Create).
# Their notes aren't in the schema.org data, but steps often say "(Note 3)".
NOTES_SELECTORS = ".wprm-recipe-notes, .tasty-recipes-notes-body, .mv-create-notes-content, .recipe-notes"
_NOTE_REF_RES = [
    re.compile(r"\s*\((?:see\s+)?(?:the\s+)?notes?\b[^)]*\)", re.IGNORECASE),  # "(Note 3 Slow Cooker)", "(see Notes)"
    re.compile(r"\s*See (?:the )?notes?\b[^.]*\.", re.IGNORECASE),  # "See Note 7 for more serving options."
]


class ScrapeError(Exception):
    pass


async def fetch_html(url: str) -> tuple[str, str]:
    """Return (html, final_url) after redirects.

    Impersonates Safari's TLS fingerprint: many recipe blogs sit behind bot
    protection that rejects ordinary Python HTTP clients outright.
    """
    try:
        async with AsyncSession(impersonate="safari", timeout=20) as session:
            resp = await session.get(url, allow_redirects=True)
            resp.raise_for_status()
    except RequestException as e:
        raise ScrapeError(f"Couldn't download the page: {e}") from e
    return resp.text, str(resp.url)


def parse_recipe(html: str, url: str) -> dict:
    try:
        s = scrape_html(html, org_url=url, supported_only=False)
    except Exception as e:
        raise ScrapeError(f"No recipe found on that page ({type(e).__name__}).") from e

    title = _try(s.title)
    if not title:
        raise ScrapeError("No recipe found on that page.")

    groups = _try(s.ingredient_groups) or [SimpleNamespace(purpose=None, ingredients=_try(s.ingredients) or [])]
    ingredient_groups = [
        {"name": (g.purpose or "").strip(), "items": [parse_ingredient(line) for line in g.ingredients if line.strip()]}
        for g in groups
    ]
    step_groups = _try(lambda: _sectioned_steps(s.schema.data.get("recipeInstructions")))
    if not step_groups:
        steps = [_clean(step) for step in (_try(s.instructions_list) or []) if step.strip()]
        step_groups = [{"name": "", "steps": steps}] if steps else []
    notes = _try(lambda: _notes(html)) or ""
    if not notes:
        # References to notes we couldn't capture only confuse.
        for group in ingredient_groups:
            group["items"] = [{**i, "item": _strip_note_refs(i["item"])} for i in group["items"]]
        for group in step_groups:
            group["steps"] = [_strip_note_refs(st) for st in group["steps"]]

    return {
        "title": title.strip(),
        "description": (_try(s.description) or "").strip(),
        "source_url": url,
        "image_url": _try(s.image) or "",
        "servings": _try(s.yields) or "",
        "prep_time": _try(s.prep_time),
        "cook_time": _try(s.cook_time),
        "total_time": _try(s.total_time),
        "tags": [],
        "ingredient_groups": [g for g in ingredient_groups if g["items"]],
        "step_groups": step_groups,
        "notes": notes,
        "status": "needs_review",
    }


async def scrape(url: str) -> dict:
    html, final_url = await fetch_html(url)
    return parse_recipe(html, final_url)


def _sectioned_steps(raw) -> list[dict]:
    """Rebuild the site's own step sections from schema.org data; recipe-scrapers flattens them.

    Sections come either as HowToSection items, or as a HowToStep whose "name" is a
    sub-heading ("Make the frosting") rather than a summary of its own text.
    """
    if not isinstance(raw, list) or not all(isinstance(i, dict) for i in raw):
        return []
    groups = [{"name": "", "steps": []}]
    for item in raw:
        if item.get("@type") == "HowToSection":
            steps = [_clean(st.get("text") or st.get("name")) for st in item.get("itemListElement", []) if isinstance(st, dict)]
            groups.append({"name": _clean(item.get("name")), "steps": steps})
            continue
        name, text = _clean(item.get("name")), _clean(item.get("text"))
        if name and not text.lower().startswith(name.lower().rstrip(".")):
            groups.append({"name": name, "steps": []})
        groups[-1]["steps"].append(text)
    groups = [{**g, "steps": [st for st in g["steps"] if st]} for g in groups]
    return [g for g in groups if g["steps"]]


def _notes(html: str) -> str:
    """The recipe card's notes as plain paragraphs separated by blank lines."""
    el = BeautifulSoup(html, "html.parser").select_one(NOTES_SELECTORS)
    if not el:
        return ""
    for br in el.select("br"):
        br.replace_with("\n")
    for block in el.select("p, li, div, h3, h4, span[style*='block']"):
        block.append("\n\n")
    paragraphs = (" ".join(p.split()) for p in re.split(r"\n\s*\n", el.get_text()))
    return "\n\n".join(p for p in paragraphs if p and p.lower() != "notes")


def _strip_note_refs(text: str) -> str:
    for pattern in _NOTE_REF_RES:
        text = pattern.sub("", text)
    return text.strip()


def _clean(text) -> str:
    text = re.sub(r"<[^>]+>", " ", htmllib.unescape(text or ""))
    return " ".join(text.split())


def _try(fn):
    # recipe-scrapers raises when a site omits an optional field.
    try:
        return fn()
    except Exception:
        return None
