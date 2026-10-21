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
"""

import json
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


def call(method: str, path: str, body=None):
    base = _config()
    req = urllib.request.Request(base + path, method=method)
    if os.environ.get("CF_ACCESS_CLIENT_ID"):
        req.add_header("CF-Access-Client-Id", os.environ["CF_ACCESS_CLIENT_ID"])
        req.add_header("CF-Access-Client-Secret", os.environ.get("CF_ACCESS_CLIENT_SECRET", ""))
    # Cloudflare's bot protection tends to reject Python's default user agent.
    req.add_header("User-Agent", "recipebook-cli/1.0")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{e.code} {e.reason}: {e.read().decode(errors='replace')}")
    return json.loads(raw) if raw else None


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
    elif cmd == "delete":
        call("DELETE", f"/api/recipes/{args[0]}")
        print(f"Deleted #{args[0]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
