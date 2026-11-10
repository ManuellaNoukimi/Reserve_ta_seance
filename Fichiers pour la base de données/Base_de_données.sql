-- ============================================================================
-- StudyMatch UL - Base de données de gestion des séances de révision
-- ============================================================================
-- Schéma complet pour l'application StudyMatch UL :
-- - Gestion des étudiants et leurs programmes
-- - Création et gestion des séances de révision
-- - Participation des étudiants aux séances
-- - Évaluation et rétroaction entre étudiants
-- ============================================================================

-- Ne pas créer la même base de données dans les autres fichiers surtout dans l'insertion de données

CREATE DATABASE IF NOT EXISTS Application_revision;
USE Application_revision;

-- Ordre des CREATE TABLE : chaque table doit exister avant les clés étrangères qui la référencent
-- (ex. Inscrire dépend de Etudiants et Cours, donc ces deux tables sont créées avant Inscrire).


-- ============================================================================
-- TABLE : Programmes
-- ============================================================================
-- Contient les informations sur les programmes universitaires
-- Exemple: Baccalauréat en Informatique, Maîtrise en Informatique, etc.
-- - sigle : code unique du programme (ex: GLO)
-- - pnom : nom complet du programme
-- - cycle : Premier/Deuxième/Troisième cycle
-- - duree : nombre d'années
-- - faculte : Faculté responsable

CREATE TABLE IF NOT EXISTS Programmes (
    sigle VARCHAR(5) PRIMARY KEY,
    pnom VARCHAR(100) NOT NULL,
    cycle ENUM('Premier cycle', 'Deuxieme cycle', 'Troisieme cycle') NOT NULL,
    duree INT NOT NULL CHECK (duree BETWEEN 1 AND 4),
    faculte VARCHAR(100) NOT NULL
);

-- Table qui contient les informations sur les cours
-- ============================================================================
-- TABLE : Cours
-- ============================================================================
-- Liste de tous les cours offerts à l'université
-- - csigle : code unique du cours (ex: GLO-2005)
-- - nom_cours : nom complet du cours
-- - credits : nombre de crédits (1-4)

CREATE TABLE IF NOT EXISTS Cours (
    csigle CHAR(8) PRIMARY KEY,
    nom_cours VARCHAR(100) NOT NULL,
    credits INT NOT NULL CHECK (credits BETWEEN 1 AND 4)
);

-- Données de démonstration - INSERT IGNORE évite les doublons
INSERT IGNORE INTO Cours (csigle, nom_cours, credits) VALUES
('GLO-2005', 'Bases de données', 3),
('IFT-1004', 'Introduction à la programmation', 3),
('IFT-2002', 'Systèmes exploitation', 3),
('IFT-2008', 'Structures de données', 3),
('IFT-3101', 'Compilation', 3),
('MAT-1200', 'Calcul différentiel et intégral I', 3),
('MAT-1910', 'Mathématiques pour informaticien', 3),
('CHM-1000', 'Chimie générale', 3),
('PHY-1001', 'Physique mécanique', 3),
('BIO-1001', 'Biologie cellulaire', 3),
('STT-1000', 'Probabilités et statistiques', 3);

-- ============================================================================
-- TABLE : Etudiants
-- ============================================================================
-- Contient les profils de tous les utilisateurs du système
-- - etudiant_id : clé primaire auto-générée
-- - nom, prenom : identité de l'étudiant
-- - email_ulaval : email unique (validé avec @ulaval.ca)
-- - mot_de_passe : hash bcrypt du mot de passe
-- - statut : 'Actif' (connecté) ou 'Inactif' (déconnecté)
-- - note : note moyenne de l'étudiant basée sur les évaluations reçues

CREATE TABLE IF NOT EXISTS Etudiants (
    etudiant_id  INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(50) NOT NULL,
    prenom VARCHAR(50) NOT NULL,
    email_ulaval VARCHAR(100) UNIQUE NOT NULL CHECK (email_ulaval LIKE '%@ulaval.ca'),
    mot_de_passe VARCHAR(255) NOT NULL,
    statut VARCHAR(50),
    note DECIMAL(3,2) DEFAULT NULL
);


-- Table de liaison qui répertorie les cours auxquels chaque étudiant est inscrit
CREATE TABLE IF NOT EXISTS Inscrire (
    etudiant_id INT ,
    csigle CHAR(8),
    session VARCHAR(20) NOT NULL,
    note_cours VARCHAR(2),
    PRIMARY KEY (etudiant_id, csigle),
    FOREIGN KEY (etudiant_id) REFERENCES Etudiants(etudiant_id) ON DELETE CASCADE,
    FOREIGN KEY (csigle) REFERENCES Cours(csigle) ON DELETE CASCADE
);

-- Table de liaison entre Programmes et Cours
CREATE TABLE IF NOT EXISTS Offrir (
    sigle CHAR(5) NOT NULL,
    csigle CHAR(8) NOT NULL,
    PRIMARY KEY (sigle, csigle),
    FOREIGN KEY (sigle) REFERENCES Programmes(sigle)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    FOREIGN KEY (csigle) REFERENCES Cours(csigle)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- Relation APPARTENIR : un étudiant appartient à un programme
CREATE TABLE IF NOT EXISTS Appartenir (
    programme_sigle CHAR(5),
    etudiant_id INT ,
    PRIMARY KEY (programme_sigle, etudiant_id),
    FOREIGN KEY (programme_sigle) REFERENCES Programmes(sigle),
    FOREIGN KEY (etudiant_id) REFERENCES Etudiants(etudiant_id)
);

-- ============================================================================
-- TABLE : Seances_revision
-- ============================================================================
-- Contient toutes les séances de révision créées par les étudiants
-- - seance_id : identifiant unique auto-généré
-- - csigle : cours concerné (FK vers Cours)
-- - createur_id : étudiant qui a créé la séance (FK vers Etudiants)
-- - statut : état de la séance (En_attente, En_cours, Complete) - mis à jour automatiquement
-- - lieu_ou_lien : localisation physique ou lien de visioconférence
-- - mode : Présentiel, En ligne, ou Hybride
-- - debut_datetime : date et heure de début (détermine le statut automatiquement)
-- - description : détails supplémentaires pour les participants
-- - max_participants : nombre maximum de participants (NULL = illimité)

CREATE TABLE IF NOT EXISTS Seances_revision (
    seance_id INT AUTO_INCREMENT PRIMARY KEY,
    csigle CHAR(8) NOT NULL,
    createur_id INT  NOT NULL,
    statut VARCHAR(30),
    lieu_ou_lien VARCHAR(255),
    mode VARCHAR(50),
    debut_datetime DATETIME NOT NULL,
    description TEXT,
    max_participants TINYINT UNSIGNED,
    FOREIGN KEY (csigle) REFERENCES Cours(csigle) ON DELETE CASCADE,
    FOREIGN KEY (createur_id) REFERENCES Etudiants(etudiant_id) ON DELETE CASCADE

);

-- ============================================================================
-- TABLE : Creer
-- ============================================================================
-- Historique de création des séances (trace d'audit)
-- Enregistre qui a créé quelle séance et quand

CREATE TABLE IF NOT EXISTS Creer (
    etudiant_id INT ,
    seance_id INT,
    date_creation DATETIME NOT NULL,
    PRIMARY KEY (etudiant_id, seance_id),
    FOREIGN KEY (etudiant_id) REFERENCES Etudiants(etudiant_id),
    FOREIGN KEY (seance_id) REFERENCES Seances_revision(seance_id) ON DELETE CASCADE
);

-- ============================================================================
-- TABLE : Jumeler
-- ============================================================================
-- Gère la participation des étudiants aux séances
-- - statut : En_attente (demande en cours), Accepte (confirmé), Refuse (rejeté)
-- - date_demande : quand l'étudiant a demandé de participer
-- - date_reponse : quand le créateur a répondu (Accepte/Refuse)
-- - presence_confirme : TRUE quand la séance est terminée et l'étudiant était présent

CREATE TABLE IF NOT EXISTS Jumeler (
    etudiant_id INT ,
    seance_id INT,
    statut ENUM('Accepte', 'Refuse', 'En_attente') NOT NULL,
    date_demande DATETIME,
    date_reponse DATETIME,
    presence_confirme BOOL DEFAULT FALSE,
    PRIMARY KEY (etudiant_id, seance_id),
    FOREIGN KEY (etudiant_id) REFERENCES Etudiants(etudiant_id),
    FOREIGN KEY (seance_id) REFERENCES Seances_revision(seance_id) ON DELETE CASCADE
);

-- ============================================================================
-- TABLE : Donner
-- ============================================================================
-- Rétroactions (évaluations) entre étudiants après une séance
-- - auteur_id : qui évalue
-- - evalue_id : qui est évalué
-- - note : note de 1 à 5
-- - commentaire : feedback textuel
-- - tags : étiquettes pour catégoriser la rétroaction
-- - date_retroaction : timestamp de l'évaluation

CREATE TABLE IF NOT EXISTS Donner (
    auteur_id INT ,
    evalue_id INT ,
    seance_id INT,
    note TINYINT NOT NULL CHECK (note BETWEEN 1 AND 5),
    commentaire TEXT NULL,
    tags VARCHAR(512) NULL,
    date_retroaction DATETIME NOT NULL,
    PRIMARY KEY (auteur_id, evalue_id, seance_id),
    FOREIGN KEY (auteur_id) REFERENCES Etudiants(etudiant_id),
    FOREIGN KEY (evalue_id) REFERENCES Etudiants(etudiant_id),
    FOREIGN KEY (seance_id) REFERENCES Seances_revision(seance_id),
    CHECK (auteur_id <> evalue_id)
);

-- ============================================================================
-- TABLE : Retroactions
-- ============================================================================
-- Rétroaction globale du créateur sur la qualité de sa propre séance
-- - note : évaluation générale (1-5)
-- - objectifs_atteints : 1 si oui, 0 si non, NULL si non évalué
-- - commentaire : observations du créateur

-- Si Donner existait déjà sans ces colonnes, exécuter (sinon l’app les ajoute au démarrage) :
-- ALTER TABLE Donner ADD COLUMN commentaire TEXT NULL;
-- ALTER TABLE Donner ADD COLUMN tags VARCHAR(512) NULL;

-- Table Retroaction (entité de rétroaction globale sur une séance)
CREATE TABLE IF NOT EXISTS Retroactions (
    retroaction_id INT AUTO_INCREMENT PRIMARY KEY,
    seance_id INT NOT NULL,
    date_retroaction DATETIME NOT NULL,
    note TINYINT NOT NULL CHECK (note BETWEEN 1 AND 5),
    objectifs_atteints TINYINT(1) NULL COMMENT '1=oui, 0=non',
    commentaire TEXT NULL,
    FOREIGN KEY (seance_id) REFERENCES Seances_revision(seance_id) ON DELETE CASCADE
);

-- Si Retroactions existait déjà sans commentaire :
-- ALTER TABLE Retroactions ADD COLUMN commentaire TEXT NULL;
-- Si Retroactions existait déjà sans objectifs_atteints :
-- ALTER TABLE Retroactions ADD COLUMN objectifs_atteints TINYINT(1) NULL COMMENT '1=oui, 0=non';

--  CETTE REQUETE est pour pouvoir reinitialiser le mot de passe
CREATE TABLE IF NOT EXISTS Reinitialiser_mot_de_passe (
    email_ulaval VARCHAR(100) PRIMARY KEY,
    reset_token VARCHAR(255) NOT NULL,
    expiration DATETIME NOT NULL,
    FOREIGN KEY (email_ulaval) REFERENCES Etudiants(email_ulaval) ON DELETE CASCADE
);

-- =============================================================================
-- Gâchettes (TRIGGER), fonctions et procédures stockées
-- =============================================================================

DROP TRIGGER IF EXISTS tr_seances_avant_insert_statut_defaut;
DROP TRIGGER IF EXISTS tr_jumeler_avant_insert_date_demande;
DROP TRIGGER IF EXISTS tr_jumeler_avant_update_date_reponse;
DROP TRIGGER IF EXISTS tr_seances_avant_update_empcher_modif_complete;
DROP TRIGGER IF EXISTS tr_seances_avant_insert_valider_debut_datetime;
DROP TRIGGER IF EXISTS tr_seances_apres_update_marquer_participants_presents;

DROP FUNCTION IF EXISTS fn_places_libres_seance;
DROP FUNCTION IF EXISTS fn_nb_participants_acceptes;

DROP PROCEDURE IF EXISTS sp_statistiques_participation_seance;
DROP PROCEDURE IF EXISTS sp_lister_seances_ouvertes_aux_inscriptions;
DROP PROCEDURE IF EXISTS sp_update_etudiant_statut;
DROP PROCEDURE IF EXISTS sp_update_session_status_en_cours;
DROP PROCEDURE IF EXISTS sp_update_session_status_complete;
DROP PROCEDURE IF EXISTS sp_mark_participants_present_for_completed_sessions;

DELIMITER //

-- ============================================================================
-- TRIGGERS (Gâchettes automatiques)
-- ============================================================================

-- TRIGGER 1 : Initialiser le statut d'une séance
-- Quand on crée une séance sans spécifier le statut, le mettre à "En_attente"
CREATE TRIGGER tr_seances_avant_insert_statut_defaut
BEFORE INSERT ON Seances_revision
FOR EACH ROW
BEGIN
    IF NEW.statut IS NULL OR TRIM(NEW.statut) = '' THEN
        SET NEW.statut = 'En_attente';
    END IF;
END//

-- TRIGGER 2 : Initialiser la date de demande de participation
-- Quand un étudiant demande à participer, noter l'heure automatiquement
CREATE TRIGGER tr_jumeler_avant_insert_date_demande
BEFORE INSERT ON Jumeler
FOR EACH ROW
BEGIN
    IF NEW.date_demande IS NULL THEN
        SET NEW.date_demande = NOW();
    END IF;
END//

-- TRIGGER 3 : Enregistrer la date de réponse
-- Quand le créateur accepte/refuse une demande, horodater la réponse
CREATE TRIGGER tr_jumeler_avant_update_date_reponse
BEFORE UPDATE ON Jumeler
FOR EACH ROW
BEGIN
    IF OLD.statut = 'En_attente'
       AND NEW.statut <> 'En_attente'
       AND NEW.date_reponse IS NULL THEN
        SET NEW.date_reponse = NOW();
    END IF;
END//

-- TRIGGER 4 : Empêcher la modification d'une séance terminée
-- Une séance "Complete" ne peut plus être modifiée (immuabilité)
CREATE TRIGGER tr_seances_avant_update_empcher_modif_complete
BEFORE UPDATE ON Seances_revision
FOR EACH ROW
BEGIN
    IF OLD.statut = 'Complete' AND NEW.statut = 'Complete' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Impossible de modifier une séance complètement terminée.';
    END IF;
END//

-- TRIGGER 5 : Valider la date de début
-- Une séance ne peut pas être créée avec une date dans le passé
CREATE TRIGGER tr_seances_avant_insert_valider_debut_datetime
BEFORE INSERT ON Seances_revision
FOR EACH ROW
BEGIN
    IF NEW.debut_datetime < NOW() THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'La date de début ne peut pas être dans le passé.';
    END IF;
END//

-- TRIGGER 6 : Marquer les participants présents automatiquement
-- Quand une séance devient "Complete", tous les participants acceptés sont marqués présents
CREATE TRIGGER tr_seances_apres_update_marquer_participants_presents
AFTER UPDATE ON Seances_revision
FOR EACH ROW
BEGIN
    IF NEW.statut = 'Complete' AND OLD.statut <> 'Complete' THEN
        UPDATE Jumeler
        SET presence_confirme = TRUE
        WHERE seance_id = NEW.seance_id
        AND statut = 'Accepte'
        AND presence_confirme = FALSE;
    END IF;
END//

-- ============================================================================
-- FONCTIONS STOCKÉES
-- ============================================================================

-- FONCTION 1 : participants acceptés pour une séance
CREATE FUNCTION fn_nb_participants_acceptes(p_seance_id INT)
RETURNS INT
READS SQL DATA
NOT DETERMINISTIC
BEGIN
    DECLARE v_nb INT DEFAULT 0;
    SELECT COUNT(*) INTO v_nb
    FROM Jumeler
    WHERE seance_id = p_seance_id AND statut = 'Accepte';
    RETURN IFNULL(v_nb, 0);
END//

-- FONCTION 2 : places restantes (999 = sans plafond si max_participants NULL)
CREATE FUNCTION fn_places_libres_seance(p_seance_id INT)
RETURNS INT
READS SQL DATA
NOT DETERMINISTIC
BEGIN
    DECLARE v_max TINYINT UNSIGNED DEFAULT NULL;
    DECLARE v_acceptes INT DEFAULT 0;
    DECLARE v_restant INT DEFAULT 0;

    SELECT max_participants INTO v_max
    FROM Seances_revision
    WHERE seance_id = p_seance_id;

    IF v_max IS NULL THEN
        RETURN 999;
    END IF;

    SET v_acceptes = fn_nb_participants_acceptes(p_seance_id);
    SET v_restant = v_max - v_acceptes;
    IF v_restant < 0 THEN
        SET v_restant = 0;
    END IF;
    RETURN v_restant;
END//

-- ============================================================================
-- PROCÉDURES STOCKÉES
-- ============================================================================

-- PROCÉDURE 1 : Récupérer les statistiques complètes d'une séance
-- Retourne en paramètres OUT : nb acceptés, en attente, refusés, places libres
CREATE PROCEDURE IF NOT EXISTS sp_statistiques_participation_seance(
    IN p_seance_id INT,
    OUT p_nb_accepte INT,
    OUT p_nb_attente INT,
    OUT p_nb_refuse INT,
    OUT p_places_libres INT
)
BEGIN
    SELECT COUNT(*) INTO p_nb_accepte
    FROM Jumeler
    WHERE seance_id = p_seance_id AND statut = 'Accepte';

    SELECT COUNT(*) INTO p_nb_attente
    FROM Jumeler
    WHERE seance_id = p_seance_id AND statut = 'En_attente';

    SELECT COUNT(*) INTO p_nb_refuse
    FROM Jumeler
    WHERE seance_id = p_seance_id AND statut = 'Refuse';

    SET p_places_libres = fn_places_libres_seance(p_seance_id);
END//

-- PROCÉDURE 2 : Lister les séances ouvertes aux inscriptions
-- Retourne les séances qui ne sont pas Annulées ou Complètes
CREATE PROCEDURE IF NOT EXISTS sp_lister_seances_ouvertes_aux_inscriptions()
BEGIN
    SELECT
        s.seance_id,
        s.csigle,
        c.nom_cours,
        s.mode,
        s.debut_datetime,
        s.statut,
        s.max_participants,
        fn_nb_participants_acceptes(s.seance_id) AS nb_acceptes,
        fn_places_libres_seance(s.seance_id) AS places_libres
    FROM Seances_revision s
    JOIN Cours c ON c.csigle = s.csigle
    WHERE s.statut IS NULL
       OR s.statut NOT IN ('Annulee', 'Complete');
END//

-- PROCÉDURE 3 : Mettre à jour le statut d'un étudiant
-- Change le statut à 'Actif' (connexion) ou 'Inactif' (déconnexion)
CREATE PROCEDURE IF NOT EXISTS sp_update_etudiant_statut(
    IN p_etudiant_id INT,
    IN p_statut VARCHAR(50)
)
BEGIN
    UPDATE Etudiants
    SET statut = p_statut
    WHERE etudiant_id = p_etudiant_id;
END//

-- PROCÉDURE 4 : Mettre à jour les séances en cours
-- Marque comme "En_cours" les séances commencées mais non terminées (< 3h)
CREATE PROCEDURE IF NOT EXISTS sp_update_session_status_en_cours()
BEGIN
    UPDATE Seances_revision
    SET statut = 'En_cours'
    WHERE debut_datetime <= NOW()
    AND DATE_ADD(debut_datetime, INTERVAL 3 HOUR) > NOW()
    AND statut != 'En_cours';
END//

-- PROCÉDURE 5 : Marquer les séances comme complètes
-- Marque comme "Complete" les séances dont les 3 heures sont écoulées
CREATE PROCEDURE IF NOT EXISTS sp_update_session_status_complete()
BEGIN
    UPDATE Seances_revision
    SET statut = 'Complete'
    WHERE DATE_ADD(debut_datetime, INTERVAL 3 HOUR) <= NOW()
    AND statut != 'Complete';
END//

-- PROCÉDURE 6 : Marquer les participants présents automatiquement
-- Marque présents tous les participants acceptés des séances complètes
CREATE PROCEDURE IF NOT EXISTS sp_mark_participants_present_for_completed_sessions()
BEGIN
    UPDATE Jumeler j
    JOIN Seances_revision s ON j.seance_id = s.seance_id
    SET j.presence_confirme = TRUE
    WHERE s.statut = 'Complete'
    AND j.statut = 'Accepte'
    AND j.presence_confirme = FALSE;
END//

DELIMITER ;

-- ============================================================================
-- INDEXES - Pour optimiser les performances des requêtes fréquentes
-- ============================================================================
-- Index sur les dates pour les filtres temporels
CREATE INDEX IF NOT EXISTS idx_seances_debut_date ON Seances_revision(debut_datetime);
-- Index sur le statut pour les filtres d'affichage
CREATE INDEX IF NOT EXISTS idx_jumeler_statut ON Jumeler(statut);
