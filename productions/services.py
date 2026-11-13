"""Automate des statuts et services de dépôt.

Toute modification d'une production passe par ce module. Les vues se contentent de
transmettre des données déjà validées par les formulaires.
"""

import datetime
import os
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from comptes.exceptions import ActionInterdite
from comptes.roles import Role

from . import acces, indexation
from .models import (
    MENTIONS_MEMOIRE,
    MENTIONS_THESE,
    Avis,
    AvisEncadrement,
    CompteurCote,
    Contributeur,
    Contribution,
    DecisionVerification,
    Encadrement,
    Memoire,
    NiveauAcces,
    Production,
    RoleContribution,
    RoleEncadrement,
    Statut,
    These,
    TypeProduction,
    VerificationDocumentaire,
    VersionDocument,
)
from .validators import calculer_sha256, valider_pdf

# Exceptions ---------------------------------------------------------------------------


class TransitionInterdite(Exception):
    """Transition absente de l'automate (RG09) : convertie en HTTP 409 par le middleware."""

    def __init__(self, production, origine, cible, message=None):
        self.production = production
        self.origine = origine
        self.cible = cible
        if message is None:
            libelle_cible = Statut(cible).label if cible in Statut.values else str(cible)
            message = (
                f"Action impossible : un travail au statut « {Statut(origine).label} » "
                f"ne peut pas passer à « {libelle_cible} »."
            )
        super().__init__(message)


class MotifObligatoire(ActionInterdite):
    """RG07 : motif obligatoire pour demander des corrections, rejeter, retirer."""


class SoumissionIncomplete(ActionInterdite):
    def __init__(self, manquants):
        self.manquants = manquants
        super().__init__("Le dépôt est incomplet : " + " ; ".join(m.message for m in manquants))


# Automate -----------------------------------------------------------------------------
#
# « création → BROUILLON » : creer_brouillon (pas une transition).
# « BROUILLON → suppression » : supprimer_brouillon (pas une transition de statut).
# « import Excel → ARCHIVE » : service de création de la phase 8 (pas une transition).

TRANSITIONS: dict[tuple[str, str], str] = {
    (Statut.BROUILLON, Statut.SOUMIS): "soumettre",
    (Statut.SOUMIS, Statut.VALIDE): "avis_favorable_directeur",
    (Statut.SOUMIS, Statut.A_CORRIGER_ENCADREUR): "demander_corrections_encadreur",
    (Statut.SOUMIS, Statut.REJETE): "rejeter",
    (Statut.A_CORRIGER_ENCADREUR, Statut.SOUMIS): "soumettre_version_corrigee",
    (Statut.VALIDE, Statut.ARCHIVE): "archiver",
    (Statut.VALIDE, Statut.A_CORRIGER_BIBLIOTHEQUE): "demander_corrections_bibliotheque",
    (Statut.A_CORRIGER_BIBLIOTHEQUE, Statut.VALIDE): "soumettre_version_corrigee",
    (Statut.ARCHIVE, Statut.RETIRE): "retirer",
}

TRANSITIONS_AVEC_MOTIF = {
    (Statut.SOUMIS, Statut.A_CORRIGER_ENCADREUR),
    (Statut.SOUMIS, Statut.REJETE),
    (Statut.VALIDE, Statut.A_CORRIGER_BIBLIOTHEQUE),
    (Statut.ARCHIVE, Statut.RETIRE),
}


def transition_autorisee(origine: str, cible: str) -> bool:
    return (origine, cible) in TRANSITIONS


def _apres_changement_statut(production, ancien, nouveau, acteur, detail):
    """Point d'extension de la phase 6.

    >>> PHASE 6 : créer ici le JournalAction (RG08) dans la transaction, puis programmer
    >>> les notifications avec transaction.on_commit(...).
    """


@transaction.atomic
def changer_statut(production, nouveau_statut, acteur, detail: str = ""):
    """Unique point de changement de statut : vérifie, enregistre, journalise, notifie."""
    verrouillee = Production.objects.select_for_update().get(pk=production.pk)
    ancien = verrouillee.statut
    if not transition_autorisee(ancien, nouveau_statut):
        raise TransitionInterdite(production, ancien, nouveau_statut)
    detail = (detail or "").strip()
    if (ancien, nouveau_statut) in TRANSITIONS_AVEC_MOTIF and not detail:
        raise MotifObligatoire("Un motif est obligatoire pour cette action.")

    maintenant = timezone.now()
    champs = {"statut": nouveau_statut, "date_modification": maintenant}
    if nouveau_statut == Statut.SOUMIS:
        champs["date_soumission"] = maintenant
    if nouveau_statut == Statut.ARCHIVE:
        champs["date_archivage"] = maintenant
    if nouveau_statut == Statut.RETIRE:
        champs["motif_retrait"] = detail
        champs["date_retrait"] = maintenant
    Production.objects.filter(pk=production.pk).update(**champs)
    for nom, valeur in champs.items():
        setattr(production, nom, valeur)

    _apres_changement_statut(production, ancien, nouveau_statut, acteur, detail)
    return production


# Contrôles communs --------------------------------------------------------------------


def _exiger_brouillon_modifiable(acteur, production):
    if production.statut != Statut.BROUILLON:
        raise ActionInterdite("Seul un brouillon peut être modifié.")
    if not acces.est_auteur_principal(acteur, production):
        raise ActionInterdite("Seul l'auteur principal peut modifier ce dépôt.")


def _verrouiller(production):
    """Relit la production en base sous verrou : les contrôles portent sur l'état réel,
    jamais sur une instance éventuellement périmée transmise par l'appelant."""
    return Production.objects.select_for_update().get(pk=production.pk)


# Métadonnées --------------------------------------------------------------------------

CHAMPS_METADONNEES = (
    "titre",
    "resume",
    "langue",
    "filiere",
    "annee_academique",
    "domaine",
    "date_soutenance",
    "mention",
)


def _appliquer_metadonnees(production, donnees: dict):
    for champ in CHAMPS_METADONNEES:
        if champ in donnees:
            setattr(production, champ, donnees[champ])
    if isinstance(production, Memoire) and "niveau" in donnees:
        production.niveau = donnees["niveau"]
    production.titre = " ".join((production.titre or "").split())
    if not production.titre:
        raise ActionInterdite("Le titre est obligatoire.")
    mentions = MENTIONS_THESE if isinstance(production, These) else MENTIONS_MEMOIRE
    if production.mention and production.mention not in mentions:
        raise ActionInterdite(
            f"Cette mention n'est pas possible pour un(e) {production.libelle_type}."
        )
    try:
        production.full_clean(exclude=["mots_cles"])
    except ValidationError as erreur:
        raise ActionInterdite(" ".join(erreur.messages)) from erreur


def contributeur_pour_utilisateur(utilisateur) -> Contributeur:
    contributeur, _ = Contributeur.objects.get_or_create(
        utilisateur=utilisateur,
        defaults={
            "nom": utilisateur.last_name or utilisateur.email,
            "prenom": utilisateur.first_name,
        },
    )
    return contributeur


@transaction.atomic
def creer_brouillon(acteur, type_production: str, donnees: dict, mots_cles=()) -> Production:
    """Crée un mémoire ou une thèse au statut BROUILLON ; l'acteur en est l'auteur principal."""
    if not acteur.a_role(Role.ETUDIANT):
        raise ActionInterdite("Seul un étudiant peut déposer un travail.")
    if type_production == TypeProduction.MEMOIRE:
        production = Memoire()
    elif type_production == TypeProduction.THESE:
        production = These()
    else:
        raise ActionInterdite("Type de production inconnu.")
    _appliquer_metadonnees(production, donnees)
    try:
        production.save()
    except IntegrityError as erreur:
        raise ActionInterdite("Données incohérentes pour ce type de travail.") from erreur
    production.mots_cles.set(mots_cles)
    Contribution.objects.create(
        production=production,
        contributeur=contributeur_pour_utilisateur(acteur),
        rang=1,
        role=RoleContribution.AUTEUR_PRINCIPAL,
    )
    return production


@transaction.atomic
def modifier_brouillon(acteur, production, donnees: dict, mots_cles=None) -> Production:
    production = _verrouiller(production)
    _exiger_brouillon_modifiable(acteur, production)
    production = production.specifique()
    _appliquer_metadonnees(production, donnees)
    try:
        with transaction.atomic():
            production.save()
    except IntegrityError as erreur:
        raise ActionInterdite("Données incohérentes pour ce type de travail.") from erreur
    if mots_cles is not None:
        production.mots_cles.set(mots_cles)
    return production


# Contributeurs et encadrants ----------------------------------------------------------


@dataclass
class DonneesCoauteur:
    nom: str
    prenom: str
    affiliation: str = ""
    orcid: str | None = None
    utilisateur: object | None = None  # compte SIGAPS existant, si connu


def _renumeroter(production):
    for rang, contribution in enumerate(
        Contribution.objects.filter(production=production).order_by("rang"), start=1
    ):
        if contribution.rang != rang:
            contribution.rang = rang
            contribution.save(update_fields=["rang"])


@transaction.atomic
def ajouter_coauteur(acteur, production, donnees: DonneesCoauteur) -> Contribution:
    production = _verrouiller(production)
    _exiger_brouillon_modifiable(acteur, production)
    orcid = (donnees.orcid or "").strip().upper() or None
    if donnees.utilisateur is not None:
        contributeur = contributeur_pour_utilisateur(donnees.utilisateur)
    elif orcid and (existant := Contributeur.objects.filter(orcid=orcid).first()):
        contributeur = existant
    else:
        contributeur = Contributeur(
            nom=donnees.nom.strip(),
            prenom=donnees.prenom.strip(),
            affiliation=donnees.affiliation.strip(),
            orcid=orcid,
        )
        try:
            contributeur.full_clean(exclude=["utilisateur"])
        except ValidationError as erreur:
            raise ActionInterdite(" ".join(erreur.messages)) from erreur
        contributeur.save()
    if Contribution.objects.filter(production=production, contributeur=contributeur).exists():
        raise ActionInterdite(f"{contributeur} figure déjà parmi les auteurs.")
    rang = (
        Contribution.objects.filter(production=production).aggregate(m=Max("rang"))["m"] or 0
    ) + 1
    return Contribution.objects.create(
        production=production, contributeur=contributeur, rang=rang, role=RoleContribution.CO_AUTEUR
    )


@transaction.atomic
def retirer_coauteur(acteur, production, contribution_id) -> None:
    production = _verrouiller(production)
    _exiger_brouillon_modifiable(acteur, production)
    contribution = Contribution.objects.filter(production=production, pk=contribution_id).first()
    if contribution is None:
        raise ActionInterdite("Ce co-auteur ne fait pas partie du dépôt.")
    if contribution.role == RoleContribution.AUTEUR_PRINCIPAL:
        raise ActionInterdite("L'auteur principal ne peut pas être retiré.")
    contribution.delete()
    _renumeroter(production)


@transaction.atomic
def ajouter_encadrant(acteur, production, enseignant, role: str) -> Encadrement:
    production = _verrouiller(production)
    _exiger_brouillon_modifiable(acteur, production)
    if role not in RoleEncadrement.values:
        raise ActionInterdite("Rôle d'encadrement inconnu.")
    utilisateur = enseignant.utilisateur
    if not utilisateur.a_role(Role.ENSEIGNANT):
        raise ActionInterdite(f"{utilisateur} n'est pas un enseignant actif.")
    if acces.est_auteur(utilisateur, production):
        raise ActionInterdite("Un auteur ne peut pas encadrer son propre travail.")
    if Encadrement.objects.filter(production=production, enseignant=enseignant).exists():
        raise ActionInterdite(f"{utilisateur} encadre déjà ce travail.")
    if (
        role == RoleEncadrement.DIRECTEUR
        and Encadrement.objects.filter(production=production, role=role).exists()
    ):
        raise ActionInterdite(
            "Ce travail a déjà un directeur. Retirez-le avant d'en désigner un autre."
        )
    return Encadrement.objects.create(production=production, enseignant=enseignant, role=role)


@transaction.atomic
def retirer_encadrant(acteur, production, encadrement_id) -> None:
    production = _verrouiller(production)
    _exiger_brouillon_modifiable(acteur, production)
    supprimes, _ = Encadrement.objects.filter(production=production, pk=encadrement_id).delete()
    if not supprimes:
        raise ActionInterdite("Cet encadrant ne fait pas partie du dépôt.")


# Versions -----------------------------------------------------------------------------


def _creer_version(acteur, production, fichier, note_corrections: str = "") -> VersionDocument:
    """Valide le PDF, calcule l'empreinte et enregistre une nouvelle version (verrou tenu)."""
    try:
        valider_pdf(fichier)
    except ValidationError as erreur:
        raise ActionInterdite(" ".join(erreur.messages)) from erreur
    version = VersionDocument(
        production=production,
        numero=VersionDocument.prochain_numero(production),
        nom_original=os.path.basename(fichier.name or "document.pdf")[:255],
        taille=fichier.size,
        empreinte_sha256=calculer_sha256(fichier),
        depose_par=acteur,
        note_corrections=(note_corrections or "").strip(),
    )
    # Le fichier est écrit avant la ligne en base. Si l'enregistrement échoue, on l'efface.
    # (Une annulation plus tardive de la transaction laisserait un fichier orphelin, sans
    # ligne associée : il sera signalé par la commande verifier_integrite.)
    version.fichier.save("document.pdf", fichier, save=False)
    try:
        with transaction.atomic():
            version.save()
    except Exception:
        version.fichier.storage.delete(version.fichier.name)
        raise
    return version


@transaction.atomic
def ajouter_version(acteur, production, fichier) -> VersionDocument:
    production = _verrouiller(production)
    _exiger_brouillon_modifiable(acteur, production)
    version = _creer_version(acteur, production, fichier)
    Production.objects.filter(pk=production.pk).update(date_modification=timezone.now())
    return version


# Suppression et soumission ------------------------------------------------------------


@transaction.atomic
def supprimer_brouillon(acteur, production) -> None:
    """Supprime un brouillon jamais soumis, ses versions et leurs fichiers (décision Q2)."""
    production = _verrouiller(production)
    if production.statut != Statut.BROUILLON:
        raise TransitionInterdite(
            production,
            production.statut,
            "SUPPRESSION",
            "Seul un brouillon peut être supprimé : ce travail a déjà été soumis.",
        )
    if not acces.est_auteur_principal(acteur, production):
        raise ActionInterdite("Seul l'auteur principal peut supprimer ce dépôt.")
    versions = VersionDocument.objects.filter(production=production)
    fichiers = [(v.fichier.storage, v.fichier.name) for v in versions]
    versions._supprimer_versions_d_un_brouillon()
    production.specifique().delete()
    transaction.on_commit(lambda: [stockage.delete(nom) for stockage, nom in fichiers])


@dataclass(frozen=True)
class Manquant:
    message: str
    etape: int


def elements_manquants(production) -> list[Manquant]:
    """Ce qui empêche la soumission, dans l'ordre des étapes du dépôt."""
    production = production.specifique()
    manquants = []
    if not production.titre:
        manquants.append(Manquant("le titre", 1))
    if not production.resume.strip():
        manquants.append(Manquant("le résumé", 1))
    if not production.langue:
        manquants.append(Manquant("la langue", 1))
    if isinstance(production, Memoire) and not production.niveau:
        manquants.append(Manquant("le niveau (Licence ou Master)", 1))
    if production.filiere_id is None:
        manquants.append(Manquant("la filière", 1))
    if production.annee_academique_id is None:
        manquants.append(Manquant("l'année académique", 1))
    if production.domaine_id is None:
        manquants.append(Manquant("le domaine", 1))
    if not production.mots_cles.exists():
        manquants.append(Manquant("au moins un mot-clé", 1))
    principaux = production.contributions.filter(role=RoleContribution.AUTEUR_PRINCIPAL).count()
    if principaux != 1:
        manquants.append(Manquant("un auteur principal", 2))
    directeurs = production.encadrements.filter(role=RoleEncadrement.DIRECTEUR).count()
    if directeurs != 1:
        manquants.append(Manquant("un directeur (encadrant principal)", 2))
    if not production.versions.exists():
        manquants.append(Manquant("le fichier PDF", 3))
    return manquants


@transaction.atomic
def soumettre(acteur, production) -> Production:
    """BROUILLON → SOUMIS, si le dépôt est complet ; sinon SoumissionIncomplete."""
    verrouillee = _verrouiller(production)
    if verrouillee.statut != Statut.BROUILLON:
        raise TransitionInterdite(production, verrouillee.statut, Statut.SOUMIS)
    if not acces.est_auteur_principal(acteur, verrouillee):
        raise ActionInterdite("Seul l'auteur principal peut soumettre ce dépôt.")
    manquants = elements_manquants(verrouillee)
    if manquants:
        raise SoumissionIncomplete(manquants)
    return changer_statut(production, Statut.SOUMIS, acteur)  # met aussi à jour l'instance


# Évaluation par l'encadreur (phase 3) ---------------------------------------------------

STATUT_APRES_AVIS_DU_DIRECTEUR = {
    Avis.FAVORABLE: Statut.VALIDE,
    Avis.CORRECTIONS_DEMANDEES: Statut.A_CORRIGER_ENCADREUR,
    Avis.DEFAVORABLE: Statut.REJETE,
}


def _apres_avis_consultatif(production, avis, acteur):
    """Point d'extension de la phase 6.

    >>> PHASE 6 : journaliser l'avis du co-directeur et notifier le directeur
    >>> (transaction.on_commit).
    """


@transaction.atomic
def donner_avis(acteur, production, avis: str, commentaire: str = "") -> AvisEncadrement:
    """Enregistre l'avis d'un encadrant sur la version courante.

    L'avis du directeur fait changer le statut (RG02) ; celui d'un co-directeur est consultatif.
    """
    verrouillee = _verrouiller(production)
    if avis not in Avis.values:
        raise ActionInterdite("Avis inconnu.")
    if verrouillee.statut != Statut.SOUMIS:
        raise TransitionInterdite(
            production,
            verrouillee.statut,
            STATUT_APRES_AVIS_DU_DIRECTEUR[avis],
            "Ce travail n'est plus en attente d'évaluation : son statut a changé.",
        )
    encadrement = Encadrement.objects.filter(
        production=verrouillee, enseignant__utilisateur=acteur
    ).first()
    if encadrement is None or not acteur.a_role(Role.ENSEIGNANT):
        raise ActionInterdite("Seuls les encadrants de ce travail peuvent l'évaluer.")
    commentaire = (commentaire or "").strip()
    if avis != Avis.FAVORABLE and not commentaire:
        raise MotifObligatoire(
            "Un motif est obligatoire pour demander des corrections ou rejeter le travail."
        )
    version = verrouillee.version_courante()
    if version is None:
        raise ActionInterdite("Aucune version à évaluer.")
    if AvisEncadrement.objects.filter(encadrement=encadrement, version=version).exists():
        raise ActionInterdite(f"Vous avez déjà donné votre avis sur la version {version.numero}.")

    resultat = AvisEncadrement.objects.create(
        production=verrouillee,
        encadrement=encadrement,
        version=version,
        avis=avis,
        commentaire=commentaire,
    )
    if encadrement.role == RoleEncadrement.DIRECTEUR:
        changer_statut(production, STATUT_APRES_AVIS_DU_DIRECTEUR[avis], acteur, commentaire)
    else:
        _apres_avis_consultatif(production, resultat, acteur)
    return resultat


STATUT_APRES_VERSION_CORRIGEE = {
    Statut.A_CORRIGER_ENCADREUR: Statut.SOUMIS,
    Statut.A_CORRIGER_BIBLIOTHEQUE: Statut.VALIDE,
}


@transaction.atomic
def soumettre_version_corrigee(acteur, production, fichier, note: str = "") -> VersionDocument:
    """Dépose la version corrigée (nouveau PDF obligatoire) et renvoie le travail à
    l'encadreur (A_CORRIGER_ENCADREUR → SOUMIS) ou à la bibliothèque
    (A_CORRIGER_BIBLIOTHEQUE → VALIDE)."""
    verrouillee = _verrouiller(production)
    cible = STATUT_APRES_VERSION_CORRIGEE.get(verrouillee.statut)
    if cible is None:
        raise TransitionInterdite(
            production,
            verrouillee.statut,
            Statut.SOUMIS,
            "Aucune correction n'est attendue sur ce travail.",
        )
    if not acces.est_auteur_principal(acteur, verrouillee):
        raise ActionInterdite("Seul l'auteur principal peut déposer la version corrigée.")
    if fichier is None:
        raise ActionInterdite("Déposez le PDF corrigé.")
    version = _creer_version(acteur, verrouillee, fichier, note_corrections=note)
    changer_statut(production, cible, acteur, f"Version corrigée n° {version.numero} déposée.")
    return version


@dataclass(frozen=True)
class DemandeCorrections:
    """Dernière demande de corrections, qu'elle vienne de l'encadreur ou de la bibliothèque."""

    origine: str  # « encadreur » ou « bibliothèque »
    auteur: object  # Utilisateur (None si le compte a disparu)
    date: datetime.datetime
    version: VersionDocument
    texte: str


def motif_corrections(production) -> DemandeCorrections | None:
    """Motif de la demande de corrections en cours, si le travail est à corriger."""
    if production.statut == Statut.A_CORRIGER_ENCADREUR:
        avis = (
            AvisEncadrement.objects.filter(
                production=production,
                avis=Avis.CORRECTIONS_DEMANDEES,
                encadrement__role=RoleEncadrement.DIRECTEUR,
            )
            .select_related("encadrement__enseignant__utilisateur", "version")
            .first()
        )
        if avis is not None:
            return DemandeCorrections(
                "encadreur",
                avis.encadrement.enseignant.utilisateur,
                avis.date,
                avis.version,
                avis.commentaire,
            )
    if production.statut == Statut.A_CORRIGER_BIBLIOTHEQUE:
        verification = (
            VerificationDocumentaire.objects.filter(
                production=production, decision=DecisionVerification.A_CORRIGER
            )
            .select_related("bibliothecaire", "version")
            .first()
        )
        if verification is not None:
            return DemandeCorrections(
                "bibliothèque",
                verification.bibliothecaire,
                verification.date,
                verification.version,
                verification.motif,
            )
    return None


def enregistrer_consultation(utilisateur, production, adresse_ip=None) -> None:
    """Point d'extension de la phase 6.

    >>> PHASE 6 : créer le JournalAction « consultation » de la fiche (RG08).
    """


def enregistrer_telechargement(utilisateur, version, adresse_ip=None) -> None:
    """Point d'extension de la phase 6.

    >>> PHASE 6 : créer le JournalAction « téléchargement » (RG08).
    """


# Contrôle de la bibliothèque, cote, archivage, retrait (phase 4) ------------------------

STATUTS_METADONNEES_BIBLIOTHEQUE = (
    Statut.VALIDE,
    Statut.A_CORRIGER_BIBLIOTHEQUE,
    Statut.ARCHIVE,
)


def _exiger_bibliothecaire(acteur, production):
    if not (acteur is not None and acteur.is_authenticated and acteur.a_role(Role.BIBLIOTHECAIRE)):
        raise ActionInterdite("Cette action est réservée aux bibliothécaires.")
    if acces.est_auteur(acteur, production):
        raise ActionInterdite("Vous ne pouvez pas traiter un travail dont vous êtes l'auteur.")


def _verifier_embargo(date_fin_embargo, actuelle=None):
    """Une date de fin d'embargo est dans le futur ; la date déjà enregistrée reste admise
    (modification du seul niveau d'accès après la levée de l'embargo)."""
    if date_fin_embargo is None or date_fin_embargo == actuelle:
        return
    if date_fin_embargo <= acces.aujourd_hui():
        raise ActionInterdite("La date de fin d'embargo doit être postérieure à aujourd'hui.")


def _verifier_niveau(niveau_acces):
    if niveau_acces not in NiveauAcces.values:
        raise ActionInterdite("Choisissez un niveau d'accès.")


def attribuer_cote(code_type: str, annee: int) -> str:
    """Tire le prochain numéro du CompteurCote (code_type, annee), verrouillé (RG06).

    À appeler dans une transaction : le verrou est tenu jusqu'à sa fin, ce qui sérialise
    les archivages concurrents. Les productions existantes ne sont jamais comptées.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("attribuer_cote doit être appelé dans une transaction.")
    # INSERT … ON CONFLICT DO NOTHING : crée le compteur s'il n'existe pas, sans erreur
    # si un archivage concurrent vient de le créer.
    CompteurCote.objects.bulk_create(
        [CompteurCote(code_type=code_type, annee=annee)], ignore_conflicts=True
    )
    compteur = CompteurCote.objects.select_for_update().get(code_type=code_type, annee=annee)
    compteur.dernier_numero += 1
    compteur.save(update_fields=["dernier_numero"])
    return f"{code_type}-{annee}-{compteur.dernier_numero:04d}"


@transaction.atomic
def archiver(acteur, production, niveau_acces: str, date_fin_embargo=None) -> Production:
    """VALIDE → ARCHIVE : vérification CONFORME, cote, niveau d'accès et embargo (BF07, BF08).

    L'année de la cote est celle de la soutenance (décision Q1 de la phase 4).
    """
    verrouillee = _verrouiller(production)
    if verrouillee.statut != Statut.VALIDE:
        raise TransitionInterdite(production, verrouillee.statut, Statut.ARCHIVE)
    _exiger_bibliothecaire(acteur, verrouillee)
    _verifier_niveau(niveau_acces)
    _verifier_embargo(date_fin_embargo)
    if verrouillee.date_soutenance is None:
        raise ActionInterdite(
            "Renseignez la date de soutenance avant d'archiver : son année figure dans la cote."
        )
    version = verrouillee.version_courante()
    if version is None:
        raise ActionInterdite("Aucune version à archiver.")

    VerificationDocumentaire.objects.create(
        production=verrouillee,
        version=version,
        bibliothecaire=acteur,
        decision=DecisionVerification.CONFORME,
    )
    cote = attribuer_cote(verrouillee.code_type(), verrouillee.date_soutenance.year)
    Production.objects.filter(pk=production.pk).update(
        cote=cote, niveau_acces=niveau_acces, date_fin_embargo=date_fin_embargo
    )
    production.cote = cote
    production.niveau_acces = niveau_acces
    production.date_fin_embargo = date_fin_embargo
    changer_statut(
        production, Statut.ARCHIVE, acteur, f"Cote {cote}, version {version.numero} archivée."
    )
    indexation.indexer(production)
    return production


@transaction.atomic
def demander_corrections_bibliotheque(acteur, production, motif: str):
    """VALIDE → A_CORRIGER_BIBLIOTHEQUE, motif obligatoire (RG07)."""
    verrouillee = _verrouiller(production)
    if verrouillee.statut != Statut.VALIDE:
        raise TransitionInterdite(production, verrouillee.statut, Statut.A_CORRIGER_BIBLIOTHEQUE)
    _exiger_bibliothecaire(acteur, verrouillee)
    motif = (motif or "").strip()
    if not motif:
        raise MotifObligatoire("Un motif est obligatoire pour demander des corrections.")
    version = verrouillee.version_courante()
    if version is None:
        raise ActionInterdite("Aucune version à contrôler.")
    verification = VerificationDocumentaire.objects.create(
        production=verrouillee,
        version=version,
        bibliothecaire=acteur,
        decision=DecisionVerification.A_CORRIGER,
        motif=motif,
    )
    changer_statut(production, Statut.A_CORRIGER_BIBLIOTHEQUE, acteur, motif)
    return verification


@transaction.atomic
def retirer(acteur, production, motif: str) -> Production:
    """ARCHIVE → RETIRE, motif obligatoire (BF20, RG07). Le retrait est définitif."""
    verrouillee = _verrouiller(production)
    if verrouillee.statut != Statut.ARCHIVE:
        raise TransitionInterdite(production, verrouillee.statut, Statut.RETIRE)
    _exiger_bibliothecaire(acteur, verrouillee)
    motif = (motif or "").strip()
    if not motif:
        raise MotifObligatoire("Un motif est obligatoire pour retirer un travail.")
    return changer_statut(production, Statut.RETIRE, acteur, motif)


def _apres_modification(production, acteur, detail):
    """Point d'extension de la phase 6.

    >>> PHASE 6 : créer le JournalAction « modification de métadonnées » (RG08).
    """


@transaction.atomic
def modifier_acces(acteur, production, niveau_acces: str, date_fin_embargo=None) -> Production:
    """Change le niveau d'accès et l'embargo d'un travail archivé (BF08)."""
    verrouillee = _verrouiller(production)
    if verrouillee.statut != Statut.ARCHIVE:
        raise ActionInterdite("Seul l'accès d'un travail archivé peut être modifié.")
    _exiger_bibliothecaire(acteur, verrouillee)
    _verifier_niveau(niveau_acces)
    _verifier_embargo(date_fin_embargo, actuelle=verrouillee.date_fin_embargo)
    Production.objects.filter(pk=production.pk).update(
        niveau_acces=niveau_acces,
        date_fin_embargo=date_fin_embargo,
        date_modification=timezone.now(),
    )
    production.niveau_acces = niveau_acces
    production.date_fin_embargo = date_fin_embargo
    _apres_modification(
        production,
        acteur,
        f"Accès : {NiveauAcces(niveau_acces).label}, fin d'embargo : {date_fin_embargo or '—'}.",
    )
    return production


@transaction.atomic
def modifier_metadonnees(acteur, production, donnees: dict, mots_cles=None) -> Production:
    """Correction des métadonnées par la bibliothèque (BF12), pendant le contrôle et après
    l'archivage. Le type et la cote ne changent jamais."""
    verrouillee = _verrouiller(production)
    if verrouillee.statut not in STATUTS_METADONNEES_BIBLIOTHEQUE:
        raise ActionInterdite("Les métadonnées de ce travail ne peuvent pas être modifiées.")
    _exiger_bibliothecaire(acteur, verrouillee)
    if verrouillee.statut == Statut.ARCHIVE and donnees.get("date_soutenance", True) is None:
        raise ActionInterdite("La date de soutenance d'un travail archivé est obligatoire.")
    specifique = verrouillee.specifique()
    _appliquer_metadonnees(specifique, donnees)
    try:
        with transaction.atomic():
            specifique.save()
    except IntegrityError as erreur:
        raise ActionInterdite("Données incohérentes pour ce type de travail.") from erreur
    if mots_cles is not None:
        specifique.mots_cles.set(mots_cles)
    indexation.indexer(specifique)
    _apres_modification(specifique, acteur, "Métadonnées modifiées par la bibliothèque.")
    return specifique
