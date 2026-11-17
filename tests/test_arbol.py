"""Árbol de decisión declarativo."""
import copy

import pytest

from src.arbol import (DESCONOCIDO, a_mermaid, clases_bajo, clasificar, nodos,
                       validar_arbol)
from src.config import cargar_config
from tests.conftest import ARBOL_SINTETICO

CLASES = ["nuez", "avellana", "almendra", "anacardo", "cacahuete"]


def f(**kw):
    base = dict(area_mm2=250, relacion_aspecto=1.7, L_media=40, solidez=0.97)
    base.update(kw)
    return base


@pytest.mark.parametrize("feat, esperado", [
    (f(area_mm2=800, relacion_aspecto=1.1), "nuez"),
    (f(relacion_aspecto=1.1), "avellana"),
    (f(), "almendra"),
    (f(L_media=75, solidez=0.8), "anacardo"),
    (f(L_media=75, solidez=0.95), "cacahuete"),
])
def test_clasificar(feat, esperado):
    assert clasificar(feat, ARBOL_SINTETICO).clase == esperado


def test_traza_explica_la_decision():
    d = clasificar(f(L_media=75, solidez=0.8), ARBOL_SINTETICO)
    assert [t[0] for t in d.traza] == ["N1", "N2", "N3", "N4"]
    assert [t[5] for t in d.traza] == [False, False, True, True]
    assert "anacardo" in d.texto_traza()


def test_fuera_de_rango_es_desconocido():
    d = clasificar(f(area_mm2=5000), ARBOL_SINTETICO)
    assert d.clase == DESCONOCIDO and d.clase_arbol == "nuez" and d.motivo


def test_arbol_de_config_es_valido():
    cfg = cargar_config()
    validar_arbol(cfg["arbol"], cfg["clases"])
    assert clases_bajo(cfg["arbol"]) == set(cfg["clases"])


@pytest.mark.parametrize("romper, mensaje", [
    (lambda a: a["si"].update(clase="pistacho"), "pistacho"),
    (lambda a: a.update(caracteristica="sabor"), "sabor"),
    (lambda a: a.update(operador=">="), "operador"),
    (lambda a: a.pop("sino"), "sino"),
    (lambda a: a["sino"].update(id="N1"), "repetido"),
])
def test_validar_detecta_errores(romper, mensaje):
    a = copy.deepcopy(ARBOL_SINTETICO)
    romper(a)
    with pytest.raises(ValueError, match=mensaje):
        validar_arbol(a, CLASES)


def test_nodos_y_mermaid():
    assert [n["id"] for n in nodos(ARBOL_SINTETICO)] == ["N1", "N2", "N3", "N4"]
    m = a_mermaid(ARBOL_SINTETICO)
    assert m.startswith("flowchart TD") and "ANACARDO" in m and "N4 -->|sí|" in m
