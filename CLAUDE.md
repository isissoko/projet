Tu vas développer SIGAPS, une plateforme web de gestion, validation et archivage des productions académiques (mémoires et thèses) d'un établissement d'enseignement supérieur au Mali.

Première action : enregistre l'intégralité de ce message dans un fichier CLAUDE.md à la racine du projet (crée-le s'il n'existe pas, sinon vérifie qu'il est identique). Ce fichier est la référence du projet pour toutes les sessions.

=== MÉTHODE DE TRAVAIL (obligatoire) ===
1. Avant chaque phase, présente un plan court (fichiers, modèles, vues, tests) et attends ma validation avant de coder.
2. Une phase à la fois. Une phase est terminée seulement si pytest passe et si ruff check . ne signale rien.
3. Un commit Git par étape logique, message en français à l'impératif.
4. Aucune dépendance hors de la liste autorisée sans me demander. Vérifie les versions actuelles avant d'installer, et n'utilise pas une version publiée depuis moins de deux semaines.
5. À la fin de chaque phase, mets à jour README.md et docs/JOURNAL.md (fait, décisions, points ouverts).
6. Si une consigne est ambiguë ou contradictoire, arrête-toi et pose la question.

=== PILE TECHNIQUE ===
- Python 3.12+, Django 5.2 LTS, PostgreSQL (aussi en dev, via docker-compose.yml ; la recherche plein texte utilise la configuration "french").
- HTML rendu par les templates Django + Tailwind CSS v4 via le binaire autonome (django-tailwind-cli ou CLI standalone), SANS Node.js, jamais le CDN en production. Pas de framework JS ; JavaScript vanilla minimal autorisé.
- Paquets autorisés : django-environ, psycopg[binary], argon2-cffi, django-axes, pypdf, openpyxl, weasyprint, pytest, pytest-django, factory-boy, ruff, coverage.
- Settings séparés base/dev/prod/test, secrets dans .env (+ .env.example). LANGUAGE_CODE="fr", TIME_ZONE="Africa/Bamako", USE_TZ=True.

=== ARCHITECTURE ===
Applications : comptes, referentiel, productions (services.py = automate, acces.py = règles d'accès, validators.py), bibliotheque, recherche, journal, notifications, statistiques, imports. Dossiers templates/, static/src/input.css, docs/.
Conventions : noms du domaine en français sans accents (Production, VersionDocument, date_fin_embargo). Logique métier dans les services, jamais dans les vues. Transitions et journalisation dans transaction.atomic. Utilisateur personnalisé (AbstractUser, connexion par e-mail unique) déclaré dans AUTH_USER_MODEL dès la phase 0.

=== ACTEURS ET RÔLES ===
Rôles = groupes Django : ETUDIANT, ENSEIGNANT, BIBLIOTHECAIRE, ADMINISTRATEUR. Un compte peut cumuler plusieurs rôles.
- Visiteur : rechercher, consulter les fiches, télécharger le libre accès.
- Étudiant : déposer, soumettre des corrections, suivre le statut.
- Enseignant : évaluer les travaux qu'il encadre (valider, demander des corrections, rejeter), annoter, contrôle de similitude.
- Bibliothécaire : contrôler la conformité et les métadonnées, archiver, niveau d'accès, référentiel, retrait.
- Administrateur : comptes et rôles, import Excel, paramètres, journal d'audit, statistiques.

=== BESOINS FONCTIONNELS (M = indispensable, S = important, C = souhaitable) ===
BF01 Connexion/déconnexion sécurisées (M). BF02 Gérer comptes et rôles (M). BF03 Déposer avec métadonnées : titre, auteurs, encadreur, année, filière, résumé, mots-clés, type (M). BF04 Téléverser avec contrôle format et taille (M). BF05 Suivre le statut (M). BF06 Évaluation par l'encadreur avec motif (M). BF07 Contrôle et archivage, conservation des versions (M). BF08 Niveau d'accès + date de fin d'embargo (M). BF09 Recherche multicritère : titre, auteur, année, mot-clé, encadreur, type, filière (M). BF10 Fiche + visualisation/téléchargement selon droits (M). BF11 Notifications internes et e-mail (S). BF12 Modifier les métadonnées (S). BF13 Tableau de bord par filière et par année (S). BF14 Journal des actions (S). BF15 Import Excel historique (S). BF16 Exports PDF/Excel (C). BF17 Contrôle de similitude via service externe (C). BF18 Version corrigée (M). BF19 Référentiel : filières, domaines, mots-clés, années (S). BF20 Retrait avec motif (S). BF21 Annotations (C). BF22 Paramètres et sauvegardes (S).

=== RÈGLES DE GESTION ===
RG01 Authentification obligatoire hors recherche/consultation publique.
RG02 Exactement un encadrant DIRECTEUR par travail (0..n CO_DIRECTEUR). Seul l'avis du directeur change le statut ; celui des co-directeurs est consultatif.
RG03 PDF uniquement (signature %PDF- + ouverture par pypdf, pas seulement l'extension), 50 Mo maximum.
RG04 Empreinte SHA-256 de chaque version, calculée par blocs.
RG05 Versions jamais supprimées. Production jamais supprimée sauf à l'état BROUILLON.
RG06 Cote unique attribuée à l'archivage, format {CODE_TYPE}-{ANNEE}-{NUMERO:04d} (MEM-2026-0042, THE-2026-0003), numéro tiré d'un CompteurCote(code_type, annee) verrouillé par select_for_update. Ne jamais compter les productions existantes.
RG07 Motif obligatoire pour demander des corrections, rejeter, retirer.
RG08 JournalAction pour chaque changement de statut, modification de métadonnées, retrait, consultation, téléchargement.
RG09 Transition non prévue → exception TransitionInterdite → HTTP 409.
RG10 La recherche publique ne renvoie que les productions ARCHIVE.
RG11 Production non archivée visible seulement par ses auteurs, encadrants, bibliothécaires, administrateurs ; tout autre utilisateur reçoit 404.
RG12 Memoire.niveau ∈ {LICENCE, MASTER} ; mentions HONORABLE et TRES_HONORABLE réservées aux thèses.

=== ACCÈS AUX FICHIERS D'UNE PRODUCTION ARCHIVE ===
La fiche est visible par tous. Le PDF :
- LIBRE : tout le monde ;
- RESTREINT : utilisateurs connectés ;
- CONFIDENTIEL : auteurs, encadrants, bibliothécaires, administrateurs ;
- embargo actif (date_fin_embargo > aujourd'hui) : auteurs, encadrants, bibliothécaires, administrateurs.
L'embargo est une date, pas un niveau ; il se lève tout seul car la règle est évaluée à chaque requête. Toute cette logique est dans productions/acces.py : peut_voir_fiche(user, production) et peut_telecharger(user, production). Aucune vue ne la réimplémente.

=== MODÈLE DE DONNÉES ===
- Production concrète (héritage multi-tables), Memoire et These en héritent ; code_type() renvoie "MEM" ou "THE". Champs : titre, resume, langue (FRANCAIS, ANGLAIS, BAMBARA, AUTRE), statut, niveau_acces, date_fin_embargo (null), cote (unique, null), date_soutenance, mention (null), filiere, annee_academique, domaine, mots_cles (M2M), lot_import (null), dates de création/soumission/archivage. Pas de compteurs de consultations : statistiques calculées depuis JournalAction.
- VersionDocument : numero, fichier (stockage privé, nom UUID), nom_original, taille, empreinte_sha256, date_depot. Version courante = plus grand numéro.
- Contributeur (utilisateur OneToOne nullable, pour les co-auteurs externes) + Contribution (rang unique, un seul AUTEUR_PRINCIPAL).
- Encadrement (production, ProfilEnseignant, role DIRECTEUR/CO_DIRECTEUR) + AvisEncadrement en historique (version évaluée, avis FAVORABLE/CORRECTIONS_DEMANDEES/DEFAVORABLE, commentaire, date).
- VerificationDocumentaire (production, version, bibliothecaire, decision CONFORME/A_CORRIGER, motif, date).
- ProfilEtudiant (matricule, niveau, filière), ProfilEnseignant (grade, spécialité, département).
- Référentiel : Etablissement, Departement, Filiere, AnneeAcademique (une seule courante), Domaine (hiérarchique), MotCle.
- JournalAction (date, type, acteur nullable, production nullable, ancien/nouveau statut, détail, IP), Notification, LotImport, Annotation, ControleSimilitude.
Contraintes en base (UniqueConstraint conditionnelles, CheckConstraint) doublées d'une validation dans les services.

=== AUTOMATE DES STATUTS (table de transitions explicite dans productions/services.py, fonction unique changer_statut, sans bibliothèque externe) ===
création → BROUILLON
BROUILLON → SOUMIS : soumettre [PDF valide, métadonnées complètes, un directeur]
BROUILLON → suppression : supprimer_brouillon
SOUMIS → VALIDE : avis FAVORABLE du directeur
SOUMIS → A_CORRIGER_ENCADREUR : avis CORRECTIONS_DEMANDEES [motif]
SOUMIS → REJETE : avis DEFAVORABLE [motif]
A_CORRIGER_ENCADREUR → SOUMIS : soumettre_version_corrigee
VALIDE → ARCHIVE : archiver(niveau_acces, date_fin_embargo) + attribution de la cote
VALIDE → A_CORRIGER_BIBLIOTHEQUE : demander_corrections [motif]
A_CORRIGER_BIBLIOTHEQUE → VALIDE : soumettre_version_corrigee
ARCHIVE → RETIRE : retirer [motif]
import Excel → ARCHIVE
changer_statut vérifie la transition, enregistre, journalise et notifie via transaction.on_commit.

=== SÉCURITÉ ===
Fichiers hors MEDIA public ; téléchargement uniquement via une vue qui appelle peut_telecharger(), journalise et renvoie FileResponse (X-Accel-Redirect configurable en prod). Argon2 en premier hasheur. django-axes : blocage après 5 échecs. Réinitialisation de mot de passe par e-mail. En prod : DEBUG=False, cookies Secure et HttpOnly, HSTS, ALLOWED_HOSTS par .env. Querysets filtrés par utilisateur, aucun IDOR. Commande verifier_integrite pour recalculer les empreintes.

=== INTERFACE ===
Mobile d'abord, pages légères (connexions lentes), tout en français, dates au format "25 octobre 2026". HTML sémantique, labels, contraste AA, focus visible, navigation clavier. Style sobre : bleu nuit + une couleur d'accent + gris, définis par @theme dans static/src/input.css. Composants inclus : champ de formulaire (avec erreurs), bouton, carte de production, pagination, badge de statut unique, chronologie, tableau, état vide, modale de confirmation.
Pages : accueil (recherche, derniers archivés, chiffres) ; résultats filtrés et paginés ; fiche (bouton de téléchargement ou raison de l'indisponibilité) ; connexion ; mot de passe oublié ; Mes dépôts ; dépôt en étapes (métadonnées → contributeurs et encadrants → fichier → récapitulatif → soumission) ; version corrigée ; Travaux à évaluer ; écran d'évaluation ; À contrôler ; écran de contrôle ; catalogue avec retrait ; référentiel ; comptes ; journal d'audit ; tableau de bord ; import Excel ; notifications (cloche + compteur).

=== TESTS ===
pytest-django + factory_boy. Obligatoires : chaque transition autorisée et interdite ; matrice d'accès complète (rôle × niveau × embargo × statut) ; validation PDF (faux PDF, > 50 Mo) ; unicité de la cote avec test de concurrence ; 404 pour un tiers sur une production non archivée ; journalisation de RG08 ; import Excel (valide, invalide, dry-run). Couverture ≥ 85 % sur services.py, acces.py, validators.py.

=== PHASES ===
0 Socle : projet, settings, PostgreSQL docker-compose, Tailwind v4 sans Node, Utilisateur personnalisé, base.html, ruff, pytest, README.
1 Comptes et référentiel.
2 Dépôt (modèles, validation PDF, versions, dépôt en étapes, Mes dépôts).
3 Évaluation par l'encadreur et version corrigée.
4 Contrôle bibliothèque, cote, archivage, accès, retrait.
5 Recherche plein texte, fiche, téléchargement sécurisé.
6 Journal et notifications.
7 Statistiques et exports.
8 Import Excel (commande + écran, dry-run, rapport d'erreurs, docs/IMPORT.md + modèle).
9 Annotations et similitude (interface ServiceSimilitude + implémentation factice).
10 Durcissement (check --deploy), pages d'erreur, charger_demo, accessibilité, docs/DEPLOIEMENT.md (Gunicorn + Nginx + PostgreSQL).

=== MAINTENANT ===
1. Crée CLAUDE.md avec ce message.
2. Résume le projet en 10 lignes et liste les points ambigus.
3. Vérifie ce qui est installé sur ma machine (Python, Docker, Git) et ce qui manque.
4. Présente ton plan pour la phase 0.
N'écris aucun autre code avant ma validation.
