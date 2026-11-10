import json
import os
import unicodedata
from datetime import datetime, timedelta

import pymysql
from dotenv import load_dotenv

_MOIS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
_JOURS_FR = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)

# Aligné sur l’affichage des cartes (plage ~3 h) : l’évaluation n’est permise qu’après cette fenêtre.
DUREE_SEANCE_EVALUATION_HEURES = 3

# Suggestions dépendantes de la note (clés stockées en JSON dans Donner.tags).
EVALUATION_TAGS_BY_NOTE = {
    5: (
        ("exc_prep", "Excellente préparation"),
        ("exc_ponctuel", "Très ponctuel(le)"),
        ("exc_particip", "Participation exceptionnelle"),
        ("exc_entraide", "A beaucoup fait progresser le groupe"),
        ("exc_comm", "Communication remarquable"),
    ),
    4: (
        ("tres_prep", "Bonne préparation"),
        ("ponctuel", "Ponctuel(le)"),
        ("participation", "Bonne participation"),
        ("respectueux", "Respectueux(se)"),
        ("entraide", "A aidé le groupe"),
        ("communication", "Communication claire"),
    ),
    3: (
        ("prep_correcte", "Préparation correcte"),
        ("particip_moder", "Participation modérée"),
        ("qq_retards", "Quelques retards"),
        ("encourager", "À encourager pour la suite"),
    ),
    2: (
        ("en_retard", "Retards ou absences injustifiés"),
        ("peu_prepare", "Peu préparé(e)"),
        ("particip_faible", "Participation trop faible"),
        ("desengage", "Désengagement notable"),
    ),
    1: (
        ("en_retard_grave", "Retards répétés / manque de respect du groupe"),
        ("non_prepare", "Très peu ou pas préparé(e)"),
        ("particip_absente", "Participation quasi absente"),
        ("perturbation", "A nui à l’ambiance de révision"),
    ),
}

EVALUATION_NOTE_LABELS = {
    5: "Excellent",
    4: "Très bien",
    3: "Satisfaisant",
    2: "Insuffisant",
    1: "Très insuffisant",
}

EVALUATION_TAG_LABELS = {}
for _pairs in EVALUATION_TAGS_BY_NOTE.values():
    for k, lab in _pairs:
        EVALUATION_TAG_LABELS[k] = lab
EVALUATION_TAGS_ALLOWED = frozenset(EVALUATION_TAG_LABELS.keys())


def tags_autorises_pour_note(note):
    """Clés de tags permises pour une note donnée (1–5)."""
    try:
        n = int(note)
    except (TypeError, ValueError):
        return frozenset()
    pairs = EVALUATION_TAGS_BY_NOTE.get(n)
    if not pairs:
        return frozenset()
    return frozenset(k for k, _ in pairs)

_RETRO_COMMENTAIRE_MAX_LEN = 350
_RETRO_SEANCE_COMMENTAIRE_MAX_LEN = 600
_RETRO_TAGS_JSON_MAX_LEN = 500


def _parse_tags_column(raw):
    if raw is None or str(raw).strip() == "":
        return []
    try:
        v = json.loads(str(raw))
        if not isinstance(v, list):
            return []
        return [x for x in v if isinstance(x, str) and x in EVALUATION_TAGS_ALLOWED]
    except json.JSONDecodeError:
        return []


def _parse_mysql_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if "." in s:
        s = s.split(".")[0]
    for n, fmt in ((19, "%Y-%m-%d %H:%M:%S"), (16, "%Y-%m-%d %H:%M"), (10, "%Y-%m-%d")):
        if len(s) >= n:
            try:
                return datetime.strptime(s[:n], fmt)
            except ValueError:
                continue
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except ValueError:
        return None


def _date_longue_fr(dt):
    if not dt:
        return None
    return f"{_JOURS_FR[dt.weekday()]} {dt.day} {_MOIS_FR[dt.month - 1]} {dt.year}"


def _heure_hm(dt):
    if not dt:
        return None
    return dt.strftime("%H:%M")


def _relatif_passe(dt):
    """Pour une date passée : 'Il y a 2 jours', etc."""
    if not dt:
        return None
    now = datetime.now()
    if dt > now:
        return None
    delta = now - dt
    j = delta.days
    if j >= 1:
        return "Il y a 1 jour" if j == 1 else f"Il y a {j} jours"
    h = int(delta.total_seconds() // 3600)
    if h >= 1:
        return "Il y a environ 1 heure" if h == 1 else f"Il y a environ {h} heures"
    return "Il y a moins d’une heure"


def _initiales(prenom, nom):
    a = (prenom or "").strip()[:1]
    b = (nom or "").strip()[:1]
    return f"{a}{b}".upper() or "?"


def _norm_statut_seance_key(statut):
    """Normalise la valeur BD pour comparaison (accents, espaces)."""
    if statut is None:
        return ""
    t = str(statut).strip().lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a")):
        t = t.replace(a, b)
    return t.replace(" ", "_")


def statut_seance_est_complete(statut):
    """True si le statut en base correspond à une séance terminée (Complete, Complète, etc.)."""
    return _norm_statut_seance_key(statut) == "complete"


def _sql_condition_seance_eligible_evaluation():
    """
    Fragment SQL : séance évaluable si statut « complète » OU délai après début (fenêtre révision).
    Condition : doit être Complete OU (doit être commencée ET 3h écoulées depuis début).
    """
    return (
        "("
        "LOWER(REPLACE(REPLACE(REPLACE(TRIM(COALESCE(s.statut,'')), 'é', 'e'), 'è', 'e'), 'ê', 'e')) = 'complete' "
        "OR (s.debut_datetime <= NOW() AND DATE_ADD(s.debut_datetime, INTERVAL %s HOUR) < NOW())"
        ")"
    )


def seance_eligible_pour_evaluation(debut_dt, statut_raw):
    """
    Même règle que _sql_condition_seance_eligible_evaluation, en Python (affichage bouton Évaluer).
    """
    if not debut_dt:
        return False
    now = datetime.now()
    if statut_seance_est_complete(statut_raw):
        return True
    if debut_dt > now:
        return False
    fin = debut_dt + timedelta(hours=DUREE_SEANCE_EVALUATION_HEURES)
    return now > fin


def parse_debut_datetime(value):
    """Parse une valeur debut_datetime (routes / dict séance)."""
    return _parse_mysql_datetime(value)


def _etiquette_statut_seance(statut):
    """
    Libellé affiché sur la pastille de statut (carte Mes sessions).
    Cycle prévu : en attente → en cours → complète (modifiable après création).
    """
    key = _norm_statut_seance_key(statut)
    if not key:
        return "en attente"
    labels = {
        "en_attente": "en attente",
        "en_cours": "en cours",
        "complete": "complète",
        "annulee": "annulée",
        # Anciennes valeurs / données déjà en base
        "ouverte": "en attente",
        "discussion": "en attente",
    }
    return labels.get(key, str(statut).strip().lower())


def _normalize_sigle_for_match(value):
    """Normalise un csigle pour comparaison (casse, tirets, caractères invisibles, NFKC)."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    s = unicodedata.normalize("NFKC", str(value))
    s = (
        s.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
    # Retire format / largeur (ex. ZWSP, BOM) qui cassent l’égalité avec la base
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")
    s = s.replace("\ufeff", "").strip()
    return s.lower()


def _same_identifier(a, b):
    """Compare deux identifiants de manière robuste (int/str/espaces)."""
    if a is None or b is None:
        return False
    return str(a).strip() == str(b).strip()


class Database:
    def __init__(self):
        """
            Chargez les variables d'environnement de votre fichier .env comme le montre la dame dans l'atelier de migration
        """
        # Charge le .env ; override=True évite que des vars système (ex. PASSWORD vide sur Windows)
        # écrasent les valeurs du fichier — sinon connexion « sans mot de passe ».
        load_dotenv(override=True)

        # Connexion MySQL / MariaDB via PyMySQL (schéma défini dans Base_de_données.sql).
        # MYSQL_* en priorité : USER / PASSWORD peuvent entrer en conflit avec l’environnement.
        self.host = os.getenv("MYSQL_HOST") or os.getenv("HOST", "localhost")
        self.port = int(os.getenv("MYSQL_PORT") or os.getenv("PORT", "3306"))
        self.database = os.getenv("MYSQL_DATABASE") or os.getenv("DATABASE")
        self.user = os.getenv("MYSQL_USER") or os.getenv("USER")
        self.password = os.getenv("MYSQL_PASSWORD") or os.getenv("PASSWORD")

        self._open_sql_connection()

        self.migration_counter = 0

    def _open_sql_connection(self):
        self.connection = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.database,
            autocommit=True,
            charset="utf8mb4",
            use_unicode=True,
        )

        self.cursor = self.connection.cursor()

# === PARTICIPATIONS & PROFIL ===
    def get_participations_henriette(self, etudiant_id):
        """
        Récupère les séances auxquelles un étudiant participe.
        
        Exclut les séances créées par l'étudiant lui-même (on veut ses PARTICIPATIONS, pas ses créations).
        Utilise les procédures de synchronisation des colonnes pour compatibilité rétroactive.
        
        Args:
            etudiant_id (int): ID de l'étudiant
        
        Returns:
            list: Liste de dictionnaires avec infos séances (seance_id, csigle, statut, etc.)
        """
        self.cursor.execute("SET NAMES utf8mb4;")
        self._ensure_donner_retroaction_columns()
        self._ensure_retroactions_commentaire_column()
        self._ensure_retroactions_objectifs_atteints_column()

        sql = """
              SELECT s.seance_id, 
                     s.csigle, 
                     c.nom_cours, 
                     s.statut, 
                     s.mode, 
                     s.lieu_ou_lien, 
                     s.debut_datetime, 
                     s.description, 
                     e.prenom, 
                     e.nom, 
                     e.note,
                     s.createur_id
              FROM Jumeler j
                       JOIN Seances_revision s ON j.seance_id = s.seance_id
                       JOIN Cours c ON s.csigle = c.csigle
                       JOIN Etudiants e ON s.createur_id = e.etudiant_id
              WHERE j.etudiant_id = %s 
                AND j.statut = 'Accepte'
              ORDER BY s.debut_datetime DESC 
              """
        self.cursor.execute(sql, (etudiant_id,))
        rows = self.cursor.fetchall()

        participations = []
        for r in rows:
            # r indices:
            # 0 seance_id, 1 csigle, 2 nom_cours, 3 statut, 4 mode, 5 lieu, 6 debut_datetime,
            # 7 description, 8 prenom createur, 9 nom createur, 10 note createur, 11 createur_id
            dt = _parse_mysql_datetime(r[6])
            prenom = r[8]
            nom = r[9]
            participations.append(
                {
                    "seance_id": r[0],
                    "csigle": r[1],
                    "nom_cours": r[2],
                    "statut": r[3],
                    "mode": r[4],
                    "lieu_ou_lien": r[5],
                    "debut_date": _date_longue_fr(dt),
                    "debut_datetime": str(r[6]) if r[6] else None,
                    "description": r[7],
                    "createur": f"{(prenom or '').strip()} {(nom or '').strip()}".strip(),
                    "initiales": _initiales(prenom, nom),
                    "note": float(r[10]) if r[10] is not None else None,
                    "createur_id": r[11],
                }
            )
        return participations

    def _ensure_retroactions_objectifs_atteints_column(self):
        """Anciennes bases : Retroactions sans objectifs_atteints (oui/non avant le commentaire)."""
        try:
            self.cursor.execute(
                """
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'retroactions'
                LIMIT 1
                """
            )
            row = self.cursor.fetchone()
            if not row or not row[0]:
                return
            tname = row[0]
            if isinstance(tname, (bytes, bytearray)):
                tname = tname.decode("utf-8", errors="replace")
            tname = str(tname).strip()
            if not tname:
                return

            self.cursor.execute(
                """
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND LOWER(COLUMN_NAME) = 'objectifs_atteints'
                LIMIT 1
                """,
                (tname,),
            )
            if self.cursor.fetchone():
                return
            self.cursor.execute(
                f"ALTER TABLE `{tname}` ADD COLUMN objectifs_atteints TINYINT(1) NULL "
                f"COMMENT '1=oui, 0=non'"
            )
        except pymysql.err.OperationalError as err:
            code = err.args[0] if err.args else 0
            if code not in (1060, 1146):
                raise
        except Exception:
            pass

    def _ensure_retroactions_commentaire_column(self):
        """Anciennes bases : Retroactions sans colonne commentaire (évaluation globale séance)."""
        try:
            self.cursor.execute(
                """
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'retroactions'
                LIMIT 1
                """
            )
            row = self.cursor.fetchone()
            if not row or not row[0]:
                return
            tname = row[0]
            if isinstance(tname, (bytes, bytearray)):
                tname = tname.decode("utf-8", errors="replace")
            tname = str(tname).strip()
            if not tname:
                return

            self.cursor.execute(
                """
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND LOWER(COLUMN_NAME) = 'commentaire'
                LIMIT 1
                """,
                (tname,),
            )
            if self.cursor.fetchone():
                return
            self.cursor.execute(
                f"ALTER TABLE `{tname}` ADD COLUMN commentaire TEXT NULL"
            )
        except pymysql.err.OperationalError as err:
            code = err.args[0] if err.args else 0
            if code not in (1060, 1146):
                raise
        except Exception:
            pass

    def _ensure_donner_retroaction_columns(self):
        """
        Anciennes bases : Donner sans commentaire/tags (CREATE IF NOT EXISTS ne les ajoute pas).
        Ajoute les colonnes manquantes pour l’écran Évaluer.
        """
        try:
            self.cursor.execute(
                """
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND LOWER(TABLE_NAME) = 'donner'
                LIMIT 1
                """
            )
            row = self.cursor.fetchone()
            if not row or not row[0]:
                return
            tname = row[0]
            if isinstance(tname, (bytes, bytearray)):
                tname = tname.decode("utf-8", errors="replace")
            tname = str(tname).strip()
            if not tname:
                return

            def _has_column(col_lower):
                self.cursor.execute(
                    """
                    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = %s
                      AND LOWER(COLUMN_NAME) = %s
                    LIMIT 1
                    """,
                    (tname, col_lower),
                )
                return self.cursor.fetchone() is not None

            if not _has_column("commentaire"):
                self.cursor.execute(
                    f"ALTER TABLE `{tname}` ADD COLUMN commentaire TEXT NULL"
                )
            if not _has_column("tags"):
                self.cursor.execute(
                    f"ALTER TABLE `{tname}` ADD COLUMN tags VARCHAR(512) NULL"
                )
        except pymysql.err.OperationalError as err:
            code = err.args[0] if err.args else 0
            if code not in (1060, 1146):
                raise
        except Exception:
            pass

    def close(self):
        """
        Ferme la connexion à la base de données.
        
        Ferme d'abord le curseur, puis la connexion.
        Les exceptions sont silencieuses pour éviter les erreurs en cascade.
        """
        try:
            self.cursor.close()
        except Exception:
            pass
        try:
            self.connection.close()
        except Exception:
            pass

    def alloc_etudiant_id(self):
        """
        Si Etudiants.etudiant_id est AUTO_INCREMENT, retourne None (ne pas passer la colonne à l'INSERT).
        Sinon retourne une valeur compatible avec le type de colonne (ex. NI0000121 pour un VARCHAR
        comme dans insertiondata.py, ou MAX+1 pour un INT sans auto_increment).
        """
        self.cursor.execute(
            """
            SELECT COLUMN_TYPE, COALESCE(EXTRA, '')
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'Etudiants'
              AND COLUMN_NAME = 'etudiant_id'
            """
        )
        row = self.cursor.fetchone()
        if not row:
            return None
        col_type, extra = row[0], row[1]
        if isinstance(col_type, (bytes, bytearray)):
            col_type = col_type.decode("utf-8", errors="replace")
        if isinstance(extra, (bytes, bytearray)):
            extra = extra.decode("utf-8", errors="replace")
        col_type_l = (col_type or "").lower()
        extra_l = (extra or "").lower()
        if "auto_increment" in extra_l:
            return None

        if "varchar" in col_type_l or (
            "char" in col_type_l and "varchar" not in col_type_l
        ):
            self.cursor.execute(
                """
                SELECT etudiant_id FROM Etudiants
                WHERE etudiant_id REGEXP '^NI[0-9]{7}$'
                ORDER BY CAST(SUBSTRING(etudiant_id, 3) AS UNSIGNED) DESC
                LIMIT 1
                """
            )
            r = self.cursor.fetchone()
            if r and r[0] is not None:
                eid = r[0]
                if isinstance(eid, (bytes, bytearray)):
                    eid = eid.decode("utf-8", errors="replace")
                eid = str(eid).strip()
                if len(eid) >= 3 and eid.upper().startswith("NI"):
                    n = int(eid[2:]) + 1
                else:
                    n = 1
            else:
                n = 1
            return f"NI{n:07d}"

        self.cursor.execute("SELECT COALESCE(MAX(etudiant_id), 0) + 1 FROM Etudiants")
        return self.cursor.fetchone()[0]
    # ========================================================================
    # MÉTHODES DE GESTION DES SESSIONS
    # ========================================================================
    
    def get_mes_sessions(self, etudiant_id):
        """
        Récupère toutes les séances créées par un étudiant.
        
        Retourne les informations détaillées incluant:
        - Statut calculé dynamiquement
        - Nombre de participants acceptés
        - Date formatée pour l'affichage
        
        Args:
            etudiant_id (int): ID du créateur de la séance
        
        Returns:
            list: Liste de dictionnaires avec infos séances (seance_id, csigle, statut, etc.)
        """
        # Note : On utilise les noms de tables EXACTS (Majuscules) de ton script SQL
        sql = """
            SELECT
                s.seance_id,
                s.csigle,
                c.nom_cours,
                s.statut,
                s.mode,
                s.lieu_ou_lien,
                s.debut_datetime,
                s.max_participants,
                s.description,
                e.prenom,
                e.nom,
                e.note,
                COALESCE(SUM(CASE WHEN j.statut = 'En_attente' THEN 1 ELSE 0 END), 0) AS demandes_en_attente,
                COALESCE(SUM(CASE WHEN j.statut = 'Accepte' THEN 1 ELSE 0 END), 0) AS participants_acceptes
            FROM Seances_revision s
            JOIN Cours c ON c.csigle = s.csigle
            JOIN Etudiants e ON e.etudiant_id = s.createur_id
            LEFT JOIN Jumeler j ON j.seance_id = s.seance_id
            WHERE s.createur_id = %s
            GROUP BY
                s.seance_id,
                s.csigle,
                c.nom_cours,
                s.statut,
                s.mode,
                s.lieu_ou_lien,
                s.debut_datetime,
                s.max_participants,
                s.description,
                s.createur_id,
                e.prenom,
                e.nom,
                e.note
            ORDER BY s.debut_datetime DESC;
        """
        self.cursor.execute(sql, (etudiant_id,))
        rows = self.cursor.fetchall()

        sessions = []
        for row in rows:
            debut_dt = _parse_mysql_datetime(row[6])
            prenom, nom = row[9], row[10]
            note_cr = row[11]
            h0 = _heure_hm(debut_dt)
            h1 = _heure_hm(debut_dt + timedelta(hours=3)) if debut_dt else None
            heure_plage = f"{h0} – {h1}" if h0 and h1 else h0
            sessions.append({
                "seance_id": row[0],
                "csigle": row[1],
                "nom_cours": row[2],
                "statut": row[3],
                "statut_label": _etiquette_statut_seance(row[3]),
                "mode": row[4],
                "lieu_ou_lien": row[5],
                "debut_datetime": str(row[6]) if row[6] else None,
                "debut_date_longue": _date_longue_fr(debut_dt),
                "debut_heure": h0,
                "heure_plage": heure_plage,
                "max_participants": row[7],
                "description": row[8],
                "createur_prenom": prenom,
                "createur_nom": nom,
                "createur_display": f"{(prenom or '').strip()} {(nom or '').strip()}".strip(),
                "createur_initiales": _initiales(prenom, nom),
                "createur_note": float(note_cr) if note_cr is not None else None,
                "demandes_en_attente": int(row[12] or 0),
                "participants_acceptes": int(row[13] or 0),
            })
        return sessions

    def get_profil_henriette(self, etudiant_id):
        """
        Récupère le profil complet d'un étudiant.
        
        Inclut: identité, email, note moyenne, statut (Actif/Inactif), programme
        
        Args:
            etudiant_id (int): ID de l'étudiant
        
        Returns:
            dict: {id, prenom, nom, email, note, statut, programme_id} ou None si introuvable
        """
        sql = """
            SELECT e.etudiant_id, e.prenom, e.nom, e.email_ulaval, e.note, e.statut, a.programme_sigle
            FROM Etudiants e
            LEFT JOIN Appartenir a ON e.etudiant_id = a.etudiant_id
            WHERE e.etudiant_id = %s
        """
        self.cursor.execute(sql, (etudiant_id,))
        r = self.cursor.fetchone()

        if r:
            return {
                "id": r[0],
                "prenom": r[1],
                "nom": r[2],
                "email": r[3],
                "note": float(r[4]) if r[4] else None,
                "statut": r[5],  # Maintenant récupéré
                "programme_id": r[6]  # Récupéré via Appartenir (programme_sigle)
            }
        return None



    def get_sessions_passees_a_evaluer(self, etudiant_id):
        cond = _sql_condition_seance_eligible_evaluation()
        sql = f"""
            SELECT
                s.seance_id,
                s.csigle,
                c.nom_cours,
                s.debut_datetime,
                AVG(d.note) AS moyenne_note
            FROM Seances_revision s
            JOIN Cours c ON c.csigle = s.csigle
            LEFT JOIN Donner d ON d.seance_id = s.seance_id
            WHERE s.createur_id = %s
              AND {cond}
            GROUP BY s.seance_id, s.csigle, c.nom_cours, s.debut_datetime
            ORDER BY s.debut_datetime DESC;
        """
        self.cursor.execute(sql, (etudiant_id, DUREE_SEANCE_EVALUATION_HEURES))
        rows = self.cursor.fetchall()
        sessions = []
        for row in rows:
            debut_dt = _parse_mysql_datetime(row[3])
            sessions.append(
                {
                    "seance_id": row[0],
                    "csigle": row[1],
                    "nom_cours": row[2],
                    "debut_datetime": str(row[3]) if row[3] else None,
                    "debut_relatif": _relatif_passe(debut_dt),
                    "moyenne_note": float(row[4]) if row[4] is not None else None,
                }
            )
        return sessions

    def _cours_table_name(self):
        """Nom réel de la table tel que MySQL la stocke (Cours, cours, etc.)."""
        cached = getattr(self, "_cours_table_cached", None)
        if cached:
            return cached
        try:
            self.cursor.execute(
                """
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND LOWER(TABLE_NAME) = 'cours'
                LIMIT 1
                """
            )
            row = self.cursor.fetchone()
            if row and row[0]:
                name = row[0]
                if isinstance(name, (bytes, bytearray)):
                    name = name.decode("utf-8", errors="replace")
                name = str(name).strip()
                if name:
                    self._cours_table_cached = name
                    return name
        except Exception:
            pass
        for name in ("Cours", "cours"):
            try:
                self.cursor.execute(f"SELECT 1 FROM `{name}` LIMIT 1")
                self._cours_table_cached = name
                return name
            except Exception:
                continue
        self._cours_table_cached = "Cours"
        return "Cours"

    def list_cours(self):
        """Liste des cours pour formulaires (sigle + nom), tri par csigle."""
        t = self._cours_table_name()
        self.cursor.execute(
            f"""
            SELECT TRIM(csigle), nom_cours
            FROM `{t}`
            ORDER BY TRIM(csigle)
            """
        )
        return [
            {"csigle": (row[0] or "").strip(), "nom_cours": row[1]}
            for row in self.cursor.fetchall()
        ]

    def resolve_csigle(self, raw):
        """
        Retourne le csigle tel qu’en base (trim) si le cours existe, sinon None.
        Comparaison en Python après chargement des lignes : évite les écarts collation / TRIM en SQL.
        """
        want = _normalize_sigle_for_match(raw)
        if not want:
            return None
        t = self._cours_table_name()
        self.cursor.execute(f"SELECT csigle FROM `{t}`")
        for row in self.cursor.fetchall():
            if not row:
                continue
            cell = row[0]
            if isinstance(cell, (bytes, bytearray)):
                cell = cell.decode("utf-8", errors="replace")
            db_sigle = str(cell).strip()
            if _normalize_sigle_for_match(db_sigle) == want:
                return db_sigle
        return None



    def create_session(
        self,
        csigle,
        createur_id,
        debut_datetime,
        mode=None,
        statut=None,
        lieu_ou_lien=None,
        description=None,
        max_participants=None,
    ):
        try:
            # 1. Insertion dans Seances_revision
            sql_seance = """
                INSERT INTO Seances_revision
                ( csigle, createur_id, statut, lieu_ou_lien, mode, debut_datetime, description, max_participants)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """
            self.cursor.execute(
                sql_seance,
                (
                    csigle,
                    createur_id,
                    statut,
                    lieu_ou_lien,
                    mode,
                    debut_datetime,
                    description,
                    max_participants,
                ),
            )

            # 2. Récupérer l'ID auto-généré
            seance_id = self.cursor.lastrowid

            # 3. Insertion dans Creer (Historique)
            sql_creer = """
                INSERT INTO Creer (seance_id, etudiant_id, date_creation)
                VALUES (%s, %s, NOW());
            """
            self.cursor.execute(sql_creer, (seance_id, createur_id))

            # 4. Ajouter le créateur comme participant accepté
            sql_jumeler = """
                INSERT INTO Jumeler (seance_id, etudiant_id, statut)
                VALUES (%s, %s, 'Accepte');
            """
            self.cursor.execute(sql_jumeler, (seance_id, createur_id))

            # 5. On valide toutes les opérations ensemble
            self.connection.commit()
            
        except Exception as e:
            # En cas d'erreur sur l'une des étapes, on annule tout
            self.connection.rollback()
            print(f"Erreur lors de la création de la séance : {e}")
            raise e

    # --- Page « Gérer » (organisateur) ---
    def get_seance_pour_organisateur(self, seance_id, createur_id):
        """Retourne la séance si createur_id est bien l’organisateur, sinon None."""
        sql = """
            SELECT
                s.seance_id,
                s.csigle,
                c.nom_cours,
                s.statut,
                s.mode,
                s.lieu_ou_lien,
                s.debut_datetime,
                s.description,
                s.max_participants,
                s.createur_id
            FROM Seances_revision s
            JOIN Cours c ON c.csigle = s.csigle
            WHERE s.seance_id = %s AND s.createur_id = %s
        """
        self.cursor.execute(sql, (seance_id, createur_id))
        row = self.cursor.fetchone()
        if not row:
            return None
        debut_dt = _parse_mysql_datetime(row[6])
        h0 = _heure_hm(debut_dt)
        h1 = _heure_hm(debut_dt + timedelta(hours=3)) if debut_dt else None
        heure_plage = f"{h0} – {h1}" if h0 and h1 else h0
        return {
            "seance_id": row[0],
            "csigle": row[1],
            "nom_cours": row[2],
            "statut": row[3],
            "statut_label": _etiquette_statut_seance(row[3]),
            "mode": row[4],
            "lieu_ou_lien": row[5],
            "debut_datetime": str(row[6]) if row[6] else None,
            "debut_date_longue": _date_longue_fr(debut_dt),
            "heure_plage": heure_plage,
            "description": row[7],
            "max_participants": row[8],
            "createur_id": row[9],
        }

    def list_inscriptions_seance(self, seance_id):
        """
        Liste les inscriptions (demandes de participation) pour une séance.
        
        Retourne tous les étudiants avec leur statut (En_attente, Accepte, Refuse),
        incluant les notes d'évaluation si elles existent.
        
        Args:
            seance_id (int): ID de la séance
        
        Returns:
            list: Dictionnaires {etudiant_id, statut, display, note, note_existante, ...}
        """
        sql = """
            SELECT
                j.etudiant_id,
                j.statut,
                j.date_demande,
                j.date_reponse,
                e.prenom,
                e.nom,
                e.email_ulaval,
                e.note
            FROM Jumeler j
            JOIN Etudiants e ON e.etudiant_id = j.etudiant_id
            WHERE j.seance_id = %s
            ORDER BY
                CASE j.statut
                    WHEN 'En_attente' THEN 0
                    WHEN 'Accepte' THEN 1
                    ELSE 2
                END,
                j.date_demande DESC
        """
        self.cursor.execute(sql, (seance_id,))
        rows = self.cursor.fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "etudiant_id": row[0],
                    "statut": row[1],
                    "date_demande": str(row[2]) if row[2] else None,
                    "date_reponse": str(row[3]) if row[3] else None,
                    "prenom": row[4],
                    "nom": row[5],
                    "email_ulaval": row[6],
                    "note": row[7],
                    "display": f"{(row[4] or '').strip()} {(row[5] or '').strip()}".strip(),
                }
            )
        return out

    def compter_participants_acceptes(self, seance_id):
        self.cursor.execute(
            """
            SELECT COUNT(*) FROM Jumeler
            WHERE seance_id = %s AND statut = 'Accepte'
            """,
            (seance_id,),
        )
        return int(self.cursor.fetchone()[0] or 0)

    def update_seance_statut(self, seance_id, createur_id, nouveau_statut):
        """Met à jour le statut si l’étudiant est l’organisateur."""
        allowed = {"En_attente", "En_cours", "Complete", "Annulee"}
        if nouveau_statut not in allowed:
            raise ValueError(f"Statut non autorisé : {nouveau_statut}")
        self.cursor.execute(
            """
            UPDATE Seances_revision
            SET statut = %s
            WHERE seance_id = %s AND createur_id = %s
            """,
            (nouveau_statut, seance_id, createur_id),
        )
        self.connection.commit()
        return self.cursor.rowcount

    def debut_seance_modifiable_par_organisateur(self, seance_id, createur_id):
        """True si la date/heure de début peut encore être changée (strictement plus de 24 h avant)."""
        self.cursor.execute(
            """
            SELECT debut_datetime FROM Seances_revision
            WHERE seance_id = %s AND createur_id = %s
            """,
            (seance_id, createur_id),
        )
        row = self.cursor.fetchone()
        if not row or row[0] is None:
            return False
        debut = _parse_mysql_datetime(row[0])
        if not debut:
            return False
        return datetime.now() < debut - timedelta(hours=24)

    def update_seance_informations_organisateur(
        self,
        seance_id,
        createur_id,
        lieu_ou_lien=None,
        max_participants=None,
        nouveau_debut_brut=None,
        mode=None,
        description=None,
    ):
        """
        Met a jour le lieu, le mode, la description, le nombre max de participants et, si autorise, la date de debut.
        max_participants : int ou None (illimite). nouveau_debut_brut : valeur datetime-local.
        """
        self.cursor.execute(
            "SELECT createur_id FROM Seances_revision WHERE seance_id = %s",
            (seance_id,),
        )
        row = self.cursor.fetchone()
        if not row or not _same_identifier(row[0], createur_id):
            raise PermissionError("Tu n’es pas l’organisateur de cette séance.")

        n_acc = self.compter_participants_acceptes(seance_id)
        if max_participants is not None:
            max_participants = int(max_participants)
            if max_participants < 1 or max_participants > 255:
                raise ValueError(
                    "Nombre max. de participants : entre 1 et 255, ou laisse vide pour illimité."
                )
            if max_participants < n_acc:
                raise ValueError(
                    "Le plafond ne peut pas être inférieur au nombre de participants "
                    f"déjà acceptés ({n_acc})."
                )

        lieu = (lieu_ou_lien or "").strip()
        lieu_sql = lieu if lieu else None

        mode_val = (mode or "").strip()
        mode_sql = mode_val if mode_val else None

        desc = (description or "").strip()
        desc_sql = desc if desc else None

        debut_sql = None
        brut = (nouveau_debut_brut or "").strip()
        if brut:
            if not self.debut_seance_modifiable_par_organisateur(seance_id, createur_id):
                raise PermissionError(
                    "La date de début ne peut plus être modifiée (moins de 24 h avant la séance)."
                )
            s = brut.replace("T", " ")
            if len(s) == 16:
                s += ":00"
            dt = _parse_mysql_datetime(s)
            if not dt:
                raise ValueError("Date ou heure de début invalide.")
            if dt < datetime.now():
                raise ValueError("La nouvelle date de début doit être dans le futur.")
            debut_sql = s

        if debut_sql is not None:
            self.cursor.execute(
                """
                UPDATE Seances_revision
                SET lieu_ou_lien = %s, mode = %s, description = %s, max_participants = %s, debut_datetime = %s
                WHERE seance_id = %s AND createur_id = %s
                """,
                (lieu_sql, mode_sql, desc_sql, max_participants, debut_sql, seance_id, createur_id),
            )
        else:
            self.cursor.execute(
                """
                UPDATE Seances_revision
                SET lieu_ou_lien = %s, mode = %s, description = %s, max_participants = %s
                WHERE seance_id = %s AND createur_id = %s
                """,
                (lieu_sql, mode_sql, desc_sql, max_participants, seance_id, createur_id),
            )
        self.connection.commit()
        return self.cursor.rowcount

    def demander_participation(self, seance_id, etudiant_id):
        """
        Enregistre une demande de participation (insertion dans Jumeler avec statut En_attente).
        Vérifie que la séance existe et qu'on n'est pas le créateur.
        """
        self.cursor.execute(
            "SELECT createur_id FROM Seances_revision WHERE seance_id = %s",
            (seance_id,),
        )
        row = self.cursor.fetchone()
        if not row:
            raise ValueError("Séance introuvable.")
        
        if row[0] == etudiant_id:
            raise ValueError("Tu ne peux pas demander à participer à ta propre séance.")
        
        # Vérifier si une demande existe déjà
        self.cursor.execute(
            "SELECT statut FROM Jumeler WHERE seance_id = %s AND etudiant_id = %s",
            (seance_id, etudiant_id),
        )
        existing = self.cursor.fetchone()
        if existing:
            raise ValueError("Tu as déjà envoyé une demande pour cette séance.")
        
        # Insérer la demande
        self.cursor.execute(
            """
            INSERT INTO Jumeler (seance_id, etudiant_id, statut, date_demande)
            VALUES (%s, %s, 'En_attente', NOW())
            """,
            (seance_id, etudiant_id),
        )
        self.connection.commit()
        return self.cursor.rowcount

    def repondre_demande_participation(self, seance_id, createur_id, demandeur_id, accepter):
        """
        Accepter ou refuser une demande En_attente.
        Vérifie que createur_id est bien l’organisateur de la séance.
        """
        self.cursor.execute(
            "SELECT createur_id, max_participants FROM Seances_revision WHERE seance_id = %s",
            (seance_id,),
        )
        row = self.cursor.fetchone()
        if not row or not _same_identifier(row[0], createur_id):
            raise PermissionError("Tu n’es pas l’organisateur de cette séance.")
        max_p = row[1]
        if accepter and max_p is not None:
            n = self.compter_participants_acceptes(seance_id)
            if n >= int(max_p):
                raise ValueError("Nombre maximum de participants atteint.")
        nouveau = "Accepte" if accepter else "Refuse"
        self.cursor.execute(
            """
            UPDATE Jumeler
            SET statut = %s, date_reponse = NOW()
            WHERE seance_id = %s AND etudiant_id = %s AND statut = 'En_attente'
            """,
            (nouveau, seance_id, demandeur_id),
        )
        self.connection.commit()
        return self.cursor.rowcount

    def get_seance_passe_pour_evaluation(self, seance_id, createur_id):
        """
        Séance dont createur_id est l’organisateur, éligible à l’écran Évaluer :
        statut « complète » ou délai écoulé depuis le début (début + N h).
        """
        cond = _sql_condition_seance_eligible_evaluation()
        sql = f"""
            SELECT
                s.seance_id,
                s.csigle,
                c.nom_cours,
                s.debut_datetime,
                s.createur_id
            FROM Seances_revision s
            JOIN Cours c ON c.csigle = s.csigle
            WHERE s.seance_id = %s
              AND (s.createur_id = %s OR s.seance_id IN (
                SELECT seance_id FROM Jumeler 
                WHERE etudiant_id = %s AND statut = 'Accepte'
              ))
              AND {cond}
        """
        self.cursor.execute(
            sql, (seance_id, createur_id, createur_id, DUREE_SEANCE_EVALUATION_HEURES)
        )
        row = self.cursor.fetchone()
        if not row:
            return None
        debut_dt = _parse_mysql_datetime(row[3])
        return {
            "seance_id": row[0],
            "csigle": row[1],
            "nom_cours": row[2],
            "debut_datetime": str(row[3]) if row[3] else None,
            "debut_date_longue": _date_longue_fr(debut_dt),
            "debut_heure": _heure_hm(debut_dt),
            "debut_relatif": _relatif_passe(debut_dt),
            "createur_id": row[4],
        }

    def get_retroaction_seance_organisateur(self, seance_id, organisateur_id):
        """
        Dernière rétroaction globale sur la séance (table Retroactions), si l’utilisateur est organisateur.
        """
        sql = """
            SELECT r.retroaction_id, r.note, r.commentaire, r.date_retroaction,
                   r.objectifs_atteints
            FROM Retroactions r
            INNER JOIN Seances_revision s ON s.seance_id = r.seance_id
            WHERE r.seance_id = %s AND s.createur_id = %s
            ORDER BY r.retroaction_id DESC
            LIMIT 1
        """
        self.cursor.execute(sql, (seance_id, organisateur_id))
        row = self.cursor.fetchone()
        if not row:
            return None
        obj = row[4]
        if obj is not None:
            obj = int(obj)
        return {
            "retroaction_id": row[0],
            "note": int(row[1]) if row[1] is not None else None,
            "commentaire": row[2] if row[2] is not None else "",
            "date_retroaction": str(row[3]) if row[3] else None,
            "objectifs_atteints": obj,
        }

    def enregistrer_retroaction_seance_organisateur(
        self, organisateur_id, seance_id, note, commentaire=None, objectifs_atteints=None
    ):
        """
        Note globale 1–5 sur la séance, objectifs atteints (oui/non), commentaire optionnel.
        Met à jour la dernière ligne Retroactions pour cette séance ou en crée une nouvelle.
        """
        try:
            note = int(note)
        except (TypeError, ValueError):
            raise ValueError("Note séance invalide.")
        if note < 1 or note > 5:
            raise ValueError("La note de la séance doit être entre 1 et 5.")

        try:
            oa = int(objectifs_atteints)
        except (TypeError, ValueError):
            raise ValueError("Indique si les objectifs de la séance ont été atteints (oui ou non).")
        if oa not in (0, 1):
            raise ValueError("Les objectifs : choisir oui ou non.")

        texte = (commentaire or "").strip()
        if len(texte) > _RETRO_SEANCE_COMMENTAIRE_MAX_LEN:
            raise ValueError(
                f"Commentaire séance trop long (max {_RETRO_SEANCE_COMMENTAIRE_MAX_LEN} caractères)."
            )

        cond = _sql_condition_seance_eligible_evaluation()
        self.cursor.execute(
            f"""
            SELECT 1
            FROM Seances_revision s
            WHERE s.seance_id = %s
              AND s.createur_id = %s
              AND {cond}
            """,
            (seance_id, organisateur_id, DUREE_SEANCE_EVALUATION_HEURES),
        )
        if not self.cursor.fetchone():
            raise PermissionError(
                "Évaluation séance impossible : séance introuvable, tu n’en es pas l’organisateur, "
                "ou la séance n’est pas encore éligible (statut complète ou délai après le début)."
            )

        comm_sql = texte if texte else None

        self.cursor.execute(
            """
            SELECT r.retroaction_id
            FROM Retroactions r
            INNER JOIN Seances_revision s ON s.seance_id = r.seance_id
            WHERE r.seance_id = %s AND s.createur_id = %s
            ORDER BY r.retroaction_id DESC
            LIMIT 1
            """,
            (seance_id, organisateur_id),
        )
        prev = self.cursor.fetchone()
        if prev:
            self.cursor.execute(
                """
                UPDATE Retroactions
                SET note = %s, objectifs_atteints = %s, commentaire = %s, date_retroaction = NOW()
                WHERE retroaction_id = %s
                """,
                (note, oa, comm_sql, prev[0]),
            )
        else:
            self.cursor.execute(
                """
                INSERT INTO Retroactions (seance_id, date_retroaction, note, objectifs_atteints, commentaire)
                VALUES (%s, NOW(), %s, %s, %s)
                """,
                (seance_id, note, oa, comm_sql),
            )
        self.connection.commit()

    def list_participants_acceptes_pour_retroaction(self, seance_id, organisateur_id):
        """
        Participants acceptés (hors organisateur) avec la note déjà donnée par l’organisateur, le cas échéant.
        """
        sql = """
            SELECT
                j.etudiant_id,
                e.prenom,
                e.nom,
                e.email_ulaval,
                d.note,
                d.commentaire,
                d.tags
            FROM Jumeler j
            JOIN Etudiants e ON e.etudiant_id = j.etudiant_id
            LEFT JOIN Donner d
                ON d.seance_id = j.seance_id
                AND d.auteur_id = %s
                AND d.evalue_id = j.etudiant_id
            WHERE j.seance_id = %s
              AND j.statut = 'Accepte'
              AND j.etudiant_id <> %s
            ORDER BY e.nom, e.prenom, j.etudiant_id
        """
        self.cursor.execute(sql, (organisateur_id, seance_id, organisateur_id))
        rows = self.cursor.fetchall()
        out = []
        for row in rows:
            note = row[4]
            comm = row[5]
            out.append(
                {
                    "etudiant_id": row[0],
                    "prenom": row[1],
                    "nom": row[2],
                    "email_ulaval": row[3],
                    "display": f"{(row[1] or '').strip()} {(row[2] or '').strip()}".strip(),
                    "note_existante": int(note) if note is not None else None,
                    "commentaire_existant": comm if comm is not None else "",
                    "tags_existant": _parse_tags_column(row[6]),
                }
            )
        return out

    def update_etudiant_note(self, etudiant_id):
        """
        Recalcule la note moyenne de l'étudiant basée sur toutes les notes reçues dans Donner,
        et met à jour la colonne note dans Etudiants.
        """
        try:
            # Calculer la moyenne des notes reçues
            self.cursor.execute(
                """
                SELECT AVG(note) FROM Donner WHERE evalue_id = %s
                """,
                (etudiant_id,)
            )
            result = self.cursor.fetchone()
            moyenne = result[0] if result and result[0] is not None else None
            
            # Mettre à jour la note dans Etudiants
            self.cursor.execute(
                """
                UPDATE Etudiants SET note = %s WHERE etudiant_id = %s
                """,
                (moyenne, etudiant_id)
            )
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise e

    def update_etudiant_note(self, etudiant_id):
        """
        Recalcule la note moyenne de l'étudiant basée sur toutes les notes reçues dans Donner,
        et met à jour la colonne note dans Etudiants.
        """
        try:
            # Calculer la moyenne des notes reçues
            self.cursor.execute(
                """
                SELECT AVG(note) FROM Donner WHERE evalue_id = %s
                """,
                (etudiant_id,)
            )
            result = self.cursor.fetchone()
            moyenne = result[0] if result and result[0] is not None else None
            
            # Mettre à jour la note dans Etudiants
            self.cursor.execute(
                """
                UPDATE Etudiants SET note = %s WHERE etudiant_id = %s
                """,
                (moyenne, etudiant_id)
            )
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise e

    def enregistrer_retroaction_participant_organisateur(
        self, organisateur_id, evalue_id, seance_id, note, commentaire=None, tags_keys=None
    ):
        """
        Insère ou met à jour Donner : note, commentaire optionnel, tags (liste de clés autorisées).
        """
        try:
            note = int(note)
        except (TypeError, ValueError):
            raise ValueError("Note invalide.")
        if note < 1 or note > 5:
            raise ValueError("La note doit être entre 1 et 5.")

        texte = (commentaire or "").strip()
        if len(texte) > _RETRO_COMMENTAIRE_MAX_LEN:
            raise ValueError(
                f"Commentaire trop long (max {_RETRO_COMMENTAIRE_MAX_LEN} caractères)."
            )

        tags_in = tags_keys if isinstance(tags_keys, (list, tuple)) else []
        permis = tags_autorises_pour_note(note)
        tags_clean = sorted(
            {str(t).strip() for t in tags_in if str(t).strip() in permis}
        )
        tags_json = json.dumps(tags_clean, ensure_ascii=True)
        if len(tags_json) > _RETRO_TAGS_JSON_MAX_LEN:
            raise ValueError("Trop de tags sélectionnés.")

        cond = _sql_condition_seance_eligible_evaluation()
        self.cursor.execute(
            f"""
            SELECT 1
            FROM Seances_revision s
            WHERE s.seance_id = %s
              AND (s.createur_id = %s OR s.seance_id IN (
                SELECT seance_id FROM Jumeler 
                WHERE etudiant_id = %s AND statut = 'Accepte'
              ))
              AND {cond}
            """,
            (seance_id, organisateur_id, organisateur_id, DUREE_SEANCE_EVALUATION_HEURES),
        )
        if not self.cursor.fetchone():
            raise PermissionError(
                "Évaluation impossible : séance introuvable, tu n’en es pas l’organisateur, "
                "ou la séance n’est pas encore au statut complète et le délai après le début n’est pas écoulé."
            )

        if evalue_id == organisateur_id:
            raise ValueError("Tu ne peux pas t’évaluer toi-même.")

        self.cursor.execute(
            """
            SELECT 1 FROM Jumeler
            WHERE seance_id = %s AND etudiant_id = %s AND statut = 'Accepte'
            """,
            (seance_id, evalue_id),
        )
        if not self.cursor.fetchone():
            raise ValueError("Cet étudiant n’est pas un participant accepté de cette séance.")

        comm_sql = texte if texte else None
        tags_sql = tags_json if tags_clean else None

        self.cursor.execute(
            """
            INSERT INTO Donner (auteur_id, evalue_id, seance_id, note, commentaire, tags, date_retroaction)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                note = %s,
                commentaire = %s,
                tags = %s,
                date_retroaction = NOW()
            """,
            (
                organisateur_id,
                evalue_id,
                seance_id,
                note,
                comm_sql,
                tags_sql,
                note,
                comm_sql,
                tags_sql,
            ),
        )
        self.connection.commit()
        
        # Mettre à jour la note moyenne de l'étudiant évalué
        self.update_etudiant_note(evalue_id)
        
        return self.cursor.rowcount
    def update_all_session_statuses(self):
        """
        Met à jour le statut de toutes les séances dans la BD basé sur l'heure actuelle.

        Règles:
        - En_cours si séance commencée et < 3h
        - Complete si >= 3h après le début
        - Ne jamais écraser une séance annulée manuellement

        Exécuté avant chaque requête Flask (@app.before_request).
        """
        try:
            # 1) Sessions en cours: on exclut Annulee et Complete.
            self.cursor.execute(
                """
                UPDATE Seances_revision
                SET statut = 'En_cours'
                WHERE debut_datetime <= NOW()
                  AND DATE_ADD(debut_datetime, INTERVAL 3 HOUR) > NOW()
                  AND LOWER(REPLACE(REPLACE(REPLACE(TRIM(COALESCE(statut, '')), 'é', 'e'), 'è', 'e'), 'ê', 'e')) NOT IN ('en_cours', 'annulee', 'complete')
                """
            )

            # 2) Sessions complètes: on exclut seulement Annulee (qu'on respecte toujours).
            self.cursor.execute(
                """
                UPDATE Seances_revision
                SET statut = 'Complete'
                WHERE DATE_ADD(debut_datetime, INTERVAL 3 HOUR) <= NOW()
                  AND LOWER(REPLACE(REPLACE(REPLACE(TRIM(COALESCE(statut, '')), 'é', 'e'), 'è', 'e'), 'ê', 'e')) <> 'annulee'
                  AND LOWER(REPLACE(REPLACE(REPLACE(TRIM(COALESCE(statut, '')), 'é', 'e'), 'è', 'e'), 'ê', 'e')) <> 'complete'
                """
            )
            self.connection.commit()
        except Exception as e:
            print(f"Erreur lors de la mise à jour des statuts des séances: {e}")

    def mark_all_participants_present_for_completed_sessions(self):
        """
        Marque automatiquement les participants présents pour toutes les séances complètes.
        
        Appelle sp_mark_participants_present_for_completed_sessions() pour mettre à jour
        presence_confirme = TRUE pour tous les participants acceptés des séances terminées.
        """
        try:
            self.cursor.execute("CALL sp_mark_participants_present_for_completed_sessions()")
            self.connection.commit()
            return self.cursor.rowcount
        except Exception as e:
            print(f"Erreur lors de la mise à jour des présences automatiques: {e}")
            return 0

    def update_etudiant_statut(self, etudiant_id, statut):
        """
        Met à jour le statut d'un étudiant (Actif/Inactif).
        
        - Actif : quand l'étudiant se connecte
        - Inactif : quand l'étudiant se déconnecte
        
        Args:
            etudiant_id (int): ID de l'étudiant
            statut (str): 'actif' ou 'inactif'
        
        Returns:
            int: Nombre de lignes affectées
        """
        try:
            self.cursor.execute(
                "UPDATE Etudiants SET statut = %s WHERE etudiant_id = %s",
                (statut, etudiant_id)
            )
            self.connection.commit()
            return self.cursor.rowcount
        except Exception as e:
            print(f"Erreur lors de la mise à jour du statut étudiant: {e}")
            return 0

    def mark_participant_presence(self, seance_id, etudiant_id):
        """Marque automatiquement la présence d'un participant quand la séance est complète."""
        try:

            sql = """
                UPDATE Jumeler
                SET presence_confirme = TRUE
                WHERE seance_id = %s
                AND etudiant_id = %s
                AND statut = 'Accepte'
            """
            self.cursor.execute(sql, (seance_id, etudiant_id))
            self.connection.commit()
            return self.cursor.rowcount
        except Exception as e:
            print(f"Erreur lors de la mise à jour de la présence: {e}")
            return 0

    def mark_all_participants_present_for_completed_sessions(self):
        """Marque automatiquement les participants présents pour toutes les séances complètes."""
        try:
            self.cursor.execute("CALL sp_mark_participants_present_for_completed_sessions()")
            self.connection.commit()
            return self.cursor.rowcount
        except Exception as e:
            print(f"Erreur lors de la mise à jour des présences automatiques: {e}")
            return 0

    def update_etudiant_statut(self, etudiant_id, statut):
        """Met à jour le statut d'un étudiant (actif/inactif) via UPDATE direct."""
        try:
            self.cursor.execute(
                "UPDATE Etudiants SET statut = %s WHERE etudiant_id = %s",
                (statut, etudiant_id)
            )
            self.connection.commit()
            return self.cursor.rowcount
        except Exception as e:
            print(f"Erreur lors de la mise à jour du statut étudiant: {e}")
            return 0
