/**
 * Fichier : MesParticipations.js
 * Description : Gestion des interactions pour l'espace participations de StudyMatch UL.
 */

(() => {
    document.addEventListener("DOMContentLoaded", () => {
        const evalModal = document.getElementById("evalPresenceModal");
        const evalForm = document.getElementById("evalPresenceForm");

        window.openDetails = (seanceId) => {
            console.log("Chargement des détails pour : " + seanceId);
            // Simulation d'affichage des détails (sujet et description)
            alert("Consultation de la séance " + seanceId + ".\n\nCette fenêtre affichera le sujet complet et la liste des participants confirmés.");
        };


        window.openEvalPresence = () => {
            if (modalExists(evalModal)) {
                evalModal.showModal();
            }
        };


        evalModal?.addEventListener("click", (e) => {
            const rect = evalModal.getBoundingClientRect();
            if (e.clientY < rect.top || e.clientY > rect.bottom || e.clientX < rect.left || e.clientX > rect.right) {
                evalModal.close();
            }
        });

        /**
         * Validation de la soumission du formulaire
         */
        evalForm?.addEventListener("submit", (e) => {
            const isChecked = evalForm.querySelector('input[name="presence"]:checked');
            if (!isChecked) {
                e.preventDefault();
                alert("Veuillez indiquer si l'organisateur était présent ou absent.");
            }
        });

        // Fonction utilitaire de vérification
        function modalExists(element) {
            if (!element) {
                console.error("Élément de dialogue introuvable dans le DOM.");
                return false;
            }
            return true;
        }
    });
})();