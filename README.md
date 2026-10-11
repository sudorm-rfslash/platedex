# Platedex

> [!WARNING]
> **Under heavy development. Not ready for use.** Things break, the database may change without a migration path, and there are no releases yet. Don't use it for data you want to keep.

Self-hosted license plate log for a group of friends. Upload a phone photo of a US plate. Platedex reads the plate, pulls the GPS location and time from the photo, and links every sighting of that plate across dates, places and people.

## Quick start

Needs Docker with Compose and an `amd64` host. No GPU needed.

1. Download the compose file:
   ```sh
   mkdir platedex && cd platedex
   curl -fsSLO https://raw.githubusercontent.com/sudorm-rfslash/platedex/main/docker-compose.yml
   ```
2. In `docker-compose.yml`, replace the `PUBLIC_URL` and `SECRET_KEY` placeholders. Generate the key with `openssl rand -hex 32`.
3. Start it:
   ```sh
   docker compose up -d
   ```
4. Open `PUBLIC_URL` and create an account. The first account is the admin.

**Update:**
```sh
docker compose pull && docker compose up -d
```

## AI reader (optional)

OCR runs on the CPU and handles most plates. For a second opinion on blurry or unsure plates, point Platedex at an [Ollama](https://ollama.com) server with a GPU. Without one, Platedex runs OCR only.

**Already run Ollama?** Set `OLLAMA_URL` in `docker-compose.yml` (for example `http://192.168.1.20:11434`) and run `docker compose up -d`.

**Add Ollama to this stack** (NVIDIA GPU with about 8 GB of VRAM and `nvidia-container-toolkit`):

1. Add this service under `services:` in `docker-compose.yml`, and `ollama-data:` under `volumes:`:
   ```yaml
     ollama:
       image: ollama/ollama
       container_name: ollama
       restart: unless-stopped
       volumes:
         - ollama-data:/root/.ollama
       deploy:
         resources:
           reservations:
             devices:
               - driver: nvidia
                 count: 1
                 capabilities: [gpu]
   ```
2. Set `OLLAMA_URL: http://ollama:11434`.
3. Run `docker compose up -d`.

Platedex downloads the model (`qwen3-vl:8b`, about 6 GB) into Ollama on first start. Progress shows in **More → Admin**.

## Features

- **Reads plates automatically.** A detector and OCR read the plate on the CPU. An optional local AI model double-checks when OCR is unsure.
- **Location and time from the photo.** Photos without GPS ask you to drop a pin.
- **One shared pool.** Every sighting of a plate, from anyone, lands on one plate page with a map.
- **Review queue** for unsure readings and photos with no readable plate.
- **Installable phone app** with a camera mode, Android share target and iOS Shortcut.
- **Fully self-hosted.** One container, SQLite, no cloud services. Sign in with passwords, Pocket ID (OIDC), or both.

## Requirements

| | |
|---|---|
| **Docker** | Docker Engine with Compose v2, `linux/amd64` |
| **Disk** | A few GB for the image, plus your photos |
| **HTTPS** | A reverse proxy with TLS. Phones block the camera and location on plain HTTP. |
| **AI reader (optional)** | A separate Ollama server, ideally with an NVIDIA GPU (8 GB VRAM). See [AI reader](#ai-reader-optional). |

## Configuration

Add variables under `environment:` in `docker-compose.yml`, then run `docker compose up -d`. A plain `docker compose restart` does not re-read the file. Empty values count as unset.

**Lockable** variables can also be changed in **More → Admin**. Setting one locks it: the panel shows it read-only. Remove the variable to unlock it; the last value is kept. Besides the required `PUBLIC_URL` and `SECRET_KEY`, the example `docker-compose.yml` sets `LOCAL_LOGIN_ENABLED`, `OCR_THRESHOLD`, `VLM_MODE` and `MAX_UPLOAD_MB`; delete those lines to manage them in the panel.

### Required

| Variable | Default | Description |
|---|---|---|
| `PUBLIC_URL` | `http://localhost:8080` | Address people open in the browser. Used for OIDC callbacks and secure cookies. |
| `SECRET_KEY` | `change-me` | Signs session cookies. Generate with `openssl rand -hex 32`. |

### Sign-in

| Variable | Default | Lockable | Description |
|---|---|---|---|
| `LOCAL_LOGIN_ENABLED` | `true` | ✓ | Allow username/password sign-in. |
| `OIDC_ISSUER` | — | ✓ | OIDC issuer URL (for example Pocket ID). |
| `OIDC_CLIENT_ID` | — | ✓ | OIDC client ID. |
| `OIDC_CLIENT_SECRET` | — | ✓ | OIDC client secret. Never sent to the browser. |
| `OIDC_ADMIN_GROUP` | — | ✓ | Members of this group become admins. |
| `OIDC_AUTO_CREATE` | `true` | ✓ | Create an account on first OIDC login. |
| `OIDC_LINK_BY_EMAIL` | `true` | ✓ | Link an OIDC login to an existing account with the same verified email. |
| `OIDC_BUTTON_LABEL` | `Pocket ID` | ✓ | Text on the sign-in button. |
| `SESSION_DAYS` | `30` | | How long a sign-in lasts. |

### Plate reading

| Variable | Default | Lockable | Description |
|---|---|---|---|
| `VLM_MODE` | — | ✓ | AI second opinion: `auto` (only when OCR is unsure), `always`, or `off`. Needs `OLLAMA_URL`. |
| `VLM_MODE_DEFAULT` | `auto` | | Starting value for `VLM_MODE`. Never locks. |
| `OCR_THRESHOLD` | — | ✓ | Confidence (50–99 %) below which a reading goes to Verify. |
| `OCR_THRESHOLD_DEFAULT` | `85` | | Starting value for `OCR_THRESHOLD`. Never locks. |
| `VLM_MODEL` | `qwen3-vl:8b` | | Ollama vision model. Use `qwen3-vl:4b` on out-of-memory errors. |
| `OLLAMA_URL` | — | | Ollama server for the AI reader, for example `http://ollama:11434`. Unset = OCR only. |
| `VLM_TIMEOUT` | `120` | | Seconds to wait for one AI reading. |

### Uploads and import

| Variable | Default | Lockable | Description |
|---|---|---|---|
| `MAX_UPLOAD_MB` | `25` | ✓ | Largest accepted photo (1–500 MB). |
| `IMPORT_DIR` | — | | Watch folder inside the container (for example `/import`). Uncomment its volume in `docker-compose.yml`. |
| `IMPORT_USER` | — | | Username that watch-folder photos are credited to. |
| `SHORTCUT_URL` | — | ✓ | iCloud link to the iOS Shortcut. See [iOS Shortcut](#ios-shortcut). |

### Map

| Variable | Default | Lockable | Description |
|---|---|---|---|
| `MAP_STYLE_LIGHT` | OpenFreeMap Positron | ✓ | MapLibre style URL for light mode. |
| `MAP_STYLE_DARK` | OpenFreeMap Dark | ✓ | MapLibre style URL for dark mode. |

### Advanced

Rarely needed. The image already sets the paths.

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `/data` | Database, photos and the AI model. |
| `DATABASE_URL` | SQLite in `DATA_DIR` | SQLAlchemy URL. Only SQLite is tested. |
| `OCR_DETECTOR_MODEL` | `yolo-v9-s-608-license-plate-end2end` | Plate detector model. |
| `OCR_MODEL` | `cct-s-v2-global-model` | fast-plate-ocr model. |
| `OCR_DETECTOR_CONF` | `0.3` | Minimum detector confidence for a plate box. |

## Pocket ID (OIDC)

1. In Pocket ID, create an OIDC client with callback URL `<PUBLIC_URL>/api/auth/oidc/callback`.
2. In Platedex, open **More → Admin → Sign-in**.
3. Enter the issuer, client ID and secret. Tap **Test**, then **Save**. No restart needed.

Or set the `OIDC_*` variables in `docker-compose.yml` instead.

- New users get an account on first login. Control who gets in with Pocket ID's allowed groups.
- Existing users link Pocket ID in **More → Linked accounts**.
- Once your own account is linked, you can turn off password sign-in in **More → Admin**.

## Getting photos in

Phone browsers strip GPS from photos picked from the photo library. Platedex checks each file and asks for a pin when GPS is missing. These routes keep it:

| Route | GPS kept? |
|---|---|
| **Camera mode** in the app | Yes |
| **iOS Shortcut** (below) | Yes |
| Files app (iPhone: Browse, Android: Files) | Yes |
| Desktop browser, original file | Yes |
| **Watch folder** fed by PhotoSync, Syncthing or Nextcloud | Yes |
| **Android share sheet** after "Install app" | Usually |
| Photos sent through iMessage, WhatsApp or Signal | Usually no |

Test your own phone once: upload the same photo through each route and look for the "No location" chip.

### iOS Shortcut

Adds **Platedex** to the iPhone share sheet and uploads originals, so GPS is kept. An admin publishes one Shortcut as an iCloud link. Each person connects it to their own account with a setup code, so no token is in the link.

**Admin, once (on a Mac):**

1. Build and sign the Shortcut from a clone of this repo:
   ```sh
   cd backend && uv run platedex build-shortcut --out Platedex-unsigned.shortcut
   shortcuts sign --mode anyone -i Platedex-unsigned.shortcut -o Platedex.shortcut
   ```
2. `open Platedex.shortcut` → **Add Shortcut**. Leave the setup code empty.
3. In Shortcuts, right-click **Platedex** → **Share** → **Copy iCloud Link**.
4. In Platedex, paste it in **More → Admin → iPhone Shortcut** → **Save link**.

<details>
<summary>No Mac? Build it on an iPhone.</summary>

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
7. **Share** → **Copy iCloud Link**, then paste it in **More → Admin** as above.

Sharing clears the setup code field, so your own code never goes into the link.

</details>

**Everyone (iPhone, iPad or Mac):**

1. Open **More → API tokens → Set up iPhone Shortcut**. This copies your setup code.
2. Add the Shortcut and paste the code when asked.

Revoke the token in **API tokens** to disconnect that phone.

## Usage

### Search

| Query | Finds |
|---|---|
| `7AB*` | Plates starting with 7AB |
| `7A?12` | `?` matches one unknown character |
| `~LUVU2` | Look-alikes (LUVV2, 1UVU2) and one or two typos |
| `grateful` | Words in meaning, notes or tags |

### Review

- **Verify:** the readers disagree or aren't confident. Confirm or fix the reading.
- **Identify:** no readable plate. Draw a box, type the plate (`?` for unreadable characters), mark "no plate", or keep it unidentified.

## Troubleshooting

**Locked out after turning off passwords:**

1. Set `LOCAL_LOGIN_ENABLED: "true"` under `environment:` in `docker-compose.yml`.
2. Run `docker compose up -d` and sign in with your password.
3. Delete the line if you want to manage it in the panel again. Password sign-in stays on.

**Forgot a password:**
```sh
docker compose exec platedex platedex reset-password NAME
```

**AI reader out of memory:** add `VLM_MODEL: qwen3-vl:4b` under `environment:`, then `docker compose up -d`.

**AI reader not working:** check **More → Admin**. "No Ollama set up" means `OLLAMA_URL` is empty. "Not reachable" means the URL is wrong or Ollama is down.

**Camera or location doesn't work on phones:** `PUBLIC_URL` must be HTTPS.

## Backup and admin commands

Back up the whole `platedex-data` volume. Photos are plain files.

```sh
docker compose exec platedex platedex backup              # consistent DB copy into /data/backups
docker compose exec platedex platedex create-admin NAME   # new admin account
docker compose exec platedex platedex reset-password NAME
docker compose exec platedex platedex seed-demo           # demo data, users alex/maya/jordan, password platedex-demo
```

## How it works

The Platedex container runs two processes under `supervisord`. The AI reader is an optional, separate Ollama server:

| Process | Job | Runs on |
|---|---|---|
| `api` | FastAPI and the SvelteKit web app, port 8080 | CPU |
| `worker` | Plate detection (YOLOv9) and OCR (fast-plate-ocr), about 0.1–0.3 s per photo | CPU |
| Ollama (optional, separate) | AI second opinion (`qwen3-vl:8b`) for blurry or unsure plates | NVIDIA GPU |

All data lives in `/data`: `platedex.db` (SQLite) and `photos/`.

**Reading a photo:**

1. Find up to 4 plates.
2. Read 4–5 cleaned-up versions of each plate and combine them character by character.
3. If OCR is unsure, a character is a look-alike (O/0, I/1, B/8), or the photo is blurry, the AI reader checks the plate and reads the state.
4. Confident and in agreement → saved. Unsure → **Verify**. Nothing readable → **Identify**.
5. Same plate within 5 minutes and about 160 m → one sighting.

## Development

```sh
# backend (API on :8080)
cd backend && uv sync && uv run pytest
DATA_DIR=./data uv run platedex migrate && DATA_DIR=./data uv run platedex seed-demo
DATA_DIR=./data VLM_MODE_DEFAULT=off uv run uvicorn platedex.main:app --port 8080 &
DATA_DIR=./data uv run platedex worker &

# frontend (proxies /api to :8080)
cd frontend && npm install && npm run dev
```

- Build the image locally: `docker build -t platedex .`
- Place names: `platedex prepare-geo cities5000.zip` (the Docker build does this).
- UI design prototype: `design/`.

## License and credits

[MIT](LICENSE).

Platedex builds on these projects, which keep their own licenses:

- **Plate reading:** [fast-alpr](https://github.com/ankandrew/fast-alpr), [fast-plate-ocr](https://github.com/ankandrew/fast-plate-ocr), [open-image-models](https://github.com/ankandrew/open-image-models) (MIT). Model weights are downloaded into the Docker image at build time and are not stored in this repository.
- **AI reader (optional):** [Ollama](https://ollama.com) (MIT) running [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) (Apache-2.0). Neither is included in the Platedex image.
- **Place names:** [GeoNames](https://www.geonames.org), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **Maps:** [MapLibre GL JS](https://maplibre.org) (BSD-3-Clause), tiles from [OpenFreeMap](https://openfreemap.org). Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL).
- **Time zones:** [timezonefinder](https://github.com/jannikmi/timezonefinder) (MIT), data from OpenStreetMap (ODbL).
