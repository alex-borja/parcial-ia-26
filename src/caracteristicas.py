"""Extracción de características explícitas de cada objeto.

Todas las de tamaño se expresan en mm/mm² con la escala de la calibración,
de modo que los umbrales del árbol no dependen de la altura de la cámara.
El color se mide sobre la máscara erosionada (sin el borde mezclado con el
verde) de dos formas:
  - Absoluta (CIELAB/HSV): depende de la luz (intensidad, color, ángulo).
  - RELATIVA AL TAPETE (modelo de von Kries): el tapete es una referencia de
    color conocida que está junto a cada fruto. Dividiendo el color lineal
    del fruto entre el del tapete iluminado que lo rodea se cancelan la
    intensidad y el color de la luz que les llega a ambos:
        q = RGB_fruto / RGB_tapete_local       (reflectancia relativa)
    y la cromaticidad de q (rojo_rel = q_R / (q_R+q_G+q_B)) tampoco depende
    del ángulo de la luz, porque el sombreado escala R, G y B por igual.
"""
import math

import cv2
import numpy as np

from .segmentacion import _LUT_LINEAL, linealizar

# Catálogo: nombre -> (unidad, cómo se calcula, para qué sirve).
# Es la «tabla de características» del informe (scripts/documentar.py).
CATALOGO = {
    "area_mm2": ("mm²", "nº de píxeles de la máscara · (mm/px)²",
                 "Tamaño. Separa la nuez (muy grande) del resto."),
    "perimetro_mm": ("mm", "longitud del contorno externo (cv2.arcLength) · mm/px",
                     "Tamaño del borde; entra en la circularidad."),
    "diametro_equiv_mm": ("mm", "√(4·área/π)",
                          "Diámetro del círculo de igual área."),
    "longitud_mm": ("mm", "lado mayor del rectángulo mínimo girado (cv2.minAreaRect)",
                    "Dimensión mayor, independiente de la orientación."),
    "anchura_mm": ("mm", "lado menor del rectángulo mínimo girado",
                   "Dimensión menor."),
    "relacion_aspecto": ("—", "longitud / anchura",
                         "Alargamiento. Avellana ~1,1 vs. almendra/cacahuete > 1,5."),
    "circularidad": ("—", "4π·área / perímetro²",
                     "1 = círculo; baja con contornos alargados o rugosos."),
    "excentricidad": ("—", "√(1 − λ₂/λ₁), λ = autovalores de los momentos centrales de 2º orden",
                      "0 = círculo, →1 = muy alargado (elipse equivalente)."),
    "solidez": ("—", "área / área de la envolvente convexa",
                "Concavidad. El anacardo (media luna) deja mucho hueco."),
    "extension": ("—", "área / área del rectángulo mínimo girado",
                  "Cuánto llena su caja: elipse ~0,79, rectángulo ~1."),
    "cuello_relativo": ("—", "radio del cuello entre máximos / radio menor (transformada de distancia)",
                        "Cintura: 1 = sin cintura; el cacahuete ~0,7."),
    "entrante1_mm": ("mm", "profundidad del defecto de convexidad más hondo del contorno (cv2.convexityDefects)",
                     "Concavidad principal: ~0 en nuez/avellana/almendra, moderada en cacahuete "
                     "(cintura), alta en anacardo (media luna)."),
    "entrante2_mm": ("mm", "profundidad del SEGUNDO defecto de convexidad más hondo",
                     "Integridad: un fruto tiene como mucho un entrante hondo (o dos suaves, el "
                     "cacahuete); dos frutos pegados dejan DOS entrantes hondos en el contacto."),
    "contraste_interno": ("ΔE", "mayor distancia CIELAB entre los colores medios de los máximos internos",
                          "Uniformidad de color del objeto; valores altos = dos frutos pegados."),
    "orientacion_grados": ("°", "½·atan2(2μ₁₁, μ₂₀ − μ₀₂)",
                           "Dirección del eje mayor (solo informativa)."),
    "hu1": ("—", "−log₁₀|φ₁| (1er momento invariante de Hu)",
            "Forma invariante a rotación/escala (informativa)."),
    "L_media": ("0-100", "media de L* (CIELAB) dentro de la máscara erosionada",
                "Luminosidad. Almendra/avellana oscuras vs. anacardo/cacahuete claros."),
    "a_media": ("±", "media de a* (verde− / rojo+)", "Tono rojizo."),
    "b_media": ("±", "media de b* (azul− / amarillo+)", "Tono amarillento."),
    "L_desv": ("0-100", "desviación típica de L* dentro de la máscara",
               "Textura: la cáscara de la nuez es rugosa y con sombras internas."),
    "H_media": ("0-179", "media circular del tono H (HSV OpenCV)", "Tono (informativo)."),
    "S_media": ("0-255", "media de la saturación S (HSV)", "Viveza del color."),
    "rojo_rel": ("—", "q_R/(q_R+q_G+q_B), q = RGB lineal fruto / RGB lineal tapete iluminado de alrededor",
                 "Rojez respecto al tapete; INVARIANTE a intensidad, color y ángulo de la luz. "
                 "Almendra/avellana (piel rojiza) > anacardo/cacahuete (beige)."),
    "azul_rel": ("—", "q_B/(q_R+q_G+q_B)", "Componente azul relativa (informativa)."),
    "L_rel": ("—", "luminancia lineal fruto / luminancia tapete de alrededor",
              "Claridad respecto al tapete; invariante a la intensidad de la luz, pero NO a su color "
              "ni a su ángulo (con luz rasante el tapete recibe menos luz que el fruto)."),
}

# Luminancia de RGB lineal (Rec. 709).
_Y = np.array([0.2126, 0.7152, 0.0722], np.float32)


def _media_circular_h(h):
    """Media del tono H (0-179, circular) en la misma escala."""
    ang = h.astype(np.float64) * (2 * np.pi / 180)
    m = math.atan2(np.sin(ang).mean(), np.cos(ang).mean())
    return (m * 180 / (2 * np.pi)) % 180


def entrantes_mm(contorno, mm_por_px):
    """Profundidad (mm) de los dos defectos de convexidad más hondos."""
    if len(contorno) < 5:
        return 0.0, 0.0
    try:
        casco = cv2.convexHull(contorno, returnPoints=False)
        d = cv2.convexityDefects(contorno, np.sort(casco, axis=0))
    except cv2.error:
        return 0.0, 0.0
    if d is None:
        return 0.0, 0.0
    prof = sorted((d.reshape(-1, 4)[:, 3] / 256.0 * mm_por_px).tolist(), reverse=True) + [0.0, 0.0]
    return prof[0], prof[1]


def caracteristicas_forma(obj, mm_por_px):
    c = obj.contorno
    s = mm_por_px
    area_px = float(obj.area_px)
    perim_px = cv2.arcLength(c, True)
    (_, _), (ra, rb), _ = cv2.minAreaRect(c)
    largo_px, ancho_px = max(ra, rb), max(min(ra, rb), 1e-6)
    casco = cv2.convexHull(c)
    area_casco = max(cv2.contourArea(casco), 1e-6)

    m = cv2.moments(obj.mascara, binaryImage=True)
    mu20, mu02, mu11 = m["mu20"] / m["m00"], m["mu02"] / m["m00"], m["mu11"] / m["m00"]
    comun = math.sqrt(((mu20 - mu02) / 2) ** 2 + mu11 ** 2)
    l1, l2 = (mu20 + mu02) / 2 + comun, (mu20 + mu02) / 2 - comun
    excentricidad = math.sqrt(max(0.0, 1 - l2 / l1)) if l1 > 0 else 0.0
    orientacion = math.degrees(0.5 * math.atan2(2 * mu11, mu20 - mu02))
    hu1 = cv2.HuMoments(m)[0, 0]

    e1, e2 = entrantes_mm(c, mm_por_px)
    cx = obj.x0 + m["m10"] / m["m00"]
    cy = obj.y0 + m["m01"] / m["m00"]
    return {
        "centroide": (round(cx, 1), round(cy, 1)),
        "area_mm2": area_px * s * s,
        "perimetro_mm": perim_px * s,
        "diametro_equiv_mm": math.sqrt(4 * area_px / math.pi) * s,
        "longitud_mm": largo_px * s,
        "anchura_mm": ancho_px * s,
        "relacion_aspecto": largo_px / ancho_px,
        "circularidad": 4 * math.pi * area_px / perim_px ** 2 if perim_px else 0.0,
        "excentricidad": excentricidad,
        # Área del polígono (no nº de píxeles) para comparar con la del casco
        # en la misma medida; si no, la solidez puede salir > 1.
        "solidez": cv2.contourArea(c) / area_casco,
        "extension": area_px / max(ra * rb, 1e-6),
        "cuello_relativo": obj.cuello_relativo,
        "entrante1_mm": e1,
        "entrante2_mm": e2,
        "contraste_interno": obj.contraste_interno,
        "orientacion_grados": orientacion,
        "hu1": -math.log10(abs(hu1)) if hu1 else 0.0,
    }


class Conversiones:
    """Lab, HSV y RGB lineal de la imagen ENTERA, calculados una sola vez.

    El bucle de verificación evalúa cientos de piezas por imagen; convertir
    el recorte en cada una era la mitad del tiempo de las características."""

    def __init__(self, img_bgr):
        self.lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        self.hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        self.lin = linealizar(img_bgr)


def caracteristicas_color(obj, img_bgr, erosion_px, fraccion=0.0, conv=None):
    h, w = obj.mascara.shape
    zona = np.s_[obj.y0:obj.y0 + h, obj.x0:obj.x0 + w]
    sel = nucleo(obj.mascara, erosion_px, fraccion)
    if conv is None:
        conv = Conversiones(img_bgr[zona])
        zona = np.s_[:, :]
    lab = conv.lab[zona][sel].astype(np.float64)
    hsv = conv.hsv[zona][sel]
    L = lab[:, 0] * 100 / 255            # OpenCV guarda L* en 0-255
    return {
        "L_media": L.mean(),
        "a_media": (lab[:, 1] - 128).mean(),
        "b_media": (lab[:, 2] - 128).mean(),
        "L_desv": L.std(),
        "H_media": _media_circular_h(hsv[:, 0]),
        "S_media": float(hsv[:, 1].mean()),
    }


def nucleo(mascara, erosion_px, fraccion):
    """Píxeles del NÚCLEO del objeto para medir color: a más de `erosion_px`
    del borde y a más de `fraccion` × radio inscrito. Con poca resolución o
    JPEG (el color se guarda a media resolución) el borde mezcla fruto y
    tapete; el núcleo no. Si queda muy poco, se relaja."""
    dist = cv2.distanceTransform(mascara, cv2.DIST_L2, 5)
    umbral = max(erosion_px, fraccion * float(dist.max()))
    m = dist > umbral
    if m.sum() < 20:
        m = dist > erosion_px
    if m.sum() < 20:
        m = mascara > 0
    return m


# Un canal por encima de este nivel sRGB se considera QUEMADO (recortado o en
# el hombro de la curva de la cámara): ya no es proporcional a la luz.
SATURACION = 235


def sin_quemar(pix, saturacion=SATURACION):
    """Quita de `pix` (N×3 RGB lineal) los píxeles con algún canal quemado.

    Con exceso de luz el canal más alto de un fruto claro (R en el beige) se
    recorta y su cromaticidad se va hacia el blanco. Las zonas del MISMO
    fruto que reciben menos luz (sombreado propio) conservan la cromaticidad
    correcta, así que se mide en ellas. Si MÁS DE LA MITAD está quemada no se
    quita nada: lo poco que queda son grietas y borde (más oscuros y rojizos,
    no representan al fruto); el color sale entonces blanquecino, que el
    árbol sigue tratando como «claro» (ver rojo_rel en config.yaml)."""
    validos = pix.max(axis=1) < float(_LUT_LINEAL[saturacion])
    return pix[validos] if validos.sum() >= 0.5 * len(pix) else pix


def color_tapete_iluminado(lin, mascara, saturacion=SATURACION):
    """RGB lineal medio de la mitad MÁS clara de los píxeles de tapete dados:
    descarta las sombras, que reciben menos luz que la cara alta del fruto.
    Los píxeles quemados no cuentan."""
    pix = sin_quemar(lin[mascara > 0], saturacion)
    if len(pix) == 0:
        return None
    y = pix @ _Y
    return pix[y >= np.median(y)].mean(axis=0)


def caracteristicas_color_relativo(obj, img_bgr, mascara_tapete, cfg, global_=None,
                                   mm_por_px=0.4, conv=None):
    """Color del fruto relativo al tapete que lo rodea (anillo `anillo_mm`)."""
    c = {"nucleo_color": 0.0, **cfg["caracteristicas"]}
    h, w = obj.mascara.shape
    H, W = img_bgr.shape[:2]
    r_int, r_ext = (max(1, round(x / mm_por_px)) for x in c["anillo_mm"])
    xa, ya = max(obj.x0 - r_ext, 0), max(obj.y0 - r_ext, 0)
    xb, yb = min(obj.x0 + w + r_ext, W), min(obj.y0 + h + r_ext, H)
    local = np.zeros((yb - ya, xb - xa), np.uint8)
    local[obj.y0 - ya:obj.y0 - ya + h, obj.x0 - xa:obj.x0 - xa + w] = obj.mascara
    lin = linealizar(img_bgr[ya:yb, xa:xb]) if conv is None else conv.lin[ya:yb, xa:xb]

    k = lambda n: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * n + 1, 2 * n + 1))
    anillo = cv2.dilate(local, k(r_ext)) & ~cv2.dilate(local, k(r_int))
    anillo &= mascara_tapete[ya:yb, xa:xb]
    sat = c.get("saturacion", SATURACION)
    tapete = color_tapete_iluminado(lin, anillo, sat) if cv2.countNonZero(anillo) >= 30 else None
    if tapete is None:
        tapete = global_
    if tapete is None:
        return {"rojo_rel": 0.0, "azul_rel": 0.0, "L_rel": 0.0}

    m = nucleo(local, round(c["erosion_color_mm"] / mm_por_px), c["nucleo_color"])
    pix = sin_quemar(lin[m], sat)
    y = pix @ _Y
    pix = pix[y <= np.percentile(y, 95)]          # fuera brillos especulares
    fruto = pix.mean(axis=0)
    q = fruto / np.maximum(tapete, 1e-5)
    return {"rojo_rel": float(q[0] / q.sum()), "azul_rel": float(q[2] / q.sum()),
            "L_rel": float(fruto @ _Y / max(tapete @ _Y, 1e-5))}


def extraer(obj, img_bgr, mm_por_px, cfg, mascara_tapete=None, color_tapete=None,
            conv=None):
    """Diccionario con todas las características de `obj`.

    `mascara_tapete` (255 = tapete visible) permite medir el color relativo;
    `color_tapete` es el color de respaldo (todo el tapete) si el anillo
    alrededor del fruto no tiene tapete visible (frutos muy juntos).
    `conv` (Conversiones de `img_bgr`) evita repetir conversiones de color.
    """
    f = caracteristicas_forma(obj, mm_por_px)
    erosion_px = round(cfg["caracteristicas"]["erosion_color_mm"] / mm_por_px)
    f.update(caracteristicas_color(obj, img_bgr, erosion_px,
                                   cfg["caracteristicas"].get("nucleo_color", 0.0), conv))
    if mascara_tapete is not None:
        f.update(caracteristicas_color_relativo(obj, img_bgr, mascara_tapete, cfg, color_tapete,
                                                mm_por_px, conv))
    else:
        f.update({"rojo_rel": 0.0, "azul_rel": 0.0, "L_rel": 0.0})
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()}
