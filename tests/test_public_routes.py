import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/login",
        "/signup",
        "/forgot-password",
    ],
)
def test_public_pages_are_available(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")


def test_home_page_uses_french_document_language(client):
    response = client.get("/")

    assert b'<html lang="fr">' in response.data

