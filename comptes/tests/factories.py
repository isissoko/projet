import factory

from comptes.models import Utilisateur


class UtilisateurFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Utilisateur
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"utilisateur{n}@sigaps.test")
    first_name = factory.Faker("first_name", locale="fr_FR")
    last_name = factory.Faker("last_name", locale="fr_FR")
    password = factory.django.Password("motdepasse-solide-42")
