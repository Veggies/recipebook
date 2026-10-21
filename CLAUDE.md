# Recipe Book

FastAPI + SQLite recipe app, deployed as a container on TrueNAS. Pushing to `main`
runs the tests, then publishes `ghcr.io/<owner>/recipebook:latest`.

## Recipe format (house rules)

Every recipe must follow these, whether scraped, typed, or written by Claude:

- **Ingredient groups per component.** A cake with frosting has a "Cake" group and a
  "Frosting" group; a single-component dish has one group with an empty name.
- **Step groups mirror the components** when the method is separable (e.g. "Cake", "Frosting").
- **Every step states the amount of each ingredient it uses**, in parentheses right after
  the ingredient: `Stir in the cumin (1 tsp) and paprika (2 tsp).` If a step uses only part
  of an ingredient, give that part: `Add half the butter (2 tbsp).`
- **Every list gets a heading when there's more than one component.** Name the main group after
  what it makes ("Cupcakes", "Chili"), and give step groups the same names as their ingredient groups.
- Ingredient `amount` holds quantity + unit only ("2 1/4 cups"); prep notes stay in `item`
  ("all-purpose flour, sifted"). Keep cues like "softened to room temperature", "thawed", "diced"
  in `item` - the "Before You Start" section is built from them.
- **American kitchen:** US units first (cups, oz, lb); never Celsius or gas marks (stripped on save).
- **No blog notes.** Don't import a site's notes section, and remove references to it ("Note 3",
  "see Notes"). `notes` is only for notes the user asks to add.
- Times are integer minutes. Tags are lowercase.

## Shopping list

`/shop` → pick recipes → `/shop/list` (tick what's at home) → final list, shared to Apple Notes
via the iOS share sheet. Combining lives in `app/shopping.py`: same ingredient across recipes is
added up (volumes in tsp, weights in oz, then shown in a natural unit); unconvertible amounts sit
side by side. `GET /api/shopping-list?r=1&r=2` returns the same data as JSON.

## Where recipes live

The real recipe book is the one on the NAS. Code changes ship as a new image (push to `main`); recipe
changes go straight to the NAS through its API with `rb.py`. Never copy database files around.
The `data/` folder in this repo is a local sandbox for testing UI changes, not the real data.

Uploaded photos are stored next to the database (`/data/images`) and referenced as `/images/<name>.jpg`.

## Working with the live recipe list

Use `scripts/rb.py` (reads `RECIPEBOOK_URL` and the Cloudflare Access service token from `.env`):

```sh
python3 scripts/rb.py list --pending       # imported recipes awaiting cleanup
python3 scripts/rb.py get 12 > /tmp/r.json # edit, then:
python3 scripts/rb.py put 12 /tmp/r.json
python3 scripts/rb.py add new.json         # create from scratch
python3 scripts/rb.py import <url>         # server-side scrape
python3 scripts/rb.py export backup.json   # everything, uploaded photos embedded
python3 scripts/rb.py restore backup.json  # into RECIPEBOOK_URL; skips titles already there
```

**"Clean up pending recipes"** means: for each `needs_review` recipe, regroup ingredients by
component, split steps into matching groups, make every step state its amounts per the
rules above, fix obvious scraping junk, add a few tags, set `"status": "ready"`, and `put` it back.
Keep the scratch JSON files in the session scratchpad, not the repo.

JSON shape: see `RecipeIn` in `app/main.py`.

## Development

Tests run on Python 3.12 (the system Python here is 3.9 - too old). Use Docker:

```sh
docker build -t recipebook-test -f - . <<'EOF'
FROM python:3.12-slim
WORKDIR /w
COPY requirements*.txt ./
RUN pip install -r requirements-dev.txt
EOF
docker run --rm -v "$PWD:/w" -w /w recipebook-test python -m pytest -q -p no:cacheprovider
```

Run locally: `docker build -t recipebook . && docker run --rm -p 8420:8000 -v "$PWD/data:/data" recipebook`

The web editor (`/r/<id>/edit`) is a form for non-technical use; `/r/<id>/edit/text` keeps the
plain-text format (`app/textformat.py`).
