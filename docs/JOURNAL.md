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

## Phase 1 — Comptes et référentiel (11 novembre 2026)

### Fait
- **Rôles** : groupes `ETUDIANT`, `ENSEIGNANT`, `BIBLIOTHECAIRE`, `ADMINISTRATEUR` créés par la
  migration de données `comptes/0003`. `Utilisateur.a_role(nom)` et `a_un_role(*noms)` lisent les
  groupes une seule fois par instance et renvoient faux pour un compte désactivé.
- **Profils** : `ProfilEtudiant` (matricule unique normalisé en majuscules sans espaces, niveau,
  filière) et `ProfilEnseignant` (grade, spécialité, département), en OneToOne.
- **Référentiel** : `Etablissement`, `Departement` (code unique par établissement), `Filiere`
  (code unique), `AnneeAcademique` (une seule courante par `UniqueConstraint` conditionnelle,
  `CheckConstraint` sur les dates, libellé `AAAA-AAAA`), `Domaine` (hiérarchique, cycles refusés
  par validation, auto-référence refusée en base), `MotCle` (unique insensible à la casse en
  base). Tous ont un champ `actif`.
- **Services** : `comptes/services.py` (créer, modifier, rôles, activation, premier
  administrateur) et `referentiel/services.py` (année courante sous `select_for_update`,
  enregistrement, suppression ou désactivation, réactivation), tous en `transaction.atomic`.
- **Authentification** : vues Django intégrées avec gabarits français (connexion, déconnexion
  en POST, mot de passe oublié en 4 écrans) ; django-axes 8.3.1, page de blocage stylée (429).
- **`RoleRequisMixin`** : redirection vers la connexion pour un visiteur, page 403 stylée pour un
  rôle manquant. L'objet demandé n'est chargé qu'après le contrôle du rôle (un tiers reçoit 403,
  pas 404, et n'apprend donc pas si l'objet existe).
- **Interfaces** : gestion des comptes (liste avec recherche et filtres rôle/état, création avec
  profils, modification, activation) et gestion générique des 6 éléments du référentiel
  (`referentiel/registre.py`), menu de `base.html` selon les rôles.
- **Composants** (`templates/composants/`) : champ (avec `aria-invalid` et `aria-describedby`
  de Django 5.2), erreurs de formulaire, bouton, tableau, pagination, état vide, modale de
  confirmation (`<dialog>` + `static/js/modale.js`, 40 lignes, sans dépendance).
- **Admin Django** : tous les modèles enregistrés, profils en ligne sur l'utilisateur.
- **Commande** `creer_admin` (interactive, valide l'e-mail et le mot de passe).
- **Tests** : 106 tests, couverture 96 % sur comptes et référentiel.

### Décisions
- **Création de compte** : l'administrateur ne saisit pas de mot de passe. Le compte reçoit un
  mot de passe inutilisable et un e-mail d'invitation avec un lien de réinitialisation (3 jours).
  « Mot de passe oublié » accepte aussi ces comptes (formulaire `ReinitialisationForm`).
- **django-axes** : blocage sur le couple (e-mail, IP) pour qu'un tiers ne puisse pas bloquer le
  compte de quelqu'un d'autre ; levée après 30 minutes ; compteur remis à zéro après un succès.
  L'identifiant compté est l'e-mail normalisé (`comptes/securite.py`). Version 8.3.1 car la
  9.0.0 (30 octobre) a moins de deux semaines.
- **Auto-protection** : un administrateur ne peut ni retirer son rôle Administrateur ni
  désactiver son propre compte (service + vue + test).
- **Profils** : un profil n'est jamais supprimé quand on retire le rôle (historique conservé).
  Retirer le rôle Étudiant laisse le profil en place mais `a_role` devient faux.
- **Exception métier** : `comptes.exceptions.ActionInterdite`, affichée comme erreur de
  formulaire ou message.
- **Formulaire d'année** : cocher « année courante » bascule l'ancienne via le service ; la
  contrainte d'unicité est donc exclue de la validation du formulaire (elle reste en base).
- **Modale** : sans JavaScript, le formulaire est envoyé directement (pas de blocage).

### Points ouverts
- **Proxy et IP réelle** : sans django-ipware (non autorisé), axes lit `REMOTE_ADDR`. Derrière
  Nginx, il faudra un `AXES_CLIENT_IP_CALLABLE` lisant `X-Real-IP` posé par Nginx (phase 10),
  sinon tous les visiteurs partageront l'IP 127.0.0.1.
- Le texte « 30 minutes » de la page de blocage est écrit en dur ; à relier au réglage si la
  durée change.
- Questions C à L de la phase 0 toujours en attente (notamment F : encadrants externes, qui
  pourront être des comptes inactifs avec un profil enseignant).
