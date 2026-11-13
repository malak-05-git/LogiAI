"""L'API LogiAI : python -m uvicorn logiai.api.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from logiai import config
from logiai.api.schemas import Livraison, PredictionOut
from logiai.api.security import require_admin, verify_api_key
from logiai.predict import Predictor

state: dict = {}  # contient le "predictor" une fois le modèle chargé


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Exécuté UNE fois, au démarrage du serveur (pas à chaque requête)
    if config.MODEL_PATH.exists():
        state["predictor"] = Predictor(config.MODEL_PATH)
    yield
    state.clear()


app = FastAPI(
    title="LogiAI",
    version="1.1.0",
    description="Prédit le risque de retard d'une livraison. Authentification : en-tête X-API-Key.",
    lifespan=lifespan,
)

# TODO 3 (bloc 4) : autoriser la page web avec CORSMiddleware (app.add_middleware(...))
# origines : config.ALLOWED_ORIGINS ; méthodes : GET, POST, OPTIONS ; en-têtes : Content-Type, X-API-Key
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.get("/health")
def health():
    """Public : sert à la supervision, ne révèle aucun secret."""
    return {
        "status": "ok",
        "model_loaded": "predictor" in state,
        "auth_configured": bool(config.API_KEY and config.ADMIN_KEY),
    }


# TODO 1 (bloc 3) : protéger cette route avec dependencies=[Depends(verify_api_key)]
@app.post(
    "/v1/predict", response_model=PredictionOut, dependencies=[Depends(verify_api_key)]
)
def predict(livraison: Livraison):
    predictor = state.get("predictor")
    if predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Modèle non chargé : lancez 'python -m logiai.train' puis redémarrez l'API.",
        )
    return PredictionOut(**predictor.predict(livraison.model_dump()))


# TODO 2 (bloc 3) : réserver cette route à l'administrateur avec Depends(require_admin)
@app.get("/v1/model-info", dependencies=[Depends(require_admin)])
def model_info():
    """Doit être réservé à l'administrateur."""
    predictor = state.get("predictor")
    if predictor is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé.")
    return {
        "version": predictor.version,
        "seuil": predictor.threshold,
        "variables": config.FEATURES,
    }
