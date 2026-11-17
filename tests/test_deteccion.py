"""Detección y separación de frutos en contacto."""
import cv2
import numpy as np

from src.calibracion import mm_por_px_trabajo
from src.deteccion import astilla_de_borde, detectar, separar_region
from src.segmentacion import segmentar
from tests.sinteticas import MESA_BGR, escena


def detectar_escena(objs, cfg, calib, **kw):
    seg = segmentar(escena(objs, **kw), calib, cfg)
    mm, _ = mm_por_px_trabajo(calib, seg.escala)
    return detectar(seg.mascara_objetos, seg.roi, seg.imagen, mm, cfg)


def test_cuenta_frutos_sueltos(cfg, calib):
    objs = [("nuez", 80, 80, 0), ("avellana", 200, 80, 0), ("almendra", 320, 90, 30),
            ("anacardo", 420, 100, 200), ("cacahuete", 100, 300, 70),
            ("avellana", 260, 300, 0), ("almendra", 400, 400, 120)]
    assert len(detectar_escena(objs, cfg, calib)) == len(objs)


def test_separa_dos_avellanas_que_se_tocan(cfg, calib):
    det = detectar_escena([("avellana", 200, 200, 0), ("avellana", 216, 200, 0)], cfg, calib)
    assert len(det) == 2
    assert all(o.separado for o in det)
    areas = [o.area_px for o in det]
    assert min(areas) / max(areas) > 0.8          # la frontera cae en el cuello


def test_separa_tres_en_linea(cfg, calib):
    det = detectar_escena([("avellana", 200, 200, 0), ("avellana", 216, 200, 0),
                           ("avellana", 232, 200, 0)], cfg, calib)
    assert len(det) == 3


def test_no_parte_el_cacahuete(cfg, calib):
    """La cintura del cacahuete NO es un contacto entre dos frutos."""
    for ang in (0, 37, 90, 145):
        det = detectar_escena([("cacahuete", 250, 250, ang)], cfg, calib)
        assert len(det) == 1, f"ángulo {ang}"
        assert det[0].cuello_relativo < 1.0       # sí detecta que tiene cintura


def test_no_parte_el_anacardo(cfg, calib):
    for ang in (0, 60, 200):
        assert len(detectar_escena([("anacardo", 250, 250, ang)], cfg, calib)) == 1


def test_no_parte_la_almendra(cfg, calib):
    for ang in (0, 45, 90):
        assert len(detectar_escena([("almendra", 250, 250, ang)], cfg, calib)) == 1


def test_separa_por_color_contacto_ancho(cfg, calib):
    """Nuez clara pegada de lado a una almendra oscura: el cuello es ancho,
    pero el color los separa."""
    det = detectar_escena([("nuez", 300, 300, 0), ("almendra", 300, 321, 0)], cfg, calib)
    assert len(det) == 2


def test_ignora_motas_pequenas(cfg, calib):
    img = escena([("nuez", 250, 250, 0)])
    cv2.circle(img, (200, 200), 3, (40, 70, 120), -1)    # miga de ~2 mm
    seg = segmentar(img, calib, cfg)
    mm, _ = mm_por_px_trabajo(calib, seg.escala)
    assert len(detectar(seg.mascara_objetos, seg.roi, seg.imagen, mm, cfg)) == 1


def test_marca_objeto_en_el_borde_del_tapete(cfg, calib):
    det = detectar_escena([("nuez", 8, 250, 0), ("nuez", 250, 250, 0)], cfg, calib)
    assert sorted(o.toca_borde for o in det) == [False, True]


def test_descarta_astilla_de_fondo_en_el_borde(cfg, calib):
    img = escena([("nuez", 250, 250, 0)])
    lado = img.shape[0]
    # Muesca fina de mesa (~4 mm de grosor, 120 mm de largo) que entra por el
    # borde izquierdo del tapete, como la que deja un borde de tela ondulado.
    x = 40
    cv2.rectangle(img, (x - 5, lado // 2 - 150), (x + 10, lado // 2 + 150), MESA_BGR, -1)
    seg = segmentar(img, calib, cfg)
    mm, _ = mm_por_px_trabajo(calib, seg.escala)
    det = detectar(seg.mascara_objetos, seg.roi, seg.imagen, mm, cfg)
    assert len(det) == 1 and not det[0].toca_borde


def test_descarta_cuna_alargada_en_el_borde(cfg, calib):
    """Cuña de mesa más gruesa que una astilla (~8 mm) pero muy larga."""
    img = escena([("nuez", 250, 250, 0)])
    lado = img.shape[0]
    cv2.rectangle(img, (40 - 5, lado // 2 - 250), (40 + 20, lado // 2 + 250), MESA_BGR, -1)
    seg = segmentar(img, calib, cfg)
    mm, _ = mm_por_px_trabajo(calib, seg.escala)
    det = detectar(seg.mascara_objetos, seg.roi, seg.imagen, mm, cfg)
    assert len(det) == 1 and not det[0].toca_borde


def test_region_sin_maximos_validos_no_falla():
    m = np.zeros((20, 20), np.uint8)
    cv2.circle(m, (10, 10), 3, 255, -1)
    img = np.zeros((20, 20, 3), np.uint8)
    partes = separar_region(m, img, radio_min_px=10, ratio_cuello=0.7, delta_e_max=15)
    assert len(partes) == 1


def test_astilla_pegada_al_marco_de_la_foto():
    """Tira de 6 px de grosor cortada por el marco: su radio inscrito es 3 px
    (el borde de la imagen también es borde), no 6."""
    m = np.zeros((40, 100), np.uint8)
    m[:6, 10:90] = 255
    fuera = np.zeros_like(m)
    fuera[0] = 255
    assert astilla_de_borde(m, fuera, radio_min_px=4.5)
