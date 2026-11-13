"""Réglages du projet LogiAI : tout ce qui peut changer est ici."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")  # lit le fichier .env (jamais versionné)
except ImportError:
    pass  # sans python-dotenv, on lit seulement les variables d'environnement

DATA_PATH = ROOT / "data" / "livraisons.csv"
MODEL_PATH = ROOT / "models" / "model.joblib"
INFO_PATH = ROOT / "models" / "model_info.json"

TARGET = "retard"  # 1 = livraison en retard, 0 = à l'heure
NUM_FEATURES = [
    "distance_km",
    "poids_kg",
    "heure_depart",
    "pluie_mm",
    "trafic_index",
    "nb_arrets",
]
CAT_FEATURES = ["type_vehicule"]
FEATURES = NUM_FEATURES + CAT_FEATURES

ALERT_THRESHOLD = 0.4  # au-dessus : on prévient le dispatcher
SEED = 42

# Sécurité : les clés viennent de l'environnement, jamais du code
API_KEY = os.getenv("LOGIAI_API_KEY")  # clé d'un utilisateur ordinaire
ADMIN_KEY = os.getenv("LOGIAI_ADMIN_KEY")  # clé d'un administrateur

# Pages web autorisées à appeler l'API depuis un navigateur (CORS)
ALLOWED_ORIGINS = ["http://localhost:5500", "http://127.0.0.1:5500"]
