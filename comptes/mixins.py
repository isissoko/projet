from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


class RoleRequisMixin(AccessMixin):
    """Réserve une vue aux utilisateurs ayant au moins un des rôles de `roles_requis`.

    Visiteur non connecté : redirection vers la page de connexion.
    Utilisateur connecté sans le rôle : 403 (gabarit templates/403.html).
    """

    roles_requis: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not self.roles_requis:
            raise ValueError(f"{type(self).__name__} doit définir roles_requis.")
        if not request.user.a_un_role(*self.roles_requis):
            raise PermissionDenied("Votre compte n'a pas le rôle requis pour cette page.")
        return super().dispatch(request, *args, **kwargs)
