"""Fixtures comunes.

Los tests NO usan el árbol ni los umbrales de detección de config.yaml: esos
valores cambiarán al medir fotos reales y los tests no deben romperse por
ello. Se fija aquí un árbol para las formas SINTÉTICAS de tests/sinteticas.py.
"""
import copy

import pytest

from src.calibracion import calibrar
from src.config import cargar_config
from tests.sinteticas import tapete_vacio

ARBOL_SINTETICO = {
    "id": "N1", "pregunta": "¿grande?", "caracteristica": "area_mm2",
    "operador": ">", "umbral": 550,
    "si": {"clase": "nuez", "validar": {"area_mm2": [550, 1600]}},
    "sino": {
        "id": "N2", "pregunta": "¿redondo?", "caracteristica": "relacion_aspecto",
        "operador": "<", "umbral": 1.3,
        "si": {"clase": "avellana"},
        "sino": {
            "id": "N3", "pregunta": "¿claro?", "caracteristica": "L_media",
            "operador": ">", "umbral": 55,
            "si": {
                "id": "N4", "pregunta": "¿cóncavo?", "caracteristica": "solidez",
                "operador": "<", "umbral": 0.9,
                "si": {"clase": "anacardo"},
                "sino": {"clase": "cacahuete"},
            },
            "sino": {"clase": "almendra"},
        },
    },
}


@pytest.fixture
def cfg():
    c = copy.deepcopy(cargar_config())
    c["deteccion"].update({"area_min_mm2": 50, "separar_contactos": True,
                           "radio_min_mm": 3.0, "ratio_cuello": 0.7,
                           "delta_e_max": 15})
    c["escala"].update({"modo": "tapete", "tapete_mm": [500, 500]})
    c["arbol"] = copy.deepcopy(ARBOL_SINTETICO)
    c["interpretacion"] = {"lote_esperado": {}}
    return c


@pytest.fixture
def calib(cfg):
    return calibrar(tapete_vacio(), cfg)
