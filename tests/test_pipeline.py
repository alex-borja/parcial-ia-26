"""Cadena completa sobre escenas sintéticas con posiciones/orientaciones variadas."""
from collections import Counter

import numpy as np
import pytest

from src.calibracion import calibrar
from src.pipeline import analizar
from src.visualizacion import imagen_resultado, panel_segmentacion
from tests.sinteticas import ESCENA_EJEMPLO, escena, tapete_vacio


def test_escena_de_ejemplo(cfg, calib):
    res = analizar(escena(ESCENA_EJEMPLO), calib, cfg)
    esperado = Counter(c for c, *_ in ESCENA_EJEMPLO)
    assert res.interpretacion["conteo"] == {c: esperado.get(c, 0) for c in cfg["clases"]}
    assert res.interpretacion["desconocidos"] == 0


def escena_aleatoria(rng, n):
    """n frutos en posiciones y ángulos aleatorios sin solaparse."""
    clases = list(("nuez", "avellana", "almendra", "anacardo", "cacahuete"))
    objs, centros = [], []
    while len(objs) < n:
        x, y = rng.uniform(40, 460, 2)
        if all(np.hypot(x - a, y - b) > 45 for a, b in centros):
            centros.append((x, y))
            objs.append((clases[rng.integers(len(clases))], x, y, rng.uniform(0, 360)))
    return objs


@pytest.mark.parametrize("semilla", range(5))
def test_escenas_aleatorias(cfg, calib, semilla):
    rng = np.random.default_rng(semilla)
    objs = escena_aleatoria(rng, int(rng.integers(4, 12)))
    res = analizar(escena(objs, semilla=semilla), calib, cfg)
    esperado = Counter(c for c, *_ in objs)
    assert res.interpretacion["conteo"] == {c: esperado.get(c, 0) for c in cfg["clases"]}


def test_tapete_vacio_sin_objetos(cfg, calib):
    res = analizar(tapete_vacio(semilla=3), calib, cfg)
    assert res.objetos == [] and res.interpretacion["total"] == 0


def test_foto_mas_grande_se_reescala(cfg):
    """Foto a 4000 px: se trabaja a lado_max_px y las medidas en mm se mantienen."""
    import cv2
    vacio = tapete_vacio()
    img = escena([("nuez", 250, 250, 0)])
    grande = lambda im: cv2.resize(im, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    cal_g = calibrar(grande(vacio), cfg)
    res_g = analizar(grande(img), cal_g, cfg)
    cal = calibrar(vacio, cfg)
    res = analizar(img, cal, cfg)
    a_g = res_g.objetos[0].caracteristicas["area_mm2"]
    a = res.objetos[0].caracteristicas["area_mm2"]
    assert a_g == pytest.approx(a, rel=0.05)


def test_visualizacion_no_falla(cfg, calib):
    res = analizar(escena(ESCENA_EJEMPLO), calib, cfg)
    img = imagen_resultado(res, cfg)
    assert img.shape[0] == res.segmentacion.imagen.shape[0]
    assert panel_segmentacion(res.segmentacion).ndim == 3
