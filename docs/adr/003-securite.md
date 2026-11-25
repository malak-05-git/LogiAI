# ADR 003 : Sécurité de l'API LogiAI — Authentification et politique CORS

* **Statut :** Accepté
* **Date :** Novembre 2026
* **Auteur :** Équipe d'ingénierie LogiAI

---

## Contexte général

L'API LogiAI expose des modèles de Machine Learning prédisant les retards de livraison et des métadonnées internes du modèle (`/v1/model-info`). Jusqu'à l'Atelier 3, l'API était entièrement ouverte, sans aucun contrôle d'identité, de rôle ou de provenance des requêtes.

Pour répondre aux exigences de mise en production, l'API doit être protégée contre les accès non autorisés, cloisonner les privilèges administrateur / utilisateur, et réguler les requêtes provenant de navigateurs web tiers.

---

## Décision 1 : Transmission de la clé API via l'en-tête HTTP `X-API-Key`

### Contexte & Problématique
Une clé d'API secrète doit être transmise par le client à chaque requête protégée. Trois vecteurs de transport sont techniquement envisageables :
1. Dans l'URL sous forme de paramètre de requête (Query Parameter, ex: `?api_key=...`)
2. Dans le corps de la requête JSON (Request Body, ex: `{"api_key": "...", ...}`)
3. Dans un en-tête HTTP dédié (`X-API-Key`)

### Décision retenue
Nous adoptons l'utilisation exclusive d'un en-tête HTTP personnalisé : **`X-API-Key`**.

### Alternatives considérées & Analyse comparative

* **Clé dans l'URL (`?api_key=...`) — REJETÉE :**
  - **Risques majeurs de fuite :** Les URL complètes sont systématiquement enregistrées en clair dans les journaux d'accès des serveurs web (access logs), des proxys inverses (Nginx, Traefik), des passerelles API, des CDN, ainsi que dans l'historique du navigateur de l'utilisateur et le cache du navigateur.
  - **Fuite via le header Referer :** Si la page fait un lien externe, l'URL complète avec le secret peut être transmise au tiers via l'en-tête `Referer`.
  - **Perte :** Perte totale de confidentialité du secret dès qu'un journal est audité ou exporté.

* **Clé dans le corps JSON (`body`) — REJETÉE :**
  - **Incompatibilité HTTP sémantique :** Les requêtes `GET` (comme `GET /v1/model-info`) ne comportent pas de corps selon la spécification HTTP standard (RFC 7231). Transmettre la clé dans le corps empêcherait la protection des routes en lecture `GET`.
  - **Mélange des responsabilités (Separation of Concerns) :** La couche d'authentification (méta-information de transport) polluerait le schéma métier des données applicatives (`Livraison`), compliquant la validation Pydantic et le contrat d'interface.
  - **Perte :** Impossibilité de sécuriser les endpoints `GET` de manière standardisée et complexification inutile des schémas de données.

* **En-tête HTTP `X-API-Key` — RETENUE :**
  - **Sécurité :** Les en-têtes HTTP ne sont pas journalisés par défaut par les serveurs web et les proxys, évitant ainsi la persistance involontaire des secrets dans les logs.
  - **Universalité :** Fonctionne de manière homogène sur tous les verbes HTTP (`GET`, `POST`, `PUT`, `DELETE`).
  - **Découplage :** Sépare strictement les métadonnées de sécurité de la charge utile (payload) métier.

### Conséquences
* Les clients (curl, fetch JS, bibliothèques Python) doivent explicitement définir l'en-tête `X-API-Key`.
* En environnement de test et de production, la comparaison des clés doit impérativement utiliser `secrets.compare_digest` (`_egal()`) pour neutraliser les attaques temporelles (timing attacks).
* Les secrets proviennent exclusivement de variables d'environnement (`.env`), jamais du code source ni de Git.

---

## Décision 2 : Configuration CORS — Liste blanche stricte d'origines autorisées

### Contexte & Problématique
Le mécanisme CORS (*Cross-Origin Resource Sharing*) est une politique de sécurité appliquée par les navigateurs web pour restreindre les requêtes HTTP asynchrones (`fetch`, `XMLHttpRequest`) entre origines différentes (protocole, domaine, port). Notre frontend web est servi sur un port dédié (`http://localhost:5500`), distinct du backend (`http://localhost:8000`).

Deux stratégies étaient envisageables :
1. Autoriser toutes les origines avec le joker wildcard `allow_origins=["*"]`
2. Définir une liste blanche explicite d'origines autorisées (`config.ALLOWED_ORIGINS = ["http://localhost:5500", "http://127.0.0.1:5500"]`)

### Décision retenue
Nous configurons `CORSMiddleware` avec une **liste blanche explicite et restreinte** :
`["http://localhost:5500", "http://127.0.0.1:5500"]`.

### Alternatives considérées & Analyse comparative

* **Autoriser toutes les origines avec `*` — REJETÉE :**
  - **Risque d'usurpation et de CSRF :** N'importe quel site tiers malveillant (ex: `http://site-piege.com`) visité par un utilisateur légitime pourrait exécuter des requêtes vers notre API LogiAI en arrière-plan depuis son navigateur.
  - **Perte :** Perte du contrôle sur les applications frontales habilitées à consommer l'API depuis un navigateur.

* **Liste blanche stricte — RETENUE :**
  - **Isolation :** Seules les pages hébergées sur `http://localhost:5500` (et `127.0.0.1:5500`) reçoivent les en-têtes `Access-Control-Allow-Origin` autorisant la lecture de la réponse par le navigateur.
  - **Filtrage des méthodes et en-têtes :** Seules les méthodes nécessaires (`GET`, `POST`, `OPTIONS`) et les en-têtes `Content-Type` et `X-API-Key` sont autorisés dans les requêtes prévol (*preflight OPTIONS*).

### Conséquences & Clarification fondamentale
* **Rôle de CORS :** CORS est une barrière de sécurité appliquée **exclusivement par le navigateur** pour protéger l'utilisateur.
* **Non-substitut à l'authentification :** CORS n'est **en aucun cas** un mécanisme d'authentification de l'API. Un client non-navigateur (comme `curl`, un script Python ou un attaquant direct) n'applique pas les règles CORS et peut interroger l'API directement ; c'est pourquoi la clé API `X-API-Key` demeure la protection essentielle et indispensable côté serveur.
