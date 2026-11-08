# Changelog

Platedex follows [semantic versioning](https://semver.org). While the version is 0.x, a new minor version (0.1 → 0.2) may need you to change settings or the compose file. Those steps are listed here. Patch versions (0.1.0 → 0.1.1) never do.

## Unreleased

## 0.1.0

First release.

- **Plate reading** on the CPU (YOLOv9 detector and fast-plate-ocr), with an optional AI second opinion from your own Ollama server (`OLLAMA_URL`).
- **Location and time** from photo metadata, with a pin drop for photos that lost their GPS.
- **Home** feed of every sighting and every photo waiting in Review, with filters and sorting.
- **Plates** list with wildcard and look-alike search, CSV export, and plate pages with a map, notes, tags, edit, split, merge and delete. Uploading a photo again after deleting its plate reads it again.
- **Review** queue to verify unsure readings and identify photos without a readable plate.
- **Map** of all sightings, synced with the Plates filters.
- **Getting photos in:** upload, camera mode, Android share target, iOS Shortcut with per-person setup codes, and a watch folder (`IMPORT_DIR`). Unreadable files in the watch folder move to `.failed/`.
- **Sign-in** with passwords, Pocket ID (OIDC), or both. Invites, API tokens and an admin panel. Environment variables can lock settings.
- **Database migrations** run on every start (`platedex migrate`). From this release on, every database change ships as a migration.
