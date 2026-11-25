"""Tests de sécurité : authentification (401) et autorisation (403)."""

from logiai import config


def test_health_reste_public(client):
    assert client.get("/health").status_code == 200


def test_predict_sans_cle_refuse(client, livraison_valide):
    # Exemple fourni : écrivez les suivants sur ce modèle.
    r = client.post("/v1/predict", json=livraison_valide)
    assert r.status_code == 401


def test_predict_cle_invalide_refuse(client, livraison_valide):
    r = client.post(
        "/v1/predict", json=livraison_valide, headers={"X-API-Key": "mauvaise-cle"}
    )
    assert r.status_code == 401


def test_predict_cle_vide_refuse(client, livraison_valide):
    r = client.post("/v1/predict", json=livraison_valide, headers={"X-API-Key": ""})
    assert r.status_code == 401


def test_predict_cle_utilisateur_accepte(client, headers_user, livraison_valide):
    r = client.post("/v1/predict", json=livraison_valide, headers=headers_user)
    assert r.status_code == 200


def test_predict_cle_admin_accepte(client, headers_admin, livraison_valide):
    r = client.post("/v1/predict", json=livraison_valide, headers=headers_admin)
    assert r.status_code == 200


def test_model_info_sans_cle_refuse(client):
    r = client.get("/v1/model-info")
    assert r.status_code == 401


def test_model_info_cle_utilisateur_interdite(client, headers_user):
    r = client.get("/v1/model-info", headers=headers_user)
    assert r.status_code == 403


def test_model_info_cle_admin_accepte(client, headers_admin):
    r = client.get("/v1/model-info", headers=headers_admin)
    assert r.status_code == 200
    assert "version" in r.json()


def test_la_reponse_401_ne_revele_pas_la_cle(client, livraison_valide):
    r = client.post(
        "/v1/predict", json=livraison_valide, headers={"X-API-Key": "mauvaise-cle"}
    )
    assert r.status_code == 401
    assert config.API_KEY not in r.text
    assert config.ADMIN_KEY not in r.text


def test_sans_configuration_tout_est_refuse(client, livraison_valide, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", None)
    monkeypatch.setattr(config, "ADMIN_KEY", None)
    r = client.post(
        "/v1/predict", json=livraison_valide, headers={"X-API-Key": "cle-quelconque"}
    )
    assert r.status_code == 401
