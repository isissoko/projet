import hashlib

import pytest
from django.core.files.storage import storages

from comptes.exceptions import ActionInterdite
from comptes.tests.factories import ProfilEnseignantFactory, UtilisateurFactory
from productions import services
from productions.models import (
    Contribution,
    Encadrement,
    Memoire,
    Production,
    RoleContribution,
    RoleEncadrement,
    Statut,
    These,
    TypeProduction,
    VersionDocument,
)
from referentiel.tests.factories import FiliereFactory, MotCleFactory

from .factories import MemoireFactory, TheseFactory, ajouter_auteur_principal, depot_complet
from .fichiers import docx_renomme_en_pdf, pdf_valide

pytestmark = pytest.mark.django_db


@pytest.fixture
def etudiant():
    return UtilisateurFactory(roles=["ETUDIANT"])


# Création et modification -------------------------------------------------------------


def test_creer_brouillon_memoire_avec_auteur_principal(etudiant):
    mots = [MotCleFactory(), MotCleFactory()]
    production = services.creer_brouillon(
        etudiant,
        TypeProduction.MEMOIRE,
        {"titre": "  Étude   des sols  ", "langue": "FRANCAIS", "niveau": "LICENCE"},
        mots,
    )
    assert isinstance(production, Memoire)
    assert production.statut == Statut.BROUILLON
    assert production.titre == "Étude des sols"
    assert set(production.mots_cles.all()) == set(mots)
    contribution = production.contributions.get()
    assert contribution.role == RoleContribution.AUTEUR_PRINCIPAL
    assert contribution.rang == 1
    assert contribution.contributeur.utilisateur == etudiant


def test_creer_brouillon_these(etudiant):
    production = services.creer_brouillon(etudiant, TypeProduction.THESE, {"titre": "Thèse"})
    assert isinstance(production, These)
    assert production.code_type() == "THE"


def test_creer_brouillon_reserve_aux_etudiants():
    with pytest.raises(ActionInterdite):
        services.creer_brouillon(
            UtilisateurFactory(roles=["ENSEIGNANT"]), TypeProduction.THESE, {"titre": "X"}
        )


def test_memoire_doctorat_refuse_par_le_service(etudiant):
    with pytest.raises(ActionInterdite):
        services.creer_brouillon(
            etudiant, TypeProduction.MEMOIRE, {"titre": "X", "niveau": "DOCTORAT"}
        )
    assert not Production.objects.exists()


def test_mention_these_refusee_pour_un_memoire_par_le_service(etudiant):
    with pytest.raises(ActionInterdite):
        services.creer_brouillon(
            etudiant,
            TypeProduction.MEMOIRE,
            {"titre": "X", "niveau": "MASTER", "mention": "HONORABLE"},
        )


def test_modifier_brouillon(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    filiere = FiliereFactory()
    services.modifier_brouillon(
        etudiant, production, {"titre": "Nouveau titre", "filiere": filiere, "niveau": "LICENCE"}
    )
    production.refresh_from_db()
    assert production.titre == "Nouveau titre"
    assert production.filiere == filiere
    assert Memoire.objects.get(pk=production.pk).niveau == "LICENCE"


def test_modification_reservee_a_l_auteur_principal(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production)
    with pytest.raises(ActionInterdite):
        services.modifier_brouillon(etudiant, production, {"titre": "Piratage"})


# Co-auteurs et encadrants -------------------------------------------------------------


def test_ajouter_et_retirer_des_coauteurs(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    a = services.ajouter_coauteur(etudiant, production, services.DonneesCoauteur("Diarra", "Awa"))
    b = services.ajouter_coauteur(
        etudiant,
        production,
        services.DonneesCoauteur("Keita", "Sidi", orcid="0000-0002-1825-0097"),
    )
    assert [c.rang for c in production.contributions.order_by("rang")] == [1, 2, 3]
    services.retirer_coauteur(etudiant, production, a.pk)
    b.refresh_from_db()
    assert b.rang == 2
    assert b.role == RoleContribution.CO_AUTEUR


def test_coauteur_relie_a_un_compte(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    camarade = UtilisateurFactory(roles=["ETUDIANT"])
    services.ajouter_coauteur(
        etudiant, production, services.DonneesCoauteur("", "", utilisateur=camarade)
    )
    assert production.contributions.filter(contributeur__utilisateur=camarade).exists()
    with pytest.raises(ActionInterdite, match="figure déjà"):
        services.ajouter_coauteur(
            etudiant, production, services.DonneesCoauteur("", "", utilisateur=camarade)
        )


def test_auteur_principal_non_retirable(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    principal = production.contributions.get()
    with pytest.raises(ActionInterdite):
        services.retirer_coauteur(etudiant, production, principal.pk)


def test_un_seul_directeur_par_le_service(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    services.ajouter_encadrant(
        etudiant, production, ProfilEnseignantFactory(), RoleEncadrement.DIRECTEUR
    )
    with pytest.raises(ActionInterdite, match="déjà un directeur"):
        services.ajouter_encadrant(
            etudiant, production, ProfilEnseignantFactory(), RoleEncadrement.DIRECTEUR
        )
    services.ajouter_encadrant(
        etudiant, production, ProfilEnseignantFactory(), RoleEncadrement.CO_DIRECTEUR
    )
    assert production.encadrements.count() == 2


def test_encadrant_doit_etre_un_enseignant_actif(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    ancien = ProfilEnseignantFactory(utilisateur__is_active=False)
    with pytest.raises(ActionInterdite):
        services.ajouter_encadrant(etudiant, production, ancien, RoleEncadrement.DIRECTEUR)


def test_retirer_encadrant(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    encadrement = services.ajouter_encadrant(
        etudiant, production, ProfilEnseignantFactory(), RoleEncadrement.DIRECTEUR
    )
    services.retirer_encadrant(etudiant, production, encadrement.pk)
    assert not Encadrement.objects.exists()


# Versions -----------------------------------------------------------------------------


def test_ajouter_version_refuse_un_faux_pdf(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    with pytest.raises(ActionInterdite, match="n'est pas un PDF"):
        services.ajouter_version(etudiant, production, docx_renomme_en_pdf())
    assert not VersionDocument.objects.exists()


def test_ajouter_version_enregistre_empreinte_et_taille(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    fichier = pdf_valide()
    contenu = fichier.read()
    fichier.seek(0)
    version = services.ajouter_version(etudiant, production, fichier)
    assert version.numero == 1
    assert version.taille == len(contenu)
    assert version.empreinte_sha256 == hashlib.sha256(contenu).hexdigest()
    assert version.depose_par == etudiant
    with version.fichier.open("rb") as stocke:
        assert stocke.read() == contenu


# Soumission ---------------------------------------------------------------------------


def test_soumission_complete():
    production, etudiant, _ = depot_complet()
    services.soumettre(etudiant, production)
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS
    assert production.date_soumission is not None


def test_soumission_complete_pour_une_these():
    production, etudiant, _ = depot_complet(factory_classe=TheseFactory)
    services.soumettre(etudiant, production)
    production.refresh_from_db()
    assert production.statut == Statut.SOUMIS


def _messages(erreur):
    return [m.message for m in erreur.value.manquants]


def test_soumission_refusee_sans_directeur():
    production, etudiant, _ = depot_complet()
    production.encadrements.all().delete()
    with pytest.raises(services.SoumissionIncomplete) as erreur:
        services.soumettre(etudiant, production)
    assert _messages(erreur) == ["un directeur (encadrant principal)"]
    production.refresh_from_db()
    assert production.statut == Statut.BROUILLON


def test_soumission_refusee_avec_seulement_un_co_directeur():
    production, etudiant, _ = depot_complet()
    production.encadrements.update(role=RoleEncadrement.CO_DIRECTEUR)
    with pytest.raises(services.SoumissionIncomplete):
        services.soumettre(etudiant, production)


def test_soumission_refusee_sans_mot_cle():
    production, etudiant, _ = depot_complet()
    production.mots_cles.clear()
    with pytest.raises(services.SoumissionIncomplete) as erreur:
        services.soumettre(etudiant, production)
    assert _messages(erreur) == ["au moins un mot-clé"]


def test_soumission_refusee_sans_fichier(etudiant):
    production = MemoireFactory()
    ajouter_auteur_principal(production, etudiant)
    production.mots_cles.add(MotCleFactory())
    Encadrement.objects.create(
        production=production, enseignant=ProfilEnseignantFactory(), role="DIRECTEUR"
    )
    with pytest.raises(services.SoumissionIncomplete) as erreur:
        services.soumettre(etudiant, production)
    assert _messages(erreur) == ["le fichier PDF"]


def test_soumission_liste_tout_ce_qui_manque(etudiant):
    production = services.creer_brouillon(etudiant, TypeProduction.THESE, {"titre": "Titre"})
    with pytest.raises(services.SoumissionIncomplete) as erreur:
        services.soumettre(etudiant, production)
    assert _messages(erreur) == [
        "le résumé",
        "la filière",
        "l'année académique",
        "le domaine",
        "au moins un mot-clé",
        "un directeur (encadrant principal)",
        "le fichier PDF",
    ]
    assert [m.etape for m in erreur.value.manquants] == [1, 1, 1, 1, 1, 2, 3]


def test_soumission_refusee_sans_auteur_principal():
    production, etudiant, _ = depot_complet()
    Contribution.objects.filter(production=production).update(role=RoleContribution.CO_AUTEUR)
    with pytest.raises(ActionInterdite):  # plus d'auteur principal : plus personne n'a le droit
        services.soumettre(etudiant, production)
    assert "un auteur principal" in [m.message for m in services.elements_manquants(production)]


def test_soumission_deux_fois_leve_transition_interdite():
    production, etudiant, _ = depot_complet()
    services.soumettre(etudiant, production)
    with pytest.raises(services.TransitionInterdite):
        services.soumettre(etudiant, production)


def test_soumission_reservee_a_l_auteur_principal():
    production, _, _ = depot_complet()
    with pytest.raises(ActionInterdite):
        services.soumettre(UtilisateurFactory(roles=["ETUDIANT"]), production)


def test_brouillon_non_modifiable_apres_soumission():
    production, etudiant, _ = depot_complet()
    services.soumettre(etudiant, production)
    with pytest.raises(ActionInterdite):
        services.modifier_brouillon(etudiant, production, {"titre": "Après coup"})
    with pytest.raises(ActionInterdite):
        services.ajouter_version(etudiant, production, pdf_valide())


# Suppression --------------------------------------------------------------------------


def test_supprimer_brouillon_efface_versions_et_fichiers(django_capture_on_commit_callbacks):
    production, etudiant, _ = depot_complet()
    nom_fichier = production.versions.get().fichier.name
    stockage = storages["prive"]
    assert stockage.exists(nom_fichier)
    with django_capture_on_commit_callbacks(execute=True):
        services.supprimer_brouillon(etudiant, production)
    assert not Production.objects.filter(pk=production.pk).exists()
    assert not VersionDocument.objects.exists()
    assert not Contribution.objects.exists()
    assert not stockage.exists(nom_fichier)


@pytest.mark.parametrize("statut", [s for s in Statut.values if s != Statut.BROUILLON])
def test_suppression_refusee_hors_brouillon(statut):
    production, etudiant, _ = depot_complet()
    Production.objects.filter(pk=production.pk).update(statut=statut)
    with pytest.raises(services.TransitionInterdite):
        services.supprimer_brouillon(etudiant, production)
    assert Production.objects.filter(pk=production.pk).exists()
    assert production.versions.count() == 1


def test_suppression_refusee_a_un_autre_etudiant():
    production, _, _ = depot_complet()
    with pytest.raises(ActionInterdite):
        services.supprimer_brouillon(UtilisateurFactory(roles=["ETUDIANT"]), production)
    assert Production.objects.filter(pk=production.pk).exists()
