// Affiche le nom et la taille du fichier choisi avant l'envoi ; alerte au-delà de la limite.
// La validation réelle reste faite par le serveur.
(function () {
  "use strict";
  var champ = document.querySelector("input[type=file][data-taille-max]");
  var apercu = document.getElementById("apercu-fichier");
  if (!champ || !apercu) return;
  var max = parseInt(champ.dataset.tailleMax, 10);
  var format = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

  function taille(octets) {
    if (octets >= 1048576) return format.format(octets / 1048576) + " Mo";
    return format.format(octets / 1024) + " Ko";
  }

  champ.addEventListener("change", function () {
    var fichier = champ.files && champ.files[0];
    if (!fichier) { apercu.hidden = true; return; }
    apercu.hidden = false;
    if (fichier.size > max) {
      apercu.className = "mb-4 text-sm font-semibold text-red-700";
      apercu.textContent = "« " + fichier.name + " » fait " + taille(fichier.size) +
        " : c'est plus que la limite de " + taille(max) + ". Réduisez sa taille avant de l'envoyer.";
    } else {
      apercu.className = "mb-4 text-sm text-gris-800";
      apercu.textContent = "Fichier choisi : « " + fichier.name + " » (" + taille(fichier.size) + ").";
    }
  });
})();
