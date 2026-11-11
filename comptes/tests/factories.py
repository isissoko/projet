import factory
from django.contrib.auth.models import Group

from comptes.models import ProfilEnseignant, ProfilEtudiant, Utilisateur
from referentiel.tests.factories import DepartementFactory, FiliereFactory

MOT_DE_PASSE = "motdepasse-solide-42"


class UtilisateurFactory(factory.django.DjangoModelFactory):
    """Utilisateur ; `roles=["ETUDIANT", ...]` ajoute les groupes correspondants."""

    class Meta:
        model = Utilisateur
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"utilisateur{n}@sigaps.test")
    first_name = factory.Faker("first_name", locale="fr_FR")
    last_name = factory.Faker("last_name", locale="fr_FR")
    password = factory.django.Password(MOT_DE_PASSE)

    @factory.post_generation
    def roles(self, create, valeurs, **kwargs):
        if create and valeurs:
            self.groups.set(Group.objects.filter(name__in=valeurs))
            self.oublier_roles()


class ProfilEtudiantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProfilEtudiant

    utilisateur = factory.SubFactory(UtilisateurFactory, roles=["ETUDIANT"])
    matricule = factory.Sequence(lambda n: f"MAT{n:05d}")
    niveau = ProfilEtudiant.Niveau.MASTER
    filiere = factory.SubFactory(FiliereFactory)


class ProfilEnseignantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProfilEnseignant

    utilisateur = factory.SubFactory(UtilisateurFactory, roles=["ENSEIGNANT"])
    grade = ProfilEnseignant.Grade.MAITRE_ASSISTANT
    specialite = "Informatique"
    departement = factory.SubFactory(DepartementFactory)
