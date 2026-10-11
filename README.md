# Platedex

A self-hosted, installable web app for a small group of friends. You upload phone photos of US license plates. Platedex reads each plate, takes the photo's GPS location and capture time, and links every sighting of the same plate across dates, places and people. Everyone shares one pool. The design is in `design/` (Claude Design prototype).

## What runs where

One Docker container runs everything, supervised by `supervisord`:

| Process | Job | Hardware |
|---|---|---|
| `api` | FastAPI + the SvelteKit web app on port 8080 | CPU |
| `worker` | Plate detection (YOLOv9) + OCR (fast-plate-ocr), queue in SQLite | CPU, about 0.1–0.3 s per photo |
| `ollama` | AI second opinion (`qwen3-vl:8b`) for blurry or unsure plates | NVIDIA GPU |

Data lives in one volume at `/data`: `platedex.db` (SQLite), `photos/` (originals + thumbnails + plate crops) and `ollama/` (the model).

## Install

1. On the Docker host, install the NVIDIA driver and `nvidia-container-toolkit`. Check it works:
   `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`
2. Copy the env file and fill in `PUBLIC_URL` and `SECRET_KEY` (`openssl rand -hex 32`):
   `cp .env.example .env`
3. Build and start: `docker compose up -d --build`. The first build takes about 10 minutes. The image is about 9 GB, mostly Ollama's CUDA libraries.
4. Open `PUBLIC_URL` and create the first account. It becomes the admin.
5. On first start the worker downloads the AI model (about 6 GB). Progress shows in More → Admin. OCR works without it in the meantime.

Put it behind your reverse proxy with HTTPS. Phones only allow the camera and location on HTTPS pages.

**No GPU?** Delete the `deploy:` block in `docker-compose.yml` and set `VLM_MODE=off`. OCR still runs on the CPU.
**Already run Ollama?** Set `OLLAMA_URL=http://host:11434`. The built-in one then doesn't start.

## Pocket ID

1. In Pocket ID, create an OIDC client. Callback URL: `<PUBLIC_URL>/api/auth/oidc/callback`.
2. In Platedex: **More → Admin → Sign-in**. Enter the issuer, client ID and secret, tap **Test**, then **Save**. No restart needed.
   Or set `OIDC_ISSUER`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` as environment variables (see [Settings and environment variables](#settings-and-environment-variables)).
3. Optional: an admin group (`OIDC_ADMIN_GROUP`, e.g. `platedex_admins`) makes its members admins.

New Pocket ID users get an account on first login (auto-create, on by default). Use Pocket ID's allowed groups on the client to control who gets in. People with a password account can link Pocket ID in More → Linked accounts. Password sign-in can be turned off in More → Admin once your own account is linked to Pocket ID.

## Settings and environment variables

Most admin settings live in **More → Admin**: password sign-in, Pocket ID, the OCR threshold, the AI reader mode, the upload size limit, map styles and the iOS Shortcut link. Each one can also be set as an environment variable, in `docker-compose.yml` (`environment:`) or `.env`. The app can't tell the two apart.

- **A variable locks its setting.** The admin panel shows it read-only with the variable's name.
- **The value is saved at every start.** If you later remove the variable, the setting keeps that value and becomes editable in the panel again.
- **Empty values don't count.** `OIDC_ISSUER=` is the same as not setting it.
- **Apply changes with `docker compose up -d`.** A plain `docker compose restart` doesn't re-read `docker-compose.yml` or `.env`.
- `OCR_THRESHOLD_DEFAULT` and `VLM_MODE_DEFAULT` are only starting values and never lock. Use `OCR_THRESHOLD` and `VLM_MODE` to lock.

| Setting | Variable |
|---|---|
| Password sign-in | `LOCAL_LOGIN_ENABLED` |
| Pocket ID | `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ADMIN_GROUP`, `OIDC_AUTO_CREATE`, `OIDC_LINK_BY_EMAIL`, `OIDC_BUTTON_LABEL` |
| Plate reading | `OCR_THRESHOLD`, `VLM_MODE` |
| Uploads | `MAX_UPLOAD_MB` |
| Map | `MAP_STYLE_LIGHT`, `MAP_STYLE_DARK` |
| iOS Shortcut | `SHORTCUT_URL` |

`PUBLIC_URL`, `SECRET_KEY`, `OLLAMA_URL`, `VLM_MODEL` and `IMPORT_DIR` are environment-only.

**Locked out?** If password sign-in is off and Pocket ID isn't working, add `LOCAL_LOGIN_ENABLED: "true"` under `environment:` in `docker-compose.yml`, run `docker compose up -d`, and sign in with your password. Comment the line out again afterwards; password sign-in stays on. No password? `docker compose exec platedex platedex reset-password NAME`.

## Getting location and time off phones

Phone browsers remove GPS from photos picked from the photo library. Platedex checks every file before upload and asks for a pin or a time when one is missing. Ways to keep the location:

| Route | GPS kept? |
|---|---|
| **Camera mode** in the app (attaches the phone's location) | Yes |
| iPhone: Files app → Browse · Android: Files app | Yes |
| **iOS Shortcut** (see [iOS Shortcut](#ios-shortcut)) | Yes |
| **Android share sheet** → Platedex (after "Install app") | Usually |
| Desktop browser, original file from disk | Yes |
| Photos sent through iMessage / WhatsApp / Signal | Usually no |
| **Watch folder** (`IMPORT_DIR`): PhotoSync, Syncthing or Nextcloud drop originals there | Yes |

These are expectations, not measurements. Test your own phones once: upload the same photo through each route and look at the "No location" chip.

## iOS Shortcut

The Shortcut puts **Platedex** in the iPhone share sheet and uploads originals, so location and time are kept. iPhones only add shortcuts from iCloud links (or signed files), so an admin shares one copy as an iCloud link and pastes it into Platedex. Each person then gets their own token through a setup code; nobody's token is in the link.

**Make the link (once, as admin)**

On a Mac, from the ready-made template:

1. `cd backend && uv run platedex build-shortcut --out Platedex-unsigned.shortcut`
2. `shortcuts sign --mode anyone -i Platedex-unsigned.shortcut -o Platedex.shortcut`
3. `open Platedex.shortcut` and click **Add Shortcut**. When it asks for the setup code, leave it empty.
4. In Shortcuts, right-click **Platedex** → **Share** → **Copy iCloud Link**.
5. In Platedex: **More → Admin → iPhone Shortcut**, paste the link, **Save link**.

No Mac? Build it on an iPhone instead. In Shortcuts tap **+**, name it “Platedex”, and add:

1. **Text**, left empty. This holds the setup code.
2. **Split Text**: split the Text by **Custom** `#`.
3. **Get Item from List**: **First Item** of Split Text (the server). Then a second one: **Last Item** (the token).
4. **Repeat with Each** item in **Shortcut Input**, and inside it **Get Contents of URL**:
   - URL: *first item* + `/api/photos`. Method **POST**.
   - Header `Authorization` = `Bearer ` + *last item*.
   - Request Body **Form**: field `file` (type **File**) = **Repeat Item**, and text field `capture_mode` = `token`.
5. Tap **ⓘ**: turn on **Show in Share Sheet** and accept **Images**.
6. Tap **Setup** → **Add New Question**. Pick the Text action's text and ask “Paste your setup code from Platedex”.
7. **Share** → **Copy iCloud Link**, then paste it in More → Admin as above.

A field with an import question is cleared when the Shortcut is shared, so your own setup code never goes into the link. To change the Shortcut later, edit your copy, share a new link and save it in More → Admin.

**Add it (everyone)**

On an iPhone, iPad or Mac: **More → API tokens → Set up iPhone Shortcut**. That creates a token, copies the setup code and links to the Shortcut. Paste the code when Shortcuts asks. The button only shows on Apple devices, and only after an admin has saved the link. Revoking the token in API tokens stops that phone's Shortcut.

## How plates are read

1. Find up to 4 plates in the photo (YOLOv9 detector).
2. Make 4–5 cleaned-up versions of each plate crop (upscale, contrast, sharpen, deskew). OCR reads each one, and the readings are combined character by character into a top-3 list with per-character confidence.
3. If OCR is unsure, a character could be a look-alike (O/0, I/1, B/8…), or the photo is blurry, the AI reader looks at the crop and the whole photo. It also reads the state.
4. Routing:
   - Both readers agree and confidence is above the threshold (default 85%): saved automatically.
   - The readers disagree, or confidence is low: goes to **Review → Verify**.
   - No plate found, or nothing readable: goes to **Review → Identify**. There you can draw a box, type the plate (`?` = unreadable character), mark "no plate", or keep it as an unidentified sighting.
5. Photos taken within 5 minutes and about 160 m of each other with the same plate count as one sighting.

## Search

| Query | Finds |
|---|---|
| `7AB*` | plates starting with 7AB |
| `7A?12` | `?` is one unknown character |
| `~LUVU2` | fuzzy: look-alikes (LUVV2, 1UVU2) plus one or two typos |
| `grateful` | words in meaning, notes or tags |

## Admin commands

```sh
docker compose exec platedex platedex backup              # consistent DB copy into /data/backups
docker compose exec platedex platedex create-admin NAME   # recover access
docker compose exec platedex platedex reset-password NAME
docker compose exec platedex platedex seed-demo           # demo plates + users alex/maya/jordan (password platedex-demo)
```

Back up the whole `/data` volume. Photos are plain files.

## Development

```sh
# backend
cd backend && uv sync && uv run pytest
DATA_DIR=./data uv run platedex migrate && DATA_DIR=./data uv run platedex seed-demo
DATA_DIR=./data VLM_MODE_DEFAULT=off uv run uvicorn platedex.main:app --port 8080 &
DATA_DIR=./data uv run platedex worker &
# frontend (proxies /api to :8080)
cd frontend && npm install && npm run dev
```

Place names come from GeoNames: `platedex prepare-geo cities5000.zip` (the Docker build does this).
