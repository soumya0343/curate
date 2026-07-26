# Python 3.13-slim, not the plan's python:3.11-slim: the actual dev environment
# runs 3.13.7 (see .claude/run_log.md, 2026-07-26 "Python 3.13.7, not 3.11" —
# the plan's constraint is now recorded as "Python 3.11+", not pinned to 3.11),
# and every pinned dependency in requirements.txt supports it. Building the
# deploy image on a different minor version than the one the code was written
# and tested against would be the wrong kind of surprise to find in prod.
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# scripts/ is deliberately NOT copied into this image. Verified by reading the
# code rather than trusting the plan:
#   - app/services/scoring.py:11 imports `variant_key` from `app.core.text`,
#     not from scripts/ (the function moved; see app/core/text.py:1-9, which
#     says explicitly it lives in app/core so the dependency direction is
#     app -> nothing, offline pipeline -> app).
#   - `grep -rn "scripts" backend/app/` turns up exactly one hit, a docstring
#     comment in app/core/text.py:9 — no actual import statement anywhere
#     under app/.
#   - The only real importers of scripts/ modules are the test suite:
#     backend/tests/test_verifiers.py:1 imports scripts.verify_attributes,
#     backend/tests/test_profile.py:1 imports scripts.profile_dataset. Both
#     are offline/dev-time checks, not something the running service needs,
#     and tests/ is excluded from this image by .dockerignore anyway.
# scripts/verify_attributes.py and scripts/profile_dataset.py matter for
# *building* backend/data/catalogue.jsonl.gz and embeddings.npy offline; once
# those artifacts exist, the deployed app only reads them (app/catalogue/index.py),
# it never re-runs verification at request time.
#
COPY data ./data

# `data/` also contains the ~640 MB source CSV
# (backend/data/amz_in_total_products_data_processed.csv, see `du -sh` output
# in docs/deployment.md) that a naive `COPY data ./data` would happily bake
# into the image. backend/.dockerignore excludes it (and other offline-only
# artifacts) so this COPY only ships catalogue.jsonl.gz, embeddings.npy, and
# embeddings.manifest.json — the three files app/catalogue/index.py actually
# reads at startup. See docs/deployment.md for the full trap writeup.

# Single worker: sessions are a process-local in-memory TTL dict
# (app/services/sessions.py) — with more than one worker, a session created on
# worker A would be missing on worker B. This is load-bearing, not a default.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
