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

## Phase 2 — Dépôt (11 novembre 2026)

### Fait
- **Modèles** (`productions/models.py`) : `Production` concrète, `Memoire` et `These` par héritage
  multi-tables, `VersionDocument`, `Contributeur`, `Contribution`, `Encadrement`, et les
  énumérations `Statut`, `TypeProduction`, `NiveauAcces`, `Langue`, `Mention`, `NiveauMemoire`.
- **Contraintes en base** :
  - un seul directeur par production, un seul auteur principal, rang unique ;
  - un contributeur et un enseignant au plus une fois par production ;
  - numéro de version unique par production, empreinte au format hexadécimal sur 64 caractères ;
  - mémoire de niveau Licence ou Master uniquement ;
  - mentions Honorable et Très honorable interdites pour un mémoire, mentions de mémoire
    interdites pour une thèse.
- **Versions** : `delete()` lève `SuppressionInterdite`, sur l'instance comme sur le queryset.
  La FK vers la production est en `PROTECT` et l'admin n'autorise ni ajout ni suppression.
- **Stockage privé** : `productions.stockage.StockagePrive`, dont `url()` lève une erreur.
  Les fichiers sont nommés par un UUID.
- **Validation PDF** (`validators.py`) : taille vérifiée par `size` avant toute lecture, puis
  signature `%PDF-`, puis ouverture par pypdf (fichier lisible, au moins une page, non
  chiffré). Empreinte SHA-256 par blocs de 64 Ko.
- **Automate** (`services.py`) :
  - table complète des 9 transitions et `TRANSITIONS_AVEC_MOTIF` ;
  - `changer_statut` verrouille la ligne, vérifie la transition et le motif, met à jour les
    dates, puis appelle un point d'extension marqué pour la phase 6 ;
  - `TransitionInterdite` est convertie en page 409 par `productions.middleware`.
- **Services de dépôt** : `creer_brouillon`, `modifier_brouillon`, `ajouter_coauteur`,
  `retirer_coauteur`, `ajouter_encadrant`, `retirer_encadrant`, `ajouter_version`,
  `supprimer_brouillon`, `soumettre` et `elements_manquants`.
- **Accès** (`acces.py`) : `peut_voir_fiche`, `peut_modifier_brouillon`, `mes_depots` et
  `productions_visibles`. Les vues de détail et d'étape renvoient 404 à un tiers.
- **Interface** :
  - dépôt en 5 étapes, avec barre de progression et brouillon enregistré à chaque étape ;
  - recherche d'enseignant sans JavaScript ;
  - aperçu du fichier choisi (`static/js/fichier.js`) ;
  - Mes dépôts (cartes), page de détail (versions, chronologie, actions), suppression avec la
    modale de confirmation ;
  - composants `badge_statut`, `carte_production`, `chronologie` et `progression_depot`,
    filtre `|taille` (« 2,4 Mo »).
- **Tests** : 279 au total. Couverture : `services.py` 92 %, `acces.py` 100 %,
  `validators.py` 95 %.

### Décisions
- **Q1 Mentions** : Passable, Assez bien, Bien et Très bien pour les mémoires ; Honorable et
  Très honorable pour les thèses ; pas de « félicitations du jury ».
- **Q2 Suppression d'un brouillon** : `supprimer_brouillon` est le seul chemin qui efface les
  versions d'un brouillon jamais soumis, par `_supprimer_versions_d_un_brouillon`. Les fichiers
  sont effacés après la validation de la transaction. Partout ailleurs, la suppression d'une
  version est refusée.
- **Q3 Chronologie** : construite à partir des dates (création, versions, soumission,
  archivage) ; elle sera branchée sur `JournalAction` en phase 6.
- **Q4** :
  - date de soutenance et mention facultatives à la soumission ;
  - PDF chiffrés refusés ;
  - seul l'auteur principal modifie, soumet ou supprime le dépôt ; un co-auteur relié à un
    compte peut le consulter.
- **Champ `type_production`** : technique, non modifiable, fixé dès la construction de
  l'objet. Il permet d'exprimer la règle RG12 sur les mentions par une contrainte sur la seule
  table `Production`, et servira au filtre « type » de la recherche.
- **Type figé** : le type d'un brouillon ne change pas après sa création ; pour en changer,
  il faut supprimer le brouillon.
- **`niveau_acces` et `mention`** : nuls tant que la valeur n'est pas fixée. Ruff est
  neutralisé localement sur ces deux champs, avec un commentaire qui l'explique.
- **`lot_import`** : ajouté en phase 8, avec le modèle `LotImport`.
- **`VersionDocument.depose_par`** : champ ajouté pour la traçabilité, en plus de ceux de
  CLAUDE.md.
- **Contrôles sur l'état réel** : tous les services relisent la production sous
  `select_for_update` et font leurs vérifications sur cette relecture, pas sur l'instance
  passée par l'appelant, qui peut être périmée. Un test couvre ce cas.

### Corrections de la phase 1
- Les formulaires de modification n'étaient pas préremplis, parce que `FormView` transmet
  `initial={}` et que `setdefault` n'avait donc aucun effet. Les valeurs sont maintenant
  fusionnées, dans le formulaire de compte comme dans celui du dépôt. Un test de
  non-régression a été ajouté.
- Avec `base_url=None`, le stockage privé reprenait `MEDIA_URL`. Il est remplacé par
  `StockagePrive`, sans URL. Le test du socle a été adapté.

### Points ouverts
- Si la transaction est annulée après l'écriture d'un fichier, ce fichier reste sur le disque
  sans ligne en base. Cas rare ; il sera détecté par `verifier_integrite` (phase 10).
- La limite de 50 Mo devra aussi être posée côté Nginx (`client_max_body_size`) en phase 10,
  pour couper l'envoi plus tôt.
- Pour l'instant, le lien « ← Mes dépôts » de la page de détail ne sert qu'aux étudiants. Les
  encadrants auront leur propre liste en phase 3.
- Questions C, E, F, G, H, I, J, K et L de la phase 0 : toujours en attente (Q1 a répondu à D).

## Phase 3 — Évaluation et version corrigée (11 novembre 2026)

### Fait
- **Modèle `AvisEncadrement`** : production, encadrement, version évaluée (`PROTECT`), avis,
  commentaire, date.
  - Contraintes en base : motif non vide sauf pour un avis favorable (RG07), valeur d'avis
    valide, un seul avis par encadrant et par version.
  - `delete()` refusé, sur l'instance comme sur le queryset ; admin en lecture seule.
- **`VersionDocument.note_corrections`** : ce que l'auteur dit avoir corrigé.
- **Services** :
  - `donner_avis` : verrou, statut SOUMIS exigé (sinon 409), encadrant enseignant actif,
    motif, version courante. Seul l'avis du directeur appelle `changer_statut`. Point
    d'extension `_apres_avis_consultatif` marqué pour la phase 6.
  - `soumettre_version_corrigee` : A_CORRIGER_ENCADREUR → SOUMIS ou
    A_CORRIGER_BIBLIOTHEQUE → VALIDE ; nouveau PDF obligatoire et validé ; réservé à
    l'auteur principal.
  - `motif_corrections`, et `enregistrer_telechargement` (point d'extension pour RG08).
- **Accès** : `peut_evaluer` ; `peut_telecharger`, première version réservée aux proches ;
  `travaux_encadres`, annoté avec le rôle et « avis déjà donné sur la version courante » par
  sous-requêtes ; `nombre_a_evaluer`.
- **Vues** :
  - Travaux à évaluer : onglets À évaluer, En correction et Traités ; compteur dans le menu.
  - Écran d'évaluation : document, PDF, versions, historique, formulaire, mention
    « consultatif » pour un co-directeur, modale de confirmation.
  - Version corrigée : motif mis en évidence, aperçu du fichier, note.
  - Téléchargement : 404 pour un tiers, `FileResponse` en affichage dans le navigateur,
    `Cache-Control: private, no-store`, `X-Accel-Redirect` en option.
  - Page de détail : avis, motif, boutons selon le rôle, avis dans la chronologie, lien de
    retour adapté à la personne.
- **Tests** : 344 au total, dont 65 nouveaux. Couverture : `services.py` 92 %, `acces.py` 98 %,
  `validators.py` 95 %.

### Décisions
- **Q1** : le téléchargement est écrit dès cette phase, parce que l'encadreur doit lire le PDF.
  `peut_telecharger` sera complété en phase 4 (niveaux d'accès, embargo).
- **Q2** : REJETE est définitif ; l'étudiant fait un nouveau dépôt.
- **Q3** : la version corrigée exige un nouveau PDF et accepte une note facultative ; les
  métadonnées ne sont pas modifiables pendant les corrections (BF12 reste ouvert).
- **Q4** : les auteurs voient tous les avis, y compris ceux des co-directeurs.
- **Co-directeur** : un seul avis par version, uniquement tant que le travail est SOUMIS ;
  après la décision du directeur, toute tentative renvoie 409.
- **Accès à l'évaluation** : un enseignant qui n'encadre pas le travail reçoit 404, et un
  utilisateur sans le rôle ENSEIGNANT reçoit 403 (`RoleRequisMixin`). Un brouillon n'est
  jamais présenté à l'évaluation.
- **Chronologie** : `date_soumission` ne garde que la dernière soumission ; l'historique
  complet viendra du `JournalAction` en phase 6.

### Points ouverts
- La chronologie sera reconstruite à partir de `JournalAction` en phase 6, avec toutes les
  soumissions successives.
- Notifications (directeur averti d'un avis consultatif, étudiant averti d'une décision) :
  phase 6, aux points d'extension marqués.
- `peut_telecharger` pour les travaux archivés : phase 4.
- Questions C, F, G, I, J, K et L de la phase 0 toujours en attente.
