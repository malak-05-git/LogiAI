"""Tests de base (fournis) : le filet de sécurité hérité du TP précédent."""

from logiai.api.main import state

FACILE = {
    "distance_km": 5,
    "poids_kg": 3,
    "heure_depart": 11,
    "pluie_mm": 0,
    "trafic_index": 1,
    "nb_arrets": 0,
    "type_vehicule": "moto",
}


def test_health_repond_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_modele_charge(client):
    assert client.get("/health").json()["model_loaded"] is True


def test_predict_valide_renvoie_200(client, headers_user, livraison_valide):
    assert (
        client.post(
            "/v1/predict", json=livraison_valide, headers=headers_user
        ).status_code
        == 200
    )


def test_predict_forme_de_la_reponse(client, headers_user, livraison_valide):
    data = client.post(
        "/v1/predict", json=livraison_valide, headers=headers_user
    ).json()
    assert set(data) == {"probabilite_retard", "alerte", "seuil", "model_version"}


def test_predict_probabilite_entre_0_et_1(client, headers_user, livraison_valide):
    data = client.post(
        "/v1/predict", json=livraison_valide, headers=headers_user
    ).json()
    assert 0 <= data["probabilite_retard"] <= 1


def test_trajet_difficile_plus_risque_que_trajet_facile(
    client, headers_user, livraison_valide
):
    p_dur = client.post(
        "/v1/predict", json=livraison_valide, headers=headers_user
    ).json()["probabilite_retard"]
    p_facile = client.post("/v1/predict", json=FACILE, headers=headers_user).json()[
        "probabilite_retard"
    ]
    assert p_dur > p_facile


def test_champ_inconnu_refuse(client, headers_user, livraison_valide):
    livraison_valide["couleur"] = "rouge"
    assert (
        client.post(
            "/v1/predict", json=livraison_valide, headers=headers_user
        ).status_code
        == 422
    )


def test_modele_absent_renvoie_503(client, headers_user, livraison_valide):
    state.pop("predictor", None)  # on simule un modèle non chargé
    assert (
        client.post(
            "/v1/predict", json=livraison_valide, headers=headers_user
        ).status_code
        == 503
    )
