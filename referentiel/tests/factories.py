import datetime

import factory

from referentiel import models


class EtablissementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Etablissement

    code = factory.Sequence(lambda n: f"ETAB{n}")
    nom = factory.Sequence(lambda n: f"Université {n}")
    sigle = factory.Sequence(lambda n: f"U{n}")


class DepartementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Departement

    etablissement = factory.SubFactory(EtablissementFactory)
    code = factory.Sequence(lambda n: f"DEP{n}")
    nom = factory.Sequence(lambda n: f"Département {n}")


class FiliereFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Filiere

    departement = factory.SubFactory(DepartementFactory)
    code = factory.Sequence(lambda n: f"FIL{n}")
    libelle = factory.Sequence(lambda n: f"Filière {n}")


class AnneeAcademiqueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.AnneeAcademique

    class Params:
        debut = factory.Sequence(lambda n: 2000 + n)

    libelle = factory.LazyAttribute(lambda o: f"{o.debut}-{o.debut + 1}")
    date_debut = factory.LazyAttribute(lambda o: datetime.date(o.debut, 10, 1))
    date_fin = factory.LazyAttribute(lambda o: datetime.date(o.debut + 1, 7, 31))
    courante = False


class DomaineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Domaine

    code = factory.Sequence(lambda n: f"DOM{n}")
    libelle = factory.Sequence(lambda n: f"Domaine {n}")
    parent = None


class MotCleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.MotCle

    libelle = factory.Sequence(lambda n: f"mot-clé {n}")
