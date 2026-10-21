#!/usr/bin/env python3
"""Tiny client for the Recipe Book API (stdlib only - works with the macOS system Python).

Config via env or a .env file in the repo root:
    RECIPEBOOK_URL=https://recipes.example.com
    CF_ACCESS_CLIENT_ID=<Cloudflare Access service token id>
    CF_ACCESS_CLIENT_SECRET=<service token secret>
(The Cloudflare values aren't needed when RECIPEBOOK_URL is the NAS's LAN address.)

    rb.py list [--pending] [query]
    rb.py get ID                 # JSON to stdout
    rb.py put ID FILE.json       # replace a recipe
    rb.py add FILE.json          # create a recipe
    rb.py import URL             # scrape a link on the server
    rb.py delete ID
    rb.py export FILE.json       # every recipe, with uploaded photos embedded
    rb.py restore FILE.json      # add them to RECIPEBOOK_URL (skips titles already there)

Moving to a new server:  rb.py export backup.json, then point RECIPEBOOK_URL at the new
server and rb.py restore backup.json.
"""

from __future__ import annotations

import base64
import json
import uuid
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _config() -> str:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))
    return os.environ.get("RECIPEBOOK_URL", "http://localhost:8420").rstrip("/")


def _request(method: str, path: str, data: bytes | None = None, content_type: str | None = None) -> bytes:
    base = _config()
    req = urllib.request.Request(base + path, method=method)
    if os.environ.get("CF_ACCESS_CLIENT_ID"):
        req.add_header("CF-Access-Client-Id", os.environ["CF_ACCESS_CLIENT_ID"])
        req.add_header("CF-Access-Client-Secret", os.environ.get("CF_ACCESS_CLIENT_SECRET", ""))
    # Cloudflare's bot protection tends to reject Python's default user agent.
    req.add_header("User-Agent", "recipebook-cli/1.0")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, data, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{e.code} {e.reason}: {e.read().decode(errors='replace')}")


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    raw = _request(method, path, data, "application/json" if data else None)
    return json.loads(raw) if raw else None


def upload_image(data: bytes) -> str:
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"photo.jpg\"\r\n"
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    raw = _request("POST", "/api/images", body, f"multipart/form-data; boundary={boundary}")
    return json.loads(raw)["url"]


def export(path: str) -> None:
    recipes = []
    for summary in call("GET", "/api/recipes"):
        recipe = call("GET", f"/api/recipes/{summary['id']}")
        if recipe.get("image_url", "").startswith("/images/"):
            # Uploaded photos live on this server, so carry the bytes along.
            recipe["image_data"] = base64.b64encode(_request("GET", recipe["image_url"])).decode()
        recipes.append(recipe)
    Path(path).write_text(json.dumps(recipes, indent=2, ensure_ascii=False))
    print(f"Exported {len(recipes)} recipes to {path}")


def restore(path: str) -> None:
    existing = {r["title"] for r in call("GET", "/api/recipes")}
    added = 0
    for recipe in json.loads(Path(path).read_text()):
        if recipe["title"] in existing:
            print(f"skip (already there): {recipe['title']}")
            continue
        if recipe.get("image_data"):
            recipe["image_url"] = upload_image(base64.b64decode(recipe.pop("image_data")))
        for key in ("id", "created_at", "updated_at", "image_data"):
            recipe.pop(key, None)
        call("POST", "/api/recipes", recipe)
        added += 1
    print(f"Restored {added} recipes")


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        params = {}
        if "--pending" in args:
            args.remove("--pending")
            params["status"] = "needs_review"
        if args:
            params["q"] = " ".join(args)
        for r in call("GET", "/api/recipes?" + urllib.parse.urlencode(params)):
            flag = " [needs review]" if r["status"] == "needs_review" else ""
            print(f"{r['id']:>4}  {r['title']}{flag}")
    elif cmd == "get":
        print(json.dumps(call("GET", f"/api/recipes/{args[0]}"), indent=2, ensure_ascii=False))
    elif cmd in ("put", "add"):
        recipe = json.loads(Path(args[-1]).read_text())
        result = call("PUT", f"/api/recipes/{args[0]}", recipe) if cmd == "put" else call("POST", "/api/recipes", recipe)
        print(f"Saved #{result['id']}: {result['title']}")
    elif cmd == "import":
        result = call("POST", "/api/import", {"url": args[0]})
        print(f"#{result['id']}: {result['title']} ({result['status']})")
    elif cmd == "export":
        export(args[0])
    elif cmd == "restore":
        restore(args[0])
    elif cmd == "delete":
        call("DELETE", f"/api/recipes/{args[0]}")
        print(f"Deleted #{args[0]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
