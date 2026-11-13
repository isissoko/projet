"""Pages publiques : accueil, résultats de recherche, fiche (RG01 : sans connexion)."""

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, TemplateView

from productions import acces
from productions import services as productions_services
from productions.models import Production

from . import services
from .forms import RechercheForm

CRITERES_AVANCES = ("titre", "auteur", "encadreur", "annee", "mot_cle", "type", "filiere")


class AccueilView(TemplateView):
    template_name = "recherche/accueil.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            form=RechercheForm(),
            derniers=services.derniers_archives(),
            chiffres=services.chiffres(),
            **kwargs,
        )


class ResultatsView(ListView):
    template_name = "recherche/resultats.html"
    context_object_name = "resultats"
    paginate_by = 10

    def get_queryset(self):
        self.form = RechercheForm(self.request.GET or None)
        self.criteres = self.form.criteres() if self.request.GET else services.Criteres()
        return services.rechercher(self.criteres)

    def get_context_data(self, **kwargs):
        parametres = self.request.GET.copy()
        parametres.pop("page", None)
        # Critères actifs, chacun avec le lien qui le retire.
        actifs = []
        if self.form.is_bound:
            for nom in ("q", *CRITERES_AVANCES):
                valeur = self.form.cleaned_data.get(nom)
                if valeur in (None, ""):
                    continue
                sans = parametres.copy()
                sans.pop(nom, None)
                champ = self.form.fields[nom]
                if hasattr(champ, "choices") and not hasattr(valeur, "pk"):
                    affichage = dict(champ.choices).get(valeur, valeur)
                else:
                    affichage = valeur
                actifs.append(
                    {"libelle": champ.label, "valeur": affichage, "parametres": sans.urlencode()}
                )
        return super().get_context_data(
            form=self.form,
            criteres=self.criteres,
            actifs=actifs,
            filtres_ouverts=any(self.request.GET.get(n) for n in CRITERES_AVANCES),
            parametres=parametres.urlencode(),
            **kwargs,
        )


class FicheView(TemplateView):
    """Fiche d'un travail archivé, visible par tous (BF10). Un travail non archivé : ses
    proches sont renvoyés vers la page de suivi, les autres reçoivent 404 (RG11)."""

    template_name = "recherche/fiche.html"

    def get(self, request, *args, **kwargs):
        production = get_object_or_404(Production, pk=kwargs["pk"])
        if not production.est_archive:
            if acces.peut_voir_fiche(request.user, production):
                return redirect("productions:detail", pk=production.pk)
            raise Http404("Travail introuvable.")
        self.production = production.specifique()
        productions_services.enregistrer_consultation(
            request.user, self.production, request.META.get("REMOTE_ADDR")
        )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        p = self.production
        user = self.request.user
        version = p.version_courante()
        return super().get_context_data(
            production=p,
            version=version,
            contributions=p.contributions.select_related("contributeur").order_by("rang"),
            encadrements=p.encadrements.select_related("enseignant__utilisateur"),
            mots_cles=p.mots_cles.all(),
            telechargeable=version is not None and acces.peut_telecharger(user, p, version),
            raison_indisponibilite=acces.raison_indisponibilite(user, p),
            connexion_utile=not user.is_authenticated and p.niveau_acces == "RESTREINT",
            embargo_actif=acces.embargo_actif(p),
            est_proche=acces.est_proche(user, p),
            est_bibliothecaire=acces.est_bibliothecaire(user),
            citation=services.citation(p),
            **kwargs,
        )
