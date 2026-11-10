# ** Assurez-vous d'avoir installé flask, pymysql, python-dotenv et cryptography
# pour faire fonctionner l'app au complet (bcrypt est requis pour insertiondata.py).**
# Commande à faire dans le terminal:
# pip install flask pymysql python-dotenv cryptography bcrypt
import os
import secrets
from datetime import datetime, timedelta

import pymysql
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import escape
from database import *
import bcrypt #Pour scripter les données sensibles de la base de données

load_dotenv()


# Dossiers des gabarits et fichiers statiques : hors du répertoire par défaut de Flask
# afin de rester alignés avec la structure du projet (voir dossier « Fichier pour l'application »).
_BASE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_DIR = os.path.join(_BASE, "Fichier pour l'application", "Templates")
_STATIC_DIR = os.path.join(_BASE, "Fichier pour l'application", "static")

app = Flask(
    __name__,
    template_folder=_TEMPLATE_DIR,
    static_folder=_STATIC_DIR,
    static_url_path="/static",
)
# La clé de session ne doit jamais avoir de valeur publique par défaut.
_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    raise RuntimeError(
        "SECRET_KEY est absente. Copie .env.example vers .env et génère une clé locale."
    )

app.config.update(
    SECRET_KEY=_secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
    == "true",
)


def _sync_session_statuses():
    """Synchronise les statuts des séances dans la BD avec le temps réel."""
    try:
        db = Database()
        db.update_all_session_statuses()
        db.mark_all_participants_present_for_completed_sessions()
        db.close()
    except Exception:
        pass


def _etudiant_id_effectif():
    """Retourne uniquement l'identité authentifiée dans la session Flask."""
    return (session.get("etudiant_id") or "").strip()


def _norm_statut_seance_key(statut):
    """Normalise la valeur statut pour comparaison robuste."""
    if statut is None:
        return ""
    t = str(statut).strip().lower()
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a")):
        t = t.replace(a, b)
    return t.replace(" ", "_")


@app.context_processor
def inject_navigation():
    eid = session.get("etudiant_id")
    return {
        "nav_etudiant_id": eid,
        "nav_logged_in": bool(eid),
    }


def _compute_session_status(seance_dict):
    """
    Calcule le statut dynamique d'une séance basé sur l'heure actuelle.
    
    Logique:
    - En_attente : si maintenant < debut_datetime
    - En_cours : si debut_datetime <= maintenant < debut_datetime + 3h
    - Complete : si maintenant >= debut_datetime + 3h
    
    Args:
        seance_dict (dict): Dictionnaire contenant au minimum 'debut_datetime'
    
    Returns:
        str: Le statut calculé ('En_attente', 'En_cours', 'Complete')
    """
    if not seance_dict:
        return "En_attente"

    statut_existant = (seance_dict.get("statut") or "").strip()
    statut_key = _norm_statut_seance_key(statut_existant)

    # Respecter les statuts finaux choisis manuellement (ne pas les écraser
    # avec le calcul temporel automatique).
    if statut_key == "annulee":
        return "Annulee"
    if statut_key == "complete":
        return "Complete"

    if "debut_datetime" not in seance_dict:
        return statut_existant or "En_attente"
    
    try:
        debut_str = seance_dict["debut_datetime"]
        if isinstance(debut_str, str):
            debut = datetime.strptime(debut_str, "%Y-%m-%d %H:%M:%S")
        else:
            debut = debut_str
        
        now = datetime.now()
        fin = debut + timedelta(hours=3)
        
        if now < debut:
            return "En_attente"
        elif now < fin:
            return "En_cours"
        else:
            return "Complete"
    except (ValueError, TypeError):
        return statut_existant or "En_attente"


def _update_session_status_and_label(seance_dict):
    """
    Met à jour le statut et le label lisible d'une séance.
    
    Ajoute deux champs au dictionnaire:
    - statut : le statut technique (En_attente, En_cours, Complete)
    - statut_label : le label en français pour l'affichage
    
    Args:
        seance_dict (dict): Dictionnaire de la séance à mettre à jour
    
    Returns:
        dict: Le dictionnaire mis à jour avec les champs statut et statut_label
    """
    if not seance_dict:
        return seance_dict
    
    statut = _compute_session_status(seance_dict)
    seance_dict["statut"] = statut
    
    if statut == "En_attente":
        seance_dict["statut_label"] = "en attente"
    elif statut == "En_cours":
        seance_dict["statut_label"] = "en cours"
    elif statut == "Complete":
        seance_dict["statut_label"] = "complete"
    
    return seance_dict


@app.before_request
def before_request():
    """
    Hook exécuté avant CHAQUE requête Flask.
    
    Synchronise les statuts de toutes les séances avec la BD en fonction de l'heure actuelle.
    Met aussi à jour la présence des participants pour les séances complètement terminées.
    
    Cela garantit que les statuts affichés sont toujours à jour sans modification manuelle.
    """
    _sync_session_statuses()


@app.route("/disponibilites", methods=["GET"])
def page_disponibilite():
    """
    Affiche la page des séances disponibles pour s'inscrire.
    
    Cette page permet aux étudiants de voir toutes les séances en attente d'inscriptions
    (exclut les séances où ils sont déjà inscrits ou dont le créateur est l'utilisateur).
    
    Returns:
        HTML: Page_Disponibilité.html
    """
    return render_template("Page_Disponibilité.html")


@app.route("/mes-sessions", methods=["GET"])
def page_mes_sessions():
    etudiant_id = _etudiant_id_effectif()

    if not etudiant_id:
        flash("Connecte-toi pour accéder à tes sessions.")
        return redirect(url_for("page_login"))

    sessions = []
    sessions_passees = []
    sessions_annulees = []
    db_error = None
    cours_choices = []

    try:
        db = Database()
        try:
            all_sessions = db.get_mes_sessions(etudiant_id)
            sessions_passees = db.get_sessions_passees_a_evaluer(etudiant_id)
            
            # Recuperer les IDs des sessions passees
            ids_sessions_passees = set(s.get("seance_id") for s in sessions_passees if s)
            
            # Mettre a jour le statut dynamique et filtrer les sessions passees
            sessions = []
            for s in all_sessions:
                _update_session_status_and_label(s)
                # Exclure les sessions qui sont deja dans "sessions passees a evaluer"
                statut_key = _norm_statut_seance_key(s.get("statut"))
                if statut_key == "annulee":
                    sessions_annulees.append(s)
                elif s.get("seance_id") not in ids_sessions_passees:
                    sessions.append(s)
            
            # Mettre a jour aussi les sessions passees
            for s in sessions_passees:
                _update_session_status_and_label(s)
            
            cours_choices = db.list_cours()
        finally:
            db.close()
    except pymysql.err.OperationalError:
        db_error = (
            "Connexion à la base de données impossible. "
            "Vérifie les valeurs de ton fichier .env (HOST, PORT, DATABASE, USER, PASSWORD)."
        )

    return render_template(
        "Mes_Sessions.html",
        etudiant_id=etudiant_id,
        sessions=sessions,
        sessions_passees=sessions_passees,
        sessions_annulees=sessions_annulees,
        db_error=db_error,
        cours_choices=cours_choices,
        now_str=__import__('datetime').datetime.now().isoformat(),
    )


def _form_csigle_from_request():
    """Sigle cours envoyé par le formulaire (gère getlist, BOM, espaces)."""
    for v in request.form.getlist("csigle"):
        t = (v or "").replace("\ufeff", "").strip()
        if t:
            return t
    return (request.form.get("csigle") or "").replace("\ufeff", "").strip()


def _html_error(body_html, status):
    doc = (
        "<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"utf-8\"/>"
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>'
        "<title>Erreur</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:560px;margin:40px auto;"
        "padding:0 16px;line-height:1.5;color:#1a1a1a}a{color:#b9040f}</style>"
        f"</head><body>{body_html}</body></html>"
    )
    r = make_response(doc, status)
    r.headers["Content-Type"] = "text/html; charset=utf-8"
    return r


@app.route("/mes-sessions/evaluer/<seance_id>", methods=["GET", "POST"])
def page_evaluer_seance(seance_id):
    """
    Rétroactions organisateur → participants (table Donner), pour une séance passée.
    Requiert ?etudiant_id= (organisateur).
    """
    etudiant_id = _etudiant_id_effectif()
    if not etudiant_id:
        return _html_error(
            "<p>Paramètre <code>etudiant_id</code> requis (organisateur), ou <a href=\""
            f'{url_for("page_login")}">connecte-toi</a>.</p>'
            f'<p>Ex. : <code>/mes-sessions/evaluer/{escape(seance_id)}?etudiant_id=1</code></p>',
            400,
        )

    error_msg = None
    force_edit_session = False
    force_edit_participant_id = None
    db = None
    seance = None
    participants = []

    try:
        db = Database()
    except pymysql.err.OperationalError as err:
        return _html_error(
            f"<p>Connexion MySQL impossible.</p><p><small>{escape(str(err))}</small></p>",
            503,
        )

    if request.method == "POST":
        eval_kind = (request.form.get("eval_kind") or "participant").strip()
        if eval_kind == "session":
            note_seance = (request.form.get("note_seance") or "").strip()
            commentaire_seance = (request.form.get("commentaire_seance") or "").strip()
            objectifs_raw = (request.form.get("objectifs_atteints") or "").strip()
            try:
                if not note_seance:
                    raise ValueError("Choisis une note pour l’ensemble de la séance.")
                db.enregistrer_retroaction_seance_organisateur(
                    etudiant_id,
                    seance_id,
                    note_seance,
                    commentaire=commentaire_seance,
                    objectifs_atteints=objectifs_raw,
                )
                db.close()
                return redirect(
                    url_for(
                        "page_evaluer_seance",
                        seance_id=seance_id,
                        etudiant_id=etudiant_id,
                    )
                )
            except (ValueError, PermissionError) as err:
                error_msg = str(err)
                force_edit_session = True
            except pymysql.err.Error as err:
                error_msg = f"Erreur base de données : {err}"
                force_edit_session = True
        else:
            evalue_id = (request.form.get("evalue_id") or "").strip()
            note_raw = (request.form.get("note") or "").strip()
            commentaire = (request.form.get("commentaire") or "").strip()
            tags_selection = request.form.getlist("tags")
            try:
                if not evalue_id:
                    raise ValueError("Participant manquant.")
                db.enregistrer_retroaction_participant_organisateur(
                    etudiant_id,
                    evalue_id,
                    seance_id,
                    note_raw,
                    commentaire=commentaire,
                    tags_keys=tags_selection,
                )
                db.close()
                return redirect(
                    url_for(
                        "page_evaluer_seance",
                        seance_id=seance_id,
                        etudiant_id=etudiant_id,
                    )
                )
            except (ValueError, PermissionError) as err:
                error_msg = str(err)
                force_edit_participant_id = evalue_id if evalue_id else None
            except pymysql.err.Error as err:
                error_msg = f"Erreur base de données : {err}"
                force_edit_participant_id = evalue_id if evalue_id else None

    retro_seance = None
    try:
        seance = db.get_seance_passe_pour_evaluation(seance_id, etudiant_id)
        if seance:
            participants = db.list_participants_acceptes_pour_retroaction(
                seance_id, etudiant_id
            )
            retro_seance = db.get_retroaction_seance_organisateur(
                seance_id, etudiant_id
            )
    finally:
        try:
            db.close()
        except Exception:
            pass

    if not seance:
        return _html_error(
            "<p><strong>Évaluation indisponible.</strong></p>"
            "<p>La séance est introuvable, tu n’en es pas l’organisateur, ou elle n’est pas encore "
            "<strong>éligible</strong> (statut <strong>complète</strong> ou délai après le début : début + 3 h).</p>"
            f'<p><a href="{url_for("page_mes_sessions", etudiant_id=etudiant_id)}">Retour à Mes sessions</a></p>',
            404,
        )

    edit_session_arg = request.args.get("edit_session", "").strip() == "1"
    edit_p_arg = request.args.get("edit_p", "").strip()
    has_session_bilan = bool(retro_seance and retro_seance.get("note") is not None)
    show_session_summary = (
        has_session_bilan
        and not edit_session_arg
        and not force_edit_session
    )

    is_creator = seance and seance.get("createur_id") == etudiant_id

    return render_template(
        "Page_Evaluer_Seance.html",
        etudiant_id=etudiant_id,
        seance=seance,
        participants=participants,
        retro_seance=retro_seance,
        error_msg=error_msg,
        show_session_summary=show_session_summary,
        edit_p_requested=edit_p_arg,
        force_edit_participant_id=force_edit_participant_id,
        is_creator=is_creator,
        evaluation_tags_by_note_items=sorted(
            EVALUATION_TAGS_BY_NOTE.items(), key=lambda x: -x[0]
        ),
        evaluation_note_labels=EVALUATION_NOTE_LABELS,
        evaluation_tag_labels=EVALUATION_TAG_LABELS,
    )


@app.route("/mes-sessions/creer", methods=["GET", "POST"])
def creer_mes_sessions():
    # Évite « invalid response » si quelqu’un ouvre cette URL en GET (signet, lien direct).
    if request.method == "GET":
        eid = _etudiant_id_effectif()
        if eid:
            return redirect(url_for("page_mes_sessions", etudiant_id=eid))
        return redirect(url_for("page_login"))

    etudiant_id = _etudiant_id_effectif()
    if not etudiant_id:
        return _html_error("<p>Paramètre <code>etudiant_id</code> requis.</p>", 400)

    csigle_raw = _form_csigle_from_request()
    debut_datetime_raw = request.form.get("debut_datetime", "").strip()
    mode = request.form.get("mode", "").strip() or None
    # Nouvelle séance : toujours « en attente » ; passage en cours / complète plus tard (écran Gérer, etc.).
    statut = "En_attente"
    lieu_ou_lien = request.form.get("lieu_ou_lien", "").strip() or None
    description = request.form.get("description", "").strip() or None
    max_participants_raw = request.form.get("max_participants", "").strip()

    if not csigle_raw or not debut_datetime_raw:
        return _html_error("<p>Champs requis : cours (csigle) et date/heure de début.</p>", 400)

    # datetime-local envoie « 2026-03-15T14:30 » : MySQL attend souvent un espace à la place de « T ».
    debut_datetime = debut_datetime_raw.replace("T", " ").strip()
    if len(debut_datetime) == 16:
        debut_datetime += ":00"
    
    # Valider que la date n'est pas dans le passé
    try:
        from datetime import datetime as dt
        debut_dt = dt.strptime(debut_datetime, "%Y-%m-%d %H:%M:%S")
        if debut_dt <= dt.now():
            return _html_error(
                "<p><strong>Date invalide.</strong> La date de début ne peut pas être dans le passé ou maintenant.</p>",
                400,
            )
    except ValueError as e:
        return _html_error(
            f"<p><strong>Format de date invalide.</strong> Erreur: {escape(str(e))}</p>",
            400,
        )

    if max_participants_raw:
        try:
            max_participants = int(max_participants_raw)
            if max_participants < 1 or max_participants > 255:
                raise ValueError("hors plage")
        except ValueError:
            return _html_error(
                "<p><strong>Max participants</strong> : entier entre 1 et 255.</p>",
                400,
            )
    else:
        max_participants = None

    db = None
    try:
        db = Database()
    except pymysql.err.OperationalError as err:
        return _html_error(
            f"<p>Connexion MySQL impossible.</p><p><small>{escape(str(err))}</small></p>",
            503,
        )

    try:
        csigle = db.resolve_csigle(csigle_raw)
        if not csigle:
            try:
                nb_cours = len(db.list_cours())
            except Exception:
                nb_cours = -1
            if nb_cours == 0:
                flash(
                    "La table des cours est vide. Exécute une fois « python insertiondata.py » "
                    "à la racine du projet, ou ajoute des lignes dans Cours (ex. GLO-2005), puis recharge la page."
                )
            elif nb_cours > 0:
                flash(
                    "Le sigle envoyé ne correspond à aucun cours en base (après « "
                    + escape(csigle_raw[:32])
                    + " »). Recharge la page, choisis un cours dans la liste, ou redémarre le serveur Flask."
                )
            else:
                flash(
                    "Impossible de lire la table Cours. Vérifie la connexion MySQL et que la base "
                    "sélectionnée dans le fichier .env est bien celle qui contient tes cours."
                )
            return redirect(url_for("page_mes_sessions", etudiant_id=etudiant_id))

        db.create_session(
            csigle=csigle,
            createur_id=etudiant_id,
            debut_datetime=debut_datetime,
            mode=mode,
            statut=statut,
            lieu_ou_lien=lieu_ou_lien,
            description=description,
            max_participants=max_participants,
        )
    except pymysql.err.IntegrityError as err:
        flash(
            "Enregistrement refusé : vérifie que ton compte existe toujours dans Etudiants "
            "et que le cours existe dans Cours. Détail technique : "
            + str(err)
        )
        return redirect(url_for("page_mes_sessions", etudiant_id=etudiant_id))
    except Exception as err:
        return _html_error(
            "<p><strong>Erreur serveur lors de la création.</strong></p>"
            f"<p><small>{escape(str(err))}</small></p>"
            f'<p><a href="{url_for("page_mes_sessions", etudiant_id=etudiant_id)}">Retour</a></p>',
            500,
        )
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    return redirect(url_for("page_mes_sessions", etudiant_id=etudiant_id))


@app.route("/sessions/<seance_id>", methods=["GET", "POST"])
def page_gerer_seance(seance_id):
    """
    Gestion d’une séance par l’organisateur : statut, demandes de participation.
    Requiert ?etudiant_id= (identité de l’organisateur), faute de session Flask dédiée.
    """
    seance_id = int(seance_id)
    etudiant_id = _etudiant_id_effectif()
    if not etudiant_id:
        return _html_error(
            "<p>Paramètre <code>etudiant_id</code> requis (organisateur), ou <a href=\""
            f'{url_for("page_login")}">connecte-toi</a>.</p>'
            '<p>Ex. : <code>/sessions/1?etudiant_id=1</code></p>',
            400,
        )

    error_msg = None
    db = None

    try:
        db = Database()
    except pymysql.err.OperationalError as err:
        return _html_error(
            f"<p>Connexion MySQL impossible.</p><p><small>{escape(str(err))}</small></p>",
            503,
        )

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        try:
            if action == "statut":
                nouveau = (request.form.get("nouveau_statut") or "").strip()
                db.update_seance_statut(seance_id, etudiant_id, nouveau)
            elif action == "accepter":
                demandeur = (request.form.get("demandeur_id") or "").strip()
                if not demandeur:
                    raise ValueError("Identifiant du demandeur manquant.")
                demandeur = int(demandeur)
                n = db.repondre_demande_participation(seance_id, etudiant_id, demandeur, True)
                if n == 0:
                    raise ValueError("Aucune demande en attente pour cet étudiant.")
            elif action == "refuser":
                demandeur = (request.form.get("demandeur_id") or "").strip()
                if not demandeur:
                    raise ValueError("Identifiant du demandeur manquant.")
                demandeur = int(demandeur)
                n = db.repondre_demande_participation(seance_id, etudiant_id, demandeur, False)
                if n == 0:
                    raise ValueError("Aucune demande en attente pour cet étudiant.")
            elif action == "infos":
                lieu = (request.form.get("lieu_ou_lien") or "").strip()
                mode = (request.form.get("mode") or "").strip()
                desc = (request.form.get("description") or "").strip()
                max_raw = (request.form.get("max_participants") or "").strip()
                max_p = None
                if max_raw:
                    try:
                        max_p = int(max_raw)
                    except ValueError:
                        raise ValueError(
                            "Nombre max. de participants invalide : saisis un entier entre 1 et 255, ou laisse le champ vide."
                        ) from None
                debut_raw = ""
                if db.debut_seance_modifiable_par_organisateur(seance_id, etudiant_id):
                    debut_raw = (request.form.get("debut_datetime") or "").strip()
                db.update_seance_informations_organisateur(
                    seance_id,
                    etudiant_id,
                    lieu_ou_lien=lieu,
                    max_participants=max_p,
                    nouveau_debut_brut=debut_raw or None,
                    mode=mode or None,
                    description=desc or None,
                )
            else:
                raise ValueError("Action inconnue.")
            db.close()
            return redirect(
                url_for("page_gerer_seance", seance_id=seance_id, etudiant_id=etudiant_id)
            )
        except (ValueError, PermissionError) as err:
            error_msg = str(err)
        except pymysql.err.Error as err:
            error_msg = f"Erreur base de données : {err}"

    seance = None
    inscriptions = []
    nb_acceptes = 0
    peut_modifier_debut = False
    try:
        seance = db.get_seance_pour_organisateur(seance_id, etudiant_id)
        if seance:
            inscriptions = db.list_inscriptions_seance(seance_id)
            nb_acceptes = db.compter_participants_acceptes(seance_id)
            peut_modifier_debut = db.debut_seance_modifiable_par_organisateur(
                seance_id, etudiant_id
            )
    finally:
        try:
            db.close()
        except Exception:
            pass

    if not seance:
        return _html_error(
            "<p><strong>Séance introuvable</strong> ou tu n’en es pas l’organisateur.</p>"
            f'<p><a href="{url_for("page_mes_sessions", etudiant_id=etudiant_id)}">Retour à Mes sessions</a></p>',
            404,
        )

    return render_template(
        "Page_Gerer_Seance.html",
        etudiant_id=etudiant_id,
        seance=seance,
        inscriptions=inscriptions,
        nb_acceptes=nb_acceptes,
        error_msg=error_msg,
        peut_modifier_debut=peut_modifier_debut,
    )


@app.route("/sessions", methods=["GET"])
def get_sessions():
    type_filtre = request.args.get("type", "")
    dispo_filtre = request.args.get("dispo", "")
    query_filtre = request.args.get("query", "")
    
    etudiant_connecte = (session.get("etudiant_id") or "").strip()

    sql = """
        SELECT 
            s.seance_id,
            s.csigle,
            c.nom_cours,
            s.mode,
            s.lieu_ou_lien,
            s.debut_datetime,
            s.description,
            s.max_participants,
            s.statut,
            COUNT(j.etudiant_id) AS nb_participants,
            s.createur_id,
            (SELECT statut FROM Jumeler 
             WHERE seance_id = s.seance_id AND etudiant_id = %s LIMIT 1) AS user_participation_status
        FROM Seances_revision s
        JOIN Cours c ON s.csigle = c.csigle
        LEFT JOIN Jumeler j ON s.seance_id = j.seance_id AND j.statut = 'Accepte'
        WHERE 1=1
    """
    params = []
    
    if etudiant_connecte:
        params.append(int(etudiant_connecte))

    if type_filtre:
        sql += " AND s.mode = %s"
        params.append(type_filtre)

    if query_filtre:
        sql += " AND (c.nom_cours LIKE %s OR s.csigle LIKE %s)"
        params.append(f"%{query_filtre}%")
        params.append(f"%{query_filtre}%")

    # Exclure les sessions où l'utilisateur est déjà accepté ou refusé, sauf s'il en est le créateur
    if etudiant_connecte:
        sql += """
            AND (s.createur_id = %s OR s.seance_id NOT IN (
                SELECT seance_id FROM Jumeler 
                WHERE etudiant_id = %s AND (statut = 'Accepte' OR statut = 'Refuse')
            ))
        """
        params.append(int(etudiant_connecte))
        params.append(int(etudiant_connecte))

    # Exclure les séances dont le début a déjà commencé (prevent inscription when session has started)
    sql += " AND s.debut_datetime > NOW()"

    sql += " GROUP BY s.seance_id"

    # Par defaut, afficher toutes les sessions, mais permettre le filtre "Places disponibles"
    if dispo_filtre == "places":
        sql += " HAVING nb_participants < COALESCE(s.max_participants, 999999)"
    elif dispo_filtre == "complet":
        sql += " HAVING nb_participants >= s.max_participants"
    else:
        # Par defaut : exclure les sessions sans places (si max_participants est defini et atteint)
        sql += " HAVING (s.max_participants IS NULL OR nb_participants < s.max_participants)"

    db = Database()
    db.cursor.execute(sql, params)
    rows = db.cursor.fetchall()

    sessions = []
    for row in rows:
        sessions.append(
            {
                "seance_id": row[0],
                "csigle": row[1],
                "nom_cours": row[2],
                "mode": row[3],
                "lieu_ou_lien": row[4],
                "debut_datetime": str(row[5]),
                "description": row[6],
                "max_participants": row[7],
                "statut": row[8],
                "nb_participants": row[9],
                "createur_id": row[10],
                "user_participation_status": row[11],
            }
        )

    return jsonify({"sessions": sessions, "etudiant_connecte": etudiant_connecte})


@app.route("/", methods=["GET"])
def page_accueil():
    """
    Affiche la page d'accueil du site.
    
    Page publique sans authentification, présente les fonctionnalités de StudyMatch UL.
    
    Returns:
        HTML: Page_Accueil.html
    """
    return render_template("Page_Accueil.html")


@app.route("/login", methods=["GET", "POST"])
def page_login():
    """
    Gère l'authentification des utilisateurs.
    
    GET: Affiche le formulaire de connexion
    POST: Valide les identifiants (email + mot de passe avec bcrypt)
          - Crée une session Flask avec l'etudiant_id
          - Met à jour le statut de l'étudiant à "Actif" dans la BD
          - Redirige vers /disponibilites en cas de succès
          - Affiche erreur et reste sur /login en cas d'échec
    
    Returns:
        GET: HTML du formulaire
        POST: Redirection vers /disponibilites ou formulaire avec erreur
    """
    if request.method == "GET":
        return render_template("Page_login.html")

    email_ulaval = request.form.get("email_ulaval", "").strip()
    mot_de_passe = request.form.get("mot_de_passe", "").strip()

    if not email_ulaval or not mot_de_passe:
        flash("Veuillez remplir tous les champs.", "error")
        return redirect(url_for("page_login"))

    db = None
    try:
        db = Database()

        # On cherche l'utilisateur par email seulement
        sql = """
            SELECT etudiant_id, prenom, nom, mot_de_passe
            FROM Etudiants
            WHERE email_ulaval = %s
        """
        db.cursor.execute(sql, (email_ulaval,))
        etudiant = db.cursor.fetchone()

        # Si aucun compte n'existe avec cet email
        if not etudiant:
            flash("Courriel ou mot de passe incorrect.", "error")
            return redirect(url_for("page_login"))

        # Récupération du hash stocké en BD
        mot_de_passe_hash = etudiant[3]

        # Vérification du mot de passe avec bcrypt
        if not bcrypt.checkpw(
            mot_de_passe.encode("utf-8"),
            mot_de_passe_hash.encode("utf-8")
        ):
            flash("Courriel ou mot de passe incorrect.", "error")
            return redirect(url_for("page_login"))

        session["etudiant_id"] = str(etudiant[0])
        # Mettre à jour le statut de l'étudiant à "actif"
        db.update_etudiant_statut(etudiant[0], "actif")
        flash("Connexion réussie.", "success")
        return redirect(url_for("page_disponibilite"))

    except pymysql.Error as e:
        print(f"Erreur BD lors de la connexion : {e}")
        flash("Erreur de connexion à la base de données. Veuillez réessayer.", "error")
        return redirect(url_for("page_login"))
    except Exception as e:
        print(f"Erreur inattendue lors de la connexion : {e}")
        flash("Email ou mot de passe incorrect. Veuillez réessayer.", "error")
        return redirect(url_for("page_login"))
    finally:
        if db is not None:
            db.close()

@app.route("/logout", methods=["GET", "POST"])
def page_logout():
    etudiant_id = session.get("etudiant_id")
    if etudiant_id:
        # Mettre à jour le statut de l'étudiant à "inactif"
        try:
            db = Database()
            db.update_etudiant_statut(int(etudiant_id), "inactif")
            db.close()
        except Exception:
            pass
    session.pop("etudiant_id", None)
    # Vider les messages flash pour éviter qu'ils persistent après déconnexion
    session.pop('_flashes', None)
    return redirect(url_for("page_accueil"))


@app.route("/signup", methods=["GET", "POST"])
def page_signup():
    # Si on ouvre simplement la page, on affiche le formulaire
    if request.method == "GET":
        return render_template("Page_signup.html")

    # Récupération des données du formulaire
    prenom = request.form.get("prenom", "").strip()
    nom = request.form.get("nom", "").strip()
    email_ulaval = request.form.get("email_ulaval", "").strip()
    programme_id = request.form.get("programme_id", "").strip()
    mot_de_passe = request.form.get("mot_de_passe", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    # Vérifications de base
    if not prenom or not nom or not email_ulaval or not programme_id or not mot_de_passe:
        flash("Tous les champs sont obligatoires.", "error")
        return redirect(url_for("page_signup"))

    if not email_ulaval.endswith("@ulaval.ca"):
        flash("Veuillez utiliser un courriel universitaire @ulaval.ca.", "error")
        return redirect(url_for("page_signup"))

    if mot_de_passe != confirm_password:
        flash("Les mots de passe ne correspondent pas.", "error")
        return redirect(url_for("page_signup"))

    if len(mot_de_passe) < 8:
        flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
        return redirect(url_for("page_signup"))

    db = None
    try:
        db = Database()

        # Hachage du mot de passe
        mot_de_passe_hash = bcrypt.hashpw(
            mot_de_passe.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        new_id = db.alloc_etudiant_id()
        if new_id is not None:
            sql = """
                INSERT INTO Etudiants (
                    etudiant_id,
                    nom,
                    prenom,
                    email_ulaval,
                    mot_de_passe,
                    statut,
                    note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                new_id,
                nom,
                prenom,
                email_ulaval,
                mot_de_passe_hash,
                "inactif",
                None,
            )
        else:
            sql = """
                INSERT INTO Etudiants (
                    nom,
                    prenom,
                    email_ulaval,
                    mot_de_passe,
                    statut,
                    note
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            params = (
                nom,
                prenom,
                email_ulaval,
                mot_de_passe_hash,
                "inactif",
                None,
            )

        db.cursor.execute(sql, params)
        # Pas de commit ici - on attend que tout soit prêt

        # Récupère l'ID de l'étudiant nouvellement créé
        if new_id is None:
            # Si on a pas utilisé new_id, faut récupérer l'ID auto-généré
            db.cursor.execute("SELECT LAST_INSERT_ID()")
            new_id = db.cursor.fetchone()[0]

        # Insère la relation Appartenir
        sql_appartenir = """
            INSERT INTO Appartenir (etudiant_id, programme_sigle)
            VALUES (%s, %s)
        """
        db.cursor.execute(sql_appartenir, (new_id, programme_id))
        
        # Un seul commit pour les deux opérations
        db.connection.commit()

        flash("Inscription réussie. Vous pouvez maintenant vous connecter.", "success")
        return redirect(url_for("page_login"))

    except Exception as e:
        # Afficher un message convivialsans exposer les détails BD
        error_str = str(e).lower()
        if "duplicate" in error_str and "email" in error_str:
            flash("Cet email est déjà utilisé. Veuillez en choisir un autre.", "error")
        elif "duplicate" in error_str:
            flash("Cette valeur existe déjà. Veuillez vérifier vos données.", "error")
        else:
            flash("Une erreur s'est produite lors de l'inscription. Veuillez réessayer.", "error")
        return redirect(url_for("page_signup"))
    finally:
        if db is not None:
            db.close()
@app.route("/forgot-password", methods=["GET", "POST"])
def page_forgot_password():
    if request.method == "GET":
        return render_template(
            "Page_forgot_password.html",
            reset_link=session.pop("password_reset_link", None),
        )

    email_ulaval = request.form.get("email_ulaval", "").strip()

    if not email_ulaval:
        flash("Veuillez entrer votre courriel universitaire.","error")
        return redirect(url_for("page_forgot_password"))

    if not email_ulaval.endswith("@ulaval.ca"):
        flash("Veuillez utiliser un courriel universitaire @ulaval.ca.","error")
        return redirect(url_for("page_forgot_password"))

    db = None
    try:
        db = Database()

        sql_check = """
            SELECT email_ulaval
            FROM Etudiants
            WHERE email_ulaval = %s
        """
        db.cursor.execute(sql_check, (email_ulaval,))
        etudiant = db.cursor.fetchone()

        if not etudiant:
            flash("Aucun compte n'est associé à ce courriel.","error")
            return redirect(url_for("page_forgot_password"))

        token = secrets.token_urlsafe(32)
        expiration = datetime.now() + timedelta(minutes=15)

        sql_upsert = """
            INSERT INTO Reinitialiser_mot_de_passe (email_ulaval, reset_token, expiration)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                reset_token = VALUES(reset_token),
                expiration = VALUES(expiration)
        """
        db.cursor.execute(sql_upsert, (email_ulaval, token, expiration))
        db.connection.commit()

        reset_link = url_for("page_reset_password", token=token, _external=True)
        # Démonstration locale : en production, ce lien doit être envoyé par courriel.
        session["password_reset_link"] = reset_link
        flash("Le lien de réinitialisation a été généré.", "info")
        return redirect(url_for("page_forgot_password"))
    except Exception as e:
        flash("Une erreur s'est produite. Veuillez réessayer.","error")
        return redirect(url_for("page_forgot_password"))
    finally:
        if db is not None:
            db.close()
@app.route("/reset-password", methods=["GET", "POST"])
def page_reset_password():
    if request.method == "GET":
        token = request.args.get("token", "").strip()

        if not token:
            flash("Lien invalide.", "error")
            return redirect(url_for("page_forgot_password"))

        return render_template("Page_reset_password.html", token=token)

    token = request.form.get("token", "").strip()
    mot_de_passe = request.form.get("mot_de_passe", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not token:
        flash("Token invalide.", "error")
        return redirect(url_for("page_forgot_password"))

    if not mot_de_passe or not confirm_password:
        flash("Tous les champs sont obligatoires.", "error")
        return redirect(url_for("page_reset_password", token=token))

    if len(mot_de_passe) < 8:
        flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
        return redirect(url_for("page_reset_password", token=token))

    if mot_de_passe != confirm_password:
        flash("Les mots de passe ne correspondent pas.", "error")
        return redirect(url_for("page_reset_password", token=token))

    db = None
    try:
        db = Database()

        sql_token = """
            SELECT email_ulaval, expiration
            FROM Reinitialiser_mot_de_passe
            WHERE reset_token = %s
        """
        db.cursor.execute(sql_token, (token,))
        resultat = db.cursor.fetchone()

        if not resultat:
            flash("Lien de réinitialisation invalide.", "error")
            return redirect(url_for("page_forgot_password"))

        email_ulaval = resultat[0]
        expiration = resultat[1]

        if datetime.now() > expiration:
            flash("Le lien de réinitialisation a expiré.", "error")
            return redirect(url_for("page_forgot_password"))

        mot_de_passe_hash = bcrypt.hashpw(
            mot_de_passe.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        sql_update_password = """
            UPDATE Etudiants
            SET mot_de_passe = %s
            WHERE email_ulaval = %s
        """
        db.cursor.execute(sql_update_password, (mot_de_passe_hash, email_ulaval))

        sql_delete_token = """
            DELETE FROM Reinitialiser_mot_de_passe
            WHERE email_ulaval = %s
        """
        db.cursor.execute(sql_delete_token, (email_ulaval,))

        db.connection.commit()

        flash("Mot de passe réinitialisé avec succès.", "success")
        return redirect(url_for("page_login"))

    except Exception as e:
        flash("Une erreur s'est produite lors de la réinitialisation. Veuillez réessayer.", "error")
        return redirect(url_for("page_forgot_password"))
    finally:
        if db is not None:
            db.close()

@app.route("/demander-participation", methods=["POST"])
def demander_participation():
    """Enregistre une demande de participation de l'étudiant connecté à une séance."""
    etudiant_id = (session.get("etudiant_id") or "").strip()
    if not etudiant_id:
        return jsonify({"error": "Connecte-toi pour demander une participation"}), 401
    
    seance_id = (request.form.get("seance_id") or "").strip()
    if not seance_id:
        return jsonify({"error": "Séance manquante"}), 400
    
    db = None
    try:
        db = Database()
        db.demander_participation(seance_id, etudiant_id)
        return jsonify({"success": True, "message": "Demande de participation envoyée"}), 200
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    except Exception as err:
        return jsonify({"error": f"Erreur : {str(err)}"}), 500
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

#Participation et profil
@app.route("/mes-participations", methods=["GET"])
def page_mes_participations():
    eid = (session.get("etudiant_id") or "").strip()
    if not eid:
        return redirect(url_for("page_login"))

    try:
        eid_int = int(eid)
    except (ValueError, TypeError):
        eid_int = None

    db = Database()
    try:
        data = db.get_participations_henriette(eid)
        # Exclure les sessions creees par l'etudiant lui-meme
        if eid_int:
            data = [p for p in data if p and p.get("createur_id") != eid_int]
        # Statut affiché + bouton Évaluer (même règle que get_seance_passe_pour_evaluation)
        for p in data:
            if p:
                _update_session_status_and_label(p)
                p["peut_evaluer"] = seance_eligible_pour_evaluation(
                    parse_debut_datetime(p.get("debut_datetime")),
                    p.get("statut"),
                )
    finally:
        db.close()

    return render_template(
        "Mes_Participations.html",
        participations=data,
        etudiant_id=eid,
    )
@app.route("/mon-profil")
def page_mon_profil():
    """Affiche le profil complet de l'étudiant."""
    eid = _etudiant_id_effectif()
    if not eid:
        # Si pas d'ID, on redirige vers le login
        return redirect(url_for('page_login'))

    db = Database()
    # On récupère les infos de base (NI, nom, email, note, programme_id)
    user = db.get_profil_henriette(eid)
    db.close()

    # Si l'étudiant n'existe pas dans la DB, on redirige
    if not user:
        return redirect(url_for('page_login'))

    # Puisque l'étudiant a réussi à charger cette page,
    # on considère qu'il est en ligne.
    return render_template("Page_Profil.html",
                           user=user,
                           etudiant_id=eid,
                           is_online=True)  # Nouvelle variable passée au HTML
if __name__ == "__main__":
    # Point d'entrée pour lancer l'application en local (développement).
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
