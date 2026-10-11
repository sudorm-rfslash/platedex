# Platedex

> [!WARNING]
> **Platedex is under heavy development and not ready for use.** Things will break, the database schema may change without a migration path, and there are no releases yet. Don't run it with data you want to keep.

A self-hosted, installable web app for a small group of friends. You upload phone photos of US license plates. Platedex reads each plate, takes the photo's GPS location and capture time, and links every sighting of the same plate across dates, places and people. Everyone shares one pool.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Install](#install)
- [Configuration](#configuration)
- [Sign-in with Pocket ID](#sign-in-with-pocket-id)
- [Getting photos in](#getting-photos-in)
- [Using Platedex](#using-platedex)
- [How it works](#how-it-works)
- [Maintenance](#maintenance)
- [Development](#development)
- [License and credits](#license-and-credits)

## Features

- **Automatic plate reading.** A detector finds plates, OCR reads them, and a local vision model gives a second opinion when OCR is unsure.
- **Location and time from the photo.** EXIF GPS and capture time become a sighting on the map. Photos without GPS ask for a pin.
- **One shared pool.** Every sighting of the same plate, from anyone in the group, is linked on one plate page.
- **Review queue.** Unsure readings go to Verify, and photos with no readable plate go to Identify.
- **Search** with wildcards, unknown characters and look-alike fuzzy matching.
- **Installable app (PWA)** with a camera mode, an Android share target and an iOS Shortcut.
- **Sign-in** with passwords, Pocket ID (OIDC), or both.
- **Fully self-hosted.** One container, SQLite, no cloud services. Map tiles default to OpenFreeMap.

## Requirements

- Docker with Compose
- About 15 GB of disk: a 9 GB image, a 6 GB AI model, plus your photos
- **Optional:** an NVIDIA GPU with 8 GB of VRAM and `nvidia-container-toolkit` for the AI reader. Without one, OCR still runs on the CPU.
- A reverse proxy with HTTPS. Phones only allow the camera and location on HTTPS pages.

## Install

1. **GPU only:** install the NVIDIA driver and `nvidia-container-toolkit` on the Docker host. Check that it works:
   ```sh
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```
2. Download the compose file and the env template:
   ```sh
   mkdir platedex && cd platedex
   curl -fsSLO https://raw.githubusercontent.com/sudorm-rfslash/platedex/main/docker-compose.yml
   curl -fsSL -o .env https://raw.githubusercontent.com/sudorm-rfslash/platedex/main/.env.example
   ```
3. In `.env`, set `PUBLIC_URL` and `SECRET_KEY`. Generate the key with `openssl rand -hex 32`.
4. Pull and start:
   ```sh
   docker compose up -d
   ```
   This pulls `ghcr.io/sudorm-rfslash/platedex:latest` (about 9 GB, `linux/amd64` only).
5. Open `PUBLIC_URL` and create the first account. It becomes the admin.
6. On first start the worker downloads the AI model (about 6 GB). Progress shows in **More → Admin**. OCR works in the meantime.

**No GPU?** Delete the `deploy:` block in `docker-compose.yml` and set `VLM_MODE=off`.
**Already run Ollama?** Set `OLLAMA_URL=http://host:11434`. The built-in Ollama then doesn't start.

### Updating

```sh
docker compose pull && docker compose up -d
```

`:latest` follows the `main` branch. Each build is also tagged `:sha-<commit>`, so you can pin one.

## Configuration

Set variables in `.env` or under `environment:` in `docker-compose.yml`. Apply changes with `docker compose up -d`. A plain `docker compose restart` doesn't re-read either file. Empty values count as unset.

Variables marked **Lockable** can also be changed in **More → Admin**. Setting the variable locks it there:

- The admin panel shows it read-only, with the variable's name.
- The value is saved to the database at every start. If you remove the variable later, the setting keeps that value and becomes editable again.

### Required

| Variable | Default | Description |
|---|---|---|
| `PUBLIC_URL` | `http://localhost:8080` | The address people open in the browser. Used for OIDC callbacks. Cookies are marked secure when it starts with `https://`. |
| `SECRET_KEY` | `change-me` | Signs session cookies. Generate with `openssl rand -hex 32`. |

### Sign-in

| Variable | Default | Lockable | Description |
|---|---|---|---|
| `LOCAL_LOGIN_ENABLED` | `true` | ✓ | Allow username/password sign-in. |
| `OIDC_ISSUER` | — | ✓ | Pocket ID (or other OIDC provider) issuer URL. |
| `OIDC_CLIENT_ID` | — | ✓ | OIDC client ID. |
| `OIDC_CLIENT_SECRET` | — | ✓ | OIDC client secret. Never sent to the browser. |
| `OIDC_ADMIN_GROUP` | — | ✓ | Members of this group become Platedex admins. |
| `OIDC_AUTO_CREATE` | `true` | ✓ | Create an account on first OIDC login. |
| `OIDC_LINK_BY_EMAIL` | `true` | ✓ | Link an OIDC login to an existing account with the same verified email. |
| `OIDC_BUTTON_LABEL` | `Pocket ID` | ✓ | Text on the sign-in button. |
| `SESSION_DAYS` | `30` | | How long a sign-in lasts. |

### Plate reading

| Variable | Default | Lockable | Description |
|---|---|---|---|
| `VLM_MODE` | — | ✓ | AI second opinion: `auto` (only when OCR is unsure), `always`, or `off`. |
| `VLM_MODE_DEFAULT` | `auto` | | Starting value for `VLM_MODE`. Never locks. |
| `OCR_THRESHOLD` | — | ✓ | Confidence in percent (50–99) below which a reading goes to Verify. |
| `OCR_THRESHOLD_DEFAULT` | `85` | | Starting value for `OCR_THRESHOLD`. Never locks. |
| `VLM_MODEL` | `qwen3-vl:8b` | | Ollama vision model. Use `qwen3-vl:4b` if you see out-of-memory errors. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | | Ollama server. Pointing it anywhere else disables the built-in Ollama. |
| `VLM_TIMEOUT` | `120` | | Seconds to wait for one AI reading. |

### Uploads and import

| Variable | Default | Lockable | Description |
|---|---|---|---|
| `MAX_UPLOAD_MB` | `25` | ✓ | Largest accepted photo (1–500 MB). |
| `IMPORT_DIR` | — | | Watch folder. Photos dropped here are imported. Mount it in `docker-compose.yml`. |
| `IMPORT_USER` | — | | Username the watch-folder photos are credited to. |
| `SHORTCUT_URL` | — | ✓ | iCloud link to the iOS Shortcut. See [iOS Shortcut](#ios-shortcut). |

### Map

| Variable | Default | Lockable | Description |
|---|---|---|---|
| `MAP_STYLE_LIGHT` | OpenFreeMap Positron | ✓ | MapLibre style URL for light mode. |
| `MAP_STYLE_DARK` | OpenFreeMap Dark | ✓ | MapLibre style URL for dark mode. Point both at self-hosted styles for a fully offline setup. |

### Advanced

These rarely need changing. The Docker image already sets the paths.

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `/data` (in Docker) | Database, photos and the Ollama model. |
| `DATABASE_URL` | SQLite in `DATA_DIR` | SQLAlchemy URL. Only SQLite is tested. |
| `OCR_DETECTOR_MODEL` | `yolo-v9-s-608-license-plate-end2end` | Plate detector model. |
| `OCR_MODEL` | `cct-s-v2-global-model` | fast-plate-ocr model. |
| `OCR_DETECTOR_CONF` | `0.3` | Minimum detector confidence for a plate box. |

## Sign-in with Pocket ID

1. In Pocket ID, create an OIDC client. Callback URL: `<PUBLIC_URL>/api/auth/oidc/callback`.
2. In Platedex: **More → Admin → Sign-in**. Enter the issuer, client ID and secret, tap **Test**, then **Save**. No restart needed. You can set `OIDC_*` variables instead (see [Sign-in](#sign-in)).
3. Optional: set an admin group (`OIDC_ADMIN_GROUP`, for example `platedex_admins`). Its members become admins.

New Pocket ID users get an account on first login. Use Pocket ID's allowed groups on the client to control who gets in. People with a password account can link Pocket ID in **More → Linked accounts**. Once your own account is linked, you can turn off password sign-in in **More → Admin**.

**Locked out?** If password sign-in is off and Pocket ID isn't working:

1. Add `LOCAL_LOGIN_ENABLED: "true"` under `environment:` in `docker-compose.yml`.
2. Run `docker compose up -d` and sign in with your password.
3. Comment the line out again. Password sign-in stays on.

No password? Run `docker compose exec platedex platedex reset-password NAME`.

## Getting photos in

Phone browsers remove GPS from photos picked from the photo library. Platedex checks every file before upload and asks for a pin or a time when one is missing. These routes keep the location:

| Route | GPS kept? |
|---|---|
| **Camera mode** in the app (attaches the phone's location) | Yes |
| iPhone: Files app → Browse · Android: Files app | Yes |
| **iOS Shortcut** (see below) | Yes |
| **Android share sheet** → Platedex (after "Install app") | Usually |
| Desktop browser, original file from disk | Yes |
| Photos sent through iMessage / WhatsApp / Signal | Usually no |
| **Watch folder** (`IMPORT_DIR`): PhotoSync, Syncthing or Nextcloud drop originals there | Yes |

These are expectations, not measurements. Test your own phones once: upload the same photo through each route and look for the "No location" chip.

### iOS Shortcut

The Shortcut puts **Platedex** in the iPhone share sheet and uploads originals, so location and time are kept. iPhones only add shortcuts from iCloud links (or signed files), so an admin shares one copy as an iCloud link and pastes it into Platedex. Each person then gets their own token through a setup code. Nobody's token is in the link.

**Make the link (once, as admin)**

On a Mac, from the ready-made template:

1. `cd backend && uv run platedex build-shortcut --out Platedex-unsigned.shortcut`
2. `shortcuts sign --mode anyone -i Platedex-unsigned.shortcut -o Platedex.shortcut`
3. `open Platedex.shortcut` and click **Add Shortcut**. When it asks for the setup code, leave it empty.
4. In Shortcuts, right-click **Platedex** → **Share** → **Copy iCloud Link**.
5. In Platedex: **More → Admin → iPhone Shortcut**, paste the link, **Save link**.

<details>
<summary>No Mac? Build it on an iPhone instead.</summary>

In Shortcuts tap **+**, name it “Platedex”, and add:

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

</details>

A field with an import question is cleared when the Shortcut is shared, so your own setup code never goes into the link. To change the Shortcut later, edit your copy, share a new link and save it in More → Admin.

**Add it (everyone)**

On an iPhone, iPad or Mac: **More → API tokens → Set up iPhone Shortcut**. That creates a token, copies the setup code and links to the Shortcut. Paste the code when Shortcuts asks. The button only shows on Apple devices, and only after an admin has saved the link. Revoking the token in API tokens stops that phone's Shortcut.

## Using Platedex

### Search

| Query | Finds |
|---|---|
| `7AB*` | plates starting with 7AB |
| `7A?12` | `?` is one unknown character |
| `~LUVU2` | fuzzy: look-alikes (LUVV2, 1UVU2) plus one or two typos |
| `grateful` | words in meaning, notes or tags |

### Review

- **Verify:** the readers disagree, or confidence is below the threshold. Confirm or fix the reading.
- **Identify:** no plate found, or nothing readable. Draw a box, type the plate (`?` = unreadable character), mark "no plate", or keep it as an unidentified sighting.

## How it works

One Docker container runs everything, supervised by `supervisord`:

| Process | Job | Hardware |
|---|---|---|
| `api` | FastAPI + the SvelteKit web app on port 8080 | CPU |
| `worker` | Plate detection (YOLOv9) + OCR (fast-plate-ocr), queue in SQLite | CPU, about 0.1–0.3 s per photo |
| `ollama` | AI second opinion (`qwen3-vl:8b`) for blurry or unsure plates | NVIDIA GPU |

Data lives in one volume at `/data`: `platedex.db` (SQLite), `photos/` (originals, thumbnails and plate crops) and `ollama/` (the model).

### Plate reading pipeline

1. Find up to 4 plates in the photo (YOLOv9 detector).
2. Make 4–5 cleaned-up versions of each plate crop (upscale, contrast, sharpen, deskew). OCR reads each one, and the readings are combined character by character into a top-3 list with per-character confidence.
3. If OCR is unsure, a character could be a look-alike (O/0, I/1, B/8…), or the photo is blurry, the AI reader looks at the crop and the whole photo. It also reads the state.
4. Routing:
   - Both readers agree and confidence is above the threshold: saved automatically.
   - The readers disagree, or confidence is low: goes to **Review → Verify**.
   - No plate found, or nothing readable: goes to **Review → Identify**.
5. Photos taken within 5 minutes and about 160 m of each other with the same plate count as one sighting.

## Maintenance

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

The UI design prototype is in `design/`.

## License and credits

Platedex is released under the [MIT License](LICENSE).

It builds on other people's work, which keeps its own license:

- **Plate reading:** [fast-alpr](https://github.com/ankandrew/fast-alpr), [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr) and [open-image-models](https://github.com/ankandrew/open-image-models) (MIT). The detector and OCR model weights are downloaded at runtime and are not part of this repository.
- **AI reader:** [Ollama](https://ollama.com) (MIT) running [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) (Apache-2.0), downloaded on first start.
- **Place names:** [GeoNames](https://www.geonames.org), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Downloaded at image build time.
- **Maps:** [MapLibre GL JS](https://maplibre.org) (BSD-3-Clause) with tiles from [OpenFreeMap](https://openfreemap.org). Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL).
- **Time zones:** [timezonefinder](https://github.com/jannikmi/timezonefinder) (MIT), with data derived from OpenStreetMap (ODbL).
