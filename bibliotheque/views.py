"""Espace bibliothèque : contrôle, archivage, accès, retrait, catalogue (BF07, BF08, BF12,
BF20). Aucune règle métier ici : contrôles dans productions/acces.py et productions/services.py.
"""

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.views.generic import FormView, ListView, TemplateView

from comptes.exceptions import ActionInterdite
from comptes.mixins import RoleRequisMixin
from comptes.roles import Role
from productions import acces, services
from productions.models import Statut, TypeProduction

from .forms import AccesForm, MetadonneesBibliothequeForm, MotifForm

ONGLETS = {
    "a-controler": ("À contrôler", [Statut.VALIDE]),
    "corrections": ("Corrections en attente", [Statut.A_CORRIGER_BIBLIOTHEQUE]),
}

AIDE_CORRECTIONS = (
    "Ce que l'auteur doit corriger : il sera prévenu et déposera une nouvelle version."
)
AIDE_RETRAIT = (
    "Visible par les auteurs, les encadrants et la bibliothèque. Le retrait est définitif."
)


class BibliothecaireRequisMixin(RoleRequisMixin):
    roles_requis = (Role.BIBLIOTHECAIRE,)


def obtenir_production(user, pk):
    """Travail géré par la bibliothèque (validé, à corriger, archivé ou retiré), sinon 404."""
    production = (acces.productions_a_controler(user) | acces.catalogue(user)).filter(pk=pk).first()
    if production is None:
        raise Http404("Travail introuvable.")
    return production.specifique()


# Listes ---------------------------------------------------------------------------------


class AControlerView(BibliothecaireRequisMixin, ListView):
    template_name = "bibliotheque/a_controler.html"
    context_object_name = "travaux"
    paginate_by = 12

    def get_queryset(self):
        self.onglet = self.request.GET.get("onglet", "a-controler")
        if self.onglet not in ONGLETS:
            self.onglet = "a-controler"
        return (
            acces.productions_a_controler(self.request.user)
            .filter(statut__in=ONGLETS[self.onglet][1])
            .select_related("filiere", "annee_academique")
            .order_by("date_modification")  # le plus ancien d'abord
        )

    def get_context_data(self, **kwargs):
        base = acces.productions_a_controler(self.request.user)
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


class CatalogueView(BibliothecaireRequisMixin, ListView):
    template_name = "bibliotheque/catalogue.html"
    context_object_name = "travaux"
    paginate_by = 20

    def get_queryset(self):
        parametres = self.request.GET
        self.q = parametres.get("q", "").strip()[:100]
        self.statut = parametres.get("statut", "")
        self.type = parametres.get("type", "")
        travaux = acces.catalogue(self.request.user)
        if self.q:
            travaux = travaux.filter(Q(titre__icontains=self.q) | Q(cote__icontains=self.q))
        if self.statut in (Statut.ARCHIVE, Statut.RETIRE):
            travaux = travaux.filter(statut=self.statut)
        if self.type in TypeProduction.values:
            travaux = travaux.filter(type_production=self.type)
        return travaux.order_by("-date_archivage", "-pk")

    def get_context_data(self, **kwargs):
        filtres = {"q": self.q, "statut": self.statut, "type": self.type}
        parametres = "&".join(f"{cle}={valeur}" for cle, valeur in filtres.items() if valeur)
        return super().get_context_data(
            filtres=filtres,
            statuts=[(Statut.ARCHIVE, "Archivés"), (Statut.RETIRE, "Retirés")],
            types=TypeProduction.choices,
            parametres=parametres,
            **kwargs,
        )


# Écran de contrôle et de gestion -----------------------------------------------------------


class ControleView(BibliothecaireRequisMixin, TemplateView):
    """Contrôle d'un travail validé (archiver ou demander des corrections) et gestion d'un
    travail archivé (accès, retrait). Une seule page, des formulaires selon le statut."""

    template_name = "bibliotheque/controle.html"

    @cached_property
    def production(self):
        return obtenir_production(self.request.user, self.kwargs["pk"])

    def formulaires(self, actif=None, formulaire=None):
        p = self.production
        formulaires = {}
        if p.statut == Statut.VALIDE:
            formulaires["archiver"] = AccesForm(prefix="archivage")
            formulaires["corrections"] = MotifForm(prefix="corrections", aide=AIDE_CORRECTIONS)
        elif p.statut == Statut.ARCHIVE:
            formulaires["acces"] = AccesForm(
                prefix="acces",
                embargo_actuel=p.date_fin_embargo,
                initial={"niveau_acces": p.niveau_acces, "date_fin_embargo": p.date_fin_embargo},
            )
            formulaires["retirer"] = MotifForm(prefix="retrait", aide=AIDE_RETRAIT)
        if actif in formulaires and formulaire is not None:
            formulaires[actif] = formulaire
        return formulaires

    def get_context_data(self, **kwargs):
        p = self.production
        user = self.request.user
        kwargs.setdefault("formulaires", self.formulaires())
        return super().get_context_data(
            production=p,
            version=p.version_courante(),
            versions=p.versions.order_by("-numero"),
            contributions=p.contributions.select_related("contributeur"),
            encadrements=p.encadrements.select_related("enseignant__utilisateur"),
            mots_cles=p.mots_cles.all(),
            avis=p.avis.select_related("encadrement__enseignant__utilisateur", "version"),
            verifications=p.verifications.select_related("bibliothecaire", "version"),
            motif=services.motif_corrections(p),
            telechargeable=True,
            embargo_actif=acces.embargo_actif(p),
            metadonnees_modifiables=p.statut in services.STATUTS_METADONNEES_BIBLIOTHEQUE,
            est_auteur=acces.est_auteur(user, p),
            **kwargs,
        )

    def post(self, request, pk):
        action = request.POST.get("action")
        p = self.production
        user = request.user
        if action == "archiver":
            form = AccesForm(request.POST, prefix="archivage")
        elif action == "acces":
            form = AccesForm(request.POST, prefix="acces", embargo_actuel=p.date_fin_embargo)
        elif action == "corrections":
            form = MotifForm(request.POST, prefix="corrections", aide=AIDE_CORRECTIONS)
        elif action == "retirer":
            form = MotifForm(request.POST, prefix="retrait", aide=AIDE_RETRAIT)
        else:
            messages.error(request, "Action inconnue.")
            return redirect("bibliotheque:controle", pk=pk)

        if form.is_valid():
            d = form.cleaned_data
            try:
                if action == "archiver":
                    services.archiver(user, p, d["niveau_acces"], d["date_fin_embargo"])
                    message = f"Travail archivé sous la cote {p.cote}."
                elif action == "acces":
                    services.modifier_acces(user, p, d["niveau_acces"], d["date_fin_embargo"])
                    message = "Niveau d'accès enregistré."
                elif action == "corrections":
                    services.demander_corrections_bibliotheque(user, p, d["motif"])
                    message = "Corrections demandées : le travail attend une version corrigée."
                else:
                    services.retirer(user, p, d["motif"])
                    message = "Travail retiré du catalogue."
            except ActionInterdite as erreur:
                form.add_error(None, str(erreur))
            else:
                messages.success(request, message)
                return redirect("bibliotheque:controle", pk=pk)
        contexte = self.get_context_data(formulaires=self.formulaires(action, form), actif=action)
        return self.render_to_response(contexte)


class MetadonneesView(BibliothecaireRequisMixin, FormView):
    """Correction des métadonnées par la bibliothèque (BF12)."""

    template_name = "bibliotheque/metadonnees.html"
    form_class = MetadonneesBibliothequeForm

    @cached_property
    def production(self):
        return obtenir_production(self.request.user, self.kwargs["pk"])

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if (
            request.user.a_role(Role.BIBLIOTHECAIRE)
            and self.production.statut not in services.STATUTS_METADONNEES_BIBLIOTHEQUE
        ):
            messages.info(request, "Les métadonnées de ce travail ne peuvent plus être modifiées.")
            return redirect("bibliotheque:controle", pk=self.production.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "production": self.production}

    def get_context_data(self, **kwargs):
        return super().get_context_data(production=self.production, **kwargs)

    def form_valid(self, form):
        try:
            services.modifier_metadonnees(
                self.request.user,
                self.production,
                form.donnees_service(),
                form.cleaned_data["mots_cles"],
            )
        except ActionInterdite as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Métadonnées enregistrées.")
        return redirect(reverse("bibliotheque:controle", kwargs={"pk": self.production.pk}))
