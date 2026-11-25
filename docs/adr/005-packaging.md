# ADR 005 : Packaging Python standard de LogiAI, découplage des dépendances et distribution du modèle ML

* **Statut :** Accepté
* **Date :** Novembre 2026
* **Auteur :** Équipe d'Ingénierie Logicielle & MLOps LogiAI
* **Contexte :** Atelier 6 — Transformation du projet LogiAI en package Python distribuable (`pyproject.toml`, CLI `logiai-predict`, roue wheel et conteneurisation)

---

## 1. Contexte général

Jusqu'à présent, LogiAI fonctionnait comme une arborescence de scripts et de modules exécutés directement depuis le répertoire source du projet (`starter/`), avec un environnement virtuel figé par `requirements.txt`.

Pour hisser LogiAI au standard de l'industrie logicielle et MLOps, l'Atelier 6 vise à :
1. Transformer le code métier en un **package Python standard et distribuable** (`logiai`) conforme aux normes PEP 517 / PEP 518 / PEP 621 via `pyproject.toml`.
2. Fournir un point d'entrée console CLI exécutable (`logiai-predict`) pour les opérateurs et pipelines d'automatisation.
3. Découpler la distribution logicielle du transport d'artefacts binaires lourds (modèles sérialisés).
4. Moderniser l'image Docker applicative pour installer `logiai` dans `site-packages` au lieu de copier des fichiers plats dans `/app`.

Cette transition a conduit à trois décisions d'architecture fondamentales.

---

## 2. Décision 1 : Stratégie de déclaration des dépendances (`>=` dans `pyproject.toml` vs `==` dans `requirements.txt`)

### Problématique
Une bibliothèque ou un package réutilisable ne s'intègre pas de la même manière qu'un déploiement applicatif final. Si `pyproject.toml` fige des versions strictes (`==`), tout projet consommateur tentant d'installer `logiai` risquerait des conflits de résolution de dépendances insolubles (dependency hell).

### Décision retenue
* **Dans `pyproject.toml` : spécification de plages de compatibilité ouvertes (`>=` / range compatible).**
  - Exemple : `pandas>=2.0`, `scikit-learn>=1.3`, `joblib`, `numpy`.
  - Groupes optionnels : `[api]` (`fastapi`, `uvicorn`, `pydantic`, `python-dotenv`) et `[dev]` (`pytest`, `ruff`, `httpx`).
* **Dans `requirements.txt` (ou lockfile de déploiement) : versions précisément épinglées ou verrouillées.**
  - Garantit des builds Docker reproductibles au bit près et un environnement de staging identique à la production.

### Justification & Bonnes pratiques
* **Rôle d'un package (`pyproject.toml`) :** Définir le contrat d'interopérabilité minimal dont le code a besoin pour fonctionner. Il laisse le solveur du gestionnaire de paquets de l'application hôte libre de composer avec les autres dépendances de son écosystème.
* **Rôle d'une application / image Docker (`requirements.txt`) :** Définir l'assemblage exact de versions testées ensemble pour l'exécution en production.

---

## 3. Décision 2 : Exclusion du modèle Machine Learning du package Python (Wheel)

### Problématique
Le pipeline d'inférence de `logiai` nécessite le modèle sérialisé `models/model.joblib` (plusieurs mégaoctets) et ses métadonnées `models/model_info.json`. Devions-nous embarquer ce modèle binaire directement au sein de la roue (wheel `.whl`) distribuée sur PyPI/Artifactory ?

### Décision retenue
**Le modèle Machine Learning n'est STRICTEMENT PAS inclus dans le package Python (`.whl`).**
La configuration `[tool.setuptools.packages.find] include = ["logiai*"]` limite l'inclusion aux seuls modules Python du code source, excluant formellement `models/`, `data/`, `tests/`, `docs/`, et `.env`.

### Alternatives analysées & Motifs de rejet

1. **Inclusion comme `package_data` dans le wheel — REJETÉE :**
   - *Inconvénient 1 (Taille et bande passante) :* Le wheel gonfle démesurément. Chaque patch mineur de code (ex: correction d'une coquille de documentation ou d'une regex CLI) obligerait à re-télécharger l'intégralité du modèle binaire.
   - *Inconvénient 2 (Désynchronisation des cycles de vie) :* Le cycle de vie du code applicatif (commits git, revues de code, tests unitaires) est décorrélé de celui du cycle MLOps (réentraînement périodique du modèle sur de nouvelles données de livraisons).
   - *Inconvénient 3 (Sécurité et conformité) :* Versionner des artefacts binaires non auditables dans les dépôts de sources et registres de paquets standards viole les principes DevSecOps.

2. **Téléchargement automatique au runtime lors du premier import / inference — ÉCARTÉE POUR CETTE ÉTAPE :**
   - Télécharger dynamiquement depuis S3/HuggingFace au premier appel pose des risques majeurs : latence non déterministe lors du démarrage, échec d'inférence en environnement isolé/air-gapped sans accès internet public, et complexité de gestion du cache local.

3. **Séparation Découplée Code / Modèle avec variable `LOGIAI_HOME` — RETENUE :**
   - Le package Python fournit la logique d'inférence, de validation des données, et d'orchestration.
   - L'artefact binaire du modèle est acheminé et stocké séparément (stockage d'artefacts ML, Model Registry MLflow, bucket S3/GCS ou volume persistant).

---

## 4. Décision 3 : Résolution de l'accès au modèle via `LOGIAI_HOME` et repli sur `Path.cwd()`

### Problématique
Quand un package est installé via pip dans l'environnement virtuel (`site-packages/`), la constante `__file__` résout vers un sous-dossier de la bibliothèque système, où les fichiers de modèles ne résident pas. L'inférence échouerait systématiquement.

### Décision retenue
Dans `logiai/config.py`, le répertoire racine est résolu de manière dynamique :
```python
ROOT = Path(os.environ.get("LOGIAI_HOME", Path.cwd()))
```

### Mécanisme et comportement
1. **Priorité explicite (`LOGIAI_HOME`) :** Si la variable d'environnement `LOGIAI_HOME` est définie (comme dans le conteneur Docker `ENV LOGIAI_HOME=/app`), LogiAI résout immédiatement `ROOT / "models" / "model.joblib"` et `ROOT / "models" / "model_info.json"` vers ce chemin absolu.
2. **Repli contextuel (`Path.cwd()`) :** Si `LOGIAI_HOME` n'est pas configuré, le système cherche dans le répertoire de travail actuel depuis lequel l'utilisateur exécute sa ligne de commande.
3. **Robustesse en cas d'absence :** Si ni `LOGIAI_HOME` ni `Path.cwd()` ne contiennent le modèle, `logiai.cli:main` intercepte l'erreur `FileNotFoundError` avec un code de retour clair (1) et affiche un message explicite guidant l'utilisateur sur la variable `LOGIAI_HOME`.

---

## 5. Décision 4 : Modernisation du Dockerfile (Installation Package vs Copie à plat)

### Décision retenue
Le Dockerfile applicatif installe désormais `logiai` comme un package sans dépendances additionnelles (`pip install --no-cache-dir --no-deps /tmp/build`), puis purge les sources de build `/tmp/build`.

### Conséquences positives
* `logiai.__file__` pointe désormais rigoureusement vers `/usr/local/lib/python3.11/site-packages/logiai/__init__.py`.
* Le répertoire applicatif `/app` ne contient plus le code source dupliqué à plat, mais uniquement les points de montage d'exécution (`data/` et `models/`).
* Le comportement en conteneur est 100% aligné sur le comportement de production en tant que package Python.

---

## 6. Synthèse des impacts

| Domaine | Avant l'Atelier 6 | Après l'Atelier 6 |
| :--- | :--- | :--- |
| **Packaging** | Aucun (`setup.py` / `pyproject.toml` absents) | Conforme PEP 517/621 via `pyproject.toml` |
| **Installation** | Interprétation locale via `PYTHONPATH` | `pip install -e .` ou roue wheel installable |
| **CLI** | Script ad hoc non déclaré | Commande officielle `logiai-predict` dans `PATH` |
| **Isolation modèle** | Modèle couplé au dossier racine | Découplé du package, piloté par `LOGIAI_HOME` |
| **Image Docker** | Fichiers sources copiés à plat dans `/app/logiai` | Package installé dans `/usr/local/lib/.../site-packages` |
