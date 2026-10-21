# Recipe Book

A self-hosted recipe book for TrueNAS. Share a recipe link from your phone and it gets scraped
into a consistent format: ingredients grouped by component (cake / frosting), and every step
states the amount of each ingredient it uses.

- Mobile-first, iOS-styled, works as a Home Screen app; two-column layout on desktop
- Tap ingredients to check them off, tap a step to track your place; the screen stays awake
- Simple form editor: add a photo from the camera roll, type ingredients naturally, sections for components
- Shopping list: pick recipes, amounts are combined, tick off what you have, share the rest to Notes
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
2. **Apps → Discover Apps → ⋮ → Install via YAML** and paste `docker-compose.yml`, filling in
   `OWNER` (your GitHub username) and the dataset path.
3. Browse to `http://<nas-ip>:8420`.

The app has no login of its own: anyone who can reach port 8420 can edit recipes. That's fine on
your LAN; from outside, Cloudflare Access is the gate (next section).

**Updates:** the app tracks `:latest`. When a new image is published, TrueNAS should flag the
app as having an update; click **Update** (it re-pulls the image). If your TrueNAS version
doesn't show the badge, **Edit → Save** with "pull image" redeploys with the newest image.
Recipes are on the dataset, so updates never touch them.

## 3. Expose it through Cloudflare (with Access in front)

Use a **Cloudflare Tunnel** (no open ports on your router):

1. Cloudflare dashboard → **Zero Trust → Networks → Tunnels → Create tunnel**, and copy its token.
2. Install the **cloudflared** app from the TrueNAS catalog using that token.
3. In the tunnel, add a public hostname, e.g. `recipes.yourdomain.com` → `http://<nas-ip>:8420`.

Then put **Cloudflare Access** in front, since the app itself has no password:

4. **Zero Trust → Access → Applications → Add → Self-hosted** for `recipes.yourdomain.com`,
   with a policy **Allow → Emails → your address** (add a second login method/2FA under
   **Settings → Authentication** if you like). Set the session duration long, e.g. 1 month,
   so the Home Screen app doesn't make you sign in constantly.
5. For Claude Code and the background Shortcut: **Access → Service Auth → Service Tokens →
   Create**, copy the Client ID and Secret, then add a second policy to the application:
   **Action: Service Auth → Include: Service Token → that token**.

If Cloudflare's **Bot Fight Mode** is on, it can block the API calls; if so, add a WAF skip rule for `/api/`.

## 4. Add recipes from iPhone

Open the site in Safari, sign in, then **Share → Add to Home Screen**.

**Share Sheet shortcut.** In the Shortcuts app, create a new shortcut:

1. Turn on **Show in Share Sheet** (shortcut details ⓘ), set to receive **URLs** and **Safari web pages**.
2. Add a **Text** action: `https://recipes.yourdomain.com/add?url=` then insert **Shortcut Input**.
3. Add **Open URLs** with that Text.

Name it "Add to Recipe Book". From any recipe page, choose **Share → Add to Recipe Book**. It
opens the recipe book in Safari, imports the recipe and shows it. (It uses your Cloudflare Access
sign-in in Safari, so sign in once in Safari itself, not only in the Home Screen app.)

*Background variant (no app switch):* use **Get Contents of URL** instead: method **POST**,
URL `https://recipes.yourdomain.com/api/import`, headers `CF-Access-Client-Id` and
`CF-Access-Client-Secret` set to the service token, JSON body `url` = Shortcut Input, then
**Show Notification**.

## 5. Use Claude Code to manage recipes

Create `.env` in this repo (it's gitignored):

```sh
RECIPEBOOK_URL=https://recipes.yourdomain.com
CF_ACCESS_CLIENT_ID=<service token Client ID>
CF_ACCESS_CLIENT_SECRET=<service token Client Secret>
```

Then ask Claude things like "clean up the pending recipes", "add my grandma's lasagna:
…", or "tag everything vegetarian". The house rules Claude follows are in `CLAUDE.md`.

**Code updates never touch your recipes.** They live on the NAS dataset; a new image only replaces
the app. Claude edits recipes on the NAS directly through the API, so there's nothing to copy.

**Moving recipes to a new server (one time):**

```sh
python3 scripts/rb.py export backup.json      # from wherever they are now (RECIPEBOOK_URL)
RECIPEBOOK_URL=http://<nas-ip>:8420 python3 scripts/rb.py restore backup.json
```

The export doubles as a backup. For automatic backups, add a periodic snapshot task for the
`recipebook` dataset in TrueNAS (Data Protection → Periodic Snapshot Tasks).

Imported recipes are marked **Needs review**. The automatic import keeps whatever ingredient
groups the site provides and writes amounts into the steps, but it can't split a flat ingredient
list into components or handle "half the butter"; that's what the Claude cleanup pass is for.

## Development

See `CLAUDE.md` for running the tests (Python 3.12, via Docker) and running locally.
