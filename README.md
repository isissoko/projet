# SIGAPS

Plateforme web de gestion, de validation et d'archivage des productions académiques (mémoires et
thèses) d'un établissement d'enseignement supérieur au Mali.

Pile : Python 3.12, Django 5.2 LTS, PostgreSQL 17, Tailwind CSS v4 (binaire autonome, sans
Node.js), templates Django.

## État d'avancement

| Phase | Contenu | État |
|---|---|---|
| 0 | Socle : settings, PostgreSQL, Tailwind, utilisateur personnalisé, tests | ✅ terminée |
| 1 | Comptes et référentiel | à venir |
| 2 → 10 | Dépôt, évaluation, archivage, recherche, journal, statistiques, import, annotations, durcissement | à venir |

Le détail des décisions se trouve dans [docs/JOURNAL.md](docs/JOURNAL.md) ; le cahier des charges
dans [CLAUDE.md](CLAUDE.md).

## Prérequis

- Python 3.12 ou plus récent
- Docker et Docker Compose (pour PostgreSQL)
- `curl` (téléchargement du binaire Tailwind)

## Installation

```bash
make installer              # crée .venv et installe requirements/dev.txt
cp .env.example .env        # puis renseigner SECRET_KEY
make db                     # démarre PostgreSQL (port 5433 sur la machine)
make migrer                 # applique les migrations
make css                    # télécharge Tailwind v4 (une fois) et compile static/css/sigaps.css
.venv/bin/python manage.py createsuperuser   # connexion par adresse e-mail
make serveur                # http://127.0.0.1:8001
```

Pendant le développement de l'interface, `make css-watch` recompile le CSS à chaque modification.

> Les ports 5432 et 8000 étant souvent occupés, PostgreSQL est exposé sur **5433** et le serveur
> de développement sur **8001**. Adapter `DATABASE_URL` dans `.env` si besoin.

## Commandes utiles

| Commande | Rôle |
|---|---|
| `make test` | lance pytest (base de test PostgreSQL créée automatiquement) |
| `make couverture` | tests + rapport de couverture |
| `make lint` | `ruff check` et vérification du formatage |
| `make format` | formate et corrige automatiquement |

## Organisation

```
config/settings/   base.py, dev.py, test.py, prod.py
comptes/           utilisateur personnalisé (connexion par e-mail)
templates/         base.html et pages
static/src/        input.css (thème Tailwind via @theme)
scripts/           tailwind.sh (téléchargement vérifié + compilation)
docs/              journal de bord et documentation
```

## Dépendances

Les versions sont fixées dans `requirements/`. Règle du projet : aucune version publiée depuis
moins de deux semaines. Avec `uv`, l'option `--exclude-newer AAAA-MM-JJ` applique cette règle aux
dépendances transitives.
