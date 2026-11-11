import pytest
from django.db import IntegrityError, transaction

from comptes.tests.factories import ProfilEnseignantFactory
from productions import services
from productions.models import (
    Contribution,
    Encadrement,
    Memoire,
    Mention,
    Production,
    RoleContribution,
    RoleEncadrement,
    Statut,
    SuppressionInterdite,
    These,
    TypeProduction,
    VersionDocument,
)

from .factories import ContributeurFactory, MemoireFactory, TheseFactory, depot_complet
from .fichiers import pdf_valide

pytestmark = pytest.mark.django_db


def test_code_type_et_type_production():
    memoire = MemoireFactory()
    these = TheseFactory()
    assert memoire.code_type() == "MEM"
    assert these.code_type() == "THE"
    assert memoire.type_production == TypeProduction.MEMOIRE
    assert these.type_production == TypeProduction.THESE
    # Depuis la table parente, specifique() retrouve la bonne classe.
    assert isinstance(Production.objects.get(pk=memoire.pk).specifique(), Memoire)
    assert isinstance(Production.objects.get(pk=these.pk).specifique(), These)
    assert Production.objects.get(pk=these.pk).code_type() == "THE"


def test_nouvelle_production_au_statut_brouillon():
    assert MemoireFactory().statut == Statut.BROUILLON


def test_memoire_de_niveau_doctorat_refuse_en_base():
    with pytest.raises(IntegrityError), transaction.atomic():
        MemoireFactory(niveau="DOCTORAT")


@pytest.mark.parametrize("mention", [Mention.HONORABLE, Mention.TRES_HONORABLE])
def test_mention_de_these_refusee_pour_un_memoire(mention):
    with pytest.raises(IntegrityError), transaction.atomic():
        MemoireFactory(mention=mention)


def test_mention_de_memoire_refusee_pour_une_these():
    with pytest.raises(IntegrityError), transaction.atomic():
        TheseFactory(mention=Mention.BIEN)


def test_mentions_autorisees():
    assert MemoireFactory(mention=Mention.TRES_BIEN).mention == Mention.TRES_BIEN
    assert TheseFactory(mention=Mention.TRES_HONORABLE).mention == Mention.TRES_HONORABLE


def test_deux_directeurs_impossibles():
    production = MemoireFactory()
    Encadrement.objects.create(
        production=production, enseignant=ProfilEnseignantFactory(), role=RoleEncadrement.DIRECTEUR
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Encadrement.objects.create(
            production=production,
            enseignant=ProfilEnseignantFactory(),
            role=RoleEncadrement.DIRECTEUR,
        )
    # Un co-directeur reste possible.
    Encadrement.objects.create(
        production=production,
        enseignant=ProfilEnseignantFactory(),
        role=RoleEncadrement.CO_DIRECTEUR,
    )


def test_deux_auteurs_principaux_impossibles():
    production = MemoireFactory()
    Contribution.objects.create(
        production=production,
        contributeur=ContributeurFactory(),
        rang=1,
        role=RoleContribution.AUTEUR_PRINCIPAL,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Contribution.objects.create(
            production=production,
            contributeur=ContributeurFactory(),
            rang=2,
            role=RoleContribution.AUTEUR_PRINCIPAL,
        )


def test_rang_unique_par_production():
    production = MemoireFactory()
    Contribution.objects.create(
        production=production,
        contributeur=ContributeurFactory(),
        rang=1,
        role=RoleContribution.AUTEUR_PRINCIPAL,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Contribution.objects.create(
            production=production,
            contributeur=ContributeurFactory(),
            rang=1,
            role=RoleContribution.CO_AUTEUR,
        )


def test_orcid_unique_et_facultatif():
    ContributeurFactory(orcid=None)
    ContributeurFactory(orcid="")  # chaîne vide convertie en NULL : plusieurs autorisés
    ContributeurFactory(orcid="0000-0002-1825-0097")
    with pytest.raises(IntegrityError), transaction.atomic():
        ContributeurFactory(orcid="0000-0002-1825-0097")


def test_version_courante_et_numerotation():
    production, etudiant, _ = depot_complet()
    v2 = services.ajouter_version(etudiant, production, pdf_valide("v2.pdf"))
    v3 = services.ajouter_version(etudiant, production, pdf_valide("v3.pdf"))
    assert [v.numero for v in production.versions.all()] == [1, 2, 3]
    assert production.version_courante() == v3
    assert v2.nom_original == "v2.pdf"


def test_numero_de_version_unique_en_base():
    production, _, _ = depot_complet()
    version = production.versions.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        VersionDocument.objects.create(
            production=production,
            numero=version.numero,
            fichier=version.fichier.name,
            nom_original="x.pdf",
            taille=1,
            empreinte_sha256="0" * 64,
        )


def test_suppression_d_une_version_toujours_refusee():
    production, _, _ = depot_complet()
    version = production.versions.get()
    with pytest.raises(SuppressionInterdite):
        version.delete()
    with pytest.raises(SuppressionInterdite):
        VersionDocument.objects.filter(pk=version.pk).delete()
    with pytest.raises(SuppressionInterdite):
        production.versions.all().delete()
    assert VersionDocument.objects.filter(pk=version.pk).exists()


def test_production_non_brouillon_non_supprimable_par_le_modele():
    production = MemoireFactory()
    Production.objects.filter(pk=production.pk).update(statut=Statut.SOUMIS)
    production.refresh_from_db()
    with pytest.raises(SuppressionInterdite):
        production.delete()


def test_fichier_dans_le_stockage_prive_avec_nom_uuid(settings):
    production, _, _ = depot_complet()
    version = production.versions.get()
    with pytest.raises(ValueError):
        version.fichier.url  # noqa: B018 — aucune URL publique
    assert str(settings.STOCKAGE_PRIVE_RACINE) in version.fichier.path
    nom = version.fichier.name
    assert nom.startswith("versions/") and nom.endswith(".pdf")
    assert len(nom.removeprefix("versions/").removesuffix(".pdf")) == 32  # uuid4 hexadécimal
    assert version.nom_original == "memoire.pdf"
