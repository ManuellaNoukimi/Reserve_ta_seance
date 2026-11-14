import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/mes-sessions",
        "/mon-profil",
        "/mes-participations",
    ],
)
def test_private_pages_redirect_anonymous_users_to_login(client, path):
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


@pytest.mark.parametrize(
    "path",
    [
        "/mes-sessions?etudiant_id=1",
        "/mon-profil?etudiant_id=1",
    ],
)
def test_query_parameter_cannot_impersonate_a_user(client, path):
    response = client.get(path, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_authenticated_identity_comes_from_flask_session(client):
    with client.session_transaction() as flask_session:
        flask_session["etudiant_id"] = "42"

    with client.application.test_request_context("/?etudiant_id=7"):
        from flask import session

        session["etudiant_id"] = "42"
        from server import _etudiant_id_effectif

        assert _etudiant_id_effectif() == "42"

