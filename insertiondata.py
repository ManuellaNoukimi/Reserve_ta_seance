# Il s'agit du fichier qui permettra d'insérer des données fictives dans la base de données
# Il va chiffrer automatiquement les mots de passe en les créant
# Exécuter une seule fois : python insertiondata.py
#
# Connexion : voir database.py (autocommit activé). Prévoir MYSQL_USER dans le .env pour l’utilisateur SQL
# sous Windows afin d’éviter la confusion avec la variable système USER.

import random
import bcrypt #Pour scripter les données sensibles de la base de données


from datetime import datetime, timedelta
from database import Database # provient du fichier database.py pour la connexion avec la base de données

db = Database()
cur = db.cursor

now = datetime.now()  # cohérence temporelle

# ============================================================
# DONNÉES DE BASE
# ============================================================

programmes = [
    ('GLO', 'Génie logiciel', 'Premier cycle', 3, 'Sciences et génie'),
    ('IFT', 'Informatique', 'Premier cycle', 3, 'Sciences et génie'),
    ('MAT', 'Mathématiques', 'Premier cycle', 3, 'Sciences et génie'),
    ('CHM', 'Chimie', 'Premier cycle', 3, 'Sciences et génie'),
    ('PHY', 'Physique', 'Premier cycle', 3, 'Sciences et génie'),
    ('BIO', 'Biologie', 'Premier cycle', 3, 'Sciences et génie'),
]
cours_liste = [
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
    ('STT-1000', 'Probabilités et statistiques', 3),
]

prenoms = ['Alice', 'Bob', 'Clara', 'David', 'Emma', 'Félix', 'Gabrielle',
           'Hugo', 'Inès', 'Julien', 'Karine', 'Lucas', 'Mia', 'Nathan',
           'Olivia', 'Pierre', 'Quinn', 'Rachel', 'Samuel', 'Théa']

noms = ['Tremblay', 'Gagnon', 'Roy', 'Côté', 'Bouchard', 'Gagné', 'Lavoie','Fortin', 'Morin', 'Leblanc', 'Michaud', 'Bergeron', 'Girard', 'Bélanger']

lieux = [
    'Bibliothèque Gabrielle-Roy, salle 3210',
    'Pavillon Adrien-Pouliot, local 1244',
    'Bibliothèque des sciences, salle silencieuse',
    'Pavillon Charles-De Koninck, local 0248',
    'Pavillon Desjardins, salle 2101',
    'Bibliothèque générale, zone collaborative',
]
descriptions = [
    'Révision examen intra - dérivées et intégrales',
    'Structures de données - listes et dictionnaires',
    'Préparation examen final',
    'Exercices pratiques sur les pointeurs',
    'Révision théorème de Bayes et probabilités',
    'Questions de l\'examen de mi-session',
    'Résolution de problèmes ensemble',
    'Préparation au laboratoire de la semaine prochaine',
]

modes = ['Présentiel', 'En ligne', 'Distanciel']
statuts_etudiant = ['actif', 'inactif']
# Aligné sur le cycle Mes sessions : en attente → en cours → complète (± annulée).
statuts_seance = ['En_attente', 'En_cours', 'Complete', 'Annulee']

# ============================================================
# INSERTION PROGRAMMES
# L'utilisation du %s sert à sécuriser les insertions en cachant les données
# ============================================================

print("Insertion des programmes...")
for p in programmes:
    cur.execute("""
        INSERT IGNORE INTO Programmes (sigle, pnom, cycle, duree, faculte)
        VALUES (%s, %s, %s, %s, %s)
    """, p)

# ============================================================
# INSERTION COURS
# L'utilisation du %s sert à sécuriser les insertions en cachant les données
# ============================================================

print("Insertion des cours...")
for c in cours_liste:
    cur.execute("""
        INSERT IGNORE INTO Cours (csigle, nom_cours, credits)
        VALUES (%s, %s, %s)
    """, c)


# ============================================================
# LIAISON OFFRIR
# ============================================================

print("Liaison programmes-cours...")
for prog in programmes:
    cours_assignes = random.sample(cours_liste, k=random.randint(3, 6))
    for c in cours_assignes:
        cur.execute("""
            INSERT IGNORE INTO Offrir (sigle, csigle)
            VALUES (%s, %s)
        """, (prog[0], c[0]))

# ============================================================
# INSERTION ÉTUDIANTS
# Les noms et prénoms sont choisis aléatoirement
# L'identifiant est généré automatiquement par MySQL (AUTO_INCREMENT)
# Le hachage des mots de passe est fait avec bcrypt pour assurer la sécurité des données
# L'utilisation du %s sert à sécuriser les insertions en cachant les données
# ============================================================
print("Insertion des étudiants...")
etudiants_ids = []

# Si le script a déjà été lancé, récupérer les IDs existants en BD
cur.execute("SELECT etudiant_id FROM Etudiants")
etudiants_ids = [row[0] for row in cur.fetchall()]

for i in range(1, 121):
    prenom = random.choice(prenoms)
    nom = random.choice(noms)
    email = f"{prenom.lower()}.{nom.lower()}{i}@ulaval.ca"
    mot_de_passe_brut = f"Password{i}!"
    mot_de_passe = bcrypt.hashpw(mot_de_passe_brut.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    statut = random.choice(statuts_etudiant)
    programme_id = random.choice(programmes)[0]
    note = round(random.uniform(2.0, 4.3), 2)

    cur.execute("""
        INSERT IGNORE INTO Etudiants
            (nom, prenom, email_ulaval, mot_de_passe, statut, note)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (nom, prenom, email, mot_de_passe, statut, note))

    # Récupérer l'ID généré par MySQL (0 si ignoré car email déjà existant)
    generated_id = cur.lastrowid
    if generated_id:
        etudiants_ids.append(generated_id)

        cur.execute("""
            INSERT IGNORE INTO Appartenir (programme_sigle, etudiant_id)
            VALUES (%s, %s)
        """, (programme_id, generated_id))

# ============================================================
# INSCRIPTION AUX COURS
# L'utilisation du random.sample sert à affecter à chaque étudiant un nombre de cours aléatoire tout en étant différent
# L'insertion des notes et sessions sont aléatoires
# ============================================================

print("Inscription des étudiants aux cours...")
sessions_academique = ['Hiver 2026', 'Automne 2025']
notes_possibles = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'E', None]

for etudiant_id in etudiants_ids:
    #Attribution de cours différent à chaque étudiant en nombre varié
    cours_inscrits = random.sample(cours_liste, k=random.randint(2, 5))

    for c in cours_inscrits:
        cur.execute("""
            INSERT IGNORE INTO Inscrire (etudiant_id, csigle, session, note_cours)
            VALUES (%s, %s, %s, %s)
        """, (etudiant_id, c[0], random.choice(sessions_academique), random.choice(notes_possibles)))

# ============================================================
# INSERTION SÉANCES
# L'objectif est de créer une base de données contenant des séances déjà présentes
# L'identifiant est généré automatiquement par MySQL (AUTO_INCREMENT)
# ============================================================

print("Insertion des séances...")
seances_ids = []

for i in range(1, 121):
    csigle = random.choice(cours_liste)[0]
    createur_id = random.choice(etudiants_ids)
    mode = random.choice(modes)
    lieu = random.choice(lieux)
    description = random.choice(descriptions)
    max_participants = random.randint(2, 10)

    # Uniquement des séances à venir (aucune date passée)
    jours_offset = random.randint(1, 60)
    debut = now + timedelta(days=jours_offset, hours=random.randint(8, 20))
    debut = debut.replace(minute=0, second=0, microsecond=0)
    if debut <= now:
        debut = (now + timedelta(days=1)).replace(
            hour=random.randint(8, 20), minute=0, second=0, microsecond=0
        )

    statut = random.choice(['En_attente', 'Annulee'])

    cur.execute("""
        INSERT INTO Seances_revision
            (csigle, createur_id, statut, lieu_ou_lien,
             mode, debut_datetime, description, max_participants)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (csigle, createur_id, statut, lieu,
          mode, debut, description, max_participants))

    # Récupérer l'ID généré par MySQL
    generated_seance_id = cur.lastrowid
    seances_ids.append((generated_seance_id, createur_id))

    cur.execute("""
        INSERT INTO Creer (etudiant_id, seance_id, date_creation)
        VALUES (%s, %s, %s)
    """, (createur_id, generated_seance_id, now))

# ============================================================
# PARTICIPATION
# ============================================================

print("Insertion des participations...")
statuts_jumeler = ['Accepte', 'Refuse', 'En_attente']

for seance_id, createur_id in seances_ids:
    nb_participants = random.randint(0, 5)

    #Crée une liste de candidats qui participeront à une séance en excluant le créateur lui-même
    candidats = [e for e in etudiants_ids if e != createur_id]
    participants = random.sample(candidats, k=min(nb_participants, len(candidats)))

    for etudiant_id in participants:
        # La logique est la suivante : si la demande est accepté alors, on peut soit être présent ou non à la séance
        statut_j = random.choice(statuts_jumeler)
        date_demande = now - timedelta(days=random.randint(1, 10))

        if statut_j == 'Accepte':
            date_reponse = date_demande + timedelta(hours=random.randint(1, 48))
            presence = random.choice([True, False])
        elif statut_j == 'Refuse':
            date_reponse = date_demande + timedelta(hours=random.randint(1, 48))
            presence = False
        else:  # En_attente
            date_reponse = None
            presence = None

        cur.execute("""
            INSERT IGNORE INTO Jumeler
                (etudiant_id, seance_id, statut, date_demande, date_reponse, presence_confirme)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (etudiant_id, seance_id, statut_j, date_demande, date_reponse, presence))

# ============================================================
# RÉTROACTIONS
# Seulement entre participants acceptés d'une même séance
# ============================================================
print("Insertion des rétroactions...")
paires_vues = set()

# Récupérer les participants acceptés par séance
cur.execute("""
    SELECT seance_id, etudiant_id FROM Jumeler WHERE statut = 'Accepte'
""")
participants_par_seance = {}
for row in cur.fetchall():
    participants_par_seance.setdefault(row[0], []).append(row[1])

echantillon = random.sample(seances_ids, k=min(40, len(seances_ids)))
for seance_id, createur_id in echantillon:
    # Participants acceptés + le créateur
    participants = participants_par_seance.get(seance_id, [])
    membres = list(set(participants + [createur_id]))

    if len(membres) < 2:
        continue

    auteur_id = random.choice(membres)
    evalue_id = random.choice([m for m in membres if m != auteur_id])

    cle = (auteur_id, evalue_id, seance_id)
    if cle in paires_vues:
        continue

    paires_vues.add(cle)

    cur.execute("""
        INSERT IGNORE INTO Donner
            (auteur_id, evalue_id, seance_id, note, commentaire, tags, date_retroaction)
        VALUES (%s, %s, %s, %s, NULL, NULL, %s)
    """, (auteur_id, evalue_id, seance_id, random.randint(1, 5), now))

# ============================================================
# COMMIT FINAL
# ============================================================
# La classe Database active autocommit=True sur la connexion PyMySQL : chaque INSERT est
# validé immédiatement. Pas d’appel à connection.commit() nécessaire ici (évite l’erreur
# sur un attribut .conn inexistant).

print("✅ Seed terminé avec succès !")