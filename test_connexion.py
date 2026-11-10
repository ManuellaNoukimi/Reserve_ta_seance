from database import Database

try:
    db = Database()
    print("SUCCESS: Connexion reussie a MySQL !") 
    # Testons si on peut lire le nom de la base
    db.cursor.execute("SELECT DATABASE();")
    result = db.cursor.fetchone()
    print(f"Base de donnees active : {result[0]}")
    db.close()
except Exception as e:
    # str(e) permet d'éviter les problèmes d'affichage de l'objet erreur
    print("ERROR: Erreur de connexion !")
    print(str(e))