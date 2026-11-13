"""Vues du dépôt. Aucune règle métier ici : les contrôles sont dans acces.py et services.py."""

from functools import reduce
from operator import and_

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.http import content_disposition_header
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from comptes.exceptions import ActionInterdite
from comptes.mixins import RoleRequisMixin
from comptes.models import ProfilEnseignant
from comptes.roles import Role

from . import acces, services
from .forms import (
    AjoutEncadrantForm,
    CoauteurForm,
    FichierForm,
    MetadonneesForm,
    RechercheEnseignantForm,
    VersionCorrigeeForm,
)
from .models import Production, Statut, VersionDocument

ETAPES = [
    (1, "Type et métadonnées"),
    (2, "Auteurs et encadrants"),
    (3, "Fichier PDF"),
    (4, "Récapitulatif"),
    (5, "Soumission"),
]


def obtenir_production_visible(user, pk) -> Production:
    """Production dont la fiche est visible, sinon 404 (RG11 : jamais 403)."""
    production = get_object_or_404(Production, pk=pk)
    if not acces.peut_voir_fiche(user, production):
        raise Http404("Production introuvable.")
    return production.specifique()


class EtudiantRequisMixin(RoleRequisMixin):
    roles_requis = (Role.ETUDIANT,)


# Mes dépôts et détail ------------------------------------------------------------------


class MesDepotsView(EtudiantRequisMixin, ListView):
    template_name = "productions/mes_depots.html"
    context_object_name = "productions"
    paginate_by = 12

    def get_queryset(self):
        return acces.mes_depots(self.request.user).order_by("-date_modification")


def chronologie(production) -> list[dict]:
    """Étapes datées du dépôt. Phase 6 : remplacée par les entrées du JournalAction."""
    evenements = [{"date": production.date_creation, "libelle": "Brouillon créé"}]
    for version in production.versions.all():
        evenements.append(
            {"date": version.date_depot, "libelle": f"Version {version.numero} déposée"}
        )
    if production.date_soumission:
        evenements.append(
            {"date": production.date_soumission, "libelle": "Soumis à l'encadreur (dernière fois)"}
        )
    for avis in production.avis.select_related("encadrement__enseignant__utilisateur", "version"):
        evenements.append(
            {
                "date": avis.date,
                "libelle": f"Avis {avis.get_avis_display().lower()} de "
                f"{avis.encadrement.enseignant.utilisateur} "
                f"({avis.encadrement.get_role_display().lower()}, version {avis.version.numero})",
                "detail": avis.commentaire,
            }
        )
    for verification in production.verifications.select_related("version"):
        conforme = verification.decision == "CONFORME"
        evenements.append(
            {
                "date": verification.date,
                "libelle": (
                    "Contrôle de la bibliothèque : conforme"
                    if conforme
                    else "Corrections demandées par la bibliothèque"
                )
                + f" (version {verification.version.numero})",
                "detail": verification.motif,
            }
        )
    if production.date_archivage:
        evenements.append(
            {
                "date": production.date_archivage,
                "libelle": f"Archivé sous la cote {production.cote}",
            }
        )
    if production.date_retrait:
        evenements.append(
            {
                "date": production.date_retrait,
                "libelle": "Retiré",
                "detail": production.motif_retrait,
            }
        )
    return sorted(evenements, key=lambda e: e["date"])


class DepotDetailView(LoginRequiredMixin, TemplateView):
    template_name = "productions/detail.html"

    def get(self, request, *args, **kwargs):
        production = obtenir_production_visible(request.user, kwargs["pk"])
        if production.est_archive and not acces.est_proche(request.user, production):
            return redirect("recherche:fiche", pk=production.pk)  # fiche publique
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        user = self.request.user
        production = obtenir_production_visible(user, kwargs["pk"])
        modifiable = acces.peut_modifier_brouillon(user, production)
        return super().get_context_data(
            production=production,
            versions=acces.versions_consultables(user, production),
            contributions=production.contributions.select_related("contributeur"),
            encadrements=production.encadrements.select_related("enseignant__utilisateur"),
            mots_cles=production.mots_cles.all(),
            chronologie=chronologie(production) if acces.est_proche(user, production) else [],
            modifiable=modifiable,
            manquants=services.elements_manquants(production) if modifiable else [],
            avis=production.avis.select_related("encadrement__enseignant__utilisateur", "version"),
            telechargeable=acces.peut_telecharger(user, production),
            raison_indisponibilite=acces.raison_indisponibilite(user, production),
            embargo_actif=acces.embargo_actif(production),
            est_proche=acces.est_proche(user, production),
            correction_attendue=production.statut in services.STATUT_APRES_VERSION_CORRIGEE
            and acces.est_auteur_principal(user, production),
            motif=services.motif_corrections(production),
            evaluable=acces.est_encadrant(user, production),
            est_auteur=acces.est_auteur(user, production),
            **kwargs,
        )


class DepotSupprimerView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        production = obtenir_production_visible(request.user, pk)
        titre = production.titre
        try:
            services.supprimer_brouillon(request.user, production)
        except ActionInterdite as erreur:
            messages.error(request, str(erreur))
            return redirect("productions:detail", pk=pk)
        messages.success(request, f"Le brouillon « {titre} » a été supprimé.")
        return redirect("productions:mes_depots")


# Dépôt en étapes ------------------------------------------------------------------------


class EtapeMixin:
    etape = 1

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        production = getattr(self, "production", None)
        etapes = [
            {
                "numero": numero,
                "libelle": libelle,
                "url": reverse(f"productions:etape{numero}", kwargs={"pk": production.pk})
                if production
                else "",
            }
            for numero, libelle in ETAPES
        ]
        contexte.update(etapes=etapes, etape=self.etape, titre_etape=dict(ETAPES)[self.etape])
        return contexte


class BrouillonMixin(LoginRequiredMixin, EtapeMixin):
    """Étapes 1 à 5 d'un brouillon existant : 404 si invisible, retour au détail si non
    modifiable (co-auteur, ou travail déjà soumis)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not acces.peut_modifier_brouillon(request.user, self.production):
            if self.production.statut == Statut.BROUILLON:
                messages.info(request, "Seul l'auteur principal peut modifier ce dépôt.")
            else:
                messages.info(request, "Ce travail a été soumis : il ne peut plus être modifié.")
            return redirect("productions:detail", pk=self.production.pk)
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def production(self):
        return obtenir_production_visible(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return super().get_context_data(production=self.production, **kwargs)

    def url_etape(self, numero):
        return reverse(f"productions:etape{numero}", kwargs={"pk": self.production.pk})


class NouveauDepotView(EtudiantRequisMixin, EtapeMixin, FormView):
    template_name = "productions/etape1.html"
    form_class = MetadonneesForm
    etape = 1

    def form_valid(self, form):
        try:
            production = services.creer_brouillon(
                self.request.user,
                form.cleaned_data["type_production"],
                form.donnees_service(),
                form.cleaned_data["mots_cles"],
            )
        except ActionInterdite as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Brouillon enregistré.")
        return redirect("productions:etape2", pk=production.pk)


class Etape1View(BrouillonMixin, FormView):
    template_name = "productions/etape1.html"
    form_class = MetadonneesForm
    etape = 1

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "production": self.production}

    def form_valid(self, form):
        try:
            services.modifier_brouillon(
                self.request.user,
                self.production,
                form.donnees_service(),
                form.cleaned_data["mots_cles"],
            )
        except ActionInterdite as erreur:
            form.add_error(None, str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, "Métadonnées enregistrées.")
        return redirect(self.url_etape(2))


class Etape2View(BrouillonMixin, TemplateView):
    template_name = "productions/etape2.html"
    etape = 2

    def get_context_data(self, coauteur_form=None, **kwargs):
        recherche = RechercheEnseignantForm(self.request.GET or None)
        resultats = []
        if recherche.is_valid():
            resultats = self.rechercher_enseignants(recherche.cleaned_data["q"])
        production = self.production
        return super().get_context_data(
            contributions=production.contributions.select_related("contributeur__utilisateur"),
            encadrements=production.encadrements.select_related("enseignant__utilisateur"),
            coauteur_form=coauteur_form or CoauteurForm(),
            recherche=recherche,
            resultats=resultats,
            a_un_directeur=production.encadrements.filter(role="DIRECTEUR").exists(),
            **kwargs,
        )

    def rechercher_enseignants(self, texte):
        mots = texte.split()
        filtre = reduce(
            and_,
            (
                Q(utilisateur__first_name__icontains=m) | Q(utilisateur__last_name__icontains=m)
                for m in mots
            ),
        )
        deja = self.production.encadrements.values_list("enseignant_id", flat=True)
        return (
            ProfilEnseignant.objects.filter(
                filtre, utilisateur__is_active=True, utilisateur__groups__name=Role.ENSEIGNANT
            )
            .exclude(pk__in=deja)
            .exclude(utilisateur=self.request.user)
            .select_related("utilisateur", "departement")
            .order_by("utilisateur__last_name", "utilisateur__first_name")
            .distinct()[:10]
        )

    def post(self, request, pk):
        action = request.POST.get("action")
        coauteur_form = None
        try:
            if action == "ajouter_coauteur":
                coauteur_form = CoauteurForm(request.POST)
                if coauteur_form.is_valid():
                    services.ajouter_coauteur(
                        request.user, self.production, coauteur_form.donnees_service()
                    )
                    messages.success(request, "Co-auteur ajouté.")
                    return redirect(self.url_etape(2))
                return self.render_to_response(self.get_context_data(coauteur_form=coauteur_form))
            if action == "retirer_coauteur":
                services.retirer_coauteur(
                    request.user, self.production, request.POST.get("contribution")
                )
                messages.success(request, "Co-auteur retiré.")
            elif action == "ajouter_encadrant":
                form = AjoutEncadrantForm(request.POST)
                enseignant = ProfilEnseignant.objects.filter(
                    pk=request.POST.get("enseignant")
                ).first()
                if not form.is_valid() or enseignant is None:
                    raise ActionInterdite("Choisissez un enseignant et un rôle.")
                services.ajouter_encadrant(
                    request.user, self.production, enseignant, form.cleaned_data["role"]
                )
                messages.success(request, f"{enseignant.utilisateur} a été ajouté(e).")
            elif action == "retirer_encadrant":
                services.retirer_encadrant(
                    request.user, self.production, request.POST.get("encadrement")
                )
                messages.success(request, "Encadrant retiré.")
            else:
                messages.error(request, "Action inconnue.")
        except (ActionInterdite, ValueError) as erreur:
            messages.error(request, str(erreur) or "Action impossible.")
        return redirect(self.url_etape(2))


class Etape3View(BrouillonMixin, FormView):
    template_name = "productions/etape3.html"
    form_class = FichierForm
    etape = 3

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            versions=self.production.versions.order_by("-numero"), **kwargs
        )

    def form_valid(self, form):
        try:
            version = services.ajouter_version(
                self.request.user, self.production, form.cleaned_data["fichier"]
            )
        except ActionInterdite as erreur:
            form.add_error("fichier", str(erreur))
            return self.form_invalid(form)
        messages.success(self.request, f"Version {version.numero} enregistrée.")
        return redirect(self.url_etape(4))


class Etape4View(BrouillonMixin, TemplateView):
    template_name = "productions/etape4.html"
    etape = 4

    def get_context_data(self, **kwargs):
        production = self.production
        return super().get_context_data(
            contributions=production.contributions.select_related("contributeur"),
            encadrements=production.encadrements.select_related("enseignant__utilisateur"),
            mots_cles=production.mots_cles.all(),
            version=production.version_courante(),
            manquants=services.elements_manquants(production),
            **kwargs,
        )


class Etape5View(BrouillonMixin, TemplateView):
    template_name = "productions/etape5.html"
    etape = 5

    def get_context_data(self, **kwargs):
        kwargs.setdefault("manquants", services.elements_manquants(self.production))
        return super().get_context_data(**kwargs)

    def post(self, request, pk):
        try:
            services.soumettre(request.user, self.production)
        except services.SoumissionIncomplete as erreur:
            return self.render_to_response(self.get_context_data(manquants=erreur.manquants))
        except ActionInterdite as erreur:
            messages.error(request, str(erreur))
            return redirect(self.url_etape(5))
        messages.success(request, "Votre travail a été soumis à votre directeur.")
        return redirect("productions:detail", pk=pk)


# Version corrigée et téléchargement (phase 3) ---------------------------------------------


class VersionCorrigeeView(LoginRequiredMixin, FormView):
    template_name = "productions/version_corrigee.html"
    form_class = VersionCorrigeeForm

    @cached_property
    def production(self):
        return obtenir_production_visible(self.request.user, self.kwargs["pk"])

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        production = self.production
        if production.statut not in services.STATUT_APRES_VERSION_CORRIGEE and (
            request.method == "GET"
        ):
            messages.info(request, "Aucune correction n'est attendue sur ce travail.")
            return redirect("productions:detail", pk=production.pk)
        if not acces.est_auteur_principal(request.user, production):
            messages.info(request, "Seul l'auteur principal peut déposer la version corrigée.")
            return redirect("productions:detail", pk=production.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            production=self.production,
            motif=services.motif_corrections(self.production),
            version=self.production.version_courante(),
            **kwargs,
        )

    def form_valid(self, form):
        try:
            version = services.soumettre_version_corrigee(
                self.request.user,
                self.production,
                form.cleaned_data["fichier"],
                form.cleaned_data["note"],
            )
        except ActionInterdite as erreur:
            form.add_error("fichier", str(erreur))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Version corrigée n° {version.numero} déposée : votre travail a été renvoyé "
            "pour évaluation.",
        )
        return redirect("productions:detail", pk=self.production.pk)


def nom_de_fichier(production, version) -> str:
    """Nom proposé au navigateur : la cote pour un travail archivé (MEM-2026-0001.pdf),
    sinon le nom d'origine du fichier."""
    if production.cote:
        courante = production.version_courante()
        if courante is not None and courante.pk == version.pk:
            return f"{production.cote}.pdf"
        return f"{production.cote}-version-{version.numero}.pdf"
    return version.nom_original or f"version-{version.numero}.pdf"


class TelechargerVersionView(View):
    """Seul point de sortie des fichiers : contrôle des droits, journalisation, envoi.

    Ouvert aux visiteurs (libre accès) ; un visiteur sans droit est invité à se connecter,
    un utilisateur connecté sans droit reçoit 404.
    """

    def get(self, request, pk, numero):
        production = get_object_or_404(Production, pk=pk)
        version = VersionDocument.objects.filter(production=production, numero=numero).first()
        if version is None or not acces.peut_telecharger(request.user, production, version):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            raise Http404("Document introuvable.")
        services.enregistrer_telechargement(request.user, version, request.META.get("REMOTE_ADDR"))
        nom = nom_de_fichier(production, version)
        if settings.X_ACCEL_REDIRECT:
            reponse = HttpResponse(content_type="application/pdf")
            reponse["X-Accel-Redirect"] = settings.X_ACCEL_PREFIXE + version.fichier.name
        else:
            try:
                flux = version.fichier.open("rb")
            except FileNotFoundError:
                raise Http404("Fichier introuvable sur le serveur.") from None
            reponse = FileResponse(flux, content_type="application/pdf")
        en_piece_jointe = request.GET.get("telecharger") == "1"
        reponse["Content-Disposition"] = content_disposition_header(en_piece_jointe, nom)
        reponse["Cache-Control"] = "private, no-store"
        reponse["X-Content-Type-Options"] = "nosniff"
        return reponse
