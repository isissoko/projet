"""Services de la bibliothèque : cote (RG06), archivage (BF07, BF08), corrections,
retrait (BF20), modification de l'accès et des métadonnées (BF12)."""

import datetime

import pytest
from django.utils import timezone

from comptes.exceptions import ActionInterdite
from comptes.tests.factories import UtilisateurFactory
from productions import services
from productions.models import (
    CompteurCote,
    DecisionVerification,
    NiveauAcces,
    Production,
    Statut,
    VerificationDocumentaire,
)

from .factories import (
    TheseFactory,
    bibliothecaire,
    depot_archive,
    depot_complet,
    depot_valide,
    forcer_statut,
)
from .fichiers import pdf_valide

pytestmark = pytest.mark.django_db

DEMAIN = timezone.localdate() + datetime.timedelta(days=1)


@pytest.fixture
def biblio():
    return bibliothecaire()


# Cote ------------------------------------------------------------------------------------


def test_cote_au_format_attendu():
    assert services.attribuer_cote("MEM", 2026) == "MEM-2026-0001"
    assert services.attribuer_cote("MEM", 2026) == "MEM-2026-0002"
    assert services.attribuer_cote("THE", 2026) == "THE-2026-0001"
    assert services.attribuer_cote("MEM", 2025) == "MEM-2025-0001"
    assert CompteurCote.objects.get(code_type="MEM", annee=2026).dernier_numero == 2


def test_cote_tiree_du_compteur_et_non_des_productions_existantes(biblio):
    """RG06 : on ne compte jamais les productions existantes."""
    CompteurCote.objects.create(code_type="MEM", annee=2026, dernier_numero=41)
    production, _, _ = depot_valide(date_soutenance=datetime.date(2026, 7, 1))
    services.archiver(biblio, production, NiveauAcces.LIBRE)
    assert production.cote == "MEM-2026-0042"


def test_cote_au_dela_de_9999():
    CompteurCote.objects.create(code_type="THE", annee=2026, dernier_numero=9999)
    assert services.attribuer_cote("THE", 2026) == "THE-2026-10000"


# Archivage ----------------------------------------------------------------------------------


def test_archiver(biblio):
    production, _, _ = depot_valide(date_soutenance=datetime.date(2026, 6, 15))
    version = production.version_courante()
    services.archiver(biblio, production, NiveauAcces.RESTREINT, DEMAIN)
    production.refresh_from_db()
    assert production.statut == Statut.ARCHIVE
    assert production.cote == "MEM-2026-0001"
    assert production.niveau_acces == NiveauAcces.RESTREINT
    assert production.date_fin_embargo == DEMAIN
    assert production.date_archivage is not None
    verification = VerificationDocumentaire.objects.get(production=production)
    assert verification.decision == DecisionVerification.CONFORME
    assert verification.version == version
    assert verification.bibliothecaire == biblio


def test_annee_de_la_cote_est_celle_de_la_soutenance(biblio):
    """Décision Q1 : année de soutenance, pas celle de l'archivage ni l'année académique."""
    production, _, _ = depot_valide(
        factory_classe=TheseFactory, date_soutenance=datetime.date(2019, 12, 3)
    )
    services.archiver(biblio, production, NiveauAcces.LIBRE)
    assert production.cote == "THE-2019-0001"


@pytest.mark.parametrize("statut", [s for s in Statut.values if s != Statut.VALIDE])
def test_archivage_impossible_hors_statut_valide(biblio, statut):
    production, _, _ = depot_complet(date_soutenance=datetime.date(2026, 1, 1))
    production = forcer_statut(production, statut)
    cote_avant = production.cote
    with pytest.raises(services.TransitionInterdite):
        services.archiver(biblio, production, NiveauAcces.LIBRE)
    production.refresh_from_db()
    assert production.statut == statut
    assert production.cote == cote_avant
    assert not CompteurCote.objects.exists()


@pytest.mark.parametrize("roles", [["ETUDIANT"], ["ENSEIGNANT"], ["ADMINISTRATEUR"], []])
def test_archivage_reserve_aux_bibliothecaires(roles):
    production, _, _ = depot_valide()
    with pytest.raises(ActionInterdite):
        services.archiver(UtilisateurFactory(roles=roles), production, NiveauAcces.LIBRE)
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE
    assert not VerificationDocumentaire.objects.exists()


def test_bibliothecaire_auteur_ne_traite_pas_son_travail():
    etudiant_biblio = UtilisateurFactory(roles=["ETUDIANT", "BIBLIOTHECAIRE"])
    production, _, _ = depot_valide(etudiant=etudiant_biblio)
    with pytest.raises(ActionInterdite, match="auteur"):
        services.archiver(etudiant_biblio, production, NiveauAcces.LIBRE)


@pytest.mark.parametrize(
    ("niveau", "embargo", "message"),
    [
        ("SECRET", None, "niveau d'accès"),
        (None, None, "niveau d'accès"),
        (NiveauAcces.LIBRE, timezone.localdate(), "postérieure à aujourd'hui"),
        (NiveauAcces.LIBRE, datetime.date(2020, 1, 1), "postérieure à aujourd'hui"),
    ],
)
def test_archivage_refuse_si_acces_invalide(biblio, niveau, embargo, message):
    production, _, _ = depot_valide()
    with pytest.raises(ActionInterdite, match=message):
        services.archiver(biblio, production, niveau, embargo)
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE
    assert production.cote is None


def test_archivage_exige_la_date_de_soutenance(biblio):
    production, _, _ = depot_valide(date_soutenance=None)
    with pytest.raises(ActionInterdite, match="date de soutenance"):
        services.archiver(biblio, production, NiveauAcces.LIBRE)
    assert not CompteurCote.objects.exists()


def test_instance_perimee_ne_permet_pas_d_archiver_deux_fois(biblio):
    production, _, _ = depot_valide()
    copie = Production.objects.get(pk=production.pk)
    services.archiver(biblio, production, NiveauAcces.LIBRE)
    with pytest.raises(services.TransitionInterdite):
        services.archiver(biblio, copie, NiveauAcces.LIBRE)  # copie.statut vaut encore VALIDE
    assert CompteurCote.objects.get().dernier_numero == 1


# Corrections demandées par la bibliothèque ---------------------------------------------------


def test_demander_corrections(biblio):
    production, _, _ = depot_valide()
    verification = services.demander_corrections_bibliotheque(
        biblio, production, "  Page de garde incomplète.  "
    )
    production.refresh_from_db()
    assert production.statut == Statut.A_CORRIGER_BIBLIOTHEQUE
    assert verification.decision == DecisionVerification.A_CORRIGER
    assert verification.motif == "Page de garde incomplète."
    motif = services.motif_corrections(production)
    assert motif.origine == "bibliothèque"
    assert motif.texte == "Page de garde incomplète."
    assert motif.auteur == biblio


@pytest.mark.parametrize("motif", ["", "   ", None])
def test_corrections_sans_motif_refusees(biblio, motif):
    production, _, _ = depot_valide()
    with pytest.raises(services.MotifObligatoire):
        services.demander_corrections_bibliotheque(biblio, production, motif)
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE
    assert not VerificationDocumentaire.objects.exists()


@pytest.mark.parametrize("statut", [s for s in Statut.values if s != Statut.VALIDE])
def test_corrections_impossibles_hors_statut_valide(biblio, statut):
    production, _, _ = depot_complet()
    production = forcer_statut(production, statut)
    with pytest.raises(services.TransitionInterdite):
        services.demander_corrections_bibliotheque(biblio, production, "Motif")


def test_corrections_reservees_aux_bibliothecaires():
    production, etudiant, directeur = depot_valide()
    for acteur in [etudiant, directeur.utilisateur, UtilisateurFactory(roles=["ADMINISTRATEUR"])]:
        with pytest.raises(ActionInterdite):
            services.demander_corrections_bibliotheque(acteur, production, "Motif")


def test_parcours_corrections_bibliotheque_puis_archivage(biblio):
    production, etudiant, _ = depot_valide()
    services.demander_corrections_bibliotheque(biblio, production, "Ajouter la page de garde.")
    version = services.soumettre_version_corrigee(etudiant, production, pdf_valide("v2.pdf"))
    production.refresh_from_db()
    assert production.statut == Statut.VALIDE
    assert services.motif_corrections(production) is None
    services.archiver(biblio, production, NiveauAcces.LIBRE)
    conforme = production.verifications.get(decision=DecisionVerification.CONFORME)
    assert conforme.version == version  # c'est la version corrigée qui est archivée
    assert production.verifications.count() == 2
    assert production.versions.count() == 2


# Retrait -------------------------------------------------------------------------------------


def test_retirer(biblio):
    production, _, _ = depot_archive()
    services.retirer(biblio, production, "  Plagiat avéré.  ")
    production.refresh_from_db()
    assert production.statut == Statut.RETIRE
    assert production.motif_retrait == "Plagiat avéré."
    assert production.date_retrait is not None
    assert production.cote  # la cote est conservée


@pytest.mark.parametrize("motif", ["", "  ", None])
def test_retrait_sans_motif_refuse(biblio, motif):
    production, _, _ = depot_archive()
    with pytest.raises(services.MotifObligatoire):
        services.retirer(biblio, production, motif)
    production.refresh_from_db()
    assert production.statut == Statut.ARCHIVE


@pytest.mark.parametrize("statut", [s for s in Statut.values if s != Statut.ARCHIVE])
def test_retrait_impossible_hors_archive(biblio, statut):
    """Y compris RETIRE : le retrait est définitif (décision Q5)."""
    production = forcer_statut(depot_complet()[0], statut)
    with pytest.raises(services.TransitionInterdite):
        services.retirer(biblio, production, "Motif")


def test_retrait_reserve_aux_bibliothecaires():
    production, etudiant, _ = depot_archive()
    for acteur in [etudiant, UtilisateurFactory(roles=["ADMINISTRATEUR"])]:
        with pytest.raises(ActionInterdite):
            services.retirer(acteur, production, "Motif")


# Modification de l'accès ----------------------------------------------------------------------


def test_modifier_acces(biblio):
    production, _, _ = depot_archive()
    services.modifier_acces(biblio, production, NiveauAcces.CONFIDENTIEL, DEMAIN)
    production.refresh_from_db()
    assert production.niveau_acces == NiveauAcces.CONFIDENTIEL
    assert production.date_fin_embargo == DEMAIN
    services.modifier_acces(biblio, production, NiveauAcces.LIBRE, None)
    production.refresh_from_db()
    assert production.date_fin_embargo is None


def test_embargo_expire_conserve_lors_d_un_changement_de_niveau(biblio):
    production, _, _ = depot_archive()
    passe = datetime.date(2020, 1, 1)
    Production.objects.filter(pk=production.pk).update(date_fin_embargo=passe)
    services.modifier_acces(biblio, production, NiveauAcces.RESTREINT, passe)
    with pytest.raises(ActionInterdite, match="postérieure"):
        services.modifier_acces(
            biblio, production, NiveauAcces.RESTREINT, datetime.date(2021, 1, 1)
        )


def test_modifier_acces_refuse_hors_archive(biblio):
    production, _, _ = depot_valide()
    with pytest.raises(ActionInterdite):
        services.modifier_acces(biblio, production, NiveauAcces.LIBRE)


def test_modifier_acces_niveau_invalide(biblio):
    production, _, _ = depot_archive()
    with pytest.raises(ActionInterdite):
        services.modifier_acces(biblio, production, "SECRET")


def test_modifier_acces_reserve_aux_bibliothecaires():
    production, etudiant, _ = depot_archive()
    with pytest.raises(ActionInterdite):
        services.modifier_acces(etudiant, production, NiveauAcces.CONFIDENTIEL)


# Métadonnées (BF12) ----------------------------------------------------------------------------


@pytest.mark.parametrize("archive", [False, True])
def test_modifier_metadonnees(biblio, archive):
    production, _, _ = depot_archive() if archive else depot_valide()
    cote = production.cote
    resultat = services.modifier_metadonnees(
        biblio, production, {"titre": "  Titre   corrigé ", "mention": "TRES_BIEN"}
    )
    production.refresh_from_db()
    assert production.titre == "Titre corrigé"
    assert production.mention == "TRES_BIEN"
    assert production.cote == cote  # la cote ne change jamais
    assert resultat.type_production == production.type_production


def test_modifier_les_mots_cles(biblio):
    from referentiel.tests.factories import MotCleFactory

    production, _, _ = depot_valide()
    mot = MotCleFactory()
    services.modifier_metadonnees(biblio, production, {}, mots_cles=[mot])
    assert list(production.mots_cles.all()) == [mot]


@pytest.mark.parametrize(
    "statut",
    [Statut.BROUILLON, Statut.SOUMIS, Statut.A_CORRIGER_ENCADREUR, Statut.REJETE, Statut.RETIRE],
)
def test_metadonnees_non_modifiables_hors_controle(biblio, statut):
    production = forcer_statut(depot_complet()[0], statut)
    with pytest.raises(ActionInterdite):
        services.modifier_metadonnees(biblio, production, {"titre": "Nouveau"})


def test_metadonnees_reservees_aux_bibliothecaires():
    production, etudiant, _ = depot_valide()
    with pytest.raises(ActionInterdite):
        services.modifier_metadonnees(etudiant, production, {"titre": "Nouveau"})


def test_date_de_soutenance_obligatoire_apres_archivage(biblio):
    production, _, _ = depot_archive()
    with pytest.raises(ActionInterdite, match="soutenance"):
        services.modifier_metadonnees(biblio, production, {"date_soutenance": None})


@pytest.mark.parametrize("donnees", [{"titre": "   "}, {"mention": "HONORABLE"}])
def test_metadonnees_invalides(biblio, donnees):
    production, _, _ = depot_valide()
    with pytest.raises(ActionInterdite):
        services.modifier_metadonnees(biblio, production, donnees)
