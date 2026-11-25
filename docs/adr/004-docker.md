# ADR 004 : Conteneurisation et déploiement de LogiAI avec Docker, Nginx et Docker Compose

* **Statut :** Accepté
* **Date :** Novembre 2026
* **Auteur :** Équipe DevOps LogiAI
* **Contexte :** Atelier 5 — Déploiement multi-conteneurs, reverse proxy et persistance

---

## Contexte général

À l'issue de l'Atelier 4, le projet LogiAI disposait d'une API FastAPI sécurisée par clé d'API (`X-API-Key`), d'une politique CORS stricte et d'un client web consommant les prédictions. Toutefois, l'application dépendait de l'environnement d'exécution local de la machine hôte (interpréteur Python spécifique, gestionnaire de paquets local, serveurs distincts lancés manuellement sur différents ports).

Pour garantir la reproductibilité, l'isolation, l'évolutivité et simplifier le déploiement en production, LogiAI est conteneurisé sous la forme d'une architecture multi-services orchestrée par **Docker Compose** comprenant :
1. Un service backend FastAPI (`api`) encapsulé dans une image Python Debian-slim optimisée.
2. Un service reverse proxy frontend Nginx (`web`) servant l'interface utilisateur statique et redirigeant les requêtes API sous un même nom de domaine/port.

Deux décisions architecturales structurantes ont été arbitrées dans ce cadre.

---

## Décision 1 : Gestion et stockage du modèle Machine Learning (`COPY` vs `Volume Bind-Mount`)

### Contexte & Problématique
Le pipeline d'inférence LogiAI nécessite l'artefact sérialisé du modèle (`models/model.joblib`) ainsi que ses métadonnées (`models/model_info.json`). Deux approches de packaging étaient envisageables pour fournir ces artefacts au conteneur `api` :
1. **Intégration statique dans l'image (`COPY models/ ./models/`) :** L'artefact est figé au moment du build dans les couches de l'image Docker.
2. **Montage dynamique par volume hôte (`volumes: - ./models:/app/models`) :** Le répertoire de l'hôte est projeté dynamiquement dans le système de fichiers du conteneur au démarrage.

### Décision retenue
Nous adoptons une **stratégie hybride à dominante Volume Bind-Mount** en environnement de développement et d'intégration :
* Le `Dockerfile` inclut un `COPY models/ ./models/` assurant l'autonomie minimale de l'image (self-contained fallback).
* Le fichier `docker-compose.yml` monte explicitement le volume hôte `./models:/app/models` (ainsi que `./data:/app/data`).

### Alternatives considérées & Analyse comparative

* **Approche 100% statique (`COPY` exclusif sans volume) — REJETÉE pour le cycle d'itération :**
  - **Inconvénients majeurs :** Chaque réentraînement du modèle (par exemple suite à l'arrivée de nouvelles données de livraisons ou au réajustement d'hyperparamètres) imposerait une reconstruction intégrale de l'image Docker (`docker build`), consommant du temps CPU et de la bande passante registre.
  - **Violation de la séparation des préoccupations :** Le cycle de vie d'un modèle de Machine Learning (fréquemment réentraîné) est distinct de celui du code applicatif (versionné et validé par tests unitaires).
  - **Perte :** Perte d'agilité pour l'équipe Data Science / MLOps lors de l'actualisation des poids du modèle.

* **Approche Volume Bind-Mount (`./models:/app/models`) — RETENUE :**
  - **Mise à jour à chaud sans rebuild :** L'exécution de `python -m logiai.train` sur l'hôte ou via un pipeline externe actualise immédiatement `models/model.joblib`. Le conteneur charge la nouvelle version dès son prochain démarrage ou rechargement sans reconstruire l'image.
  - **Économie de ressources :** Les artefacts binaires volumineux ne surchargent pas les couches intermédiaires des images Docker.
  - **Séparation stricte Code / Artefacts ML :** Le conteneur ne transporte que le moteur logiciel ; les données et modèles restent des ressources externes injectées.

### Conséquences
* En développement et recette, le volume garantit un cycle d'itération court.
* En production Kubernetes / Cloud managé, ce volume sera remplacé par un stockage persistant managé (S3 / GCS / Azure Blob avec téléchargement au démarrage via init-container, ou volume persistant PVC / CSI).

---

## Décision 2 : Politique d'exposition des ports réseau (`8080` seul vs `8080` + `8001`)

### Contexte & Problématique
L'architecture Docker Compose comprend deux services réseau :
* Le reverse proxy Nginx (`web`), écoutant en interne sur le port `80`.
* L'API FastAPI (`api`), écoutant en interne sur le port `8000`.

La question se pose de savoir quels ports doivent être publiés sur la machine hôte :
1. Publier uniquement le port d'entrée Nginx (`8080:80`).
2. Publier simultanément le port Nginx (`8080:80`) et le port de l'API (`8001:8000`).

### Décision retenue
Nous choisissons de **publier temporairement les deux ports (`8080:80` et `8001:8000`) en phase de développement/test**, avec pour règle d'architecture de **ne publier que le port `8080:80` en environnement de production**.

### Alternatives considérées & Analyse comparative

* **Publication exclusive du port Nginx (`8080:80`) :**
  - **Avantages de sécurité en production :** Le conteneur API reste totalement invisible depuis l'extérieur du réseau Docker. Nginx agit comme point d'entrée unique (Single Point of Entry), applique le filtrage des requêtes, le masquage des en-têtes internes et supprime totalement le risque d'accès direct non filtré.
  - **Inconvénients en phase de développement/test :** L'accès direct à la documentation interactive Swagger UI (`/docs`) et aux métriques de supervision de l'API sans passer par le proxy Nginx devient plus complexe.

* **Double publication (`8080:80` et `8001:8000`) — RETENUE EN DÉVELOPPEMENT :**
  - **Avantages pour les tests et le diagnostic :** Permet aux ingénieurs et testeurs de valider directement l'API sur `http://localhost:8001` (tests curl, documentation Swagger sur `/docs`, validation des statuts HTTP) indépendamment du fonctionnement du reverse proxy Nginx.
  - **Risques en production :** Exposer directement le port `8001` en production permettrait à des clients de contourner Nginx et réduirait l'utilité du reverse proxy.

### Conséquences & Recommandation pour la production
* **Pour l'Atelier 5 (développement & soutenance) :** Les deux ports sont publiés (`8080` pour l'application unifiée, `8001` pour les tests API directs et Swagger).
* **En production :** La ligne `- "8001:8000"` sera retirée du bloc `ports` du service `api`. Seul Nginx (`8080:80` ou `443:443` en HTTPS) sera accessible depuis l'Internet public, tout le trafic API transitant obligatoirement par le réseau interne Docker `starter_default` via `proxy_pass http://api:8000/;`.
