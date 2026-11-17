"""Segmentación: máscara de objetos (frutos secos) sobre el tapete.

Pasos:
  1. Preprocesado (reescalado + desenfoque), compartido con la calibración.
  2. Máscara del tapete (verde) con uno de dos métodos (`segmentacion.metodo`):
     - "exg" (por defecto): índice de exceso de verde ExG = 2g − r − b sobre
       la CROMATICIDAD (r, g, b = R/(R+G+B)...) en RGB LINEAL. Al dividir por
       la suma se cancela la intensidad de la luz: una sombra o un foco
       cambian R, G y B en la misma proporción y ExG no varía. El umbral se
       adapta en cada imagen a la mediana de ExG del tapete, así que también
       tolera cambios de color de la luz después de calibrar.
     - "hsv": inRange con el rango HSV calibrado (método original; la sombra
       con luz ambiente de otro color sale del rango y engorda el objeto).
  3. ROI del tapete: lo que queda fuera del tapete no puede ser un objeto.
  4. Objetos = NO verde dentro de la ROI.
  5. Apertura (quita motas sueltas) y cierre (repara bordes mordidos).
  6. Relleno de huecos (brillos de la avellana, grietas de la nuez).

Por qué funciona bien con frutos secos: son marrones/beige (H ~ 10-25,
lejos del verde H ~ 40-80) y la sombra que proyectan conserva el tono verde,
así que cae dentro del rango del tapete y no engorda el objeto.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

from .preprocesado import preprocesar


@dataclass
class ResultadoSegmentacion:
    imagen: np.ndarray            # BGR preprocesada (resolución de trabajo)
    escala: float                 # resolución de trabajo / original
    mascara_verde: np.ndarray     # 255 = tapete
    roi: np.ndarray               # 255 = dentro del tapete
    mascara_objetos: np.ndarray   # 255 = objeto
    avisos: list = field(default_factory=list)
    mm_por_px: float | None = None  # escala de ESTA foto (escala.modo tapete_por_foto)


def kernel(n):
    return cv2.getStructuringElement(cv2.MORPH_RECT, (n, n))


def lado_px(mm, mm_por_px):
    """Lado IMPAR (px) de un elemento estructurante de `mm` milímetros.

    Los tamaños morfológicos se fijan en mm para que no dependan de la
    distancia de la cámara: 1,5 mm son 5 px a 0,3 mm/px pero 1 px (nada) a
    0,8 mm/px; un kernel fijo de 5 px se comería las puntas del anacardo con
    una webcam lejana.
    """
    return 2 * int(mm / mm_por_px / 2) + 1


# sRGB (0-255) -> RGB lineal (0-1): deshace la gamma de la cámara. Sin esto
# la cromaticidad SÍ dependería de la intensidad (la gamma no es lineal).
_LUT_LINEAL = np.array([(c / 255) / 12.92 if c / 255 <= 0.04045
                        else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in range(256)],
                       dtype=np.float32)


def linealizar(img_bgr):
    """BGR uint8 -> RGB lineal float32 (orden R, G, B)."""
    return _LUT_LINEAL[img_bgr[..., ::-1]]


# Luminancia de RGB lineal (Rec. 709).
_Y = np.array([0.2126, 0.7152, 0.0722], np.float32)


def _exg(lin):
    suma = lin.sum(axis=2) + 1e-4
    return (2 * lin[..., 1] - lin[..., 0] - lin[..., 2]) / suma


def indice_verde(img_bgr, cfg=None, mm_por_px=None):
    """ExG = 2g − r − b sobre la cromaticidad lineal. Tapete ~0,6-0,8;
    frutos secos (marrón/beige) ~ −0,1-0,15; la sombra conserva el valor.

    Con `cfg` y `mm_por_px`, en las zonas MUY OSCURAS (sombra dura, foto con
    poca luz) se usa la MEDIANA local de ExG: en un píxel casi negro quedan
    pocos niveles de 8 bits y manda el ruido del sensor, su cromaticidad es
    aleatoria y la sombra del fruto dejaba de ser «verde». La mediana quita
    ese ruido sin mover los bordes (un desenfoque los movería y ensancharía
    los contactos). Los píxeles con luz no se tocan: la mezcla es gradual
    entre los dos `nivel_oscuro` de luminancia lineal."""
    lin = linealizar(img_bgr)
    exg = _exg(lin)
    s = (cfg or {}).get("segmentacion", {})
    if not (s.get("mediana_oscuro_mm") and mm_por_px):
        return exg
    bajo, alto = s["nivel_oscuro"]
    k = max(3, lado_px(s["mediana_oscuro_mm"], mm_por_px))
    y = cv2.blur(lin @ _Y, (k, k))
    w = np.clip((y - bajo) / (alto - bajo), 0, 1)
    if w.min() >= 1:
        return exg
    # medianBlur admite cualquier tamaño solo en 8 bits: ExG ∈ [−1, 2] -> 0-255.
    q = np.clip((exg + 1) * 85, 0, 255).astype(np.uint8)
    mediana = cv2.medianBlur(q, k).astype(np.float32) / 85 - 1
    return w * exg + (1 - w) * mediana


def umbral_exg(exg, cfg):
    """Umbral adaptativo: mediana del tapete en ESTA imagen − k·σ robusta,
    acotado entre `exg_min` y mediana − `margen_min`."""
    s = cfg["segmentacion"]
    candidatos = exg[exg > s["exg_min"]]          # tapete (y sombras); no mesa ni frutos
    if candidatos.size < 100:
        return s["exg_min"], None
    m = float(np.median(candidatos))
    sigma = 1.4826 * float(np.median(np.abs(candidatos - m)))
    u = float(np.clip(m - s["k_exg"] * sigma, s["exg_min"], m - s["margen_exg"]))
    return u, m


def mascara_tapete(img_bgr, calib, cfg=None, mm_por_px=None):
    """255 = tapete. `calib` es la calibración (para el método hsv)."""
    metodo = (cfg or {}).get("segmentacion", {}).get("metodo", "hsv")
    if metodo == "exg":
        exg = indice_verde(img_bgr, cfg, mm_por_px)
        u, _ = umbral_exg(exg, cfg)
        return ((exg > u) * 255).astype(np.uint8)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array(calib["bajo"], dtype=np.uint8),
                       np.array(calib["alto"], dtype=np.uint8))


def rellenar_huecos(mascara, area_max_px=None):
    """Rellena los huecos internos de la máscara.

    Con `area_max_px` solo los huecos menores: un hueco grande es tapete
    encerrado por un racimo (p. ej. el ojo que dejan dos anacardos en anillo)
    y rellenarlo pegaría tapete a un fruto."""
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    salida = np.zeros_like(mascara)
    cv2.drawContours(salida, contornos, -1, 255, thickness=cv2.FILLED)
    if area_max_px is None:
        return salida
    huecos = cv2.bitwise_and(salida, cv2.bitwise_not(mascara))
    n, et, st, _ = cv2.connectedComponentsWithStats(huecos, connectivity=4)
    grandes = np.isin(et, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > area_max_px])
    salida[grandes] = 0
    return salida


def contorno_tapete(mascara_verde):
    """Envolvente convexa de la mayor región verde (o None si no hay verde).

    Se usa la envolvente (y no la región tal cual) porque los objetos abren
    huecos y muescas en el verde, incluso en el borde del tapete.
    """
    # Cierre grande solo aquí: une trozos de tapete separados por una sombra.
    unida = cv2.morphologyEx(mascara_verde, cv2.MORPH_CLOSE, kernel(15))
    contornos, _ = cv2.findContours(unida, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return None
    return cv2.convexHull(max(contornos, key=cv2.contourArea))


def escala_por_casco(casco, forma, tapete_mm):
    """mm/px a partir de la envolvente del tapete, de dimensiones conocidas:
    mm/px = sqrt(área_real / área_px). Devuelve (mm_por_px, avisos)."""
    avisos = []
    h, w = forma[:2]
    x, y, bw, bh = cv2.boundingRect(casco)
    if x <= 2 or y <= 2 or x + bw >= w - 2 or y + bh >= h - 2:
        avisos.append("El tapete toca el borde de la foto: no se ve entero y "
                      "la escala por área no es fiable. Usa escala.modo: fijo.")
    ancho_mm, alto_mm = tapete_mm
    mm_px = float(np.sqrt(ancho_mm * alto_mm / cv2.contourArea(casco)))

    # Comprobación: la proporción de lados medida debe parecerse a la real.
    (_, _), (lado_a, lado_b), _ = cv2.minAreaRect(casco)
    prop_medida = max(lado_a, lado_b) / max(min(lado_a, lado_b), 1)
    prop_real = max(ancho_mm, alto_mm) / min(ancho_mm, alto_mm)
    if abs(prop_medida - prop_real) / prop_real > 0.15:
        avisos.append(f"Proporción del tapete medida {prop_medida:.2f} vs. "
                      f"real {prop_real:.2f}: ¿cámara inclinada o tapete cortado?")
    return mm_px, avisos


def roi_automatica(mascara_verde, cfg_roi):
    """Devuelve (roi, aviso | None)."""
    h, w = mascara_verde.shape
    casco = contorno_tapete(mascara_verde)
    if casco is None:
        return np.full_like(mascara_verde, 255), \
            "ROI automática: no se encontró verde; se usa la imagen completa"
    if cv2.contourArea(casco) < cfg_roi["fraccion_minima"] * h * w:
        return np.full_like(mascara_verde, 255), \
            "ROI automática: el tapete detectado es demasiado pequeño; " \
            "se usa la imagen completa (¿calibración correcta?)"
    roi = np.zeros_like(mascara_verde)
    cv2.drawContours(roi, [casco], -1, 255, cv2.FILLED)
    return roi, None


def roi_por_esquinas(forma, esquinas, escala):
    pts = (np.asarray(esquinas, dtype=np.float64) * escala).round().astype(np.int32)
    roi = np.zeros(forma, dtype=np.uint8)
    cv2.fillPoly(roi, [cv2.convexHull(pts)], 255)
    return roi


def calcular_roi(mascara_verde, escala, cfg, mm_por_px=None):
    c = cfg["roi_tapete"]
    modo = c["modo"]
    aviso = None
    if modo == "auto":
        roi, aviso = roi_automatica(mascara_verde, c)
    elif modo == "esquinas":
        if len(c["esquinas"]) != 4:
            raise ValueError("roi_tapete.esquinas necesita 4 puntos [x, y]")
        roi = roi_por_esquinas(mascara_verde.shape, c["esquinas"], escala)
    elif modo == "ninguna":
        roi = np.full_like(mascara_verde, 255)
    else:
        raise ValueError(f"roi_tapete.modo desconocido: {modo!r}")

    m = round(c["margen_interior_mm"] / mm_por_px) if mm_por_px else 5
    if m > 0:
        roi = cv2.erode(roi, kernel(2 * m + 1))
    return roi, aviso


def segmentar(img_bgr, rango, cfg):
    """Imagen BGR original -> ResultadoSegmentacion."""
    s = cfg["segmentacion"]
    img, escala = preprocesar(img_bgr, cfg)
    # mm/px a la resolución de trabajo (si la calibración ya tiene escala).
    mm_px = rango["mm_por_px_original"] / escala if rango.get("mm_por_px_original") else 0.4
    verde = mascara_tapete(img, rango, cfg, mm_px)
    avisos, mm_foto = [], None
    if cfg["escala"]["modo"] == "tapete_por_foto":
        # Escala de ESTA foto con el tapete que se ve en ella (los frutos
        # quedan dentro de su envolvente): tolera que la cámara se mueva.
        casco = contorno_tapete(verde)
        if casco is None:
            avisos.append("No se encontró el tapete: se usa la escala de la calibración")
        else:
            # El tapete de la calibración (el de su sesión) manda sobre config.
            tapete_mm = rango.get("tapete_mm") or cfg["escala"]["tapete_mm"]
            mm_foto, av = escala_por_casco(casco, img.shape, tapete_mm)
            avisos += av
            mm_px = mm_foto
    roi, aviso = calcular_roi(verde, escala, cfg, mm_px)
    avisos += [aviso] if aviso else []

    objetos = cv2.bitwise_and(cv2.bitwise_not(verde), roi)
    n_ap, n_ci = lado_px(s["apertura_mm"], mm_px), lado_px(s["cierre_mm"], mm_px)
    if n_ap > 1:
        objetos = cv2.morphologyEx(objetos, cv2.MORPH_OPEN, kernel(n_ap))
    if n_ci > 1:
        objetos = cv2.morphologyEx(objetos, cv2.MORPH_CLOSE, kernel(n_ci))
    if s["rellenar_huecos"]:
        hmax = s.get("hueco_max_mm2")
        objetos = rellenar_huecos(objetos, hmax / mm_px ** 2 if hmax is not None else None)

    return ResultadoSegmentacion(img, escala, verde, roi, objetos, avisos, mm_foto)
