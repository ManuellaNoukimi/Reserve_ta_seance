# StudySync UL

Plateforme Web collaborative permettant aux étudiants de l'Université Laval de trouver, créer et gérer des séances de révision.

> Projet universitaire réalisé en équipe dans le cadre du cours GLO-2005. Le dépôt est actuellement en cours de préparation pour servir de projet de portfolio.

## Problème ciblé

L'intégration universitaire et la recherche de partenaires de révision peuvent être difficiles, particulièrement pour les nouveaux étudiants. StudySync UL facilite la mise en relation entre étudiants qui suivent les mêmes cours et souhaitent étudier ensemble.

## Fonctionnalités actuelles

- création d'un compte avec une adresse `@ulaval.ca`;
- authentification et réinitialisation du mot de passe;
- création, modification et annulation de séances de révision;
- recherche et filtrage des séances disponibles;
- demandes de participation avec acceptation ou refus par l'organisateur;
- suivi des séances créées et des participations;
- évaluation d'une séance et rétroaction entre participants;
- gestion des places disponibles et du cycle de vie des séances.

## Technologies

| Partie | Technologies |
| --- | --- |
| Interface | HTML5, CSS3, JavaScript, Jinja |
| Serveur | Python, Flask |
| Données | MySQL/MariaDB, PyMySQL |
| Sécurité | bcrypt, sessions Flask, variables d'environnement |
| Collaboration | Git et GitHub |
| Qualité | pytest, couverture de tests, GitHub Actions |

## Installation locale

### 1. Cloner le dépôt

```bash
git clone https://github.com/ManuellaNoukimi/Reserve_ta_seance.git
cd Reserve_ta_seance
```

### 2. Créer un environnement Python

Sous macOS ou Linux :

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Sous Windows PowerShell :

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Installer les dépendances

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurer l'environnement

Copier `.env.example` vers `.env`, puis remplacer les valeurs par celles de la base MySQL locale.

```bash
cp .env.example .env
```

Sous Windows PowerShell :

```powershell
Copy-Item .env.example .env
```

Pour générer une clé Flask locale :

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Initialiser MySQL

Le script SQL crée la base `Application_revision`, ses tables, ses contraintes et ses objets programmés.

```bash
mysql -u root -p < "Fichiers pour la base de données/Base_de_données.sql"
```

Après avoir configuré `.env`, les données de démonstration peuvent être ajoutées avec :

```bash
python insertiondata.py
```

### 6. Démarrer l'application

```bash
python server.py
```

Ouvrir ensuite `http://127.0.0.1:5000`.

## Tests automatisés

Installer les dépendances de développement :

```bash
pip install -r requirements-dev.txt
```

Lancer les tests :

```bash
pytest
```

Afficher également la couverture :

```bash
pytest --cov=. --cov-report=term-missing
```

Les premiers tests vérifient les pages publiques, les redirections vers la
connexion et l'impossibilité d'usurper un utilisateur avec un paramètre
`etudiant_id` dans l'URL. Ils ne nécessitent pas de serveur MySQL.

## Structure actuelle

```text
.
├── server.py                         # Routes et logique HTTP Flask
├── database.py                       # Accès aux données et logique MySQL
├── insertiondata.py                  # Données de démonstration
├── tests/                             # Tests automatisés pytest
├── .github/workflows/tests.yml        # Intégration continue
├── Fichier pour l'application/
│   ├── Templates/                    # Gabarits Jinja
│   └── static/                       # CSS, JavaScript et images
├── Fichiers pour la base de données/
│   └── Base_de_données.sql           # Schéma MySQL
├── .env.example
└── requirements.txt
```

Cette organisation reflète encore la version universitaire originale. Une restructuration progressive vers des modules Flask plus petits est prévue.

## Modèle de données

Le schéma couvre notamment :

- les étudiants et leurs programmes;
- les cours;
- les séances de révision;
- les demandes et confirmations de participation;
- les évaluations entre participants;
- la rétroaction globale sur une séance;
- les jetons de réinitialisation du mot de passe.

## Feuille de route

- [ ] renforcer l'autorisation et la protection CSRF;
- [ ] diviser `server.py` en modules Flask;
- [ ] isoler l'accès aux données de la logique métier;
- [x] ajouter les premiers tests automatisés avec `pytest`;
- [x] ajouter une intégration continue GitHub Actions;
- [ ] publier une démonstration en ligne;
- [ ] ajouter des captures d'écran et une courte vidéo de démonstration;
- [ ] recommander des séances selon les cours et disponibilités.

## État du projet

StudySync UL est un projet éducatif en amélioration active. La version actuelle est conçue pour une utilisation locale et ne doit pas être utilisée avec des données personnelles réelles avant la fin du renforcement de sécurité.
