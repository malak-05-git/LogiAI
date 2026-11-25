"""Outils partagés par tous les tests (fixtures)."""

import pytest
from fastapi.testclient import TestClient

from logiai import config
from logiai.api.main import app

CLE_USER = "cle-test-utilisateur"
CLE_ADMIN = "cle-test-admin"


@pytest.fixture(autouse=True)
def cles_de_test(monkeypatch):
    """Les tests n'utilisent jamais vos vraies clés du fichier .env."""
    monkeypatch.setattr(config, "API_KEY", CLE_USER)
    monkeypatch.setattr(config, "ADMIN_KEY", CLE_ADMIN)


@pytest.fixture
def client():
    """Un client de test ; le 'with' exécute le démarrage (chargement du modèle)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def headers_user():
    return {"X-API-Key": CLE_USER}


@pytest.fixture
def headers_admin():
    return {"X-API-Key": CLE_ADMIN}


@pytest.fixture
def livraison_valide():
    """Une livraison correcte, neuve à chaque test (on peut la modifier librement)."""
    return {
        "distance_km": 120.0,
        "poids_kg": 450.0,
        "heure_depart": 17,
        "pluie_mm": 8.0,
        "trafic_index": 7.5,
        "nb_arrets": 4,
        "type_vehicule": "camion",
    }
