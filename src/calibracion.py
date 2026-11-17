"""Calibración de la sesión con una foto del tapete VACÍO.

Mide dos cosas, ambas con la luz y la cámara reales del aula:

1. Color del tapete en HSV: rango = media ± k·desv por canal. El tono (H)
   del verde apenas cambia con la intensidad de la luz y los frutos secos
   son marrones/beige, así que H y S los separan aunque cambie el brillo (V).
2. Escala mm/px: imprescindible para que el árbol use tamaños en mm y no
   dependa de la altura de la cámara. Se obtiene del área del tapete (de
   dimensiones conocidas) o de un valor medido a mano.
"""
import json
from pathlib import Path

import cv2
import numpy as np

from .preprocesado import preprocesar
from .segmentacion import (contorno_tapete, escala_por_casco, indice_verde, mascara_tapete,
                           umbral_exg)

# Límites superiores de cada canal en OpenCV (H va de 0 a 179).
LIMITES_HSV = np.array([179, 255, 255], dtype=np.float64)


def roi_central(img, fraccion):
    h, w = img.shape[:2]
    mh, mw = int(h * (1 - fraccion) / 2), int(w * (1 - fraccion) / 2)
    return img[mh:h - mh, mw:w - mw]


def pixeles_tapete(img, cfg):
    """Máscara booleana de la ROI central que es verde por ExG. Con un tapete
    pequeño (40×30 cm) y la cámara algo alta, el centro de la foto puede
    incluir mesa: sin esta máscara contaminaría el color del tapete."""
    exg = indice_verde(roi_central(img, cfg["calibracion"]["roi_central"]))
    verde = exg > umbral_exg(exg, cfg)[0]
    return verde if verde.sum() >= 0.1 * verde.size else np.ones_like(verde)


def calibrar_color(img_bgr_vacio, cfg):
    """Rango HSV del tapete; dict con media, desv y límites `bajo`/`alto`."""
    c = cfg["calibracion"]
    img, _ = preprocesar(img_bgr_vacio, cfg)
    hsv = cv2.cvtColor(roi_central(img, c["roi_central"]), cv2.COLOR_BGR2HSV)
    pix = hsv[pixeles_tapete(img, cfg)].astype(np.float64)

    media = pix.mean(axis=0)
    desv = pix.std(axis=0)
    k = np.asarray(c["k_desviaciones"], dtype=np.float64)
    semiancho = np.maximum(k * desv, np.asarray(c["ancho_minimo"]) / 2)

    bajo = np.clip(media - semiancho, 0, LIMITES_HSV)
    alto = np.clip(media + semiancho, 0, LIMITES_HSV)
    # Las sombras de los frutos son verde oscuro: se aceptan en el tapete.
    bajo[2] = min(bajo[2], c.get("v_min_sombra", bajo[2]))
    return {
        "media": media.round(2).tolist(),
        "desv": desv.round(2).tolist(),
        "k": k.tolist(),
        "bajo": np.floor(bajo).astype(int).tolist(),
        "alto": np.ceil(alto).astype(int).tolist(),
        "n_pixeles": int(len(pix)),
    }


def escala_por_tapete(img_bgr_vacio, rango, cfg):
    """mm por px de la imagen ORIGINAL a partir del área del tapete.

    Devuelve (mm_por_px_original, avisos). Requiere que el tapete se vea
    entero: si su envolvente toca el borde de la foto, la escala sale mal.
    """
    img, escala = preprocesar(img_bgr_vacio, cfg)
    casco = contorno_tapete(mascara_tapete(img, rango, cfg))
    if casco is None:
        raise ValueError("No se encontró el tapete; no se puede medir la escala")
    mm_px_trabajo, avisos = escala_por_casco(casco, img.shape, cfg["escala"]["tapete_mm"])

    # 1 px de trabajo = 1/escala px originales.
    return float(mm_px_trabajo * escala), avisos


def calibrar(img_bgr_vacio, cfg):
    """Calibración completa: rango HSV + escala. Dict serializable."""
    rango = calibrar_color(img_bgr_vacio, cfg)
    e = cfg["escala"]
    if e["modo"] in ("tapete", "tapete_por_foto"):
        mm_px, avisos = escala_por_tapete(img_bgr_vacio, rango, cfg)
    elif e["modo"] == "fijo":
        if not e.get("mm_por_px_original"):
            raise ValueError("escala.modo == fijo necesita escala.mm_por_px_original")
        mm_px, avisos = float(e["mm_por_px_original"]), []
    else:
        raise ValueError(f"escala.modo desconocido: {e['modo']!r}")

    # Estadística del índice de verde del tapete (informativa / diagnóstico).
    img, _ = preprocesar(img_bgr_vacio, cfg)
    exg = indice_verde(roi_central(img, cfg["calibracion"]["roi_central"]))[pixeles_tapete(img, cfg)]
    rango["exg_media"] = round(float(exg.mean()), 4)
    rango["exg_desv"] = round(float(exg.std()), 4)
    if cfg["segmentacion"].get("metodo") == "exg":
        rango["exg_umbral"] = round(umbral_exg(indice_verde(img), cfg)[0], 4)

    h, w = img_bgr_vacio.shape[:2]
    campo = [round(w * mm_px, 1), round(h * mm_px, 1)]
    if not cubre_tapete(campo, e["tapete_mm"]):
        avisos.append(f"El campo de visión ({campo[0]:.0f}×{campo[1]:.0f} mm) no cubre el "
                      f"tapete ({e['tapete_mm'][0]:.0f}×{e['tapete_mm'][1]:.0f} mm): "
                      "sube la cámara o abre el encuadre.")
    rango.update({
        "mm_por_px_original": round(mm_px, 5),
        "tam_original": [w, h],
        "campo_vision_mm": campo,
        "tapete_mm": list(e["tapete_mm"]),
        "avisos": avisos,
    })
    return rango


def cubre_tapete(campo_mm, tapete_mm):
    """¿Cabe el tapete en el campo de visión (en cualquier orientación)?"""
    a, b = sorted(campo_mm, reverse=True)
    ta, tb = sorted(tapete_mm, reverse=True)
    return a >= ta and b >= tb


def mm_por_px_trabajo(calib, escala, forma_original=None):
    """mm por px a la resolución de trabajo de una foto concreta.

    Devuelve (mm_por_px, aviso | None). Si la foto tiene otra resolución que
    la de calibración, la escala ya no es válida y se avisa.
    """
    aviso = None
    if forma_original is not None and "tam_original" in calib:
        h, w = forma_original[:2]
        if [w, h] != list(calib["tam_original"]):
            aviso = (f"La foto mide {w}×{h} px pero la calibración se hizo a "
                     f"{calib['tam_original'][0]}×{calib['tam_original'][1]}: "
                     "las medidas en mm pueden ser incorrectas.")
    return calib["mm_por_px_original"] / escala, aviso


def guardar_calibracion(calib, ruta):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(calib, indent=2, ensure_ascii=False), encoding="utf-8")


def cargar_calibracion(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))
