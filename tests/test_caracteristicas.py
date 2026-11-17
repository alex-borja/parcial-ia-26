"""Fórmulas de las características sobre máscaras de geometría conocida."""
import math

import cv2
import numpy as np
import pytest

from src.caracteristicas import CATALOGO, caracteristicas_forma, extraer
from src.deteccion import Objeto


def objeto_de(mascara):
    cs, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return Objeto(1, mascara, 0, 0, max(cs, key=cv2.contourArea),
                  int(cv2.countNonZero(mascara)), 1.0, 0.0)


def elipse(a, b, ang=0, tam=400):
    m = np.zeros((tam, tam), np.uint8)
    cv2.ellipse(m, (tam // 2, tam // 2), (a, b), ang, 0, 360, 255, -1)
    return m


def test_circulo():
    f = caracteristicas_forma(objeto_de(elipse(100, 100)), mm_por_px=0.5)
    assert f["area_mm2"] == pytest.approx(math.pi * 50 ** 2, rel=0.01)
    assert f["diametro_equiv_mm"] == pytest.approx(100, rel=0.01)
    assert f["relacion_aspecto"] == pytest.approx(1, abs=0.03)
    assert f["circularidad"] == pytest.approx(1, abs=0.1)
    assert f["excentricidad"] < 0.1
    assert f["solidez"] == pytest.approx(1, abs=0.02)


def test_elipse_2_a_1():
    f = caracteristicas_forma(objeto_de(elipse(120, 60)), mm_por_px=1.0)
    assert f["relacion_aspecto"] == pytest.approx(2, rel=0.03)
    assert f["excentricidad"] == pytest.approx(math.sqrt(1 - 0.25), abs=0.01)
    assert f["longitud_mm"] == pytest.approx(240, rel=0.02)
    assert f["extension"] == pytest.approx(math.pi / 4, abs=0.02)


def test_invariancia_a_rotacion():
    base = caracteristicas_forma(objeto_de(elipse(120, 60, 0)), 1.0)
    for ang in (30, 75, 130):
        f = caracteristicas_forma(objeto_de(elipse(120, 60, ang)), 1.0)
        for k in ("area_mm2", "relacion_aspecto", "excentricidad", "solidez"):
            assert f[k] == pytest.approx(base[k], rel=0.03), (k, ang)
    f = caracteristicas_forma(objeto_de(elipse(120, 60, 30)), 1.0)
    assert abs(f["orientacion_grados"]) == pytest.approx(30, abs=2)


def test_media_luna_poco_solida():
    m = elipse(100, 100)
    cv2.circle(m, (200 + 60, 200), 100, 0, -1)
    f = caracteristicas_forma(objeto_de(m), 1.0)
    assert f["solidez"] < 0.8


def test_color_lab():
    m = elipse(50, 50, tam=200)
    img = np.zeros((200, 200, 3), np.uint8)
    img[:] = (255, 255, 255)
    f = extraer(objeto_de(m), img, 1.0, {"caracteristicas": {"erosion_color_mm": 3}})
    assert f["L_media"] == pytest.approx(100, abs=0.5)
    assert abs(f["a_media"]) < 1 and abs(f["b_media"]) < 1
    assert f["L_desv"] < 0.5


def test_catalogo_cubre_todo():
    m = elipse(50, 30, tam=200)
    img = np.full((200, 200, 3), 100, np.uint8)
    f = extraer(objeto_de(m), img, 1.0, {"caracteristicas": {"erosion_color_mm": 3}})
    assert set(CATALOGO) <= set(f)


def test_todas_numericas():
    m = elipse(50, 30, tam=200)
    img = np.full((200, 200, 3), 100, np.uint8)
    f = extraer(objeto_de(m), img, 1.0, {"caracteristicas": {"erosion_color_mm": 3}})
    for k in CATALOGO:
        assert isinstance(f[k], (int, float)), k
