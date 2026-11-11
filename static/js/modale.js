// Ouvre la modale de confirmation avant l'envoi des formulaires marqués data-confirmation.
(function () {
  "use strict";
  var modale = document.getElementById("modale-confirmation");
  if (!modale || typeof modale.showModal !== "function") return;
  var message = modale.querySelector("[data-modale-message]");
  var confirmer = modale.querySelector("[data-modale-confirmer]");
  var formulaire = null;

  document.addEventListener("submit", function (evenement) {
    var cible = evenement.target;
    if (!cible.dataset || !cible.dataset.confirmation || cible.dataset.confirme) return;
    evenement.preventDefault();
    formulaire = cible;
    message.textContent = cible.dataset.confirmation;
    confirmer.textContent = cible.dataset.confirmationBouton || "Confirmer";
    modale.showModal();
    confirmer.focus();
  });

  confirmer.addEventListener("click", function () {
    if (!formulaire) return;
    formulaire.dataset.confirme = "1";
    modale.close();
    formulaire.submit();
  });

  modale.addEventListener("close", function () {
    if (formulaire && !formulaire.dataset.confirme) {
      var bouton = formulaire.querySelector("[type=submit]");
      if (bouton) bouton.focus();
    }
    formulaire = null;
  });
})();
