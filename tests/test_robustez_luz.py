"""Robustez a la iluminación: invariancias de ExG y del color relativo,
y piezas nuevas de la detección (prominencia, cortes, verificación)."""
import copy

import cv2
import numpy as np
import pytest

from src.caracteristicas import caracteristicas_color_relativo
from src.deteccion import Objeto, cortes_por_concavidad, maximos_distancia, prominentes
from src.pipeline import analizar
from src.segmentacion import indice_verde, linealizar
from tests.sinteticas import escena

LUT_SRGB = np.array([round(255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055))
                     for v in np.linspace(0, 1, 4096)], np.uint8)


def iluminar(img, factor_rgb):
    """Aplica una luz de otra intensidad/color en el espacio LINEAL."""
    lin = linealizar(img) * np.asarray(factor_rgb, np.float32)
    idx = np.clip(lin * 4095, 0, 4095).astype(int)
    return LUT_SRGB[idx][..., ::-1].copy()


def test_exg_invariante_a_intensidad_y_tolerante_al_color():
    verde = np.full((20, 20, 3), (45, 125, 55), np.uint8)
    base = indice_verde(verde).mean()
    assert indice_verde(iluminar(verde, (0.3, 0.3, 0.3))).mean() == pytest.approx(base, abs=0.03)
    # Sombra iluminada por cielo azulado: ExG baja algo pero sigue muy por
    # encima de cualquier fruto (<= ~0,15).
    assert indice_verde(iluminar(verde, (0.25, 0.3, 0.4))).mean() > 0.45
    marron = np.full((20, 20, 3), (40, 75, 130), np.uint8)
    assert indice_verde(marron).mean() < 0.15


@pytest.mark.parametrize("luz", [(0.4, 0.4, 0.4), (1.0, 0.8, 0.55), (0.7, 0.85, 1.1)])
def test_color_relativo_invariante_a_la_luz(luz):
    """El mismo fruto con otra luz (intensidad/color) da el mismo rojo_rel y L_rel."""
    img = np.zeros((120, 120, 3), np.uint8)
    img[:] = (45, 125, 55)
    cv2.circle(img, (60, 60), 25, (50, 90, 145), -1)
    m = np.zeros((120, 120), np.uint8)
    cv2.circle(m, (60, 60), 25, 255, -1)
    obj = Objeto(1, m, 0, 0, None, int(m.sum() // 255), 1.0, 0.0)
    tapete = cv2.bitwise_not(cv2.dilate(m, np.ones((5, 5), np.uint8)))
    cfg = {"caracteristicas": {"erosion_color_mm": 1.2, "anillo_mm": [1.6, 5.6]}}
    a = caracteristicas_color_relativo(obj, img, tapete, cfg)
    b = caracteristicas_color_relativo(obj, iluminar(img, luz), tapete, cfg)
    assert b["rojo_rel"] == pytest.approx(a["rojo_rel"], abs=0.01)
    if len(set(luz)) == 1:              # L_rel solo es invariante a la INTENSIDAD
        assert b["L_rel"] == pytest.approx(a["L_rel"], rel=0.05)


def test_prominencia_quita_maximo_en_el_cuello():
    m = np.zeros((100, 160), np.uint8)
    for cx in (50, 90):
        cv2.circle(m, (cx, 50), 21, 255, -1)
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    todos = maximos_distancia(dist, 5)
    assert len(prominentes(dist, todos)) == 2


def test_cortes_por_concavidad_separan_dos_discos():
    m = np.zeros((100, 160), np.uint8)
    cv2.circle(m, (55, 50), 25, 255, -1)
    cv2.circle(m, (100, 50), 25, 255, -1)
    cfg = {"deteccion": {"profundidad_entrante_mm": 1.5, "area_min_mm2": 50,
                         "max_entrantes": 6, "max_cortes": 6}}
    particiones = cortes_por_concavidad(m, 0.4, cfg)
    assert particiones
    a, b = particiones[0]
    assert min(a.sum(), b.sum()) / max(a.sum(), b.sum()) > 0.8


def test_verificacion_no_parte_frutos_validos(cfg, calib):
    """Cacahuete y anacardo (cóncavos) siguen siendo UN objeto con la verificación."""
    res = analizar(escena([("cacahuete", 150, 150, 30), ("anacardo", 300, 300, 80)]), calib, cfg)
    assert sorted(a.clase for a in res.objetos) == ["anacardo", "cacahuete"]


def test_verificacion_separa_fusion_invalida(cfg, calib):
    """Dos almendras pegadas de lado (cuello ancho, mismo color): la región
    entera no es válida y la verificación prueba cortes por los entrantes."""
    c = copy.deepcopy(cfg)
    # La unión de las dos almendras es grande (N1 -> nuez), pero una nuez
    # real es convexa: con solidez mínima la región entera es «desconocido».
    c["arbol"]["si"]["validar"]["solidez"] = [0.97, 1.0]
    objs = [("almendra", 250, 250, 90), ("almendra", 263, 250, 90)]
    sin = copy.deepcopy(c)
    sin["deteccion"]["verificar_con_arbol"] = False
    assert len(analizar(escena(objs), calib, sin).objetos) == 1
    res = analizar(escena(objs), calib, c)
    assert [a.clase for a in res.objetos] == ["almendra", "almendra"]


def test_simulador_genera_escena_con_verdad():
    from simulador.render import Camara, Escena, Luz, Objeto as Obj, render
    cam = Camara(tam=(700, 600), mm_por_px=0.9)
    esc = Escena([Obj("nuez", 150, 150, 0, 1, 1), Obj("anacardo", 300, 250, 40, 1, 2)])
    img, verdad = render(esc, Luz(elevacion=30), cam, semilla=1)
    assert img.shape == (600, 700, 3)
    assert sorted(v["clase"] for v in verdad) == ["anacardo", "nuez"]
