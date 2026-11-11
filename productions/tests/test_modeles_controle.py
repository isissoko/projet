"""Contraintes en base de la phase 4 : vérification documentaire, cote, archivage, retrait."""

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from productions.models import (
    CompteurCote,
    DecisionVerification,
    NiveauAcces,
    Production,
    Statut,
    SuppressionInterdite,
    VerificationDocumentaire,
)

from .factories import MemoireFactory, depot_complet, forcer_statut

pytestmark = pytest.mark.django_db


def _modifier(production, **champs):
    with transaction.atomic():
        Production.objects.filter(pk=production.pk).update(**champs)


def _verification(production, decision, motif=""):
    return VerificationDocumentaire.objects.create(
        production=production,
        version=production.version_courante(),
        decision=decision,
        motif=motif,
    )


# Vérification documentaire -------------------------------------------------------------


@pytest.mark.parametrize("motif", ["", "  \n "])
def test_verification_a_corriger_exige_un_motif(motif):
    production, _, _ = depot_complet()
    with pytest.raises(IntegrityError), transaction.atomic():
        _verification(production, DecisionVerification.A_CORRIGER, motif)


def test_verification_conforme_sans_motif():
    production, _, _ = depot_complet()
    assert _verification(production, DecisionVerification.CONFORME).pk


def test_decision_inconnue_refusee_en_base():
    production, _, _ = depot_complet()
    with pytest.raises(IntegrityError), transaction.atomic():
        _verification(production, "PEUT_ETRE", "x")


def test_verification_jamais_supprimee():
    production, _, _ = depot_complet()
    verification = _verification(production, DecisionVerification.CONFORME)
    with pytest.raises(SuppressionInterdite):
        verification.delete()
    with pytest.raises(SuppressionInterdite):
        VerificationDocumentaire.objects.all().delete()


# Cote ----------------------------------------------------------------------------------


@pytest.mark.parametrize("cote", ["MEM-2026-0042", "THE-2026-0003", "MEM-2026-12345"])
def test_cote_au_bon_format(cote):
    production = MemoireFactory()
    _modifier(production, cote=cote)


@pytest.mark.parametrize("cote", ["MEM-26-0042", "XYZ-2026-0001", "MEM-2026-42", "mem-2026-0042"])
def test_cote_au_mauvais_format_refusee(cote):
    production = MemoireFactory()
    with pytest.raises(IntegrityError):
        _modifier(production, cote=cote)


def test_cote_unique():
    _modifier(MemoireFactory(), cote="MEM-2026-0001")
    with pytest.raises(IntegrityError):
        _modifier(MemoireFactory(), cote="MEM-2026-0001")


def test_compteur_unique_par_type_et_annee():
    CompteurCote.objects.create(code_type="MEM", annee=2026)
    CompteurCote.objects.create(code_type="THE", annee=2026)
    CompteurCote.objects.create(code_type="MEM", annee=2025)
    with pytest.raises(IntegrityError), transaction.atomic():
        CompteurCote.objects.create(code_type="MEM", annee=2026)


@pytest.mark.parametrize(("code_type", "annee"), [("XYZ", 2026), ("MEM", 26)])
def test_compteur_invalide_refuse(code_type, annee):
    with pytest.raises(IntegrityError), transaction.atomic():
        CompteurCote.objects.create(code_type=code_type, annee=annee)


# Archivage et retrait -------------------------------------------------------------------


@pytest.mark.parametrize(
    "manquant",
    [
        {"cote": None},
        {"niveau_acces": None},
        {"date_archivage": None},
    ],
)
@pytest.mark.parametrize("statut", [Statut.ARCHIVE, Statut.RETIRE])
def test_travail_archive_complet(statut, manquant):
    production = forcer_statut(MemoireFactory(), statut)
    with pytest.raises(IntegrityError):
        _modifier(production, **manquant)


def test_archive_sans_cote_refuse():
    production = MemoireFactory()
    with pytest.raises(IntegrityError):
        _modifier(production, statut=Statut.ARCHIVE, date_archivage=timezone.now())


def test_niveau_acces_inconnu_refuse():
    with pytest.raises(IntegrityError):
        _modifier(MemoireFactory(), niveau_acces="SECRET")


def test_niveau_acces_connu_accepte():
    production = MemoireFactory()
    _modifier(production, niveau_acces=NiveauAcces.CONFIDENTIEL)


@pytest.mark.parametrize("champs", [{"motif_retrait": "  "}, {"date_retrait": None}])
def test_retrait_motive_et_date(champs):
    production = forcer_statut(MemoireFactory(), Statut.RETIRE)
    with pytest.raises(IntegrityError):
        _modifier(production, **champs)
