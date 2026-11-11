"""Espace enseignant : travaux à évaluer et écran d'évaluation (BF06, RG02)."""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, TemplateView

from comptes.exceptions import ActionInterdite
from comptes.mixins import RoleRequisMixin
from comptes.roles import Role

from . import acces, services
from .forms import AvisForm
from .models import Encadrement, Production, Statut

ONGLETS = {
    "a-evaluer": ("À évaluer", [Statut.SOUMIS]),
    "en-correction": ("En correction", [Statut.A_CORRIGER_ENCADREUR]),
    "traites": (
        "Traités",
        [
            Statut.VALIDE,
            Statut.REJETE,
            Statut.A_CORRIGER_BIBLIOTHEQUE,
            Statut.ARCHIVE,
            Statut.RETIRE,
        ],
    ),
}


class EnseignantRequisMixin(RoleRequisMixin):
    roles_requis = (Role.ENSEIGNANT,)


class TravauxAEvaluerView(EnseignantRequisMixin, ListView):
    template_name = "evaluation/liste.html"
    context_object_name = "travaux"
    paginate_by = 12

    def get_queryset(self):
        self.onglet = self.request.GET.get("onglet", "a-evaluer")
        if self.onglet not in ONGLETS:
            self.onglet = "a-evaluer"
        statuts = ONGLETS[self.onglet][1]
        return (
            acces.travaux_encadres(self.request.user)
            .filter(statut__in=statuts)
            .order_by("avis_donne", "-date_soumission", "-date_modification")
        )

    def get_context_data(self, **kwargs):
        base = acces.travaux_encadres(self.request.user)
        onglets = [
            {
                "cle": cle,
                "libelle": libelle,
                "nombre": base.filter(statut__in=statuts).count(),
                "actif": cle == self.onglet,
            }
            for cle, (libelle, statuts) in ONGLETS.items()
        ]
        return super().get_context_data(
            onglets=onglets, parametres=f"onglet={self.onglet}", **kwargs
        )


class EvaluationView(EnseignantRequisMixin, TemplateView):
    """Écran d'évaluation : visible par les seuls encadrants du travail (sinon 404)."""

    template_name = "evaluation/ecran.html"

    def obtenir(self):
        production = get_object_or_404(Production, pk=self.kwargs["pk"])
        encadrement = (
            Encadrement.objects.filter(
                production=production, enseignant__utilisateur=self.request.user
            )
            .select_related("enseignant")
            .first()
        )
        if encadrement is None or production.statut == Statut.BROUILLON:
            raise Http404("Travail introuvable.")
        return production.specifique(), encadrement

    def get_context_data(self, form=None, **kwargs):
        production, encadrement = self.obtenir()
        version = production.version_courante()
        deja = production.avis.filter(encadrement=encadrement, version=version).first()
        peut = acces.peut_evaluer(self.request.user, production) and deja is None
        return super().get_context_data(
            production=production,
            encadrement=encadrement,
            version=version,
            versions=production.versions.order_by("-numero"),
            contributions=production.contributions.select_related("contributeur"),
            encadrements=production.encadrements.select_related("enseignant__utilisateur"),
            mots_cles=production.mots_cles.all(),
            avis=production.avis.select_related("encadrement__enseignant__utilisateur", "version"),
            avis_sur_courante=deja,
            peut_evaluer=peut,
            form=form or (AvisForm() if peut else None),
            telechargeable=True,
            **kwargs,
        )

    def post(self, request, pk):
        production, _ = self.obtenir()
        form = AvisForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            avis = services.donner_avis(
                request.user,
                production,
                form.cleaned_data["avis"],
                form.cleaned_data["commentaire"],
            )
        except ActionInterdite as erreur:
            form.add_error(None, str(erreur))
            return self.render_to_response(self.get_context_data(form=form))
        if avis.est_du_directeur:
            production.refresh_from_db()
            messages.success(
                request,
                f"Avis enregistré. Le travail est désormais « {production.get_statut_display()} ».",
            )
        else:
            messages.success(
                request, "Avis consultatif enregistré ; il a été transmis au directeur."
            )
        return redirect("evaluation:ecran", pk=pk)
