"""Validation des documents déposés (RG03) et calcul d'empreinte (RG04)."""

import hashlib

from django.core.exceptions import ValidationError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .formats import taille_lisible

TAILLE_MAX_PDF = 50 * 1024 * 1024  # 50 Mo
TAILLE_BLOC = 64 * 1024  # lecture par blocs de 64 Ko
SIGNATURE_PDF = b"%PDF-"


def valider_taille(fichier, taille_max: int = TAILLE_MAX_PDF) -> None:
    """Vérifie la taille annoncée sans lire le contenu."""
    taille = getattr(fichier, "size", None)
    if taille is None:
        raise ValidationError("Impossible de déterminer la taille du fichier.", code="taille")
    if taille == 0:
        raise ValidationError("Le fichier est vide.", code="vide")
    if taille > taille_max:
        raise ValidationError(
            f"Le fichier dépasse la taille maximale autorisée de {taille_lisible(taille_max)} "
            f"(il fait {taille_lisible(taille)}).",
            code="taille",
        )


def valider_pdf(fichier) -> None:
    """Accepte uniquement un vrai PDF lisible de 50 Mo au plus.

    1. taille (sans lecture) ; 2. signature %PDF- en début de fichier ;
    3. ouverture par pypdf (structure lisible, au moins une page, non chiffré).
    L'extension du nom de fichier n'est pas prise en compte.
    """
    valider_taille(fichier)

    fichier.seek(0)
    entete = fichier.read(len(SIGNATURE_PDF))
    fichier.seek(0)
    if entete != SIGNATURE_PDF:
        raise ValidationError(
            "Ce fichier n'est pas un PDF (son contenu ne commence pas par « %PDF- »). "
            "Enregistrez votre document au format PDF puis déposez-le à nouveau.",
            code="signature",
        )

    try:
        lecteur = PdfReader(fichier, strict=False)
        if lecteur.is_encrypted:
            raise ValidationError(
                "Ce PDF est protégé par un mot de passe. Déposez une version non protégée.",
                code="chiffre",
            )
        nombre_pages = len(lecteur.pages)
    except ValidationError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, OSError, RecursionError) as erreur:
        raise ValidationError(
            "Ce PDF est endommagé ou illisible. Exportez-le à nouveau depuis votre traitement "
            "de texte.",
            code="illisible",
        ) from erreur
    finally:
        fichier.seek(0)

    if nombre_pages == 0:
        raise ValidationError("Ce PDF ne contient aucune page.", code="sans_page")


def calculer_sha256(fichier) -> str:
    """Empreinte SHA-256 calculée par blocs de 64 Ko, sans charger le fichier en mémoire."""
    empreinte = hashlib.sha256()
    fichier.seek(0)
    while bloc := fichier.read(TAILLE_BLOC):
        empreinte.update(bloc)
    fichier.seek(0)
    return empreinte.hexdigest()
