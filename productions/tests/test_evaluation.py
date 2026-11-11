"""Services d'évaluation (BF06, RG02, RG07) et de version corrigée (BF18)."""

import pytest
from django.db import IntegrityError, transaction

from comptes.exceptions import ActionInterdite
from comptes.tests.factories import ProfilEnseignantFactory, UtilisateurFactory
from productions import acces, services
from productions.models import (
    Avis,
    AvisEncadrement,
    Production,
    Statut,
    SuppressionInterdite,
)

from .factories import ajouter_codirecteur, depot_complet, depot_soumis
from .fichiers import docx_renomme_en_pdf, pdf_valide

pytestmark = pytest.mark.django_db


def _au_statut(production, statut):
    Production.objects.filter(pk=production.pk).update(statut=statut)
    production.refresh_from_db()
    return production


# Avis du directeur --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("avis", "commentaire", "statut_attendu"),
    [
        (Avis.FAVORABLE, "", Statut.VALIDE),
        (Avis.CORRECTIONS_DEMANDEES, "Revoir la bibliographie.", Statut.A_CORRIGER_ENCADREUR),
        (Avis.DEFAVORABLE, "Hors sujet.", Statut.REJETE),
    ],
)
def test_avis_du_directeur_change_le_statut(avis, commentaire, statut_attendu):
    production, _, directeur = depot_soumis()
    resultat = services.donner_avis(directeur.utilisateur, production, avis, commentaire)
    production.refresh_from_db()
    assert production.statut == statut_attendu
    assert resultat.est_du_directeur
    assert resultat.version == production.version_courante()
    assert resultat.commentaire == commentaire


@pytest.mark.parametrize("avis", [Avis.CORRECTIONS_DEMANDEES, Avis.DEFAVORABLE])
def test_motif_obligatoire_pour_corrections_et_rejet(avis):
    production, _, directeur = depot_soumis()
    for commentaire in ["", "   "]:
        with pytest.raises(services.MotifObligatoire):
            services.donner_avis(directeur.utilisateur, production, avis, commentaire)
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS
    assert not AvisEncadrement.objects.exists()


def test_motif_obligatoire_en_base():
    production, _, _directeur = depot_soumis()
    with pytest.raises(IntegrityError), transaction.atomic():
        AvisEncadrement.objects.create(
            production=production,
            encadrement=production.encadrements.get(),
            version=production.version_courante(),
            avis=Avis.DEFAVORABLE,
            commentaire="  ",
        )


# Avis consultatif du co-directeur ----------------------------------------------------------


@pytest.mark.parametrize("avis", Avis.values)
def test_avis_du_co_directeur_ne_change_pas_le_statut(avis):
    production, _, _ = depot_soumis()
    codirecteur = ajouter_codirecteur(production)
    resultat = services.donner_avis(codirecteur.utilisateur, production, avis, "Mon avis.")
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS
    assert not resultat.est_du_directeur


def test_directeur_decide_apres_le_co_directeur():
    production, _, directeur = depot_soumis()
    codirecteur = ajouter_codirecteur(production)
    services.donner_avis(codirecteur.utilisateur, production, Avis.DEFAVORABLE, "Insuffisant.")
    services.donner_avis(directeur.utilisateur, production, Avis.FAVORABLE)
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE
    assert production.avis.count() == 2


def test_co_directeur_ne_peut_plus_donner_d_avis_apres_la_decision():
    production, _, directeur = depot_soumis()
    codirecteur = ajouter_codirecteur(production)
    services.donner_avis(directeur.utilisateur, production, Avis.FAVORABLE)
    with pytest.raises(services.TransitionInterdite):
        services.donner_avis(codirecteur.utilisateur, production, Avis.FAVORABLE)


def test_un_seul_avis_par_encadrant_et_par_version():
    production, _, _ = depot_soumis()
    codirecteur = ajouter_codirecteur(production)
    services.donner_avis(codirecteur.utilisateur, production, Avis.FAVORABLE)
    with pytest.raises(ActionInterdite, match="déjà donné votre avis"):
        services.donner_avis(codirecteur.utilisateur, production, Avis.DEFAVORABLE, "Finalement")
    with pytest.raises(IntegrityError), transaction.atomic():
        AvisEncadrement.objects.create(
            production=production,
            encadrement=production.encadrements.get(enseignant=codirecteur),
            version=production.version_courante(),
            avis=Avis.FAVORABLE,
        )


# Refus ----------------------------------------------------------------------------------


@pytest.mark.parametrize("statut", [s for s in Statut.values if s != Statut.SOUMIS])
def test_avis_impossible_hors_statut_soumis(statut):
    production, _, directeur = depot_complet()
    production = _au_statut(production, statut)
    with pytest.raises(services.TransitionInterdite):
        services.donner_avis(directeur.utilisateur, production, Avis.FAVORABLE)
    assert not AvisEncadrement.objects.exists()


@pytest.mark.parametrize("roles", [["ENSEIGNANT"], ["BIBLIOTHECAIRE"], ["ADMINISTRATEUR"]])
def test_seuls_les_encadrants_evaluent(roles):
    production, etudiant, _ = depot_soumis()
    for acteur in [UtilisateurFactory(roles=roles), etudiant]:
        with pytest.raises(ActionInterdite):
            services.donner_avis(acteur, production, Avis.FAVORABLE)
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS


def test_encadrant_desactive_ne_peut_plus_evaluer():
    production, _, directeur = depot_soumis()
    directeur.utilisateur.is_active = False
    directeur.utilisateur.save()
    with pytest.raises(ActionInterdite):
        services.donner_avis(directeur.utilisateur, production, Avis.FAVORABLE)


def test_avis_inconnu_refuse():
    production, _, directeur = depot_soumis()
    with pytest.raises(ActionInterdite):
        services.donner_avis(directeur.utilisateur, production, "PEUT_ETRE")


def test_un_avis_n_est_jamais_supprime():
    production, _, directeur = depot_soumis()
    avis = services.donner_avis(directeur.utilisateur, production, Avis.FAVORABLE)
    with pytest.raises(SuppressionInterdite):
        avis.delete()
    with pytest.raises(SuppressionInterdite):
        AvisEncadrement.objects.all().delete()


# Version corrigée -------------------------------------------------------------------------


def _a_corriger():
    production, etudiant, directeur = depot_soumis()
    services.donner_avis(
        directeur.utilisateur, production, Avis.CORRECTIONS_DEMANDEES, "Corriger le chapitre 2."
    )
    production.refresh_from_db()
    return production, etudiant, directeur


def test_version_corrigee_renvoie_le_travail_a_l_encadreur():
    production, etudiant, _ = _a_corriger()
    version = services.soumettre_version_corrigee(
        etudiant, production, pdf_valide("corrige.pdf"), note="Chapitre 2 réécrit."
    )
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS
    assert version.numero == 2
    assert version.note_corrections == "Chapitre 2 réécrit."
    assert production.version_courante() == version
    assert production.versions.count() == 2  # la version 1 est conservée


def test_nouvel_avis_possible_sur_la_version_corrigee():
    production, etudiant, directeur = _a_corriger()
    services.soumettre_version_corrigee(etudiant, production, pdf_valide())
    avis = services.donner_avis(directeur.utilisateur, production, Avis.FAVORABLE)
    assert avis.version.numero == 2
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE


def test_version_corrigee_depuis_la_bibliotheque_revient_a_valide():
    production, etudiant, _ = depot_complet()
    production = _au_statut(production, Statut.A_CORRIGER_BIBLIOTHEQUE)
    services.soumettre_version_corrigee(etudiant, production, pdf_valide())
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE


def test_version_corrigee_exige_un_fichier():
    production, etudiant, _ = _a_corriger()
    with pytest.raises(ActionInterdite, match="PDF corrigé"):
        services.soumettre_version_corrigee(etudiant, production, None)
    production.refresh_from_db()
    assert production.statut == Statut.A_CORRIGER_ENCADREUR


def test_version_corrigee_refuse_un_faux_pdf():
    production, etudiant, _ = _a_corriger()
    with pytest.raises(ActionInterdite, match="n'est pas un PDF"):
        services.soumettre_version_corrigee(etudiant, production, docx_renomme_en_pdf())
    production.refresh_from_db()
    assert production.statut == Statut.A_CORRIGER_ENCADREUR
    assert production.versions.count() == 1


@pytest.mark.parametrize(
    "statut",
    [
        Statut.BROUILLON,
        Statut.SOUMIS,
        Statut.VALIDE,
        Statut.REJETE,
        Statut.ARCHIVE,
        Statut.RETIRE,
    ],
)
def test_version_corrigee_impossible_sans_demande_de_corrections(statut):
    production, etudiant, _ = depot_complet()
    production = _au_statut(production, statut)
    with pytest.raises(services.TransitionInterdite):
        services.soumettre_version_corrigee(etudiant, production, pdf_valide())
    assert production.versions.count() == 1


def test_version_corrigee_reservee_a_l_auteur_principal():
    production, _, directeur = _a_corriger()
    for acteur in [directeur.utilisateur, UtilisateurFactory(roles=["ETUDIANT"])]:
        with pytest.raises(ActionInterdite):
            services.soumettre_version_corrigee(acteur, production, pdf_valide())


def test_rejet_definitif():
    production, etudiant, directeur = depot_soumis()
    services.donner_avis(directeur.utilisateur, production, Avis.DEFAVORABLE, "Plagiat.")
    production.refresh_from_db()
    with pytest.raises(services.TransitionInterdite):
        services.soumettre_version_corrigee(etudiant, production, pdf_valide())


def test_motif_corrections():
    production, _, _ = _a_corriger()
    motif = services.motif_corrections(production)
    assert motif.commentaire == "Corriger le chapitre 2."
    production = _au_statut(production, Statut.SOUMIS)
    assert services.motif_corrections(production) is None


# Listes de l'enseignant -------------------------------------------------------------------


def test_travaux_encadres_et_compteur():
    production, _, directeur = depot_soumis()
    codirecteur = ajouter_codirecteur(production)
    depot_complet()  # brouillon d'un autre : jamais listé
    brouillon, _, _ = depot_complet()
    ajouter_codirecteur(brouillon, codirecteur)  # brouillon non soumis : jamais listé

    travaux = acces.travaux_encadres(codirecteur.utilisateur)
    assert list(travaux.values_list("pk", flat=True)) == [production.pk]
    assert travaux.get().role_encadrement == "CO_DIRECTEUR"
    assert acces.nombre_a_evaluer(codirecteur.utilisateur) == 1
    assert acces.nombre_a_evaluer(directeur.utilisateur) == 1

    services.donner_avis(codirecteur.utilisateur, production, Avis.FAVORABLE)
    assert acces.nombre_a_evaluer(codirecteur.utilisateur) == 0
    assert acces.travaux_encadres(codirecteur.utilisateur).get().avis_donne
    assert acces.nombre_a_evaluer(directeur.utilisateur) == 1
    assert acces.nombre_a_evaluer(ProfilEnseignantFactory().utilisateur) == 0


def test_compteur_reapparait_pour_une_version_corrigee():
    production, etudiant, directeur = _a_corriger()
    assert acces.nombre_a_evaluer(directeur.utilisateur) == 0
    services.soumettre_version_corrigee(etudiant, production, pdf_valide())
    assert acces.nombre_a_evaluer(directeur.utilisateur) == 1


def test_peut_evaluer():
    production, etudiant, directeur = depot_soumis()
    assert acces.peut_evaluer(directeur.utilisateur, production)
    assert not acces.peut_evaluer(etudiant, production)
    services.donner_avis(directeur.utilisateur, production, Avis.FAVORABLE)
    production.refresh_from_db()
    assert not acces.peut_evaluer(directeur.utilisateur, production)
