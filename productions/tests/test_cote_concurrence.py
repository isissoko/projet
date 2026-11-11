"""RG06 : unicité de la cote sous concurrence réelle (transactions et connexions distinctes).

Ces tests valident vraiment leurs transactions (transaction=True) ; serialized_rollback
restaure ensuite les données des migrations (groupes de rôles).
"""

import threading

import pytest
from django.db import connection, transaction

from productions import services
from productions.models import CompteurCote, NiveauAcces, Production

from .factories import bibliothecaire, depot_valide

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

NOMBRE_DE_FILS = 8


def _en_parallele(fonction, arguments):
    """Lance fonction(argument) dans un fil par argument, démarrés ensemble ; renvoie
    (résultats, erreurs)."""
    depart = threading.Barrier(len(arguments))
    resultats, erreurs = [], []
    verrou = threading.Lock()

    def executer(argument):
        try:
            depart.wait()
            resultat = fonction(argument)
            with verrou:
                resultats.append(resultat)
        except Exception as erreur:
            with verrou:
                erreurs.append(erreur)
        finally:
            connection.close()  # chaque fil a sa propre connexion

    fils = [threading.Thread(target=executer, args=(a,)) for a in arguments]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=60)
    return resultats, erreurs


def _tirer(_):
    with transaction.atomic():
        return services.attribuer_cote("MEM", 2026)


@pytest.mark.parametrize("compteur_existant", [False, True])
def test_cotes_distinctes_et_consecutives_sous_concurrence(compteur_existant):
    if compteur_existant:
        CompteurCote.objects.create(code_type="MEM", annee=2026, dernier_numero=41)
    debut = 42 if compteur_existant else 1

    cotes, erreurs = _en_parallele(_tirer, range(NOMBRE_DE_FILS))

    assert not erreurs
    assert sorted(cotes) == [f"MEM-2026-{n:04d}" for n in range(debut, debut + NOMBRE_DE_FILS)]
    compteur = CompteurCote.objects.get(code_type="MEM", annee=2026)
    assert compteur.dernier_numero == debut + NOMBRE_DE_FILS - 1


def test_archivages_concurrents():
    biblio = bibliothecaire()
    productions = [depot_valide()[0] for _ in range(4)]

    def archiver(production):
        return services.archiver(biblio, production, NiveauAcces.LIBRE).cote

    cotes, erreurs = _en_parallele(archiver, productions)

    assert not erreurs
    assert sorted(cotes) == [f"MEM-2026-{n:04d}" for n in range(1, 5)]
    assert set(Production.objects.values_list("cote", flat=True)) == set(cotes)


def test_meme_travail_archive_une_seule_fois():
    biblio = bibliothecaire()
    production = depot_valide()[0]

    def archiver(_):
        copie = Production.objects.get(pk=production.pk)
        return services.archiver(biblio, copie, NiveauAcces.LIBRE).cote

    cotes, erreurs = _en_parallele(archiver, range(2))

    assert cotes == ["MEM-2026-0001"]
    assert len(erreurs) == 1 and isinstance(erreurs[0], services.TransitionInterdite)
    assert CompteurCote.objects.get().dernier_numero == 1


def test_attribuer_cote_exige_une_transaction():
    with pytest.raises(RuntimeError):
        services.attribuer_cote("MEM", 2026)
