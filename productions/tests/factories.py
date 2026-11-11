import factory

from comptes.tests.factories import ProfilEnseignantFactory, UtilisateurFactory
from productions import services
from productions.models import (
    Contributeur,
    Contribution,
    Encadrement,
    Memoire,
    NiveauMemoire,
    RoleContribution,
    RoleEncadrement,
    These,
)
from referentiel.tests.factories import (
    AnneeAcademiqueFactory,
    DomaineFactory,
    FiliereFactory,
    MotCleFactory,
)

from .fichiers import pdf_valide


class MemoireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Memoire

    titre = factory.Sequence(lambda n: f"Mémoire n° {n} sur l'agriculture au Sahel")
    resume = "Résumé du travail."
    niveau = NiveauMemoire.MASTER
    filiere = factory.SubFactory(FiliereFactory)
    annee_academique = factory.SubFactory(AnneeAcademiqueFactory)
    domaine = factory.SubFactory(DomaineFactory)


class TheseFactory(MemoireFactory):
    class Meta:
        model = These
        exclude = ("niveau",)

    titre = factory.Sequence(lambda n: f"Thèse n° {n} sur la linguistique mandingue")


class ContributeurFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Contributeur

    nom = factory.Faker("last_name", locale="fr_FR")
    prenom = factory.Faker("first_name", locale="fr_FR")


def ajouter_auteur_principal(production, utilisateur=None):
    utilisateur = utilisateur or UtilisateurFactory(roles=["ETUDIANT"])
    Contribution.objects.create(
        production=production,
        contributeur=services.contributeur_pour_utilisateur(utilisateur),
        rang=1,
        role=RoleContribution.AUTEUR_PRINCIPAL,
    )
    return utilisateur


def ajouter_directeur(production, enseignant=None):
    enseignant = enseignant or ProfilEnseignantFactory()
    Encadrement.objects.create(
        production=production, enseignant=enseignant, role=RoleEncadrement.DIRECTEUR
    )
    return enseignant


def depot_complet(etudiant=None, factory_classe=MemoireFactory, **attributs):
    """Brouillon complet, prêt à être soumis : renvoie (production, étudiant, directeur)."""
    production = factory_classe(**attributs)
    etudiant = ajouter_auteur_principal(production, etudiant)
    production.mots_cles.add(MotCleFactory())
    directeur = ajouter_directeur(production)
    services.ajouter_version(etudiant, production, pdf_valide())
    return production, etudiant, directeur


def ajouter_codirecteur(production, enseignant=None):
    enseignant = enseignant or ProfilEnseignantFactory()
    Encadrement.objects.create(
        production=production, enseignant=enseignant, role=RoleEncadrement.CO_DIRECTEUR
    )
    return enseignant


def depot_soumis(**attributs):
    """Travail soumis à son directeur : renvoie (production, étudiant, directeur)."""
    production, etudiant, directeur = depot_complet(**attributs)
    services.soumettre(etudiant, production)
    return production, etudiant, directeur
