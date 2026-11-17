"""Dibujo de resultados. (cv2.putText no admite tildes: textos en ASCII.)"""
import cv2
import numpy as np

from .arbol import DESCONOCIDO

COLOR_DESCONOCIDO = (0, 0, 255)
FUENTE = cv2.FONT_HERSHEY_SIMPLEX


def texto(img, t, org, escala=0.7, color=(255, 255, 255), grosor=2):
    cv2.putText(img, t, org, FUENTE, escala, (0, 0, 0), grosor + 3, cv2.LINE_AA)
    cv2.putText(img, t, org, FUENTE, escala, color, grosor, cv2.LINE_AA)


def color_clase(clase, cfg):
    if clase == DESCONOCIDO or clase not in cfg["clases"]:
        return COLOR_DESCONOCIDO
    return tuple(int(c) for c in cfg["clases"][clase]["color_bgr"])


def superponer_mascara(img_bgr, mascara, color=(0, 0, 255), alfa=0.5):
    salida = img_bgr.copy()
    sel = mascara > 0
    capa = np.zeros_like(img_bgr)
    capa[sel] = color
    salida[sel] = cv2.addWeighted(img_bgr, 1 - alfa, capa, alfa, 0)[sel]
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(salida, contornos, -1, color, 2)
    return salida


def panel_segmentacion(seg):
    """Mosaico 2×2: preprocesada | máscara verde / ROI | objetos."""
    gris = lambda m: cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
    roi_borde = seg.imagen.copy()
    contornos, _ = cv2.findContours(seg.roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(roi_borde, contornos, -1, (255, 0, 255), 3)
    paneles = [
        (seg.imagen, "preprocesada"),
        (gris(seg.mascara_verde), "mascara verde (inRange HSV)"),
        (roi_borde, "ROI del tapete"),
        (superponer_mascara(seg.imagen, seg.mascara_objetos), "objetos"),
    ]
    rot = []
    for img, t in paneles:
        img = img.copy()
        texto(img, t, (10, 35), 1.0)
        rot.append(img)
    return np.vstack([np.hstack(rot[:2]), np.hstack(rot[2:])])


def anotar_objetos(res, cfg, numeros_solo=False):
    """Contornos coloreados por clase, rectángulo girado y etiqueta."""
    img = res.segmentacion.imagen.copy()
    for a in res.objetos:
        o = a.objeto
        col = (255, 255, 255) if numeros_solo else color_clase(a.clase, cfg)
        cv2.drawContours(img, [o.contorno], -1, col, 2)
        if not numeros_solo:
            caja = cv2.boxPoints(cv2.minAreaRect(o.contorno)).astype(np.int32)
            cv2.polylines(img, [caja], True, col, 1, cv2.LINE_AA)
        cx, cy = (int(v) for v in a.caracteristicas["centroide"])
        etiqueta = str(o.id) if numeros_solo else f"{o.id} {a.clase}"
        texto(img, etiqueta, (cx - 20, cy - 5), 0.6, col)
    return img


def panel_inventario(res, cfg, alto):
    """Columna lateral con el conteo, la distribución y el veredicto del lote."""
    ancho = 430
    p = np.full((alto, ancho, 3), 30, np.uint8)
    it = res.interpretacion
    y = 40
    texto(p, "INVENTARIO", (15, y), 0.9)
    y += 40
    max_n = max(list(it["conteo"].values()) + [1])
    for c, n in it["conteo"].items():
        col = color_clase(c, cfg)
        texto(p, f"{c:<10}{n:>3}", (15, y), 0.65, col)
        texto(p, f"{it['distribucion_pct'][c]:4.0f}%", (200, y), 0.6)
        largo = int(150 * n / max_n)
        cv2.rectangle(p, (265, y - 15), (265 + largo, y), col, -1)
        y += 32
    if it["desconocidos"]:
        texto(p, f"desconocido{it['desconocidos']:>3}", (15, y), 0.65, COLOR_DESCONOCIDO)
        y += 32
    y += 10
    texto(p, f"TOTAL: {it['total']}", (15, y), 0.8)
    y += 35
    texto(p, f"Peso aprox: {it['peso_total_g']:.0f} g", (15, y), 0.65)
    y += 35
    lote = it.get("lote")
    if lote:
        ok = lote["correcto"]
        texto(p, "LOTE CORRECTO" if ok else "LOTE INCORRECTO", (15, y), 0.8,
              (80, 220, 80) if ok else (60, 60, 255))
        y += 30
        for c, n in lote["faltan"].items():
            texto(p, f"faltan {n} {c}", (25, y), 0.55)
            y += 25
        for c, n in lote["sobran"].items():
            texto(p, f"sobran {n} {c}", (25, y), 0.55)
            y += 25
    texto(p, f"{res.tiempos_ms['total']:.0f} ms", (15, alto - 20), 0.55, (180, 180, 180))
    return p


def imagen_resultado(res, cfg):
    img = anotar_objetos(res, cfg)
    return np.hstack([img, panel_inventario(res, cfg, img.shape[0])])
