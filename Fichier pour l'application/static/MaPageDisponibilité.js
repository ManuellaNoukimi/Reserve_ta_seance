// ============================================================
// État global : toutes les sessions chargées depuis le serveur
// ============================================================
let toutesLesSessions = [];
let etudiantConnecte = null;

// ============================================================
// Au chargement de la page : fetch initial + branchement des filtres
// ============================================================
window.addEventListener("DOMContentLoaded", function () {
    chargerSessions();
    brancherFiltres();
});

// ============================================================
// Récupère les sessions selon les filtres actifs
// ============================================================
function chargerSessions() {
    const params = lireParametresFiltres();
    const url = "/sessions?" + new URLSearchParams(params).toString();

    fetch(url)
        .then(function (response) {
            return response.json();
        })
        .then(function (data) {
            toutesLesSessions = data.sessions;
            etudiantConnecte = data.etudiant_connecte;
            afficherSessionsAvecFiltresClient();
        })
        .catch(function (error) {
            console.error("Erreur lors du chargement des sessions :", error);
        });
}

// ============================================================
// Applique les filtres côté client (Mode, Places disponibles)
// ============================================================
function afficherSessionsAvecFiltresClient() {
    let sessions = toutesLesSessions;

    // Filtre "Places disponibles"
    const filterPlaces = document.querySelector("#filter-places")?.checked || false;
    if (filterPlaces) {
        sessions = sessions.filter(function (s) {
            const maxPart = Number(s.max_participants ?? 0);
            const nbPart = Number(s.nb_participants ?? 0);
            return maxPart > 0 && nbPart < maxPart;
        });
    }

    afficherSessions(sessions);
}

// ============================================================
// Lit les valeurs du select Mode (#filter-mode) pour l'API /sessions
// ============================================================
function lireParametresFiltres() {
    const selectMode = document.querySelector("#filter-mode");
    const params = {};

    const mode = selectMode ? selectMode.value : "";

    if (mode) params.type = mode;

    return params;
}

// ============================================================
// Affiche une liste de sessions dans le conteneur
// ============================================================
function afficherSessions(sessions) {
    let conteneur = document.getElementById("sessions-container");

    if (!conteneur) {
        conteneur = document.createElement("div");
        conteneur.id = "sessions-container";
        document.body.appendChild(conteneur);
    }

    conteneur.innerHTML = "";

    if (!sessions || sessions.length === 0) {
        conteneur.innerHTML = "<p>Aucune session trouvée.</p>";
        return;
    }

    for (let session of sessions) {
        const carte = creerCarteSessions(session);
        conteneur.appendChild(carte);
    }
}

// ============================================================
// Crée la carte HTML d'une session
// ============================================================
function creerCarteSessions(session) {
    const div = document.createElement("div");
    div.className = "session-card";

    const maxParticipants = Number(session.max_participants ?? 0);
    const nbParticipants = Number(session.nb_participants ?? 0);
    const placesRestantes = maxParticipants - nbParticipants;
    const estComplet = maxParticipants > 0 && placesRestantes <= 0;

    const cs = session.csigle || "";
    const titre =
        session.nom_cours && String(session.nom_cours).trim() !== ""
            ? session.nom_cours + (cs ? ` (${cs})` : "")
            : cs || "Séance";

    const lieu = session.lieu_ou_lien != null && session.lieu_ou_lien !== ""
        ? session.lieu_ou_lien
        : "—";

    const desc = session.description != null && String(session.description).trim() !== ""
        ? `<div class="session-desc">${session.description}</div>`
        : "";

    const textePlaces = maxParticipants > 0
        ? (estComplet ? "Complet" : placesRestantes + " restante(s)")
        : "Illimité";

    // Vérifier le statut de participation de l'utilisateur
    const userStatus = session.user_participation_status;
    
    // Ne montrer le bouton que si:
    // - On n'est pas le créateur
    // - Il y a des places
    // - On est connecté
    // - On n'a pas déjà envoyé une demande (En_attente)
    const peutRejoin = etudiantConnecte && 
                       String(session.createur_id) !== String(etudiantConnecte) && 
                       !estComplet &&
                       userStatus !== 'En_attente';
    
    let boutonRejoin = "";
    if (userStatus === 'En_attente') {
        boutonRejoin = `
            <button type="button" class="btn btn-primary" disabled title="Demande en attente">
                Demande en attente
            </button>
        `;
    } else if (peutRejoin) {
        boutonRejoin = `
            <button type="button" class="btn btn-primary" onclick="demanderParticipation(${session.seance_id})">
                Rejoindre la session
            </button>
        `;
    }

    div.innerHTML = `
        <h3>${titre}</h3>
        <div class="session-meta">
            <div><strong>Mode</strong> ${session.mode || "—"}</div>
            <div><strong>Date</strong> ${session.debut_datetime || "—"}</div>
            <div><strong>Lieu / lien</strong> ${lieu}</div>
            <div><strong>Places</strong> ${textePlaces}</div>
        </div>
        ${desc}
        <div class="session-actions">
            ${boutonRejoin}
        </div>
    `;

    return div;
}

// ============================================================
// Branche les événements sur les filtres et la recherche
// ============================================================
function brancherFiltres() {
    // Événements sur le select mode
    const selectMode = document.querySelector("#filter-mode");
    if (selectMode) {
        selectMode.addEventListener("change", function () {
            chargerSessions();
        });
    }

    // Événements sur les checkboxes de filtrage
    const checkboxes = document.querySelectorAll("#filter-places");
    checkboxes.forEach(function (checkbox) {
        checkbox.addEventListener("change", function () {
            afficherSessionsAvecFiltresClient();
        });
    });

    // Bouton dédié à la recherche (#btn-search)
    const boutonRecherche = document.querySelector("#btn-search");
    if (boutonRecherche) {
        boutonRecherche.addEventListener("click", onSearchClick);
    }

    // Recherche aussi déclenchée par la touche Entrée
    const inputRecherche = document.querySelector("#search-input");
    if (inputRecherche) {
        inputRecherche.addEventListener("keydown", function (e) {
            if (e.key === "Enter") onSearchClick();
        });
    }
}

// ============================================================
// Recherche textuelle : filtre côté client sur les sessions déjà chargées (nom_cours, csigle).
// ============================================================
function onSearchClick() {
    const input = document.querySelector("#search-input");
    if (!input) return;

    const query = input.value.trim().toLowerCase();

    if (query === "") {
        afficherSessionsAvecFiltresClient();
        return;
    }

    const resultats = toutesLesSessions.filter(function (session) {
        const nomCours = (session.nom_cours || "").toLowerCase();
        const csigle = (session.csigle || "").toLowerCase();

        return (
            nomCours.includes(query) ||
            csigle.includes(query)
        );
    });

    // Créer une copie temp de toutes les sessions et appliquer le filtrage
    const oldSessions = toutesLesSessions;
    toutesLesSessions = resultats;
    afficherSessionsAvecFiltresClient();
    toutesLesSessions = oldSessions;
}

// ============================================================
// Demander à participer à une session
// ============================================================
function demanderParticipation(seanceId) {
    fetch("/demander-participation", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded"
        },
        body: "seance_id=" + encodeURIComponent(seanceId)
    })
    .then(function (response) {
        if (response.ok) {
            return response.json();
        }
        throw new Error("Erreur lors de la demande de participation");
    })
    .then(function (data) {
        alert("Demande de participation envoyée !");
        chargerSessions(); // Recharger les sessions
    })
    .catch(function (error) {
        alert("Erreur : " + error.message);
    });
}
