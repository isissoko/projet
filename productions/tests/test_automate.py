import itertools

import pytest
from django.utils import timezone

from comptes.tests.factories import UtilisateurFactory
from productions.models import Production, Statut
from productions.services import (
    TRANSITIONS,
    TRANSITIONS_AVEC_MOTIF,
    MotifObligatoire,
    TransitionInterdite,
    changer_statut,
)

from .factories import MemoireFactory

pytestmark = pytest.mark.django_db

TOUTES_LES_PAIRES = list(itertools.product(Statut.values, repeat=2))
PAIRES_INTERDITES = [p for p in TOUTES_LES_PAIRES if p not in TRANSITIONS]


def _production_au_statut(statut):
    production = MemoireFactory()
    Production.objects.filter(pk=production.pk).update(statut=statut)
    production.refresh_from_db()
    return production


def test_table_complete_de_l_automate():
    assert set(TRANSITIONS) == {
        (Statut.BROUILLON, Statut.SOUMIS),
        (Statut.SOUMIS, Statut.VALIDE),
        (Statut.SOUMIS, Statut.A_CORRIGER_ENCADREUR),
        (Statut.SOUMIS, Statut.REJETE),
        (Statut.A_CORRIGER_ENCADREUR, Statut.SOUMIS),
        (Statut.VALIDE, Statut.ARCHIVE),
        (Statut.VALIDE, Statut.A_CORRIGER_BIBLIOTHEQUE),
        (Statut.A_CORRIGER_BIBLIOTHEQUE, Statut.VALIDE),
        (Statut.ARCHIVE, Statut.RETIRE),
    }
    assert len(PAIRES_INTERDITES) == 64 - 9


@pytest.mark.parametrize(("origine", "cible"), list(TRANSITIONS))
def test_chaque_transition_prevue_est_autorisee(origine, cible):
    production = _production_au_statut(origine)
    acteur = UtilisateurFactory()
    changer_statut(production, cible, acteur, detail="Motif de test")
    production.refresh_from_db()
    assert production.statut == cible


@pytest.mark.parametrize(("origine", "cible"), PAIRES_INTERDITES)
def test_chaque_transition_non_prevue_leve_transition_interdite(origine, cible):
    production = _production_au_statut(origine)
    with pytest.raises(TransitionInterdite):
        changer_statut(production, cible, UtilisateurFactory(), detail="Motif")
    production.refresh_from_db()
    assert production.statut == origine


@pytest.mark.parametrize(("origine", "cible"), sorted(TRANSITIONS_AVEC_MOTIF))
def test_motif_obligatoire(origine, cible):
    production = _production_au_statut(origine)
    for motif in ["", "   "]:
        with pytest.raises(MotifObligatoire):
            changer_statut(production, cible, UtilisateurFactory(), detail=motif)
    production.refresh_from_db()
    assert production.statut == origine


def test_dates_de_soumission_et_d_archivage():
    production = _production_au_statut(Statut.BROUILLON)
    avant = timezone.now()
    changer_statut(production, Statut.SOUMIS, None)
    assert production.date_soumission >= avant
    production = _production_au_statut(Statut.VALIDE)
    changer_statut(production, Statut.ARCHIVE, None)
    production.refresh_from_db()
    assert production.date_archivage is not None


def test_statut_inconnu_interdit():
    production = _production_au_statut(Statut.BROUILLON)
    with pytest.raises(TransitionInterdite):
        changer_statut(production, "INCONNU", None)


def test_l_etat_en_base_fait_foi():
    """Une instance périmée en mémoire ne permet pas de contourner l'automate."""
    production = _production_au_statut(Statut.BROUILLON)
    Production.objects.filter(pk=production.pk).update(statut=Statut.ARCHIVE)
    with pytest.raises(TransitionInterdite):
        changer_statut(production, Statut.SOUMIS, None)  # production.statut vaut encore BROUILLON
