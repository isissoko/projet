"""Exceptions métier partagées par les services."""


class ActionInterdite(Exception):
    """Action refusée par une règle de gestion ; le message est affichable à l'utilisateur."""
