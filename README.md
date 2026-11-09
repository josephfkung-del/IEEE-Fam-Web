# FamilIEEE — UCLA IEEE Event Review App

[Live app](https://ieee-fam-web.vercel.app/) · FastAPI · PostgreSQL · Vercel

FamilIEEE lets UCLA IEEE mentorship families submit event proof, track attendance, and earn points after admin review.

## Features

- Event and quest submissions with compressed photo proof, location, date, attendance, and rule confirmations.
- Password-protected admin review with approval, denial, point awards, reviewer notes, and deletion.
- Public event feed and leaderboard based on approved point awards.
- Submission validation, retry deduplication, a transactional daily event limit, and resilient form error handling.
- Admin attendee corrections. Changing attendance preserves the existing point award; points are reviewed separately.

## Repository layout and production status

The main branch includes the submission reliability and attendee-editing patches used by the October 20, 2026 production release.

| Path | Purpose |
| --- | --- |
| `api/`, `main.py`, `pages.py`, `templates/`, `static/` | Earlier standalone application source |
| `deployment/` | Production patch modules, client code, tests, and release provenance |
| `.env.example` | Placeholder configuration; replace locally and never commit real secrets |

**The repository root is not the exact live production entry point.** The current production release also uses preserved `legacy_app.py`, `location_patch.py`, and `baseline_entry.py` files held in the existing Vercel deployment. Those files are not included in this repository. See [deployment/README.md](deployment/README.md) and [the release manifest](deployment/release_manifest.json) before reproducing or changing the production release. Do not deploy the repository root as a replacement for that release.

## Local development

To run the earlier standalone application:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to a local configuration file and supply the required values in your shell or environment manager. The app does not automatically load that file. Set a strong `ADMIN_PASSWORD` and a random `SESSION_SECRET` before starting:

```bash
uvicorn api.index:app --reload
```

Open http://127.0.0.1:8000. Production uses `DATABASE_URL` for PostgreSQL; local development can use SQLite. Optional notification settings are `RESEND_API_KEY` and `NOTIFY_EMAIL`.

## Checks

```bash
node deployment/qa_client.cjs
```

The Python release tests require the preserved production baseline files described in `deployment/README.md`. Run write-flow tests only against an isolated test database with notifications disabled.

## Access

Public visibility allows people to view and clone the source. It does not grant write access to this repository. Changes to the original repository require explicit authorization from the owner; forks and proposed pull requests do not alter the original.
