"""Tests de packaging et de l'interface en ligne de commande (CLI)."""

import importlib.metadata
import json
from pathlib import Path

from logiai.cli import main


def test_package_installe():
    """Vérifie que le package logiai est installé et possède une version valide."""
    version = importlib.metadata.version("logiai")
    assert version is not None
    assert len(version) > 0


def test_commande_declaree():
    """Vérifie que le point d'entrée 'logiai-predict' est bien déclaré dans console_scripts."""
    eps = importlib.metadata.entry_points(group="console_scripts")
    names = [ep.name for ep in eps]
    assert "logiai-predict" in names


def test_cli_fichier_absent(capsys):
    """Vérifie que la CLI retourne 1 et un message d'erreur si le fichier est introuvable."""
    code = main(["fichier_inexistant_xyz_123.json"])
    captured = capsys.readouterr()
    assert code == 1
    assert "introuvable" in captured.err or "introuvable" in captured.out


def test_cli_sans_argument(capsys):
    """Vérifie que la CLI retourne 1 si aucun argument n'est fourni."""
    code = main([])
    captured = capsys.readouterr()
    assert code == 1
    assert "Usage" in captured.err or "Usage" in captured.out


def test_cli_prediction_valide(tmp_path: Path, capsys):
    """Vérifie qu'un appel avec un JSON valide effectue la prédiction et retourne 0."""
    fichier = tmp_path / "livraison.json"
    donnees = {
        "distance_km": 15.0,
        "poids_kg": 8.5,
        "heure_depart": 10,
        "pluie_mm": 0.0,
        "trafic_index": 2.0,
        "nb_arrets": 2,
        "type_vehicule": "moto",
    }
    fichier.write_text(json.dumps(donnees), encoding="utf-8")

    code = main([str(fichier)])
    captured = capsys.readouterr()

    assert code == 0
    assert "Probabilité de retard" in captured.out
