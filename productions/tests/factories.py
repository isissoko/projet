import factory
from django.utils import timezone

from comptes.tests.factories import ProfilEnseignantFactory, UtilisateurFactory
from productions import services
from productions.models import (
    Contributeur,
    Contribution,
    Encadrement,
    Memoire,
    NiveauAcces,
    NiveauMemoire,
    Production,
    RoleContribution,
    RoleEncadrement,
    Statut,
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


def preparer_archivage(production):
    """Renseigne une cote et un niveau d'accès sans changer le statut (tests de l'automate)."""
    Production.objects.filter(pk=production.pk).update(
        cote=production.cote or f"{production.code_type()}-1999-{production.pk:04d}",
        niveau_acces=production.niveau_acces or NiveauAcces.LIBRE,
    )
    production.refresh_from_db()
    return production


def forcer_statut(production, statut):
    """Place directement une production dans un statut, sans passer par l'automate (tests
    uniquement). Pour ARCHIVE et RETIRE, renseigne les champs exigés par les contraintes."""
    champs = {"statut": statut}
    if statut in (Statut.ARCHIVE, Statut.RETIRE):
        production = preparer_archivage(production)
        champs["date_archivage"] = production.date_archivage or timezone.now()
    if statut == Statut.RETIRE:
        champs["motif_retrait"] = production.motif_retrait or "Retrait de test."
        champs["date_retrait"] = production.date_retrait or timezone.now()
    Production.objects.filter(pk=production.pk).update(**champs)
    production.refresh_from_db()
    return production
