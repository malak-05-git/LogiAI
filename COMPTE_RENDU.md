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
* **Lien de la Pull Request :** À renseigner lors de l'ouverture de la PR de `tp-securite` vers `main` sur GitHub.
