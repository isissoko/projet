"""Recalcule le vecteur de recherche plein texte de toutes les productions."""

from django.core.management.base import BaseCommand

from productions.indexation import reindexer
from productions.models import Production, Statut


class Command(BaseCommand):
    help = (
        "Recalcule l'index de recherche plein texte (après une migration, un import ou le "
        "changement du nom d'un auteur ou d'un encadrant)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--archives-seulement",
            action="store_true",
            help="Ne réindexe que les productions archivées (les seules cherchables).",
        )

    def handle(self, *args, **options):
        productions = Production.objects.all()
        if options["archives_seulement"]:
            productions = productions.filter(statut=Statut.ARCHIVE)
        nombre = reindexer(productions)
        self.stdout.write(self.style.SUCCESS(f"{nombre} production(s) réindexée(s)."))
