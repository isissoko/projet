import hashlib

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from productions.validators import (
    TAILLE_BLOC,
    TAILLE_MAX_PDF,
    calculer_sha256,
    valider_pdf,
)

from .fichiers import (
    FichierSansLecture,
    docx_renomme_en_pdf,
    faux_pdf_illisible,
    octets_pdf,
    pdf_chiffre,
    pdf_valide,
)


def _code(fichier):
    with pytest.raises(ValidationError) as erreur:
        valider_pdf(fichier)
    return erreur.value.code, " ".join(erreur.value.messages)


def test_pdf_valide_accepte():
    valider_pdf(pdf_valide(pages=3))


def test_docx_renomme_en_pdf_refuse():
    code, message = _code(docx_renomme_en_pdf())
    assert code == "signature"
    assert "n'est pas un PDF" in message


def test_texte_avec_extension_pdf_refuse():
    code, _ = _code(SimpleUploadedFile("note.pdf", b"Bonjour, ceci est du texte."))
    assert code == "signature"


def test_signature_correcte_mais_contenu_illisible_refuse():
    code, message = _code(faux_pdf_illisible())
    assert code == "illisible"
    assert "endommagé ou illisible" in message


def test_pdf_chiffre_refuse():
    code, message = _code(pdf_chiffre())
    assert code == "chiffre"
    assert "mot de passe" in message


def test_fichier_vide_refuse():
    code, _ = _code(SimpleUploadedFile("vide.pdf", b""))
    assert code == "vide"


def test_fichier_de_plus_de_50_mo_refuse_en_memoire():
    gros = SimpleUploadedFile("gros.pdf", b"%PDF-1.7\n" + b"0" * (TAILLE_MAX_PDF - 8))
    assert gros.size == TAILLE_MAX_PDF + 1
    code, message = _code(gros)
    assert code == "taille"
    assert "taille maximale autorisée de 50 Mo" in message


def test_taille_controlee_avant_toute_lecture():
    code, _ = _code(FichierSansLecture(TAILLE_MAX_PDF + 1))
    assert code == "taille"


def test_fichier_de_exactement_50_mo_passe_le_controle_de_taille():
    # 50 Mo pile : la taille est acceptée, c'est la structure qui est ensuite refusée.
    fichier = SimpleUploadedFile("limite.pdf", b"%PDF-1.7\n" + b"0" * (TAILLE_MAX_PDF - 9))
    assert fichier.size == TAILLE_MAX_PDF
    code, _ = _code(fichier)
    assert code == "illisible"


def test_empreinte_sha256_correcte():
    contenu = octets_pdf(pages=2)
    fichier = SimpleUploadedFile("a.pdf", contenu)
    assert calculer_sha256(fichier) == hashlib.sha256(contenu).hexdigest()
    assert fichier.tell() == 0  # le fichier est rembobiné


def test_empreinte_calculee_par_blocs_de_64_ko():
    contenu = b"%PDF-" + bytes(range(256)) * 1000  # ≈ 256 Ko : plusieurs blocs
    assert len(contenu) > 3 * TAILLE_BLOC

    class Espion(SimpleUploadedFile):
        lectures = []

        def read(self, taille=-1):
            self.lectures.append(taille)
            return super().read(taille)

    fichier = Espion("b.pdf", contenu)
    assert calculer_sha256(fichier) == hashlib.sha256(contenu).hexdigest()
    assert set(Espion.lectures) == {TAILLE_BLOC}
