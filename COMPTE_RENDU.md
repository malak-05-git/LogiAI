# Compte Rendu : TP API LogiAI (Atelier 3)

**Module :** Développement et déploiement d’applications intelligentes  
**Encadrante :** Mme Soukaina Gouraguine  
**Année universitaire :** 2026-2027  
**Étudiantes :** Malak Moukhliss & Binôme  
**Groupe :** IA & Big Data  

---

## 1. Contexte, Objectifs & Architecture

### 1.1 Contexte du projet
Le projet **LogiAI** vise à industrialiser un modèle de Machine Learning prédisant le risque de retard de livraisons sous la forme d'un service web RESTful avec **FastAPI**, interrogeable par des applications tierces (notamment un client interactif **Streamlit**).

### 1.2 Architecture globale de l'application
Le projet respecte une architecture modulaire et découplée :
- `logiai/config.py` : Configuration centralisée des chemins, des hyperparamètres, des variables explicatives et du seuil d'alerte (`0.4`).
- `logiai/dataset.py` : Génération et préparation des données de livraison synthétiques (`data/livraisons.csv`).
- `logiai/train.py` : Pipeline d'entraînement scikit-learn (`StandardScaler` + `OneHotEncoder` + `LogisticRegression`) et sérialisation du modèle (`models/model.joblib`).
- `logiai/predict.py` : Module de prédiction encapsulant le chargement du pipeline et le calcul de la probabilité de retard.
- `logiai/api/schemas.py` : Contrats de données Pydantic v2 (`Livraison` en entrée avec validation stricte, `PredictionOut` en sortie).
- `logiai/api/main.py` : Point d'entrée de l'API FastAPI avec gestion de cycle de vie `lifespan` et routes `/health` et `/v1/predict`.
- `app_streamlit.py` : Interface utilisateur web pour la saisie interactive des paramètres et l'affichage des alertes.
- `tests/test_api.py` : Suite de tests automatisés validant la conformité de l'API sous différents scénarios avec `pytest` et `TestClient`.

### 1.3 Technologies utilisées
| Technologie | Version | Rôle |
|---|---|---|
| **FastAPI** | >= 0.110 | Framework web asynchrone haute performance pour l'API REST |
| **Uvicorn** | >= 0.29 | Serveur ASGI d'exécution pour FastAPI |
| **Pydantic** | >= 2.6 | Validation des types, des bornes métiers et génération du schéma OpenAPI |
| **Scikit-learn** | >= 1.4 | Entraînement du pipeline de régression logistique |
| **Pandas / NumPy** | >= 2.0 / >= 1.26 | Traitement et manipulation des données matricielles |
| **Joblib** | >= 1.3 | Sérialisation et chargement rapide du pipeline entraîné |
| **Pytest / HTTPX** | >= 8.0 / >= 0.27 | Tests unitaires et d'intégration HTTP |
| **Streamlit** | >= 1.35 | Interface graphique utilisateur pour les démonstrations |

---

## 2. Environnement et premiers tests

### Sortie de `python -m pytest` au départ (diagnostic initial)
```text
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\DELL\Downloads\starter-20261028T092813Z-1-001\starter
plugins: anyio-4.15.1
collected 13 items

tests\test_api.py ..FFFF......F                                          [100%]

=========================== short test summary info ===========================
FAILED tests/test_api.py::test_predict_valide_renvoie_200 - assert 422 == 200
FAILED tests/test_api.py::test_predict_forme_de_la_reponse - AssertionError
FAILED tests/test_api.py::test_predict_probabilite_entre_0_et_1 - KeyError: 'probabilite_retard'
FAILED tests/test_api.py::test_predict_trajet_risque_plus_eleve_que_trajet_facile - KeyError: 'probabilite_retard'
FAILED tests/test_api.py::test_modele_absent_renvoie_503 - assert 422 == 503
=================== 5 failed, 8 passed, 1 warning in 17.42s ===================
```

### Pourquoi certains tests qui attendent un 422 passent-ils déjà, alors que rien n'est écrit ?
Dans le code de départ, le schéma Pydantic `Livraison` ne contenait qu'un seul champ déclaré (`distance_km`) et était configuré avec `model_config = ConfigDict(extra="forbid")`.  
Lors des tests envoyant un payload complet (contenant `poids_kg`, `type_vehicule="avion"`, `pluie_mm=500`, etc.), Pydantic rejetait systématiquement la requête avec un code **HTTP 422** en indiquant que ces champs étaient des champs non autorisés (*extra fields not permitted*).  
Ainsi, les tests qui attendaient une erreur 422 pour véhicule inconnu ou pluie impossible passaient par "accident" (faux succès), car la validation métier n'était pas encore active : le rejet provenait uniquement de l'absence de déclaration des champs dans le schéma.

---

## 3. Schéma Pydantic et Validation Métier

### Tableau des bornes et justification physique

| Variable | Type | Min | Max | Justification physique et métier |
|---|---|---|---|---|
| `distance_km` | `float` | 1.0 | 1000.0 | Distance d'une course de livraison : minimum 1 km (course urbaine locale) et maximum 1 000 km (trajet routier longue distance national). |
| `poids_kg` | `float` | 0.1 | 3500.0 | Masse transportée : minimum 100 g (pli ou petit paquet) et maximum 3,5 tonnes (charge utile légale maximale d'un véhicule utilitaire léger ou porteur urbain). |
| `heure_depart` | `int` | 0 | 23 | Heure de début de la tournée sur l'échelle des 24 heures d'une journée civile (format entier 0 à 23). |
| `pluie_mm` | `float` | 0.0 | 100.0 | Précipitations mesurées sur l'itinéraire : 0 mm pour un temps sec ; 100 mm correspond au seuil de pluie torrentielle / vigilance inondation extrême. |
| `trafic_index` | `float` | 0.0 | 10.0 | Indice d'encombrement routier normalisé de 0 (circulation parfaitement fluide) à 10 (saturation totale / blocage complet du trafic). |
| `nb_arrets` | `int` | 0 | 30 | Nombre d'arrêts de livraison intermédiaires, borné entre 0 (trajet direct point à point) et 30 arrêts (capacité maximale raisonnable d'une tournée journalière). |
| `type_vehicule` | `Literal` | - | - | Restreint strictement aux trois modes de transport supportés : `"moto"`, `"fourgon"`, `"camion"`. |

Tous les champs numériques flottants sont protégés par `allow_inf_nan=False` afin de refuser formellement les valeurs `NaN` et infinies. Les champs entiers (`heure_depart`, `nb_arrets`) interdisent les valeurs fractionnaires (par exemple `8.5`).

---

## 4. Implémentation de la fonction `predict()`

```python
@app.post("/v1/predict", response_model=PredictionOut)
def predict(livraison: Livraison):
    # 1. Récupération du predictor instancié au démarrage dans l'état partagé
    predictor = state.get("predictor")
    
    # 2. Gestion de l'indisponibilité du modèle (HTTP 503)
    if predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Modèle de prédiction non disponible. Veuillez vérifier le chargement du modèle.",
        )
        
    # 3. Prédiction et réponse conforme au schéma de sortie
    result = predictor.predict(livraison.model_dump())
    return PredictionOut(**result)
```

---

## 5. Quatre Requêtes de Référence

| Requête | Code HTTP obtenu | Explication détaillée |
|---|---|---|
| **Livraison normale** (distance 120 km, poids 450 kg, heure 17h, pluie 8 mm, trafic 7.5, 4 arrêts, camion) | **200 OK** | Données parfaitement conformes au schéma Pydantic. Le modèle calcule une probabilité de retard (`0.7320`), déclenchant l'alerte (`alerte: true` car `0.7320 >= 0.4`). |
| **`distance_km = -5`** | **422 Unprocessable Entity** | Rejet immédiat par Pydantic : la valeur -5 viole la contrainte `ge=1.0` du champ `distance_km`. |
| **`type_vehicule = "avion"`** | **422 Unprocessable Entity** | Rejet immédiat par Pydantic : `"avion"` n'appartient pas à l'ensemble autorisé `Literal["moto", "fourgon", "camion"]`. |
| **Modèle absent** (clé `predictor` supprimée de `state` ou modèle non entraîné) | **503 Service Unavailable** | L'API intercepte l'absence du prédicteur en mémoire et retourne une erreur 503 explicite sans provoquer de crash du serveur. |

---

## 6. Questions de Compréhension

### 1. Pourquoi charge-t-on le modèle au démarrage et pas à chaque requête ?
Le chargement d'un modèle sérialisé (`model.joblib`) nécessite de lire le fichier sur disque, de désérialiser les objets Python et d'allouer les structures mémoire scikit-learn. Cette opération prend entre 50 et 200 ms.  
En chargeant le modèle **une seule fois au démarrage** au sein du gestionnaire de cycle de vie `lifespan` de FastAPI :
- Le modèle reste conservé en mémoire RAM.
- Le temps de traitement d'une requête de prédiction descend à quelques millisecondes seulement.
- L'API supporte une charge concurrente bien plus élevée sans saturer les I/O du disque.

### 2. Qui écrit le contrôle « pluie <= 100 », et où est-il écrit ?
C'est le développeur de l'API qui l'écrit dans le schéma Pydantic `Livraison` dans le fichier `logiai/api/schemas.py`, via le paramètre de validation :  
`pluie_mm: float = Field(ge=0.0, le=100.0, allow_inf_nan=False, description="...")`.  
FastAPI et Pydantic interceptent et valident automatiquement ce contrôle avant même que la requête n'atteigne le corps de la fonction `predict()`.

### 3. Différence entre 422 et 503 ?
- **Code 422 (Unprocessable Entity) :** Erreur côté **client**. La requête est bien formée au sens HTTP/JSON, mais son contenu sémantique est invalide au regard des règles métiers (champ manquant, type incorrect, valeur hors bornes). Le client doit rectifier sa saisie.
- **Code 503 (Service Unavailable) :** Erreur côté **serveur**. La requête du client est parfaitement valide, mais le service backend n'est temporairement pas capable de délivrer le résultat demandé car une ressource essentielle (le modèle ML) n'est pas disponible.

### 4. Pourquoi une route `/v1/predict` plutôt que `/predict` ?
Le préfixe `/v1/` implémente le principe de **versioning d'API**. Il permet d'assurer la rétrocompatibilité des systèmes clients : si une nouvelle version `/v2/predict` est déployée (avec des variables supplémentaires ou un format différent), les clients existants peuvent continuer à consommer `/v1/predict` sans interruption de service ni régression.

### 5. Que se passerait-il si la distance était déclarée `int` ?
Si la distance était déclarée `int` :
- Une requête avec une distance décimale (par exemple `12.5 km`) serait rejetée avec une erreur 422 (`int_from_float`), empêchant la saisie de trajets réalistes.
- En cas de conversion forcée sans mode strict, la valeur serait tronquée à l'entier inférieur (`12 km`), induisant un biais de calcul dans le modèle de régression logistique qui a été calibré sur une variable continue.

---

## 7. Décision Architecturale : Modèle Absent

**Répondre 503 ou refuser de démarrer ? Qu'est-ce que chaque option fait perdre ?**

- **Option retenue : Répondre 503 (dégradation gracieuse)**  
  *Avantages :* L'application web démarre et reste joignable. Les endpoints de supervision comme `/health` restent fonctionnels et indiquent `"model_loaded": false`. La documentation interactive Swagger (`/docs`) reste consultable pour les développeurs.  
  *Ce que l'on perd :* L'erreur n'est pas bloquante au déploiement (pas de *fail-fast*) : un orchestrateur qui ne surveille que le port HTTP pensera que le pod est prêt, jusqu'à ce que les clients reçoivent des 503.
- **Option alternative : Refuser de démarrer (*fail-fast* / crash)**  
  *Avantages :* Détection immédiate du problème lors du déploiement (le conteneur redémarre ou l'orchestrateur refuse la bascule de trafic).  
  *Ce que l'on perd :* Toute l'API est indisponible (y compris `/health` et `/docs`), empêchant le diagnostic à distance via l'interface web.

---

## 8. Résultats des Tests Automatisés

Après implémentation des schémas, de la route de prédiction et ajout des cas de tests étendus (validation fine des heures entières, bornes de trafic, arrêts, cohérence seuil 0.4), la suite complète compte **19 tests**, tous validés avec succès :

```text
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\DELL\Downloads\starter-20261028T092813Z-1-001\starter
collected 19 items

tests/test_api.py::test_health_repond_ok PASSED                          [  5%]
tests/test_api.py::test_health_modele_charge PASSED                      [ 10%]
tests/test_api.py::test_predict_valide_renvoie_200 PASSED                [ 15%]
tests/test_api.py::test_predict_forme_de_la_reponse PASSED               [ 21%]
tests/test_api.py::test_predict_probabilite_entre_0_et_1 PASSED          [ 26%]
tests/test_api.py::test_predict_trajet_risque_plus_eleve_que_trajet_facile PASSED [ 31%]
tests/test_api.py::test_distance_negative_refusee PASSED                 [ 36%]
tests/test_api.py::test_pluie_impossible_refusee PASSED                  [ 42%]
tests/test_api.py::test_vehicule_inconnu_refuse PASSED                   [ 47%]
tests/test_api.py::test_champ_manquant_refuse PASSED                     [ 52%]
tests/test_api.py::test_champ_inconnu_refuse PASSED                      [ 57%]
tests/test_api.py::test_texte_a_la_place_d_un_nombre_refuse PASSED       [ 63%]
tests/test_api.py::test_modele_absent_renvoie_503 PASSED                 [ 68%]
tests/test_api.py::test_heure_depart_hors_limites_refusee PASSED         [ 73%]
tests/test_api.py::test_trafic_index_hors_limites_refuse PASSED          [ 78%]
tests/test_api.py::test_poids_invalide_refuse PASSED                     [ 84%]
tests/test_api.py::test_nb_arrets_invalide_refuse PASSED                 [ 89%]
tests/test_api.py::test_coherence_alerte_et_seuil_sur_requete_reelle PASSED [ 94%]
tests/test_api.py::test_seuil_alerte_cas_controles_autour_du_seuil PASSED [100%]

======================== 19 passed, 1 warning in 3.65s ========================
```

---

## 9. Métriques du Modèle de Machine Learning

Entraîné via le script `logiai.train` sur les 5 000 données de livraison :
- **Taux de retard global :** 27.4 %
- **Baseline accuracy :** 0.726 (72.6 %)
- **Accuracy du modèle :** 0.774 (77.4 %)
- **Rappel (Recall) :** 0.464 (46.4 %)
- **Précision :** 0.617 (61.7 %)
- **ROC AUC :** 0.769

---

## 10. Guide d'Exécution et Démonstration

### 10.1 Installation et Lancement sous Windows PowerShell
```powershell
# 1. Se positionner dans le dossier du projet
cd C:\Users\DELL\Downloads\starter-20261028T092813Z-1-001\starter

# 2. Création et activation de l'environnement virtuel
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Installation des dépendances
pip install -r requirements.txt

# 4. Préparation des données et entraînement du modèle
python -m logiai.dataset
python -m logiai.train

# 5. Lancement de l'API FastAPI
python -m uvicorn logiai.api.main:app --reload
```

### 10.2 Accès à la documentation interactive
- Swagger UI : [http://localhost:8000/docs](http://localhost:8000/docs)
- Schéma OpenAPI : [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

### 10.3 Lancement du Client Streamlit
Dans un second terminal PowerShell :
```powershell
cd C:\Users\DELL\Downloads\starter-20261028T092813Z-1-001\starter
.\.venv\Scripts\Activate.ps1
streamlit run app_streamlit.py
```
L'interface s'ouvre automatiquement sur [http://localhost:8501](http://localhost:8501).

---

## 11. Captures d'Écran Recommandées pour la Démonstration

Pour le rapport PDF final ou la soutenance, capturer :
1. **Terminal 1 :** Sortie de `python -m pytest -v` montrant les 19 tests réussis.
2. **Swagger UI (`/docs`) :** Page principale montrant les endpoints `GET /health` et `POST /v1/predict` avec le schéma `Livraison`.
3. **Swagger UI :** Exécution interactive d'une requête valide avec réponse 200 et probabilité calculée.
4. **Interface Streamlit :** Exemple avec livraison à risque élevé (alerte rouge déclenchée, probabilité > 40%).
5. **Interface Streamlit :** Exemple avec livraison fluide (indicateur vert sans alerte, probabilité < 40%).

---

## 12. Répartition du Travail en Binôme

| Membre | Tâches principales réalisées |
|---|---|
| **Malak Moukhliss** | - Configuration de l'environnement virtuel et entraînement du modèle ML.<br>- Conception et validation stricte des schémas Pydantic (`logiai/api/schemas.py`).<br>- Développement de la route de prédiction et gestion du code 503 (`logiai/api/main.py`). |
| **Binôme** | - Rédaction et automatisation des tests pytest (`tests/test_api.py`).<br>- Développement de l'interface utilisateur Streamlit (`app_streamlit.py`).<br>- Rédaction du compte-rendu technique et des justifications physiques. |

---

## 13. Dépôt Git & Pull Request

- **Branche de travail :** `tp-api`
- **Dépôt GitHub :** À renseigner lors de la publication sur le compte GitHub étudiant.
- **Lien de la Pull Request :** À renseigner lors de l'ouverture de la PR de `tp-api` vers `main`.
