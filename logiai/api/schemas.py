"""Les fiches techniques (schémas Pydantic) de l'API LogiAI."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Livraison(BaseModel):
    """Une livraison à évaluer : les 7 variables du contrat."""

    model_config = ConfigDict(extra="forbid")  # un champ inconnu est refusé (422)

    # Le premier champ est donné. À VOUS : écrire les 6 autres, avec des bornes réalistes.
    distance_km: float = Field(ge=1, le=1000, description="Distance du trajet (km)")
    # poids_kg        : float  (kg)
    # heure_depart    : int    (0 à 23)
    # pluie_mm        : float  (mm)
    # trafic_index    : float  (0 = fluide, 10 = saturé)
    # nb_arrets       : int
    # type_vehicule   : Literal["moto", "fourgon", "camion"]


class PredictionOut(BaseModel):
    probabilite_retard: float = Field(ge=0, le=1, description="Probabilité que la livraison soit en retard")
    alerte: bool = Field(description="True si la probabilité atteint le seuil")
    seuil: float = Field(description="Seuil d'alerte utilisé")
    model_version: str = Field(description="Version du modèle")
