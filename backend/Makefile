PY=python
export PYTHONPATH:=..
ALEMBIC=alembic -c alembic.ini

.PHONY: help
help:
	@echo "Targets: install, db-upgrade, db-revise, db-seed, db-reset, db-test, run, run-debug"

.PHONY: install
install:
	$(PY) -m pip install -r requirements.txt

.PHONY: db-upgrade
db-upgrade:
	$(PY) -m db.auto_align
	$(ALEMBIC) upgrade head

.PHONY: db-revise
db-revise:
	@if [ -z "$(m)" ]; then echo "Usage: make db-revise m=\"message\""; exit 1; fi
	$(ALEMBIC) revision --autogenerate -m "$(m)"

.PHONY: db-seed
db-seed: db-upgrade
	$(PY) -m db.seed

.PHONY: db-reset
db-reset:
	rm -f var/data/app.db var/data/app.db-wal var/data/app.db-shm || true
	$(ALEMBIC) upgrade head
	$(PY) -m db.seed

.PHONY: db-test
db-test:
	$(PY) -m db.auto_align
	$(ALEMBIC) upgrade head
	$(PY) -m db.test_db

.PHONY: run
run:
	$(PY) app.py

.PHONY: run-debug
run-debug:
	ENABLE_DB_DEBUG_ROUTES=true $(PY) app.py
