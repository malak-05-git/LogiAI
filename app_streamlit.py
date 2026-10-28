"""Interface utilisateur Streamlit pour l'API LogiAI.

Lancement :
    streamlit run app_streamlit.py
"""
import os
import requests
import streamlit as st

st.set_page_config(
    page_title="LogiAI — Prédiction Retards Livraisons",
    page_icon="🚚",
    layout="wide",
)

st.title("🚚 LogiAI — Prédiction du Risque de Retard")
st.markdown(
    "Application client connectée à l'API REST FastAPI de **LogiAI**. "
    "Elle évalue le risque de retard d'une livraison selon ses caractéristiques logistiques et météo."
)

# Configuration de l'URL API (configurable)
DEFAULT_API_URL = os.getenv("LOGIAI_API_URL", "http://localhost:8000")

with st.sidebar:
    st.header("⚙️ Configuration API")
    api_base_url = st.text_input("URL de base de l'API :", value=DEFAULT_API_URL).rstrip("/")
    predict_endpoint = f"{api_base_url}/v1/predict"
    health_endpoint = f"{api_base_url}/health"

    st.markdown("---")
    st.subheader("État du service")
    if st.button("Vérifier la connexion à l'API"):
        try:
            resp = requests.get(health_endpoint, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                st.success(f"API en ligne (status: {data.get('status')})")
                if data.get("model_loaded"):
                    st.info("✅ Modèle chargé et opérationnel")
                else:
                    st.warning("⚠️ Modèle non chargé (indisponible)")
            else:
                st.error(f"API a répondu avec le statut HTTP {resp.status_code}")
        except requests.exceptions.RequestException as exc:
            st.error(f"Impossible de joindre l'API : {exc}")

st.header("📋 Caractéristiques de la livraison")

col1, col2 = st.columns(2)

with col1:
    distance_km = st.number_input(
        "Distance du trajet (km)",
        min_value=1.0,
        max_value=1000.0,
        value=120.0,
        step=1.0,
        help="Distance totale prévue en kilomètres (1 à 1000 km)",
    )
    poids_kg = st.number_input(
        "Poids transporté (kg)",
        min_value=0.1,
        max_value=3500.0,
        value=450.0,
        step=5.0,
        help="Poids de la marchandise transportée (0.1 à 3500 kg)",
    )
    heure_depart = st.slider(
        "Heure de départ (0h à 23h)",
        min_value=0,
        max_value=23,
        value=17,
        help="Heure entière de départ de la livraison (format 24h)",
    )
    type_vehicule = st.selectbox(
        "Type de véhicule",
        options=["moto", "fourgon", "camion"],
        index=2,
        help="Catégorie de véhicule assignée à la course",
    )

with col2:
    pluie_mm = st.number_input(
        "Précipitations prévues (mm de pluie)",
        min_value=0.0,
        max_value=100.0,
        value=8.0,
        step=0.5,
        help="Niveau de pluie prévu sur l'itinéraire (0 à 100 mm)",
    )
    trafic_index = st.slider(
        "Indice de trafic (0 = fluide, 10 = saturé)",
        min_value=0.0,
        max_value=10.0,
        value=7.5,
        step=0.1,
        help="Indice d'intensité du trafic routier estimé",
    )
    nb_arrets = st.number_input(
        "Nombre d'arrêts prévus",
        min_value=0,
        max_value=30,
        value=4,
        step=1,
        help="Nombre d'arrêts de déchargement intermédiaires",
    )

payload = {
    "distance_km": float(distance_km),
    "poids_kg": float(poids_kg),
    "heure_depart": int(heure_depart),
    "pluie_mm": float(pluie_mm),
    "trafic_index": float(trafic_index),
    "nb_arrets": int(nb_arrets),
    "type_vehicule": str(type_vehicule),
}

st.markdown("---")

if st.button("🚀 Prédire le risque de retard", type="primary", use_container_width=True):
    with st.spinner("Interrogation de l'API LogiAI..."):
        try:
            response = requests.post(predict_endpoint, json=payload, timeout=5)

            if response.status_code == 200:
                result = response.json()
                proba = result["probabilite_retard"]
                alerte = result["alerte"]
                seuil = result["seuil"]
                version = result["model_version"]

                st.subheader("📊 Résultat de l'analyse")

                res_col1, res_col2, res_col3 = st.columns(3)
                res_col1.metric("Probabilité de retard", f"{proba * 100:.1f} %")
                res_col2.metric("Seuil critique d'alerte", f"{seuil * 100:.0f} %")
                res_col3.metric("Version du modèle", version)

                st.progress(min(max(proba, 0.0), 1.0))

                if alerte:
                    st.error(
                        f"🚨 **ALERTE RETARD DÉCLENCHÉE** (Risque : {proba * 100:.1f}% >= Seuil : {seuil * 100:.0f}%)\n\n"
                        "Cette livraison présente un risque élevé de retard. Le dispatcher doit être notifié pour envisager "
                        "une réorganisation d'itinéraire ou une réaffectation."
                    )
                else:
                    st.success(
                        f"✅ **LIVRAISON CONFORME / DANS LES DÉLAIS** (Risque : {proba * 100:.1f}% < Seuil : {seuil * 100:.0f}%)\n\n"
                        "Le risque estimé est sous le seuil d'alerte. La livraison peut être exécutée normalement."
                    )

            elif response.status_code == 422:
                err_detail = response.json().get("detail", "Données invalides")
                st.error("⚠️ **Erreur 422 — Données d'entrée non valides**")
                st.json(err_detail)

            elif response.status_code == 503:
                err_detail = response.json().get("detail", "Service indisponible")
                st.error(f"🛑 **Erreur 503 — Modèle indisponible :** {err_detail}")

            else:
                st.error(f"Erreur inattendue HTTP {response.status_code} : {response.text}")

        except requests.exceptions.ConnectionError:
            st.error(
                f"❌ **Impossible de joindre le serveur API à l'adresse `{predict_endpoint}`.**\n\n"
                "Vérifiez que le serveur FastAPI est bien démarré avec la commande :\n"
                "```powershell\n"
                "python -m uvicorn logiai.api.main:app --reload\n"
                "```"
            )
        except requests.exceptions.Timeout:
            st.error("⏱️ **Délai d'attente dépassé** lors de la communication avec l'API.")
        except Exception as exc:
            st.error(f"Une erreur imprévue est survenue : {exc}")
