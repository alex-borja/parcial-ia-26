"""Racimos de frutos pegados, invariancia a la distancia y simulador de contactos."""
import cv2
import numpy as np
import pytest

from src.caracteristicas import entrantes_mm
from src.deteccion import (inundar, inundar_cola, maximos_distancia, particiones_multiescala,
                           prominentes)
from src.calibracion import mm_por_px_trabajo
from src.deteccion import regiones_conexas, separar_por_cuello_y_color
from src.pipeline import Verificador, analizar, fundir_astillas, zonas_cercanas
from src.segmentacion import lado_px, segmentar
from tests.sinteticas import escena


def discos(centros, r, forma=(300, 400)):
    m = np.zeros(forma, np.uint8)
    for c in centros:
        cv2.circle(m, c, r, 255, -1)
    return m


def test_inundacion_por_niveles_equivale_a_la_exacta():
    m = discos([(80, 150), (150, 150), (220, 150), (150, 85)], 38)
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    sem = [[p[:2]] for p in prominentes(dist, maximos_distancia(dist, 7))]
    a, b = inundar_cola(m, dist, sem), inundar(m, dist, sem)
    assert ((a == b) & (m > 0)).sum() / (m > 0).sum() > 0.99


def test_multiescala_propone_racimo_de_seis():
    m = discos([(60, 150), (125, 150), (190, 150), (255, 150), (125, 85), (190, 215)], 34)
    img = np.full(m.shape + (3,), 120, np.uint8)
    parts = particiones_multiescala(m, img, 7, [0.85, 0.95, 1.01], 15)
    assert max(len(p) for p in parts) == 6


def test_fundir_astillas():
    grande = discos([(100, 100)], 40)
    astilla = np.zeros_like(grande)
    cv2.rectangle(astilla, (140, 95), (146, 105), 255, -1)
    otra = discos([(250, 100)], 40)
    piezas = fundir_astillas([grande, astilla, otra], 200)
    assert len(piezas) == 2
    assert (piezas[0] > 0).sum() == ((grande | astilla) > 0).sum()   # unida a su vecina


def test_zonas_cercanas_reparten_las_lineas_de_corte():
    fruto = discos([(150, 150)], 40)
    izq, der = fruto.copy(), fruto.copy()
    izq[:, 147:] = 0                            # corte de 6 px de ancho
    der[:, :153] = 0
    a, b = zonas_cercanas(fruto, [izq, der])
    assert ((a | b) == fruto).all() and not (a & b).any()


def verificador_de(img, calib, cfg):
    seg = segmentar(img, calib, cfg)
    mm_px, _ = mm_por_px_trabajo(calib, seg.escala, img.shape)
    tapete = cv2.bitwise_and(seg.mascara_verde, seg.roi)
    regs = regiones_conexas(seg.mascara_objetos, seg.roi, seg.imagen, mm_px, cfg)
    return Verificador(seg, mm_px, cfg, tapete, None), regs


def test_fruto_partido_se_vuelve_a_unir(cfg, calib):
    """Una nuez partida en dos mitades (cada una con forma válida de otro
    fruto) se une otra vez: Verificador.fusionar."""
    ver, (reg,) = verificador_de(escena([("nuez", 200, 200, 0)]), calib, cfg)
    ys, xs = np.nonzero(reg.mascara)
    xc = int(xs.mean())
    izq, der = reg.mascara.copy(), reg.mascara.copy()
    izq[:, xc - 1:] = 0
    der[:, :xc + 2] = 0
    mitades = [ver.analizar_parte(reg, m, separado=True) for m in (izq, der)]
    assert [a.clase for a in ver.fusionar(reg, mitades)] == ["nuez"]


def test_dos_frutos_validos_pegados_no_se_unen(cfg, calib):
    ver, (reg,) = verificador_de(escena([("avellana", 200, 200, 0),
                                         ("avellana", 216, 200, 0)]), calib, cfg)
    partes = [p for p, _, _ in separar_por_cuello_y_color(reg, ver.mm_px, cfg)]
    assert len(partes) == 2
    piezas = [ver.analizar_parte(reg, p, separado=True) for p in partes]
    assert [a.clase for a in piezas] == ["avellana"] * 2
    assert len(ver.fusionar(reg, piezas)) == 2


def test_entrantes_distinguen_un_fruto_de_dos_pegados():
    uno = discos([(150, 150)], 40)
    dos = discos([(110, 150), (185, 150)], 40)
    c = lambda m: max(cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0],
                      key=cv2.contourArea)
    e1u, e2u = entrantes_mm(c(uno), 0.4)
    e1d, e2d = entrantes_mm(c(dos), 0.4)
    assert e1u < 0.5 and e2u < 0.5
    assert e1d > 2 and e2d > 2          # dos entrantes hondos en el contacto


def test_kernels_en_mm_no_dependen_de_la_distancia():
    assert lado_px(1.5, 0.3) == 5 and lado_px(1.5, 0.8) == 1


def test_racimo_de_cuatro_en_linea(cfg, calib):
    objs = [("avellana", 200 + 16 * k, 250, 0) for k in range(4)]
    res = analizar(escena(objs), calib, cfg)
    assert [a.clase for a in res.objetos] == ["avellana"] * 4


@pytest.mark.parametrize("semilla", range(3))
def test_simulador_contactos_sin_interpenetrar(semilla):
    from simulador.escenas import CELDA_MM, Tapete, escena_racimos
    rng = np.random.default_rng(semilla)
    esc = escena_racimos(rng, [5, 3], 3, prob_apilado=0.0)
    assert len([o for o in esc.objetos if o.racimo]) == 8
    tap = Tapete()
    for o in esc.objetos:
        assert tap.solape(o) == 0, "dos frutos ocupan las mismas celdas"
        tap.poner(o)
    # Cada miembro de un racimo toca (a <= 1 mm) a otro del mismo racimo.
    for o in esc.objetos:
        if not o.racimo:
            continue
        otros = Tapete()
        for p in esc.objetos:
            if p is not o and p.racimo == o.racimo:
                otros.poner(p)
        m, f0, c0 = otros.huella(o)
        cerca = cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        ven, mm = otros._ventana(cerca, f0, c0)
        assert (otros.ocupado[ven] & mm).any(), f"un fruto del racimo no toca a nadie ({CELDA_MM} mm)"


def test_perspectiva_amplia_frutos_altos():
    from simulador.render import Camara, Escena, Luz, Objeto, render
    esc = Escena([Objeto("nuez", 250, 250, 0, 1, 1)])
    areas = []
    for altura in (None, 450):
        img, _ = render(esc, Luz(elevacion=89), Camara(mm_por_px=0.8, tam=(800, 700), altura_mm=altura))
        verde = (img[..., 1].astype(int) - img[..., 2]) > 30
        areas.append((~verde[200:500, 250:550]).sum())
    assert areas[1] > areas[0] * 1.03          # vista de cerca, se ve mayor que su huella
