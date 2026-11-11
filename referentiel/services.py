"""Services du référentiel : enregistrement, année courante, suppression ou désactivation."""

from django.db import transaction
from django.db.models import ProtectedError, RestrictedError

from comptes.exceptions import ActionInterdite

from .models import AnneeAcademique

SUPPRIME = "supprime"
DESACTIVE = "desactive"


def est_utilise(element) -> bool:
    """Vrai si un autre enregistrement fait référence à cet élément (clé étrangère, M2M…)."""
    for relation in element._meta.related_objects:
        nom = relation.get_accessor_name()
        if relation.one_to_one:
            if relation.related_model.objects.filter(**{relation.field.name: element}).exists():
                return True
        elif getattr(element, nom).exists():
            return True
    return False


@transaction.atomic
def definir_annee_courante(annee: AnneeAcademique) -> AnneeAcademique:
    """Fait de `annee` l'unique année courante (verrouillage pour éviter les courses)."""
    if not annee.actif:
        raise ActionInterdite("Une année désactivée ne peut pas devenir l'année courante.")
    list(AnneeAcademique.objects.select_for_update().filter(courante=True))
    AnneeAcademique.objects.filter(courante=True).exclude(pk=annee.pk).update(courante=False)
    annee.courante = True
    if annee.pk:
        AnneeAcademique.objects.filter(pk=annee.pk).update(courante=True)
    else:
        annee.save()
    return annee


@transaction.atomic
def enregistrer(formulaire):
    """Enregistre un formulaire du référentiel (création ou modification)."""
    element = formulaire.save(commit=False)
    if isinstance(element, AnneeAcademique) and element.courante:
        element.courante = False
        element.save()
        definir_annee_courante(element)
    else:
        element.save()
    formulaire.save_m2m()
    return element


@transaction.atomic
def supprimer_ou_desactiver(element) -> str:
    """Supprime l'élément s'il n'est référencé nulle part, sinon le désactive."""
    if isinstance(element, AnneeAcademique) and element.courante:
        raise ActionInterdite("L'année courante ne peut être ni supprimée ni désactivée.")
    if not est_utilise(element):
        try:
            with transaction.atomic():
                element.delete()
            return SUPPRIME
        except (ProtectedError, RestrictedError):
            pass  # référence apparue entre-temps : on désactive
    element.actif = False
    element.save(update_fields=["actif"])
    return DESACTIVE


@transaction.atomic
def reactiver(element) -> None:
    element.actif = True
    element.save(update_fields=["actif"])
