import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.views import View

from comptes.mixins import RoleRequisMixin
from comptes.roles import Role

from .factories import UtilisateurFactory

pytestmark = pytest.mark.django_db


def test_migration_cree_les_quatre_groupes():
    noms = set(Group.objects.values_list("name", flat=True))
    assert {"ETUDIANT", "ENSEIGNANT", "BIBLIOTHECAIRE", "ADMINISTRATEUR"} <= noms


def test_a_role_et_cumul():
    u = UtilisateurFactory(roles=[Role.ENSEIGNANT, Role.BIBLIOTHECAIRE])
    assert u.a_role(Role.ENSEIGNANT)
    assert u.a_role(Role.BIBLIOTHECAIRE)
    assert not u.a_role(Role.ADMINISTRATEUR)
    assert u.a_un_role(Role.ADMINISTRATEUR, Role.BIBLIOTHECAIRE)
    assert u.libelles_roles() == ["Enseignant", "Bibliothécaire"]


def test_a_role_faux_pour_un_compte_desactive():
    u = UtilisateurFactory(roles=[Role.ADMINISTRATEUR], is_active=False)
    assert not u.a_role(Role.ADMINISTRATEUR)
    assert u.roles == {Role.ADMINISTRATEUR}  # le rôle reste affiché dans la liste


def test_roles_lus_une_seule_fois(django_assert_num_queries):
    u = UtilisateurFactory(roles=[Role.ETUDIANT])
    u.oublier_roles()
    with django_assert_num_queries(1):
        u.a_role(Role.ETUDIANT)
        u.a_role(Role.ENSEIGNANT)
        u.a_un_role(Role.ADMINISTRATEUR)


class VueEnseignant(RoleRequisMixin, View):
    roles_requis = (Role.ENSEIGNANT,)

    def get(self, request):
        return HttpResponse("espace enseignant")


class VueBibliotheque(RoleRequisMixin, View):
    roles_requis = (Role.BIBLIOTHECAIRE,)

    def get(self, request):
        return HttpResponse("espace bibliothèque")


def _appeler(vue, rf, utilisateur):
    requete = rf.get("/espace/")
    requete.user = utilisateur
    return vue.as_view()(requete)


def test_mixin_utilisateur_deux_roles_accede_aux_deux_espaces(rf):
    u = UtilisateurFactory(roles=[Role.ENSEIGNANT, Role.BIBLIOTHECAIRE])
    assert _appeler(VueEnseignant, rf, u).status_code == 200
    assert _appeler(VueBibliotheque, rf, u).status_code == 200


def test_mixin_role_manquant_leve_403(rf):
    u = UtilisateurFactory(roles=[Role.ENSEIGNANT])
    assert _appeler(VueEnseignant, rf, u).status_code == 200
    with pytest.raises(PermissionDenied):
        _appeler(VueBibliotheque, rf, u)


def test_mixin_visiteur_redirige_vers_connexion(rf):
    reponse = _appeler(VueEnseignant, rf, AnonymousUser())
    assert reponse.status_code == 302
    assert reponse.url.startswith("/comptes/connexion/?next=")


def test_mixin_sans_roles_requis_est_une_erreur_de_programmation(rf):
    class VueMalConfiguree(RoleRequisMixin, View):
        pass

    with pytest.raises(ValueError):
        _appeler(VueMalConfiguree, rf, UtilisateurFactory(roles=[Role.ETUDIANT]))
