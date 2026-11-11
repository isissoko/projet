# Journal de bord

## Phase 0 — Socle (11 novembre 2026)

### Fait
- Projet Django 5.2.18, réglages séparés `base` / `dev` / `test` / `prod`, secrets dans `.env`
  (modèle : `.env.example`), lecture par django-environ.
- PostgreSQL 17.10 (alpine) via `docker-compose.yml`, exposé sur `127.0.0.1:5433`. Les tests
  tournent aussi sur PostgreSQL ; la configuration plein texte `french` est vérifiée par un test.
- Utilisateur personnalisé `comptes.Utilisateur` (`AUTH_USER_MODEL`) : pas de `username`,
  connexion par e-mail unique.
- Argon2 en premier hasheur (MD5 en test uniquement, pour la vitesse).
- Stockage `prive` déclaré dans `STORAGES` (sans URL publique), distinct de `MEDIA_ROOT`.
  Réglages `X_ACCEL_REDIRECT` / `X_ACCEL_PREFIXE` prêts pour la phase 5.
- Tailwind CSS v4.3.3 par le binaire autonome : `scripts/tailwind.sh` le télécharge, vérifie son
  empreinte SHA-256 et compile `static/src/input.css` → `static/css/sigaps.css`. Le
  téléchargement reprend après une coupure (connexions lentes).
- Thème `@theme` : bleu nuit, accent ocre, gris ; focus visible, lien d'évitement.
- `templates/base.html` sémantique (en-tête, navigation, messages, `main`, pied de page) et
  page d'accueil provisoire.
- ruff (règles E, W, F, I, B, UP, DJ, SIM, C4, RUF), pytest-django, factory_boy, coverage,
  `Makefile`.
- 16 tests : utilisateur (création, normalisation, unicité insensible à la casse en base et
  dans le gestionnaire, authentification), réglages, format de date « 25 octobre 2026 »,
  PostgreSQL `french`, page d'accueil.

### Décisions
- **Tailwind** : binaire autonome plutôt que `django-tailwind-cli` (le paquet n'est pas dans la
  liste autorisée). Le CSS compilé n'est pas versionné ; il est produit au déploiement.
- **E-mail** : normalisé (espaces retirés, minuscules) à l'enregistrement, et protégé par une
  contrainte `UniqueConstraint(Lower("email"))` en base. Le champ `username` est supprimé.
- **Ports** : 5433 (PostgreSQL) et 8001 (runserver), car 5432 et 8000 sont occupés sur le
  poste de développement.
- **Versions** : installation avec `uv pip install --exclude-newer 2026-10-28` pour respecter la
  règle des deux semaines, y compris pour les dépendances transitives. Tailwind 4.3.4/4.3.5 et
  psycopg 3.3.7/3.3.8 écartés (trop récents).
- **Applications** : seule `comptes` est créée ; les autres le seront dans leur phase.
- **Profils et rôles** (`ProfilEtudiant`, `ProfilEnseignant`, groupes) : reportés à la phase 1.

### Points ouverts
- `check --deploy` signale seulement `SECURE_HSTS_PRELOAD` (laissé à `False` volontairement :
  l'inscription à la liste de préchargement est un engagement à décider en phase 10).
- Questions en attente (voir l'échange de lancement) : année utilisée dans la cote ; liste des
  mentions des mémoires ; caractère définitif de REJETE et RETIRE ; encadrants externes sans
  compte ; lien entre `archiver` et `VerificationDocumentaire` ; retour de
  A_CORRIGER_BIBLIOTHEQUE vers VALIDE sans repasser par le directeur ; droits de modification des
  métadonnées ; champs propres aux thèses ; forme des sauvegardes (BF22) ; Gunicorn (phase 10).
