from django.core.files.storage import FileSystemStorage


class StockagePrive(FileSystemStorage):
    """Stockage des documents déposés, hors MEDIA public : aucun fichier n'a d'URL directe.

    Les fichiers ne sont servis que par la vue de téléchargement, après contrôle des droits
    (productions.acces.peut_telecharger, phase 5).
    """

    def url(self, name):
        raise ValueError("Les documents privés n'ont pas d'URL publique.")
