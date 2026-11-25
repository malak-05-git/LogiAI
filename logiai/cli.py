"""Interface en ligne de commande pour LogiAI."""

import json
import sys
from pathlib import Path

from logiai.predict import Predictor


def main(argv=None):
    """Point d'entrée de la commande logiai-predict.

    Usage : logiai-predict <fichier_livraison.json>
    Retourne 0 en cas de succès, 1 en cas d'erreur.
    """
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) != 1:
        print("Usage : logiai-predict <fichier_livraison.json>", file=sys.stderr)
        return 1

    fichier = Path(argv[0])
    if not fichier.exists() or not fichier.is_file():
        print(f"Erreur : fichier '{fichier}' introuvable.", file=sys.stderr)
        return 1

    try:
        contenu = fichier.read_text(encoding="utf-8")
        data = json.loads(contenu)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        print(f"Erreur lors de la lecture du fichier JSON : {exc}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print(
            "Erreur : le fichier JSON doit contenir un objet (dictionnaire) représentant la livraison.",
            file=sys.stderr,
        )
        return 1

    try:
        predictor = Predictor()
        result = predictor.predict(data)
    except FileNotFoundError as exc:
        print(
            f"Erreur : modèle introuvable. Vérifiez la variable d'environnement LOGIAI_HOME. ({exc})",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Erreur lors de la prédiction : {exc}", file=sys.stderr)
        return 1

    proba = result["probabilite_retard"]
    pct = proba * 100
    alerte = result.get("alerte", False)
    mention = " (ALERTE)" if alerte else ""
    print(f"Probabilité de retard : {pct:.1f} %{mention}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
