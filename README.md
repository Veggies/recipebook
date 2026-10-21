# Recipe Book

A self-hosted recipe book for TrueNAS. Share a recipe link from your phone and it gets scraped
into a consistent format: ingredients grouped by component (cake / frosting), and every step
states the amount of each ingredient it uses.

- Mobile-first, iOS-styled, works as a Home Screen app; two-column layout on desktop
- Tap ingredients to check them off, tap a step to track your place; the screen stays awake
- Plain-text editor that's comfortable on a phone
- JSON API + `scripts/rb.py` so Claude Code can add and clean up recipes

## 1. Publish the image (once)

Pushing to `main` runs the tests and publishes `ghcr.io/<you>/recipebook:latest`
(see `.github/workflows/docker.yml`).

After the first run, make the image public so TrueNAS can pull it without credentials:
GitHub → your profile → **Packages** → `recipebook` → **Package settings** → **Change visibility → Public**.
The image holds code only; your recipes live on the NAS. (Or keep it private and add a
GHCR registry credential in TrueNAS with a `read:packages` token.)

## 2. Install on TrueNAS SCALE

1. Create a dataset, e.g. `tank/apps/recipebook`, and give the `apps` user (568) ownership of it.
2. **Apps → Discover Apps → ⋮ → Install via YAML** and paste `docker-compose.yml`, filling in:
   - `OWNER` → your GitHub username
   - the dataset path
   - `APP_PASSWORD` → your sign-in password
   - `API_TOKEN` → a long random string (`openssl rand -hex 32`)
3. Browse to `http://<nas-ip>:8420`.

**Updates:** the app tracks `:latest`. When a new image is published, TrueNAS should flag the
app as having an update; click **Update** (it re-pulls the image). If your TrueNAS version
doesn't show the badge, **Edit → Save** with "pull image" redeploys with the newest image.
Recipes and sessions are on the dataset, so updates never touch them.

## 3. Expose it through Cloudflare

Use a **Cloudflare Tunnel** (no open ports on your router):

1. Cloudflare dashboard → **Zero Trust → Networks → Tunnels → Create tunnel**, and copy its token.
2. Install the **cloudflared** app from the TrueNAS catalog using that token.
3. In the tunnel, add a public hostname, e.g. `recipes.yourdomain.com` → `http://<nas-ip>:8420`.

The app has its own password, so this is enough. If Cloudflare's **Bot Fight Mode** is on, it may
block the iOS Shortcut's API call; if so, add a WAF skip rule for the path `/api/`.

## 4. Add recipes from iPhone

Open the site in Safari, sign in, then **Share → Add to Home Screen**.

**Share Sheet shortcut.** In the Shortcuts app, create a new shortcut:

1. Turn on **Show in Share Sheet** (shortcut details ⓘ), set to receive **URLs** and **Safari web pages**.
2. Add a **Text** action: `https://recipes.yourdomain.com/add?url=` then insert **Shortcut Input**.
3. Add **Open URLs** with that Text.

Name it "Add to Recipe Book". From any recipe page, choose **Share → Add to Recipe Book**. It
opens the app, imports the recipe and shows it. (It uses your Safari sign-in, so sign in once in
Safari itself, not only in the Home Screen app.)

*Background variant (no app switch):* use **Get Contents of URL** instead: method **POST**,
URL `https://recipes.yourdomain.com/api/import`, header `Authorization: Bearer <API_TOKEN>`,
JSON body `url` = Shortcut Input, then **Show Notification**.

## 5. Use Claude Code to manage recipes

Create `.env` in this repo (it's gitignored):

```sh
RECIPEBOOK_URL=https://recipes.yourdomain.com
RECIPEBOOK_TOKEN=<API_TOKEN>
```

Then ask Claude things like "clean up the pending recipes", "add my grandma's lasagna:
…", or "tag everything vegetarian". The house rules Claude follows are in `CLAUDE.md`.

Imported recipes are marked **Needs review**. The automatic import keeps whatever ingredient
groups the site provides and writes amounts into the steps, but it can't split a flat ingredient
list into components or handle "half the butter"; that's what the Claude cleanup pass is for.

## Development

See `CLAUDE.md` for running the tests (Python 3.12, via Docker) and running locally.
