document.addEventListener("DOMContentLoaded", function () {
    const ctaButton = document.querySelector(".button--light");

    if (!ctaButton) return;

    ctaButton.addEventListener("click", function () {
        console.log("Redirection vers la page des disponibilités.");
    });
});