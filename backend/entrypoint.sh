#!/bin/sh
# Container entrypoint: align DB, run migrations, optionally seed, then start app.
set -e

# Align and migrate DB inside container. Uses /app/alembic.ini
python -m db.auto_align || true
alembic -c /app/alembic.ini upgrade head || true

# Ensure seed directory exists (packaged location) and scraper output dir
mkdir -p /app/db/seed_data
mkdir -p /app/var/seed_data

# Optionally scrape latest events and posters from VIS/AMIV
if [ "$AUTO_SCRAPE_EVENTS" = "true" ]; then
  echo "[entrypoint] Scraping VIS + AMIV events (and posters) ..."
  # These scripts write JSON into /app/db/seed_data and posters into /app/var/uploads
  # Continue on failure to avoid blocking the app startup
  SCRAPER_OUT_DIR=/app/var/seed_data python scripts/old/scrape_vis_events.py || true
  SCRAPER_OUT_DIR=/app/var/seed_data python scripts/old/scrape_amiv_events.py || true
fi

# Seed from JSON
if [ "$AUTO_SEED" = "true" ]; then
  echo "[entrypoint] Seeding DB from JSON files ..."
  python -m db.seed || true
fi

exec python app.py
