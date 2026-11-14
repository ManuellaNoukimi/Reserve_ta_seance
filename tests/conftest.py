import os
import sys
from pathlib import Path

import pytest


# Garantit que le module server.py à la racine est importable, que pytest soit
# lancé avec `pytest` ou `python -m pytest`, sous Windows comme sous Linux.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# server.py exige volontairement une clé de session. Les tests utilisent une
# valeur locale qui n'est jamais destinée à la production.
os.environ.setdefault("SECRET_KEY", "test-secret-key-only")
os.environ.setdefault("FLASK_DEBUG", "false")

import server  # noqa: E402  (variables d'environnement définies avant l'import)


@pytest.fixture()
def app(monkeypatch):
    """Application Flask configurée pour des tests sans connexion MySQL."""
    monkeypatch.setattr(server, "_sync_session_statuses", lambda: None)
    server.app.config.update(TESTING=True)
    yield server.app


@pytest.fixture()
def client(app):
    return app.test_client()

