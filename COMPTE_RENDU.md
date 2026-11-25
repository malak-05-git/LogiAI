# Compte Rendu : Tester, sécuriser et appeler l'API LogiAI (Atelier 4)

**Module :** Développement et déploiement d'applications intelligentes  
**Encadrante :** Pr. Soukaina Gouraguine  
**Année universitaire :** 2026 - 2027  
**Auteur :** Malak Moukhliss  
**Classe :** 5ème année Ingénierie IA & Big Data  
**Projet :** LogiAI — Atelier 4 : Tests automatisés (Pytest), validation Pydantic, clés API & rôles, CORS et client Web Fetch  

---

## 1. Introduction et Objectifs de l'Atelier 4

Dans la continuité de l'Atelier 3 où le modèle de Machine Learning a été exposé sous la forme d'un service web RESTful avec FastAPI, l'**Atelier 4** a pour mission d'industrialiser, fiabiliser et sécuriser l'API **LogiAI**.

Les objectifs pédagogiques et techniques sont organisés en quatre axes majeurs :
1. **Robustesse et validation stricte (Activités 1 & 2) :** Éprouver l'API avec des scénarios de requêtes malformées (`TestClient`), traquer les anomalies aux limites des données (`@pytest.mark.parametrize`) et corriger les bugs de spécification dans les schémas Pydantic v2.
2. **Contrôle d'accès et sécurité (Sprint 1) :** Mettre en œuvre une authentification par clé API via l'en-tête HTTP `X-API-Key`, établir une hiérarchie de privilèges (rôle standard `user` vs rôle privilégié `admin`), et neutraliser les attaques temporelles (*timing attacks*) via `secrets.compare_digest`.
3. **Cloisonnement des secrets et principe Twelve-Factor App :** Isoler les informations sensibles dans un fichier `.env` local, documenter le contrat de configuration avec `.env.example`, et garantir l'étanchéité du versionnement Git via `.gitignore`.
4. **Régulation CORS et client frontend (Sprint 2) :** Mettre en place `CORSMiddleware` pour restreindre les origines de navigateurs autorisées (`http://localhost:5500`), développer une interface web interactive en HTML5/JavaScript moderne (`fetch`), gérer ergonomiquement les retours d'erreurs (401, 403, 422, 503) et analyser les limites de la visibilité des secrets côté client.

---

## 2. Diagnostic initial : l'API ouverte à tous (Le problème de départ)

À l'issue de l'Atelier 3, l'API LogiAI répondait parfaitement aux requêtes nominales. Cependant, un audit de sécurité initial révèle une faille critique : **l'API est entièrement ouverte sans aucun contrôle d'identité ni de provenance**.

Une simple requête transmise via `curl` sans aucune clé ni en-tête d'authentification reçoit immédiatement une réponse favorable HTTP 200 :

```bash
curl.exe -i -X POST http://localhost:8000/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"distance_km": 120.0, "poids_kg": 450.0, "heure_depart": 17, "pluie_mm": 8.0, "trafic_index": 7.5, "nb_arrets": 4, "type_vehicule": "camion"}'
```

```http
HTTP/1.1 200 OK
content-type: application/json

{"probabilite_retard":0.732,"alerte":true,"seuil":0.4,"model_version":"1.0"}
```

De même, l'endpoint d'administration `GET /v1/model-info`, qui divulgue des informations internes sensibles sur le pipeline de Machine Learning (version sérialisée, seuil de classification, liste des features exploitées), était accessible publiquement sans restriction. N'importe quel client pouvait saturer les ressources du serveur ou aspirer des données internes. Ce constat justifie la mise en œuvre impérative d'un système d'authentification et d'autorisation.

---

## 3. Activité 1 : Casser son API (5 scénarios de requêtes invalides)

Pour tester la résilience du backend face à des saisies accidentelles ou malveillantes, nous avons conçu 5 scénarios d'invalidation automatisés avec `FastAPI TestClient` et `@pytest.mark.parametrize` dans `tests/test_casser.py`.

### Tableau des 5 scénarios de requêtes invalides :

| Cas testé | Requête (URL et charge utile) | Code HTTP prévu | Code HTTP obtenu | Justification technique |
|---|---|---|---|---|
| **1. Champ manquant** | `POST /v1/predict`<br>`{...VALID sans "poids_kg"}` | **422** | **422 Unprocessable Entity** | Pydantic détecte l'absence d'un champ obligatoire du modèle `Livraison`. |
| **2. Valeur absurde** | `POST /v1/predict`<br>`{...VALID, "poids_kg": 99999}` | **422** | **422 Unprocessable Entity** | La valeur viole la contrainte de borne supérieure `le=3500`. |
| **3. Texte au lieu d'un nombre** | `POST /v1/predict`<br>`{...VALID, "distance_km": "beaucoup"}` | **422** | **422 Unprocessable Entity** | Échec de conversion de type (`float` attendu). |
| **4. Champ en trop** | `POST /v1/predict`<br>`{...VALID, "remise": 10}` | **422** | **422 Unprocessable Entity** | Refusé grâce à `model_config = ConfigDict(extra="forbid")`. |
| **5. Mauvaise route** | `POST /v1/inconnue`<br>`{...VALID}` | **404** | **404 Not Found** | Le routeur FastAPI ne trouve aucune correspondance pour cette URL. |

### Code de test paramétré (`tests/test_casser.py`) :

```python
CAS_REFUSES = [
    ("valeur absurde", "/v1/predict", {**VALID, "poids_kg": 99999}, 422),
    ("champ manquant", "/v1/predict", SANS_POIDS, 422),
    (
        "texte au lieu d'un nombre",
        "/v1/predict",
        {**VALID, "distance_km": "beaucoup"},
        422,
    ),
    ("champ en trop", "/v1/predict", {**VALID, "remise": 10}, 422),
    ("mauvaise route", "/v1/inconnue", VALID, 404),
]


@pytest.mark.parametrize("description, url, corps, attendu", CAS_REFUSES)
def test_requete_refusee(client, headers_user, description, url, corps, attendu):
    assert client.post(url, json=corps, headers=headers_user).status_code == attendu, (
        description
    )
```

---

## 4. Activité 2 : Chasser les 2 bugs de bornes dans les schémas

Le starter contenait 2 bugs volontaires dans les définitions de contraintes Pydantic de `logiai/api/schemas.py`. L'écriture de 29 tests systématiques aux bornes (valeur juste à l'intérieur $\rightarrow$ 200, valeur juste à l'extérieur $\rightarrow$ 422) dans `tests/test_limites.py` a permis d'isoler ces anomalies :

### Tableau de découverte et correction des bugs :

| Bug identifié | Test qui l'a révélé | Comportement avant (Starter) | Correction apportée (`schemas.py`) |
|---|---|---|---|
| **Bug 1 : `heure_depart`** | `test_valeurs_limites[heure_depart-24-422]` | **Code 200 retourné** pour `heure_depart = 24`. La contrainte était `le=24`. Or, les heures d'une journée vont de 0 à 23. | `heure_depart: int = Field(ge=0, le=23, description="Heure de départ (0 à 23)")` |
| **Bug 2 : `nb_arrets`** | `test_valeurs_limites[nb_arrets--1-422]` | **Code 200 retourné** pour `nb_arrets = -1`. Aucune borne inférieure n'était définie (`le=15` seul). Un nombre d'arrêts négatif n'a aucun sens physique. | `nb_arrets: int = Field(ge=0, le=15, description="Nombre d'arrêts de livraison")` |

### Cas de l'heure décimale (`heure_depart = 11.5`) :
Un test dédié aux nombres à virgule a été intégré :
```python
(("heure_depart", 11.5, 422),)
```
*Comportement vérifié :* Pydantic v2 applique une validation de type stricte sur `int` et rejette `11.5` avec le code HTTP **422 Unprocessable Entity** (`Input should be a valid integer, got a number with a fractional part`).

---

## 5. Sprint 1 : Authentification par clé API et gestion des rôles

### A. Implémentation dans `logiai/api/security.py`

Le mécanisme d'authentification et de contrôle d'accès repose sur l'injection de dépendances (`FastAPI Depends`) et le module standard de cryptographie `secrets` :

```python
def _egal(a: str | None, b: str | None) -> bool:
    """Comparaison en temps constant. Une clé non configurée n'est jamais valide."""
    if not a or not b:
        return False
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Authentification : valide la clé d'API et retourne le rôle ('admin' ou 'user')."""
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Clé API absente. Veuillez fournir l'en-tête X-API-Key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if _egal(x_api_key, config.ADMIN_KEY):
        return "admin"
    if _egal(x_api_key, config.API_KEY):
        return "user"
    raise HTTPException(
        status_code=401,
        detail="Clé API invalide.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_admin(role: str = Depends(verify_api_key)) -> str:
    """Autorisation : restreint l'accès aux utilisateurs ayant le rôle administrateur."""
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux administrateurs.",
        )
    return role
```

### B. Protection des endpoints dans `logiai/api/main.py`

* `POST /v1/predict` : protégé par `dependencies=[Depends(verify_api_key)]` (accessible aux rôles `user` et `admin`).
* `GET /v1/model-info` : protégé par `dependencies=[Depends(require_admin)]` (accessible uniquement au rôle `admin`).
* `GET /health` : reste **public** pour permettre le probing des orchestrateurs (Kubernetes, AWS ALB, Docker Healthcheck).

### C. Ordre strict des contrôles de sécurité
L'architecture garantit l'ordre d'évaluation suivant :
$$\text{Route (404)} \longrightarrow \text{Authentification Clé (401/403)} \longrightarrow \text{Validation Schéma (422)} \longrightarrow \text{Modèle ML (200/503)}$$
*Preuve concrète :* Une requête soumise sans clé avec un payload invalide (ex: pluie de 500 mm) reçoit immédiatement un code **401 Unauthorized** et non 422, car l'identité est vérifiée avant le traitement de la charge utile.

---

## 6. Configuration des secrets et isolation Git (`.env` & `.gitignore`)

Conformément au standard *Twelve-Factor App (Config)* :
1. **Fichier modèle `.env.example` :** Versionné dans Git pour documenter les variables nécessaires sans divulguer de secrets :
   ```env
   LOGIAI_API_KEY=cle-utilisateur-123
   LOGIAI_ADMIN_KEY=cle-admin-456
   ```
2. **Fichier réel `.env` :** Présent localement, contenant les véritables clés distinctes :
   ```env
   LOGIAI_API_KEY=cle-utilisateur-logiai-2026
   LOGIAI_ADMIN_KEY=cle-admin-logiai-super-secret
   ```
3. **Protection Git (`.gitignore`) :** La règle `.env` inscrite dans `.gitignore` empêche tout archivage accidentel dans le dépôt.

### Preuve par `git status --ignored` :
```powershell
$ git status --ignored
On branch tp-securite
Ignored files:
  (use "git add -f <file>..." to include in what will be committed)
	.env
	.venv/
	.pytest_cache/
```
Le fichier `.env` apparaît strictement dans la section des fichiers ignorés.

---

## 7. Tests automatisés de sécurité (`tests/test_securite.py`)

Les 11 scénarios de sécurité sont validés avec succès :

| Scénario testé | Endpoint | En-tête X-API-Key | Code HTTP obtenu | Diagnostic |
|---|---|---|---|---|
| **1. Endpoint health public** | `/health` | *Aucun* | **200 OK** | Supervision opérationnelle sans secret |
| **2. Prédiction sans clé** | `/v1/predict` | *Aucun* | **401 Unauthorized** | Accès bloqué avec message explicite |
| **3. Prédiction fausse clé** | `/v1/predict` | `mauvaise-cle` | **401 Unauthorized** | Échec de comparaison à temps constant |
| **4. Prédiction clé vide** | `/v1/predict` | `""` | **401 Unauthorized** | Clé vide immédiatement rejetée |
| **5. Prédiction clé utilisateur** | `/v1/predict` | Clé user valide | **200 OK** | Inférence ML autorisée |
| **6. Prédiction clé admin** | `/v1/predict` | Clé admin valide | **200 OK** | Inférence ML autorisée pour l'admin |
| **7. Métadonnées sans clé** | `/v1/model-info` | *Aucun* | **401 Unauthorized** | Authentification préalable requise |
| **8. Métadonnées clé utilisateur** | `/v1/model-info` | Clé user valide | **403 Forbidden** | Rôle `user` insuffisant |
| **9. Métadonnées clé admin** | `/v1/model-info` | Clé admin valide | **200 OK** | Métadonnées délivrées |
| **10. Non-dévoilement du secret** | `/v1/predict` | `mauvaise-cle` | **401 Unauthorized** | Les clés configurées ne figurent pas dans la réponse 401 |
| **11. Variables non configurées** | `/v1/predict` | Clé quelconque | **401 Unauthorized** | Si `API_KEY=None`, tout accès protégé est refusé |

---

## 8. Sprint 2 : Configuration CORS et Interface Web

### A. Configuration CORS dans `logiai/api/main.py`
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,  # ["http://localhost:5500", "http://127.0.0.1:5500"]
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)
```
*Justification technique :* L'utilisation du joker `*` a été rejetée pour prévenir les attaques CSRF et interdire aux sites tiers d'appeler l'API en tâche de fond depuis le navigateur de l'utilisateur.

### B. Client Web Frontend (`web/index.html`)
L'interface web permet à un opérateur de renseigner les paramètres d'une course et sa clé d'API.

#### Fonction d'appel asynchrone (`fetch`) :
```javascript
async function appelerApi(livraison, cle) {
  const reponse = await fetch("http://localhost:8000/v1/predict", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": cle,
    },
    body: JSON.stringify(livraison),
  });
  const corps = await reponse.json();
  return { status: reponse.status, corps };
}
```

#### Améliorations ergonomiques intégrées :
1. **Désactivation du bouton et indicateur de chargement :** Le bouton d'évaluation passe à l'état désactivé (`bouton.disabled = true`) avec le message *« Calcul en cours… »* pendant la durée de la requête, puis est réactivé dans le bloc `finally`.
2. **Formatage clair des erreurs 422 :** Décomposition du tableau `corps.detail` pour afficher chaque champ erroné et la contrainte enfreinte (ex: `pluie_mm : Input should be less than or equal to 100`).
3. **Gestion des pannes et erreurs réseau :** Un bloc `catch` intercepte les interruptions de serveur ou les blocages CORS et affiche une consigne claire invitant à vérifier Uvicorn et la console F12.
4. **Restitution lisible du verdict ML :** Affichage en pourcentage avec coloration contextuelle (vert pour `ok`, orange/gras pour `alerte`).

### C. Expérience comparative CORS (Port 5500 vs Port 5501)
* **Test sur le port 5500 (Origine autorisée) :**  
  La requête prévol `OPTIONS` retourne `HTTP 200 OK` avec l'en-tête `Access-Control-Allow-Origin: http://localhost:5500`. La prédiction s'affiche correctement sur la page :  
  `Probabilité de retard : 73.2 %. Alerte : livraison à risque.`
* **Test sur le port 5501 (Origine non autorisée) :**  
  La requête prévol `OPTIONS` échoue avec `HTTP 400 Bad Request` sans en-tête d'autorisation. Le navigateur bloque immédiatement la réponse et la console F12 consigne l'erreur :  
  `Access to fetch at 'http://localhost:8000/v1/predict' from origin 'http://localhost:5501' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.`
* **Pourquoi `curl` fonctionne-t-il quand même ?**  
  CORS est une politique de sécurité implémentée et appliquée **exclusivement par le moteur d'un navigateur web** (*Same-Origin Policy*). Le serveur traite la requête quel que soit le client. Mais sans l'accord CORS, le navigateur refuse de transmettre la réponse au JavaScript de la page. `curl` n'étant pas un navigateur, il ignore la politique CORS et reçoit la réponse 200. **CORS n'est donc pas une authentification de l'API, d'où la nécessité de la clé API.**

### D. Visibilité de la clé dans F12 et risque d'exposition côté client
* Dans l'inspecteur web (F12) > Onglet **Réseau (Network)** > Requête `predict` > Sous-onglet **Headers**, la clé apparaît en clair : `X-API-Key: cle-utilisateur-logiai-2026`.
* **Conséquence sécuritaire majeure :** Tout secret stocké ou manipulé côté client dans un navigateur (dans le code JavaScript, dans le LocalStorage ou saisi dans un champ) est extractible par l'utilisateur ou par des scripts tiers (XSS). En production, un frontend public ne doit jamais détenir directement de clé d'API backend : on interpose une architecture **BFF (Backend-for-Frontend)** ou une authentification utilisateur par session sécurisée avec cookie `HttpOnly` et jetons éphémères.

---

## 9. Architecture Decision Record (ADR 003)

Le document formalisé dans `docs/adr/003-securite.md` consigne deux arbitrages structurants :

### Décision 1 : En-tête HTTP `X-API-Key` vs Clé dans l'URL vs Clé dans le corps JSON
* **Décision retenue :** En-tête HTTP dédié `X-API-Key`.
* **Rejet de la clé dans l'URL (`?api_key=...`) :** Les URL complètes sont enregistrées en clair dans les journaux d'accès des serveurs (access logs), des proxys inverses, des CDN et dans l'historique du navigateur. Elles peuvent également fuiter via l'en-tête `Referer`.
* **Rejet de la clé dans le corps JSON :** La spécification HTTP (RFC 7231) proscrit les corps de requêtes pour les méthodes `GET` (comme `GET /v1/model-info`). De plus, mélanger le secret d'authentification avec les attributs de la classe métier `Livraison` viole le principe de séparation des responsabilités.

### Décision 2 : Liste blanche stricte d'origines CORS vs Joker Wildcard `*`
* **Décision retenue :** Liste blanche restreinte `["http://localhost:5500", "http://127.0.0.1:5500"]`.
* **Rejet du wildcard `*` :** Autoriser `*` permettrait à n'importe quel site internet malveillant visité par un opérateur de déclencher des appels API frauduleux en arrière-plan depuis son navigateur.

---

## 10. Contrôle qualité du code (Ruff) et validation des tests (Pytest)

### A. Audit statique de code avec Ruff :

```powershell
$ ruff check .
All checks passed!

$ ruff format --check .
19 files already formatted
```
Le code source est conforme aux standards de formatage PEP 8, exempt d'imports inutilisés, de variables orphelines et d'anomalies syntaxiques.

### B. Bilan global de la suite de tests Pytest (53 tests réussis) :

```text
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\DELL\Downloads\starter-20261028T092813Z-1-001\starter
plugins: anyio-4.15.1
collected 53 items

tests\test_api.py ........                                               [ 15%]
tests\test_casser.py .....                                               [ 24%]
tests\test_limites.py .............................                      [ 79%]
tests\test_securite.py ...........                                       [100%]

======================= 53 passed, 1 warning in 21.74s ========================
```

---

## 11. Réponses approfondies aux 5 questions de compréhension

### 1. Quelle différence entre 401, 403 et 422 ?
* **HTTP 401 Unauthorized :** Erreur d'**authentification** (*« Qui êtes-vous ? »*). L'en-tête `X-API-Key` est absent, vide ou contient une clé non reconnue par le serveur.
* **HTTP 403 Forbidden :** Erreur d'**autorisation** (*« Avez-vous les droits ? »*). L'identité de l'appelant est validée avec succès, mais le rôle attribué ne possède pas les privilèges requis pour accéder à la ressource demandée (ex: clé avec rôle `user` interrogeant `GET /v1/model-info` réservé au rôle `admin`).
* **HTTP 422 Unprocessable Entity :** Erreur de **validation des données** (*« Les données violent le contrat »*). Le client est correctement authentifié et autorisé, mais le contenu de la requête viole les contraintes définies dans le modèle Pydantic (borne numérique dépassée, champ requis absent, type incompatible).

### 2. Pourquoi la clé n'est-elle ni dans le code ni dans Git ?
Le code source est partagé au sein des équipes, inspecté par des outils tiers et synchronisé sur des forges logicielles distantes. Si une clé est inscrite dans le code, elle intègre de manière définitive l'historique de Git (le graphe des commits). Même si le fichier est supprimé lors d'un commit ultérieur, le secret demeure extractible par un simple `git log -p`. De plus, des robots automatisés scannent en continu les dépôts GitHub publics pour dérober des identifiants exposés. Isoler les clés dans des variables d'environnement (`.env` local exclu par `.gitignore`) respecte le standard *Twelve-Factor App* et sépare strictement la logique logicielle de la configuration de déploiement.

### 3. Pourquoi comparer avec `compare_digest` plutôt qu'avec `==` ?
L'opérateur standard d'égalité `==` effectue une comparaison séquentielle avec court-circuit : il s'interrompt dès le premier caractère divergent. Par conséquent, plus le préfixe de la clé soumise est exact, plus la comparaison prend de temps à s'exécuter. Un attaquant peut mesurer ces variations infinitésimales de durée (quelques nanosecondes) pour reconstituer la clé secrète caractère après caractère (*timing attack* ou attaque par canal auxiliaire). La fonction `secrets.compare_digest()` garantit une comparaison en temps constant, quel que soit le contenu des chaînes, neutralisant définitivement ce vecteur d'attaque.

### 4. Pourquoi `curl` fonctionne-t-il alors que la page du port 5501 est bloquée ?
CORS n'est pas un pare-feu réseau au niveau du serveur, mais une politique de sécurité appliquée **uniquement par le moteur du navigateur web** (*Same-Origin Policy*). Le serveur FastAPI traite la requête et renvoie les données pour les deux clients. Cependant, en l'absence de l'en-tête `Access-Control-Allow-Origin: http://localhost:5501` dans la réponse, le navigateur de la page bloque l'accès aux données par le script JavaScript. `curl` étant un client autonome en ligne de commande, il n'intègre aucun moteur de navigateur et ignore les restrictions CORS.

### 5. Pourquoi la validation faite par le navigateur ne remplace-t-elle pas celle de l'API ?
La validation côté client (attributs HTML5 `required`, `min`, `max`, scripts JS) n'offre qu'un confort ergonomique pour l'utilisateur en évitant des allers-retours réseau inutiles. Elle n'offre **aucune garantie de sécurité**, car elle est facilement contournable en modifiant le code source dans l'inspecteur du navigateur, en désactivant JavaScript ou en soumettant directement des requêtes forgées via `curl`, `Postman` ou un script Python. Le backend de l'API REST est l'unique garant de l'intégrité des données avant leur injection dans le modèle de Machine Learning.

---

## 12. Procédure Git, Pull Request et Tags de rendu

* **Branche de travail :** `tp-securite`
* **Dépôt GitHub :** `https://github.com/malak-05-git/logiai`
* **Message de commit standardisé :** `TP sécurité : tests, clé API, page web`
* **Note sur le tag de rendu :** Le sujet mentionne `tp2` à certains endroits dans les exemples de lignes de commande et `tp4` dans l'énoncé principal et les critères d'évaluation. Il est recommandé de poser le tag `tp4` (Atelier 4) ainsi que `tp2` si nécessaire pour garantir la compatibilité avec toutes les grilles de notation :
  ```bash
  git tag tp4
  git push origin tp4
  ```
* **Lien de la Pull Request Atelier 4 :** PR #1 (`tp-api`) fusionnée dans `main`, et PR de `tp-securite` vers `main`.

---

# PARTIE II : RÉALISATION DE L'ATELIER 5 — CONTENEURISATION & DÉPLOIEMENT (DOCKER, NGINX, COMPOSE)

## 13. Présentation et Objectifs de l'Atelier 5

L'Atelier 5 concrétise le déploiement industriel de **LogiAI** par sa conteneurisation complète. L'objectif est d'éliminer le biais d'environnement (*« ça marche sur ma machine »*) en isolant le moteur de prédiction et l'interface utilisateur dans des conteneurs Linux standardisés, gérés par un reverse proxy et orchestrés par Docker Compose.

### Objectifs techniques majeurs :
1. **Conteneurisation de l'API FastAPI :** Création d'une image Docker optimisée basée sur `python:3.11-slim`, configuration de `LOGIAI_HOME`, isolation via `.dockerignore`.
2. **Réalisation des trois expériences fondamentales :** Analyse empirique de l'injection des variables d'environnement (`--env-file`), de la publication des ports (`-p`) et de l'écoute réseau (`0.0.0.0` vs `127.0.0.1`).
3. **Mise en place d'un Reverse Proxy Nginx :** Centralisation du trafic sur le port `8080`, routage transparent des requêtes `/api/` vers `api:8000`, et résolution native de la politique CORS par unification d'origine (*Same-Origin*).
4. **Orchestration avec Docker Compose :** Définition d'un réseau interne partagé, synchronisation du cycle de vie via `healthcheck` (`depends_on: condition: service_healthy`), et persistance/modularité des modèles ML via volume bind-mount.
5. **Résilience et observabilité :** Simulation de panne backend (`docker compose stop api` $\rightarrow$ 502 Bad Gateway), reprise de service à chaud et mesure des métriques réelles avec `docker stats`.

---

## 14. Audit initial de l'Atelier 5 (Tableau de conformité)

| Exigence | État initial | Problème identifié | Action corrective réalisée |
|---|---|---|---|
| **Moteur Docker & WSL2** | Présent (arrêté) | Le daemon `docker-desktop` était stoppé | Démarrage du service backend Docker Desktop et validation de `docker ps` |
| **Configuration `LOGIAI_HOME`** | Incomplet | `config.py` utilisait un chemin relatif fixe sans vérifier la variable d'environnement | Mise à jour de `config.py` : `ROOT = Path(os.getenv("LOGIAI_HOME", ...))` |
| **Dockerfile API** | Absent | Aucun fichier de construction pour l'API | Création du `Dockerfile` multi-stage basé sur `python:3.11-slim` écoutant sur `0.0.0.0:8000` |
| **Fichier `.dockerignore`** | Absent | Risque de copier `.venv/`, `.env`, `.git` et les caches dans l'image | Création de `.dockerignore` excluant les artefacts locaux tout en conservant `data/` et `models/` |
| **Dockerfile Web** | Absent | Pas de conteneur pour le frontend statique | Création de `web/Dockerfile` basé sur `nginx:alpine` |
| **Configuration Nginx** | Absent | Pas de configuration de reverse proxy | Création de `nginx/default.conf` avec proxy_pass `http://api:8000/` |
| **Client Frontend Web** | Partiel | `web/index.html` pointait en dur vers `http://localhost:8000/v1/predict` | Mise à jour de l'URL en chemin relatif unifié : `const API_URL = '/api/v1/predict';` |
| **Docker Compose** | Absent | Pas d'orchestration unifiée | Création de `docker-compose.yml` avec services `api` et `web`, volumes, env_file et healthcheck |
| **Healthcheck** | Absent | Nginx pouvait démarrer avant que l'API ne soit prête | Healthcheck Python standardisé testant `GET /health` toutes les 30s |
| **Volumes persistants** | Absent | Les modifications du modèle imposaient un rebuild | Bind-mount de `./models:/app/models` et `./data:/app/data` |
| **ADR 004** | Absent | Choix d'architecture non formalisés | Rédaction complète de `docs/adr/004-docker.md` |
| **Tests de non-régression** | Opérationnel | Nécessité de vérifier la compatibilité continue | Exécution de `pytest` validant 53 tests sur 53 (100% de succès) |

---

## 15. Conteneurisation de l'API & Les Trois Expériences Obligatoires

### A. Construction et validation de l'image `logiai:1.0`
L'image backend a été construite avec succès :
```powershell
$ docker build -t logiai:1.0 .
# ...
naming to docker.io/library/logiai:1.0 done
unpacking to docker.io/library/logiai:1.0 8.1s done
```
*Taille de l'image :* **766 MB** (taille compressée du contenu : 174 MB).

### B. Résultats détaillés des trois expériences de conteneurisation

| Expérience | Commande exécutée | Résultat prévu | Résultat réellement obtenu | Code HTTP / Erreur | Explication technique |
|---|---|---|---|---|---|
| **1. Démarrage sans `--env-file`** | `docker run -d --name exp1-no-env -p 8001:8000 logiai:1.0` | L'API démarre mais l'authentification est désactivée/refusée | `GET /health` renvoie `auth_configured: false`. Tout appel à `/v1/predict` échoue | **HTTP 401 Unauthorized** (`{"detail": "Clé API invalide."}`) | Les variables `LOGIAI_API_KEY` et `LOGIAI_ADMIN_KEY` ne sont pas injectées dans le conteneur. Par conséquent, `config.API_KEY` vaut `None` et la fonction `_egal(cle, None)` retourne `False`. |
| **2. Démarrage sans publication de port (`-p`)** | `docker run -d --name exp2-no-port --env-file .env logiai:1.0` | Le conteneur tourne mais est inaccessible depuis l'hôte | La commande `curl` vers `localhost:8000` et `localhost:8001` échoue immédiatement | **curl: (7) Failed to connect** (`Could not connect to server`) | Le conteneur s'exécute dans un espace de noms réseau (*network namespace*) isolé. Sans l'argument `-p`, Docker ne configure aucune règle NAT sur l'hôte pour acheminer les paquets TCP vers l'IP du conteneur. |
| **3. Remplacement de `0.0.0.0` par `127.0.0.1`** | `docker run -d --name exp3-localhost -p 8001:8000 --env-file .env logiai:1.0 uvicorn ... --host 127.0.0.1` | Le conteneur n'écoute que sur son interface de loopback interne | Le client reçoit une fermeture brutale de connexion | **curl: (52) Empty reply from server** | Uvicorn se lie exclusivement à l'interface `lo` (`127.0.0.1`) interne au conteneur. Le proxy Docker (`docker-proxy`) redirigeant le flux vers l'interface `eth0` du conteneur, aucun processus n'y répond. L'écoute sur `0.0.0.0` est impérative. |

---

## 16. Architecture Reverse Proxy Nginx & Élimination native de CORS

### A. Configuration `nginx/default.conf`
```nginx
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://api:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### B. Analyse critique du slash final (`proxy_pass http://api:8000/;`)
Le slash final après le numéro de port modifie fondamentalement la réécriture d'URI par Nginx :
* Une requête client reçue sur `http://localhost:8080/api/v1/predict` a pour préfixe de directive `/api/`.
* Grâce au slash final dans `proxy_pass http://api:8000/;`, Nginx **tronque** le préfixe `/api/` et le remplace par `/`.
* Le backend FastAPI reçoit donc la requête nettoyée : `GET /v1/predict` (ou `GET /health` pour `/api/health`).

### C. Élimination native des problématiques CORS
Dans l'Atelier 4, le frontend (port 5500) et l'API (port 8000) constituaient deux origines distinctes, imposant une négociation prévol `OPTIONS` et l'en-tête `Access-Control-Allow-Origin`.  
Avec l'architecture Nginx :
* L'utilisateur charge la page web sur `http://localhost:8080/`.
* Le script JS appelle l'API via l'URL relative `/api/v1/predict` $\rightarrow$ l'origine est strictement `http://localhost:8080`.
* **Conséquence :** La requête est considérée comme **Same-Origin** par le navigateur. Aucun mécanisme CORS n'est déclenché, aucune requête prévol `OPTIONS` n'est requise, éliminant totalement les risques de blocage par le navigateur.

---

## 17. Orchestration avec Docker Compose

Le fichier [`docker-compose.yml`](file:///C:/Users/DELL/Downloads/starter-20261028T092813Z-1-001/starter/docker-compose.yml) orchestre les deux microservices :

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: logiai-api
    ports:
      - "8001:8000"
    env_file:
      - .env
    environment:
      LOGIAI_HOME: /app
    volumes:
      - ./models:/app/models
      - ./data:/app/data
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  web:
    build:
      context: .
      dockerfile: web/Dockerfile
    container_name: logiai-web
    ports:
      - "8080:80"
    depends_on:
      api:
        condition: service_healthy
```

### Mécanisme de Healthcheck et dépendance conditionnelle :
Au démarrage (`docker compose up -d`), Docker Compose lance `logiai-api` et active la sonde de santé toutes les 30 secondes (avec période d'échauffement de 10s). Le service `logiai-web` est maintenu en attente jusqu'à ce que `logiai-api` passe à l'état **Healthy** (`Container logiai-api Healthy` $\rightarrow$ `Container logiai-web Starting`). Cela empêche Nginx de recevoir du trafic utilisateur alors que le modèle Machine Learning n'est pas encore chargé en mémoire.

---

## 18. Résultats réels des Tests de Bout en Bout

### A. État opérationnel des conteneurs (`docker compose ps`)
```powershell
$ docker compose ps
NAME         IMAGE         COMMAND                  SERVICE   CREATED         STATUS                   PORTS
logiai-api   starter-api   "uvicorn logiai.api.…"   api       2 minutes ago   Up 2 minutes (healthy)   0.0.0.0:8001->8000/tcp, [::]:8001->8000/tcp
logiai-web   starter-web   "/docker-entrypoint.…"   web       2 minutes ago   Up 2 minutes             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
```

### B. Validation des 4 scénarios via le Reverse Proxy Nginx (`http://localhost:8080/api/...`)

| Scénario testé | Méthode & URL Nginx | En-tête X-API-Key | Code HTTP obtenu | Corps de réponse réel |
|---|---|---|---|---|
| **1. Endpoint Health** | `GET /api/health` | *Aucun* | **200 OK** | `{"status":"ok","model_loaded":true,"auth_configured":true}` |
| **2. Prédiction sans clé** | `POST /api/v1/predict` | *Aucun* | **401 Unauthorized** | `{"detail":"Clé API absente. Veuillez fournir l'en-tête X-API-Key."}` |
| **3. Prédiction mauvaise clé** | `POST /api/v1/predict` | `cle-invalide` | **401 Unauthorized** | `{"detail":"Clé API invalide."}` |
| **4. Prédiction clé valide** | `POST /api/v1/predict` | `cle-utilisateur-logiai-2026` | **200 OK** | `{"probabilite_retard":0.732,"alerte":true,"seuil":0.4,"model_version":"1.0"}` |

### C. Test de panne et résilience backend
1. **Arrêt du conteneur API :**
   ```powershell
   $ docker compose stop api
   Container logiai-api Stopped
   ```
2. **Requête client transmise à travers Nginx :**
   * *Code HTTP obtenu :* **502 Bad Gateway**
   * *En-tête serveur :* `Server: nginx/1.31.8`
   * *Comportement frontend :* Le client intercepte le code d'erreur HTTP 502 et affiche le message explicite d'indisponibilité.
3. **Redémarrage et reprise automatique :**
   ```powershell
   $ docker compose start api
   Container logiai-api Started
   ```
   Après validation de la sonde de santé (`Up (healthy)`), une nouvelle prédiction soumise depuis l'interface web retourne immédiatement le statut **200 OK** avec un verdict nominal (`probabilite_retard: 0.732`).

### D. Vérification de la persistance des volumes
```powershell
$ docker compose exec api ls /app/models
model.joblib
model_info.json

$ docker compose exec api ls /app/data
livraisons.csv
```
Les fichiers du modèle et du jeu de données sont parfaitement synchronisés entre le système de fichiers hôte et les conteneurs.

---

## 19. Métriques réelles de consommation des ressources (`docker stats`)

Relevé instantané mesuré sur les conteneurs en production locale :

```text
CONTAINER ID   NAME         CPU %     MEM USAGE / LIMIT     MEM %     NET I/O           BLOCK I/O     PIDS
3900613d1319   logiai-web   0.00%     7.828MiB / 7.664GiB   0.10%     9.54kB / 16.6kB   0B / 8.19kB   9
d9ff5d73825a   logiai-api   10.35%    124.1MiB / 7.664GiB   1.58%     1.86kB / 763B     0B / 0B       20
```

### Analyse des métriques :
* **Service Nginx (`logiai-web`) :** Consommation mémoire extrêmement réduite (**~7.8 MB**), charge CPU nulle au repos (**0.00%**), démontrant la très haute efficacité de l'image Alpine Linux pour servir les fichiers statiques et agir en reverse proxy.
* **Service FastAPI (`logiai-api`) :** Empreinte mémoire modérée (**~124 MB**) correspondant au runtime Python 3.11, au framework FastAPI, à Scikit-Learn et à l'artefact `model.joblib` chargé en mémoire vive.

---

## 20. Réponses approfondies aux 5 questions de compréhension (Atelier 5)

### 1. Pourquoi utilise-t-on `0.0.0.0` au lieu de `127.0.0.1` pour écouter dans un conteneur Docker ?
`127.0.0.1` représente l'adresse de bouclage locale (*loopback interface*) propre au réseau interne du conteneur. Si Uvicorn écoute sur `127.0.0.1`, seules les requêtes générées *à l'intérieur* de ce même conteneur sont acceptées. La passerelle réseau de Docker (`docker-proxy`), qui transfère les paquets provenant de la machine hôte vers l'interface réseau virtuelle du conteneur (`eth0`), verrait ses connexions immédiatement réinitialisées (`Empty reply from server`). En spécifiant `0.0.0.0`, on ordonne au serveur de lier sa socket à **toutes les interfaces réseau disponibles** du conteneur, permettant ainsi la réception du trafic routé depuis l'hôte ou d'autres conteneurs.

### 2. Quelle est la différence entre `EXPOSE` dans un Dockerfile et `ports:` dans `docker-compose.yml` ?
* **`EXPOSE 8000` (dans le Dockerfile) :** Est une simple instruction documentaire de métadonnées. Elle informe les développeurs et l'orchestrateur que le processus écoute sur ce port, mais **ne publie aucun port sur la machine hôte**. Les autres conteneurs du même réseau Docker peuvent communiquer avec ce port, mais la machine hôte ne peut pas l'atteindre directement.
* **`ports: - "8001:8000"` (dans Compose ou `-p` dans `docker run`) :** Configure une règle de redirection de port (*port forwarding*) et met en place des règles NAT au niveau du système hôte. Tout paquet arrivant sur le port 8001 de l'hôte est activement redirigé vers le port 8000 du conteneur.

### 3. Pourquoi le volume bind-mount est-il particulièrement pertinent pour le fichier de modèle de Machine Learning ?
Dans le cycle de vie MLOps, les données et les modèles évoluent à une fréquence beaucoup plus élevée que le code applicatif. Si le modèle est figé dans l'image avec `COPY`, tout réentraînement exige de reconstruire l'image entière (`docker build`), de redistribuer plusieurs centaines de mégaoctets et de redéployer le conteneur. Grâce au bind-mount (`./models:/app/models`), le fichier sérialisé `model.joblib` réside sur l'hôte : une simple mise à jour du fichier par le script d'entraînement est immédiatement visible par l'API sans aucune reconstruction d'image.

### 4. Pourquoi l'utilisation de Nginx en reverse proxy résout-elle nativement les problématiques de CORS pour le frontend ?
Le mécanisme CORS (*Cross-Origin Resource Sharing*) est une politique de sécurité imposée par le navigateur lorsque le JavaScript d'une page hébergée sur une origine A (ex: `http://localhost:5500`) tente d'interroger une origine B (ex: `http://localhost:8000`). En interposant Nginx sur le port `8080`, Nginx sert simultanément les fichiers HTML/JS (`/`) et relaie les requêtes API (`/api/`). Du point de vue du navigateur web, le frontend et l'API partagent exactement le même protocole, le même nom de domaine et le même port (`http://localhost:8080`). La communication devenant **Same-Origin**, le navigateur n'applique aucune restriction CORS et ne transmet aucune requête prévol `OPTIONS`.

### 5. Que se passe-t-il lors de l'arrêt du service API (`docker compose stop api`) et quel est le rôle du healthcheck dans la gestion des dépendances ?
* **Comportement en cas d'arrêt :** Le conteneur Nginx reste actif et continue de servir la page web. Toutefois, lorsqu'un utilisateur soumet une prédiction, Nginx tente d'acheminer la requête vers `http://api:8000/`. Ne recevant aucune réponse TCP du conteneur éteint, Nginx génère immédiatement une erreur standard **HTTP 502 Bad Gateway**.
* **Rôle du Healthcheck (`depends_on: condition: service_healthy`) :** Une simple directive `depends_on: [api]` ne vérifie que le démarrage du conteneur `api`, sans savoir si l'application Python est prête à recevoir des requêtes. En définissant une sonde de santé (`healthcheck`) sur `GET /health` et en liant Nginx à `condition: service_healthy`, Docker Compose retarde le démarrage de Nginx jusqu'à ce que l'API réponde avec succès (statut 200 et modèle chargé), évitant ainsi que les premiers utilisateurs ne reçoivent des erreurs 502 au démarrage du cluster.

---

## 21. Procédure Git, Pull Request et Tag de livraison Atelier 5

* **Branche de travail :** `tp-docker`
* **Dépôt GitHub :** `https://github.com/malak-05-git/logiai`
* **Message de commit standardisé :** `Atelier 5 : Docker, Nginx et Compose`
* **Tag officiel de l'Atelier 5 :** `tp5` (à poser après fusion de la Pull Request sur `main`).
* **Lien de la Pull Request Atelier 5 :** À renseigner lors de l'ouverture de la PR de `tp-docker` vers `main` sur GitHub.

