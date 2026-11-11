PY := .venv/bin/python

.PHONY: installer db css css-watch migrer serveur test couverture lint format

installer:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements/dev.txt

db:
	docker compose up -d --wait db

css:
	scripts/tailwind.sh build

css-watch:
	scripts/tailwind.sh watch

migrer:
	$(PY) manage.py migrate

serveur:
	$(PY) manage.py runserver 127.0.0.1:8001

test:
	$(PY) -m pytest

couverture:
	$(PY) -m coverage run -m pytest
	$(PY) -m coverage report

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .
