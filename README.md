# SIGAPS

Plateforme web de gestion, de validation et d'archivage des productions académiques (mémoires et
thèses) d'un établissement d'enseignement supérieur au Mali.

Pile : Python 3.12, Django 5.2 LTS, PostgreSQL 17, Tailwind CSS v4 (binaire autonome, sans
Node.js), templates Django.

## État d'avancement

| Phase | Contenu | État |
|---|---|---|
| 0 | Socle : settings, PostgreSQL, Tailwind, utilisateur personnalisé, tests | ✅ terminée |
| 1 | Comptes, rôles, authentification, référentiel | ✅ terminée |
| 2 | Dépôt : modèles, validation PDF, versions, automate, dépôt en étapes | ✅ terminée |
| 3 | Évaluation par l'encadreur, version corrigée, téléchargement contrôlé | ✅ terminée |
| 4 | Contrôle bibliothèque, cote, archivage, niveaux d'accès et embargo, retrait | ✅ terminée |
| 5 → 10 | Recherche, journal, statistiques, import, annotations, durcissement | à venir |

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
.venv/bin/python manage.py creer_admin       # premier administrateur (interactif)
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

## Rôles et accès

Les rôles sont des groupes Django créés par migration : `ETUDIANT`, `ENSEIGNANT`,
`BIBLIOTHECAIRE`, `ADMINISTRATEUR`. Un compte peut en cumuler plusieurs.

| Espace | URL | Rôles |
|---|---|---|
| Connexion, mot de passe oublié | `/comptes/connexion/`, `/comptes/mot-de-passe-oublie/` | tous |
| Mes dépôts, dépôt en 5 étapes | `/depots/` | Étudiant |
| Détail d'un dépôt | `/depots/<id>/` | auteurs, encadrants, bibliothécaires, administrateurs (sinon 404) |
| Travaux à évaluer, écran d'évaluation | `/evaluation/` | Enseignant encadrant (sinon 404) |
| Version corrigée | `/depots/<id>/version-corrigee/` | Auteur principal |
| Ouvrir un PDF | `/depots/<id>/versions/<n>/telecharger/` | selon `acces.peut_telecharger` (visiteurs compris pour le libre accès) |
| À contrôler, écran de contrôle | `/bibliotheque/a-controler/`, `/bibliotheque/travaux/<id>/` | Bibliothécaire |
| Catalogue (archivés et retirés) | `/bibliotheque/catalogue/` | Bibliothécaire |
| Gestion des comptes | `/comptes/gestion/` | Administrateur |
| Référentiel | `/referentiel/` | Bibliothécaire, Administrateur |
| Admin Django (dépannage) | `/admin/` | superutilisateur |

- Connexion par adresse e-mail ; blocage de 30 minutes après 5 échecs pour un même couple
  (e-mail, adresse IP) grâce à django-axes. Pour débloquer : `manage.py axes_reset`.
- Un compte créé par l'administrateur n'a pas de mot de passe : la personne reçoit un lien
  (valable 3 jours) pour le choisir. En développement, les e-mails s'affichent dans la console.
- Un administrateur ne peut ni retirer son propre rôle Administrateur ni désactiver son compte.
- Un élément du référentiel déjà utilisé est désactivé au lieu d'être supprimé.

## Dépôt d'un travail

- **Fichier** : PDF uniquement, 50 Mo au maximum. Le contrôle porte sur la taille, la signature
  `%PDF-` et l'ouverture par pypdf ; l'extension ne suffit pas. Les PDF protégés par mot de
  passe sont refusés. L'empreinte SHA-256 est calculée par blocs de 64 Ko.
- **Stockage** : les fichiers sont rangés dans `prive/versions/<uuid>.pdf` (hors MEDIA public,
  sans URL directe). Chaque envoi crée une nouvelle version ; une version n'est jamais supprimée.
- **Soumission** : il faut une version, les métadonnées (titre, résumé, langue, filière, année,
  domaine, niveau pour un mémoire), au moins un mot-clé, un directeur et un auteur principal.
  La date de soutenance et la mention sont facultatives à ce stade.
- **Automate** : la table complète des transitions est dans `productions/services.py`
  (`TRANSITIONS`). Une transition non prévue renvoie une page 409.
- **Évaluation** : seul l'avis du directeur change le statut (favorable → validé, corrections
  demandées → à corriger, défavorable → rejeté, définitif). L'avis d'un co-directeur est
  consultatif. Un motif est obligatoire pour demander des corrections ou rejeter. Chaque
  encadrant donne au plus un avis par version ; les avis ne sont jamais modifiés ni supprimés.
- **Version corrigée** : un nouveau PDF obligatoire, accompagné d'une note facultative ; le
  travail repart chez le directeur. Les versions précédentes restent consultables.
- **Téléchargement** : uniquement par la vue contrôlée (`FileResponse`, ou `X-Accel-Redirect`
  si `X_ACCEL_REDIRECT=True`). Pour un travail non archivé, seuls ses auteurs, ses encadrants,
  les bibliothécaires et les administrateurs y ont accès.
- **Suppression** : seul l'auteur principal peut supprimer un brouillon, avec ses versions et
  leurs fichiers ; c'est impossible dès que le travail a été soumis.

## Contrôle, archivage et accès

- **Contrôle** : un travail validé par son directeur apparaît dans « À contrôler ». Le
  bibliothécaire peut corriger les métadonnées, puis soit **archiver**, soit **demander des
  corrections** (motif obligatoire ; l'étudiant dépose une version corrigée, et le travail
  revient dans « À contrôler »). Chaque décision crée une `VerificationDocumentaire`, jamais
  supprimée. Un bibliothécaire ne traite pas un travail dont il est l'auteur.
- **Cote** : attribuée à l'archivage, au format `MEM-2026-0042` ou `THE-2026-0003`. L'année est
  celle de la **soutenance** (la date de soutenance est donc exigée pour archiver). Le numéro
  vient de `CompteurCote(code_type, annee)`, verrouillé par `select_for_update` ; les
  productions existantes ne sont jamais comptées. La cote ne change plus ensuite.
- **Accès au PDF d'un travail archivé** (`productions/acces.py`) :

  | Situation | Qui peut ouvrir le PDF |
  |---|---|
  | Embargo actif (fin d'embargo après aujourd'hui) | auteurs, encadrants, bibliothécaires, administrateurs |
  | LIBRE | tout le monde, visiteurs compris |
  | RESTREINT | utilisateurs connectés (un visiteur est invité à se connecter) |
  | CONFIDENTIEL | auteurs, encadrants, bibliothécaires, administrateurs |

  L'embargo est une date, réévaluée à chaque requête (heure de Bamako) : il se lève tout seul.
  Le public n'accède qu'à la version archivée ; les versions antérieures restent réservées aux
  proches. La fiche indique la raison quand le PDF n'est pas accessible.
- **Retrait** : depuis le catalogue, avec un motif obligatoire ; il est définitif. Un travail
  retiré n'est plus visible que par ses proches et la bibliothèque (404 pour les autres) ; il
  garde sa cote.

## Organisation

```
config/settings/   base.py, dev.py, test.py, prod.py
comptes/           utilisateur, rôles, profils, authentification, gestion des comptes
referentiel/       établissements, départements, filières, années, domaines, mots-clés
productions/       modèles, validators.py (PDF), services.py (automate), acces.py (droits)
bibliotheque/      vues de la bibliothèque : contrôle, archivage, catalogue, retrait
templates/         base.html, pages, composants/ (champ, bouton, tableau, pagination…)
static/src/        input.css (thème Tailwind via @theme)
scripts/           tailwind.sh (téléchargement vérifié + compilation)
docs/              journal de bord et documentation
```

## Dépendances

Les versions sont fixées dans `requirements/`. Règle du projet : aucune version publiée depuis
moins de deux semaines. Avec `uv`, l'option `--exclude-newer AAAA-MM-JJ` applique cette règle aux
dépendances transitives.
