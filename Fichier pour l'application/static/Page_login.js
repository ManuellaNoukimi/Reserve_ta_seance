document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("loginForm");

    if (!form) return;

    form.addEventListener("submit", function (e) {
        const email = document.querySelector("input[name='email_ulaval']").value.trim();
        const password = document.querySelector("input[name='mot_de_passe']").value.trim();

        if (!email || !password) {
            e.preventDefault();
            alert("Veuillez remplir tous les champs.");
            return;
        }

        if (!email.endsWith("@ulaval.ca")) {
            e.preventDefault();
            alert("Veuillez utiliser un courriel universitaire @ulaval.ca.");
            return;
        }

        if (password.length < 8) {
            e.preventDefault();
            alert("Le mot de passe doit contenir au moins 8 caractères.");
            return;
        }
        // Le formulaire part normalement vers Flask.
    });
});