from functools import reduce
from operator import or_

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from comptes.exceptions import ActionInterdite
from comptes.mixins import RoleRequisMixin
from comptes.roles import Role

from . import services
from .models import AnneeAcademique
from .registre import TYPES, type_element


class ReferentielMixin(RoleRequisMixin):
    roles_requis = (Role.BIBLIOTHECAIRE, Role.ADMINISTRATEUR)

    def dispatch(self, request, *args, **kwargs):
        if "type" in kwargs:
            self.type = type_element(kwargs["type"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        if hasattr(self, "type"):
            contexte["type"] = self.type
        return contexte


class ReferentielAccueilView(ReferentielMixin, TemplateView):
    template_name = "referentiel/accueil.html"

    def get_context_data(self, **kwargs):
        types = [
            {
                "type": t,
                "actifs": t.modele.objects.filter(actif=True).count(),
                "inactifs": t.modele.objects.filter(actif=False).count(),
            }
            for t in TYPES.values()
        ]
        return super().get_context_data(
            types=types,
            annee_courante=AnneeAcademique.objects.filter(courante=True).first(),
            **kwargs,
        )


def _valeur_affichee(element, attribut):
    valeur = getattr(element, attribut)
    if isinstance(valeur, bool):
        return "Oui" if valeur else ""
    return valeur


class ElementListeView(ReferentielMixin, ListView):
    template_name = "referentiel/liste.html"
    paginate_by = 25

    def get_queryset(self):
        elements = self.type.queryset()
        self.q = self.request.GET.get("q", "").strip()
        if self.q and self.type.recherche:
            elements = elements.filter(
                reduce(or_, (Q(**{f"{c}__icontains": self.q}) for c in self.type.recherche))
            )
        self.etat = self.request.GET.get("etat", "actifs")
        if self.etat == "actifs":
            elements = elements.filter(actif=True)
        elif self.etat == "inactifs":
            elements = elements.filter(actif=False)
        return elements

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["lignes"] = [
            (element, [_valeur_affichee(element, a) for _, a in self.type.colonnes])
            for element in contexte["object_list"]
        ]
        parametres = self.request.GET.copy()
        parametres.pop("page", None)
        contexte.update(
            q=self.q,
            etat=self.etat,
            parametres=parametres.urlencode(),
            type_entetes=[entete for entete, _ in self.type.colonnes],
        )
        return contexte


class ElementFormulaireView(ReferentielMixin, FormView):
    template_name = "referentiel/formulaire.html"
    element = None

    def get_form_class(self):
        return self.type.formulaire

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.element}

    def form_valid(self, form):
        try:
            element = services.enregistrer(form)
        except ActionInterdite as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"« {element} » a été enregistré.")
        return redirect("referentiel:liste", type=self.type.slug)


class ElementCreerView(ElementFormulaireView):
    def get_context_data(self, **kwargs):
        return super().get_context_data(titre=self.type.libelle_nouveau, **kwargs)


class ElementModifierView(ElementFormulaireView):
    @cached_property
    def element(self):
        # Chargé après le contrôle des rôles : un tiers reçoit 403, jamais 404.
        return get_object_or_404(self.type.modele, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            titre=f"Modifier « {self.element} »", element=self.element, **kwargs
        )


class ElementActionView(ReferentielMixin, View):
    """Actions POST : supprimer (ou désactiver si utilisé), réactiver, rendre courante."""

    http_method_names = ["post"]

    def post(self, request, type, pk, action):
        element = get_object_or_404(self.type.modele, pk=pk)
        try:
            if action == "supprimer":
                resultat = services.supprimer_ou_desactiver(element)
                if resultat == services.SUPPRIME:
                    messages.success(request, f"« {element} » a été supprimé.")
                else:
                    messages.success(
                        request, f"« {element} » est utilisé : il a été désactivé, pas supprimé."
                    )
            elif action == "reactiver":
                services.reactiver(element)
                messages.success(request, f"« {element} » a été réactivé.")
            elif action == "courante" and isinstance(element, AnneeAcademique):
                services.definir_annee_courante(element)
                messages.success(request, f"{element} est désormais l'année courante.")
            else:
                messages.error(request, "Action inconnue.")
        except ActionInterdite as erreur:
            messages.error(request, str(erreur))
        return redirect("referentiel:liste", type=self.type.slug)
