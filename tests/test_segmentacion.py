"""Calibración (color + escala) y segmentación con escenas sintéticas."""
import copy

import cv2
import numpy as np
import pytest

from src.calibracion import calibrar, calibrar_color, mm_por_px_trabajo
from src.preprocesado import redimensionar
from src.segmentacion import indice_verde, linealizar, rellenar_huecos, segmentar
from tests.sinteticas import escena, tapete_vacio


def regiones(mascara):
    n, _, stats, cent = cv2.connectedComponentsWithStats(mascara)
    return stats[1:], cent[1:]


def test_calibracion_contiene_el_verde(cfg):
    r = calibrar_color(tapete_vacio(), cfg)
    assert 40 < r["media"][0] < 90
    assert all(b <= m <= a for b, m, a in zip(r["bajo"], r["media"], r["alto"]))


def test_calibracion_excluye_el_marron(cfg):
    """El tono de los frutos (H ~ 10-25) queda fuera del rango del verde."""
    r = calibrar_color(tapete_vacio(), cfg)
    assert r["bajo"][0] > 30


def test_sombras_aceptadas_como_tapete(cfg):
    r = calibrar_color(tapete_vacio(), cfg)
    assert r["bajo"][2] <= cfg["calibracion"]["v_min_sombra"]


def test_escala_por_area_del_tapete(cfg):
    cal = calibrar(tapete_vacio(mm_por_px=0.4), cfg)
    assert cal["mm_por_px_original"] == pytest.approx(0.4, rel=0.02)
    assert cal["avisos"] == []


def test_escala_avisa_si_el_tapete_esta_cortado(cfg):
    img = tapete_vacio()[100:-100, 100:-100]     # recorte: el tapete llena la foto
    cal = calibrar(img, cfg)
    assert any("borde" in a for a in cal["avisos"])


def test_escala_fija(cfg):
    c = copy.deepcopy(cfg)
    c["escala"].update({"modo": "fijo", "mm_por_px_original": 0.25})
    assert calibrar(tapete_vacio(), c)["mm_por_px_original"] == 0.25


def test_escala_por_foto_tolera_que_la_camara_se_mueva(cfg):
    """Calibración a 0,4 mm/px; la foto se toma más lejos (0,5 mm/px)."""
    from src.pipeline import analizar
    c = copy.deepcopy(cfg)
    c["escala"]["modo"] = "tapete_por_foto"
    cal = calibrar(tapete_vacio(mm_por_px=0.4), c)
    res = analizar(escena([("nuez", 250, 250, 0)], mm_por_px=0.5), cal, c)
    assert res.mm_por_px == pytest.approx(0.5, rel=0.03)
    assert not any("resolución" in a or "calibración" in a for a in res.avisos)
    c["escala"]["modo"] = "tapete"               # con la escala fija se equivocaría
    assert analizar(escena([("nuez", 250, 250, 0)], mm_por_px=0.5), cal, c).mm_por_px \
        == pytest.approx(0.4, rel=0.03)


def test_escala_trabajo_con_reescalado(calib):
    mm, aviso = mm_por_px_trabajo(calib, 0.5, None)
    assert mm == pytest.approx(calib["mm_por_px_original"] * 2)
    _, aviso = mm_por_px_trabajo(calib, 1.0, (10, 10, 3))
    assert aviso


def test_un_objeto_por_fruto_separado(cfg, calib):
    objs = [("nuez", 100, 100, 0), ("avellana", 250, 120, 0),
            ("almendra", 380, 300, 45), ("anacardo", 150, 380, 10),
            ("cacahuete", 300, 420, 120)]
    seg = segmentar(escena(objs), calib, cfg)
    stats, cent = regiones(seg.mascara_objetos)
    assert len(stats) == len(objs)


def test_sombra_no_engorda_el_objeto(cfg, calib):
    """Con y sin sombra el área segmentada debe ser casi la misma."""
    areas = []
    for sombra in (False, True):
        seg = segmentar(escena([("avellana", 250, 250, 0)], sombra=sombra), calib, cfg)
        areas.append(regiones(seg.mascara_objetos)[0][0, cv2.CC_STAT_AREA])
    assert areas[1] == pytest.approx(areas[0], rel=0.05)


def test_mesa_fuera_del_tapete_no_es_objeto(cfg, calib):
    seg = segmentar(escena([("nuez", 250, 250, 0)]), calib, cfg)
    assert len(regiones(seg.mascara_objetos)[0]) == 1
    assert seg.avisos == []


def test_robusto_a_luz_baja_con_recalibracion(cfg):
    kw = dict(luz=0.55, gradiente=0.4)
    cal = calibrar(tapete_vacio(**kw), cfg)
    objs = [("nuez", 100, 100, 0), ("anacardo", 300, 300, 30), ("avellana", 400, 120, 0)]
    seg = segmentar(escena(objs, **kw), cal, cfg)
    assert len(regiones(seg.mascara_objetos)[0]) == 3


def test_roi_por_esquinas(cfg):
    c = copy.deepcopy(cfg)
    c["roi_tapete"]["modo"] = "esquinas"
    c["roi_tapete"]["esquinas"] = [[40, 40], [1290, 40], [1290, 1290], [40, 1290]]
    cal = calibrar(tapete_vacio(), c)
    seg = segmentar(escena([("nuez", 250, 250, 0)]), cal, c)
    assert len(regiones(seg.mascara_objetos)[0]) == 1


def test_sin_verde_avisa(cfg, calib):
    seg = segmentar(np.full((600, 800, 3), 128, np.uint8), calib, cfg)
    assert seg.avisos


def test_rellenar_huecos():
    m = np.zeros((50, 50), np.uint8)
    cv2.rectangle(m, (10, 10), (40, 40), 255, -1)
    cv2.circle(m, (25, 25), 5, 0, -1)
    assert rellenar_huecos(m)[25, 25] == 255


def test_rellenar_huecos_respeta_el_tapete_encerrado():
    """Un hueco grande (tapete dentro de un anillo de frutos) no se rellena."""
    m = np.zeros((100, 100), np.uint8)
    cv2.circle(m, (50, 50), 40, 255, -1)
    cv2.circle(m, (50, 50), 20, 0, -1)          # ojo grande: tapete
    cv2.circle(m, (50, 82), 2, 0, -1)           # mota pequeña: ruido
    r = rellenar_huecos(m, area_max_px=50)
    assert r[50, 50] == 0 and r[82, 50] == 255


def test_redimensionar_no_amplia():
    img = np.zeros((100, 200, 3), np.uint8)
    out, esc = redimensionar(img, 1600)
    assert out.shape == img.shape and esc == 1.0
    out, esc = redimensionar(np.zeros((3000, 4000, 3), np.uint8), 1600)
    assert max(out.shape[:2]) == 1600 and esc == pytest.approx(0.4)


def test_mediana_en_oscuro_quita_el_ruido_de_la_sombra(cfg):
    """Tapete casi negro (sombra dura) con ruido: ExG por píxel es aleatorio;
    con la mediana local vuelve a ser verde. Una zona con luz no cambia."""
    rng = np.random.default_rng(0)
    img = np.empty((120, 240, 3), np.uint8)
    img[:, :120] = (4, 9, 4)                      # sombra: verde a nivel ~9
    img[:, 120:] = (60, 140, 60)                  # tapete con luz
    img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    c = copy.deepcopy(cfg)
    c["segmentacion"].update({"mediana_oscuro_mm": 3.0, "nivel_oscuro": [0.03, 0.08]})
    crudo, filtrado = indice_verde(img), indice_verde(img, c, 0.4)
    assert (crudo[:, :100] < 0.25).mean() > 0.10          # sin filtro: sombra con agujeros
    assert (filtrado[:, :100] < 0.25).mean() < 0.01
    assert np.allclose(crudo[:, 140:], filtrado[:, 140:])
