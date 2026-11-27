# Music Recommendation

A music recommendation class project with a Next.js frontend, async FastAPI catalog API, Supabase catalog migrations, and an independent local Music4All-Onion recommendation prototype.

## Full Music4All training on Kaggle

**Train now without original audio:** the notebook defaults to `configs/onion.json`, using Onion genre IDs and interaction counts with an explicit non-temporal hash split. No MP3, lyrics or original metadata is required. Add timestamps and select temporal splitting for a separate time-based experiment. The later full-data track (`configs/full.json`) still verifies the complete original Music4All catalog, metadata, 30-second excerpts and lyrics.

- [Download/access, full-data requirements, inventory gate, private storage and Drive](docs/MUSIC4ALL_DATASET_SETUP.md)
- [Kaggle setup: what to upload, run each stage, save outputs and run inference](docs/KAGGLE_TRAINING.md)
- [Importable Kaggle notebook](recommender/notebooks/music4all_kaggle.ipynb)
- [Full-catalog configuration](recommender/training/configs/full.json)
- [Train-now Onion configuration](recommender/training/configs/onion.json)
- [Team handoff: remaining frontend/backend/training work and what to commit](docs/TEAM_NEXT_STEPS.md)

```bash
uv sync --project recommender/training --dev --locked
python scripts/package_kaggle_code.py
# Upload artifacts/kaggle/training-code.zip as a private Kaggle input Dataset.
# Import the notebook, attach Onion counts + genre and this code Dataset,
# leave PROFILE='onion', edit input paths, then prepare → fit → evaluate.
```

Training exports ALS + genre/popularity hybrid artifacts and an offline prediction CLI. An optional separate multi-label genre classifier uses audio features. Full Kaggle execution still requires your original dataset access and a Kaggle session; it has not been run here. The new ALS artifacts do not automatically replace the SQLite Item-kNN model used by `/research`.

## Music4All first working prototype

See [the full local walkthrough](docs/MUSIC4ALL_LOCAL_DEMO.md). This mode does not use Supabase, credentials or cloud services. It supports research catalog search and hybrid recommendations; the downloaded dataset has no song names or playable audio.

```bash
# From the repository root, using the downloaded/audited dataset
uv run --project recommender/eda python recommender/eda/prepare_research_demo.py
uv run --project backend uvicorn app.research_demo:app --host 127.0.0.1 --port 8001

# In another terminal
cd frontend
npm run dev
# Open http://localhost:3000/research
```

## Structure

```text
frontend/              Next.js app router frontend
backend/               FastAPI backend
supabase/migrations/   SQL migrations
recommender/           Future recommendation experiments and serving code
docs/                  Project notes and handoff documents
```

## Local Setup

### Backend

```bash
cd backend
uv sync --dev
uv run uvicorn app.main:app --reload
```

The backend serves `GET /health` on `http://localhost:8000/health`.
The backend automatically reads `backend/.env` using a path relative to its own source file, so the terminal may be started from the repository root or from `backend/`; running `source .env` is not required. Operating-system environment variables override values from that file. Copy `backend/.env.example` when setting up a new checkout, and never commit `.env` files.

Use `/health` as the liveness check. Catalog requests return a generic `503` when the Supabase URL or publishable key is missing; no credential is included in the response.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The frontend expects `NEXT_PUBLIC_API_BASE_URL` to point at the backend, for example `http://localhost:8000`.

### Backend catalog local gate

Run these commands from `backend/`:

```bash
# Unit tests only (does not require Docker or Supabase)
uv run pytest -m "not integration and not research_integration"

# Integration tests; provide local Supabase values explicitly, never production values
SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_PUBLISHABLE_KEY="<local-anon-key>" \
  uv run pytest -m integration

# Full local gate (integration test skips when local Supabase is unavailable)
uv run pytest
uv run ruff check .
uv run ruff format --check .
python -m compileall app tests
git diff --check
```

The integration test does not start Supabase, apply migrations, or seed data. Prepare the local instance separately with `supabase start` and `supabase db reset`; the test only connects to loopback and skips clearly when the local API is unavailable or credentials are not supplied.

## Environment

Commit only `.env.example` files. Do not commit real `.env`, `.env.local`, service-role keys, database passwords, provider tokens, or object storage credentials.

## Current Scope

The Supabase catalog and player remain separate from the Music4All research demo. The demo adds an Item-kNN/content/popularity baseline on a bounded local subset. Authentication, production recommendation training, automatic provider ingestion and deployment remain future work. No service-role credentials are used in the browser.
