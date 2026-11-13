"""Tester pour casser : valeurs limites et entrées malformées.

Le projet contient 2 bugs volontaires dans les bornes. Vos tests doivent les trouver.
"""

import pytest

# (champ, valeur envoyée, code attendu) : on teste les DEUX côtés de chaque borne
CAS_LIMITES = [
    # distance_km : [1, 1000]
    ("distance_km", 1, 200),
    ("distance_km", 0.9, 422),
    ("distance_km", 1000, 200),
    ("distance_km", 1001, 422),
    # poids_kg : [0.1, 3500]
    ("poids_kg", 0.1, 200),
    ("poids_kg", 0.05, 422),
    ("poids_kg", 3500, 200),
    ("poids_kg", 3500.1, 422),
    # heure_depart : [0, 23] (entier)
    ("heure_depart", 0, 200),
    ("heure_depart", -1, 422),
    ("heure_depart", 23, 200),
    ("heure_depart", 24, 422),
    ("heure_depart", 11.5, 422),
    # pluie_mm : [0, 100]
    ("pluie_mm", 0, 200),
    ("pluie_mm", -0.1, 422),
    ("pluie_mm", 100, 200),
    ("pluie_mm", 100.1, 422),
    # trafic_index : [0, 10]
    ("trafic_index", 0, 200),
    ("trafic_index", -0.1, 422),
    ("trafic_index", 10, 200),
    ("trafic_index", 10.1, 422),
    # nb_arrets : [0, 15] (entier)
    ("nb_arrets", 0, 200),
    ("nb_arrets", -1, 422),
    ("nb_arrets", 15, 200),
    ("nb_arrets", 16, 422),
    # type_vehicule : "moto" | "fourgon" | "camion"
    ("type_vehicule", "moto", 200),
    ("type_vehicule", "fourgon", 200),
    ("type_vehicule", "camion", 200),
    ("type_vehicule", "trottinette", 422),
]


@pytest.mark.parametrize("champ, valeur, attendu", CAS_LIMITES)
def test_valeurs_limites(
    client, headers_user, livraison_valide, champ, valeur, attendu
):
    livraison_valide[champ] = valeur
    r = client.post("/v1/predict", json=livraison_valide, headers=headers_user)
    assert r.status_code == attendu, (
        f"{champ}={valeur} : attendu {attendu}, obtenu {r.status_code}"
    )
