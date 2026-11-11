from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import FormView, ListView

from .exceptions import ActionInterdite
from .forms import CompteForm, ConnexionForm, RechercheComptesForm, ReinitialisationForm
from .mixins import RoleRequisMixin
from .models import Utilisateur
from .roles import Role
from .services import changer_activation, creer_compte, modifier_compte

# Authentification ---------------------------------------------------------


class ConnexionView(auth_views.LoginView):
    template_name = "comptes/connexion.html"
    authentication_form = ConnexionForm
    redirect_authenticated_user = True


class DeconnexionView(auth_views.LogoutView):
    pass


class MotDePasseOublieView(auth_views.PasswordResetView):
    template_name = "comptes/mot_de_passe_oublie.html"
    form_class = ReinitialisationForm
    email_template_name = "comptes/emails/reinitialisation.txt"
    subject_template_name = "comptes/emails/reinitialisation_sujet.txt"
    success_url = reverse_lazy("comptes:reinitialisation_envoyee")


class ReinitialisationEnvoyeeView(auth_views.PasswordResetDoneView):
    template_name = "comptes/reinitialisation_envoyee.html"


class ReinitialisationConfirmationView(auth_views.PasswordResetConfirmView):
    template_name = "comptes/reinitialisation_confirmation.html"
    success_url = reverse_lazy("comptes:reinitialisation_terminee")


class ReinitialisationTermineeView(auth_views.PasswordResetCompleteView):
    template_name = "comptes/reinitialisation_terminee.html"


# Administration des comptes -----------------------------------------------


class AdministrateurRequisMixin(RoleRequisMixin):
    roles_requis = (Role.ADMINISTRATEUR,)


class ComptesListeView(AdministrateurRequisMixin, ListView):
    template_name = "comptes/liste.html"
    context_object_name = "comptes"
    paginate_by = 20

    def get_queryset(self):
        self.recherche = RechercheComptesForm(self.request.GET or None)
        comptes = Utilisateur.objects.prefetch_related("groups").order_by("last_name", "first_name")
        if self.recherche.is_valid():
            q = self.recherche.cleaned_data["q"].strip()
            if q:
                comptes = comptes.filter(
                    Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
                )
            if role := self.recherche.cleaned_data["role"]:
                comptes = comptes.filter(groups__name=role)
            if actif := self.recherche.cleaned_data["actif"]:
                comptes = comptes.filter(is_active=actif == "1")
        return comptes.distinct()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        parametres = self.request.GET.copy()
        parametres.pop("page", None)
        lignes = [
            (
                compte,
                [
                    compte.get_full_name() or compte.email,
                    compte.email,
                    ", ".join(compte.libelles_roles()),
                    "Actif" if compte.is_active else "Désactivé",
                ],
            )
            for compte in contexte["comptes"]
        ]
        contexte.update(
            recherche=self.recherche,
            parametres=parametres.urlencode(),
            lignes=lignes,
            entetes=["Nom", "E-mail", "Rôles", "État"],
            suivant=self.request.get_full_path(),
        )
        return contexte


class CompteCreerView(AdministrateurRequisMixin, FormView):
    template_name = "comptes/formulaire.html"
    form_class = CompteForm
    extra_context = {"titre": "Nouveau compte"}

    def form_valid(self, form):
        try:
            compte = creer_compte(
                **form.arguments_service(), url_base=self.request.build_absolute_uri("/")
            )
        except ActionInterdite as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Le compte de {compte} a été créé. Une invitation a été envoyée à {compte.email}.",
        )
        return redirect("comptes:liste")


class CompteModifierView(AdministrateurRequisMixin, FormView):
    template_name = "comptes/formulaire.html"
    form_class = CompteForm

    @cached_property
    def compte(self):
        # Chargé après le contrôle des rôles : un tiers reçoit 403, jamais 404.
        return get_object_or_404(
            Utilisateur.objects.select_related("profil_etudiant", "profil_enseignant"),
            pk=self.kwargs["pk"],
        )

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "utilisateur": self.compte}

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            titre=f"Modifier le compte de {self.compte}", compte=self.compte, **kwargs
        )

    def form_valid(self, form):
        try:
            modifier_compte(
                acteur=self.request.user, utilisateur=self.compte, **form.arguments_service()
            )
        except ActionInterdite as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Le compte de {self.compte} a été mis à jour.")
        return redirect("comptes:liste")


class CompteActivationView(AdministrateurRequisMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        compte = get_object_or_404(Utilisateur, pk=pk)
        actif = request.POST.get("actif") == "1"
        try:
            changer_activation(request.user, compte, actif)
        except ActionInterdite as erreur:
            messages.error(request, str(erreur))
        else:
            etat = "réactivé" if actif else "désactivé"
            messages.success(request, f"Le compte de {compte} a été {etat}.")
        suivant = request.POST.get("suivant", "")
        if suivant.startswith(reverse("comptes:liste")):
            return redirect(suivant)
        return redirect("comptes:liste")
