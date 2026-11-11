"""Fichiers de test générés en mémoire (rien n'est écrit dans le dépôt Git)."""

import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from pypdf import PdfWriter


def octets_pdf(pages: int = 1, mot_de_passe: str | None = None) -> bytes:
    ecrivain = PdfWriter()
    for _ in range(pages):
        ecrivain.add_blank_page(width=595, height=842)
    if mot_de_passe:
        ecrivain.encrypt(mot_de_passe)
    tampon = io.BytesIO()
    ecrivain.write(tampon)
    return tampon.getvalue()


def pdf_valide(nom: str = "memoire.pdf", pages: int = 1) -> SimpleUploadedFile:
    return SimpleUploadedFile(nom, octets_pdf(pages), content_type="application/pdf")


def pdf_chiffre(nom: str = "protege.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(nom, octets_pdf(mot_de_passe="secret"), "application/pdf")


def docx_renomme_en_pdf(nom: str = "memoire.pdf") -> SimpleUploadedFile:
    """Vrai document Word (archive ZIP) dont seule l'extension est .pdf."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        archive.writestr("word/document.xml", "<w:document/>")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="application/pdf")


def faux_pdf_illisible(nom: str = "casse.pdf") -> SimpleUploadedFile:
    """Commence par %PDF- mais n'a aucune structure PDF."""
    return SimpleUploadedFile(nom, b"%PDF-1.7\n" + b"x" * 2000, content_type="application/pdf")


class FichierSansLecture:
    """Objet fichier qui échoue dès qu'on tente de le lire : prouve que la taille est
    contrôlée avant toute lecture."""

    name = "enorme.pdf"

    def __init__(self, taille: int):
        self.size = taille

    def read(self, *args):
        raise AssertionError("Le fichier n'aurait pas dû être lu.")

    seek = read
