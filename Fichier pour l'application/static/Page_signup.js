document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("signupForm");

    if (!form) return;

    form.addEventListener("submit", function (e) {
        const prenom = document.getElementById("prenom").value.trim();
        const nom = document.getElementById("nom").value.trim();
        const email = document.getElementById("email").value.trim();
        const programme = document.getElementById("program").value;
        const password = document.getElementById("password").value;
        const confirmPassword = document.getElementById("confirmPassword").value;

        if (!prenom || !nom  || !email || !programme || !password || !confirmPassword) {
            e.preventDefault();
            alert("Tous les champs sont obligatoires.");
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

        if (password !== confirmPassword) {
            e.preventDefault();
            alert("Les mots de passe ne correspondent pas.");
            return;
        }

        // Si tout est correct, on laisse le formulaire partir vers Flask.
    });
});