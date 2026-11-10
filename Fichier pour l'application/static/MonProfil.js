/**
 * Fichier : MonProfil.js
 * Description : Gestion de la page Profil utilisateur pour StudyMatch UL.
 */
document.addEventListener("DOMContentLoaded", () => {
    // 1. Gestion de la déconnexion
    const logoutBtn = document.querySelector(".logout-link");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", (e) => {
            const confirmation = confirm("Voulez-vous vraiment vous déconnecter de StudyMatch UL ?");
            if (!confirmation) {
                e.preventDefault();
            }
        });
    }

    // 2. Gestion du bouton Paramètres (Nouveau !)
    // On récupère le bouton grâce à l'id "settingsBtn" ajouté dans le HTML
    const settingsBtn = document.getElementById("settingsBtn");
    if (settingsBtn) {
        settingsBtn.addEventListener("click", () => {
            // Affichage d'un message neutre et professionnel
            alert("Cette fonctionnalité (Paramètres du profil) sera disponible dans la prochaine version de StudyMatch UL !");
        });
    }
});