"""Simulador fotorrealista (sencillo) de escenas cenitales de frutos secos.

Sirve para PROBAR el sistema en condiciones controladas, sobre todo de
iluminación, con la verdad conocida de cada objeto. No sustituye a las fotos
reales: los umbrales definitivos se miden con fotos reales.

Modelo físico:
  - Cada fruto es un campo de alturas (mm) con su albedo (reflectancia RGB
    lineal), rugosidad y brillo especular. Formas e irregularidades
    aproximan las reales (arrugas de la nuez, casquete de la avellana,
    estrías de la almendra, media luna del anacardo, retícula y cintura
    del cacahuete).
  - Luz principal direccional (elevación y azimut variables) + luz ambiente
    (posiblemente de otro color). Sombreado Lambert + Blinn-Phong.
  - Sombras PROYECTADAS calculadas por trazado sobre el campo de alturas,
    con penumbra, y oclusión ambiental cerca de los objetos.
  - No uniformidad: foco puntual, viñeteado, gradiente.
  - Cámara: balance de blancos parcial, autoexposición, ruido de sensor,
    desenfoque, gamma sRGB, compresión JPEG y ligera inclinación (homografía).
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

CLASES = ("nuez", "avellana", "almendra", "anacardo", "cacahuete")
# Radio aproximado (mm) para colocar objetos sin solaparse.
RADIO_MM = {"nuez": 17, "avellana": 9, "almendra": 12.5, "anacardo": 13, "cacahuete": 14}
# Tapete del montaje final (ancho, alto en mm). Los bancos generados antes
# usaban 500×500 y lo indican en su tapete.json.
TAPETE_MM = (400, 300)


@dataclass
class Luz:
    nombre: str = "cenital"
    elevacion: float = 75.0          # grados sobre el tapete (90 = cenital)
    azimut: float = 30.0             # grados
    intensidad: float = 1.0
    ambiente: float = 0.35           # fracción de luz ambiente
    color: tuple = (1.0, 1.0, 1.0)   # color de la luz principal (RGB)
    color_ambiente: tuple = (1.0, 1.0, 1.0)
    penumbra_px: float = 3.0
    foco: float = 0.0                # 0 = uniforme; >0 = foco puntual
    foco_pos: tuple = (0.5, 0.5)     # posición del foco (fracción de la imagen)
    gradiente: float = 0.0           # caída lineal de luz de un lado a otro
    viñeteado: float = 0.15
    exposicion: float = 1.0          # error de la autoexposición (1 = correcta)
    balance_blancos: float = 0.7     # 1 = corrige del todo el color de la luz
    # Segunda lámpara (0 = no hay): otra dirección -> dos sombras por fruto.
    intensidad2: float = 0.0
    elevacion2: float = 50.0
    azimut2: float = 200.0


@dataclass
class Camara:
    mm_por_px: float = 0.37
    tam: tuple = (2000, 1500)        # ancho, alto (px)
    ruido: float = 0.012
    desenfoque: float = 0.7
    jpeg: int = 88
    inclinacion: float = 0.01        # perturbación de esquinas (fracción)
    # Altura de la cámara sobre el tapete (mm). None = proyección ortográfica.
    # Con perspectiva, un fruto de grosor z se ve ampliado h/(h − z/2) (su
    # contorno visible está a media altura) y desplazado radialmente.
    altura_mm: float = None


@dataclass
class Objeto:
    clase: str
    x_mm: float
    y_mm: float
    angulo: float
    escala: float = 1.0
    semilla: int = 0
    racimo: int = 0                  # 0 = suelto; >0 = id del racimo


# Grosor típico (mm) de cada fruto tumbado: para la perspectiva.
GROSOR_MM = {"nuez": 26, "avellana": 15, "almendra": 9, "anacardo": 9, "cacahuete": 13}


@dataclass
class Escena:
    objetos: list = field(default_factory=list)
    tapete_mm: tuple = TAPETE_MM


# --- utilidades --------------------------------------------------------------

def ruido_suave(forma, sigma_px, rng):
    """Ruido gaussiano filtrado (desv. 1) de escala espacial `sigma_px`."""
    r = rng.normal(0, 1, forma).astype(np.float32)
    r = cv2.GaussianBlur(r, (0, 0), max(sigma_px, 0.5))
    return r / (r.std() + 1e-9)


def _smax(a, b, k):
    """Máximo suave (une lóbulos sin arista)."""
    h = np.clip(k - np.abs(a - b), 0, None) / k
    return np.maximum(a, b) + h * h * k / 4


# --- formas: (h_mm, albedo_rgb, ks, brillo) en una rejilla local ----------------

def forma_fruto(o, u, v, mm_px, rng):
    """u, v: coordenadas locales (mm) a lo largo / a lo ancho del fruto."""
    s = o.escala
    n = lambda sig_mm: ruido_suave(u.shape, sig_mm / mm_px, rng)
    tono = rng.normal(1, 0.05, 3)                       # variación entre unidades

    if o.clase == "nuez":
        a, b = 16.5 * s, 14.5 * s
        q = (u / a) ** 2 + (v / b) ** 2
        base = np.sqrt(np.clip(1 - q, 0, 1))
        arrugas = 0.6 * n(1.0) + 0.4 * n(2.5)
        h = 24 * s * base ** 0.8 + (1.4 * arrugas + 1.3 * np.exp(-(v / 0.9) ** 2)) * (base > 0)
        alb = np.array([0.60, 0.45, 0.30]) * tono
        oscuro = np.clip(0.78 + 0.22 * arrugas, 0.45, 1.15)[..., None]
        albedo = alb * oscuro
        ks, brillo = 0.04, 8
        dentro = q < 1
    elif o.clase == "avellana":
        a, b = 8.6 * s, 7.6 * s
        q = (u / a) ** 2 + (v / b) ** 2
        h = 14 * s * np.sqrt(np.clip(1 - q, 0, 1))
        rayas = 1 + 0.07 * np.sin(v * 2.2 + 0.8 * n(2.0))
        albedo = np.array([0.40, 0.22, 0.11]) * tono * rayas[..., None]
        casquete = np.clip((-u / a - 0.55) / 0.2, 0, 1)[..., None]   # base rugosa clara
        albedo = albedo * (1 - casquete) + np.array([0.55, 0.45, 0.33]) * casquete
        ks, brillo = 0.35, 40
        dentro = q < 1
    elif o.clase == "almendra":
        a = 12 * s
        bu = 7.2 * s * np.clip(1 - 0.28 * u / a, 0.3, None)          # forma de gota
        q = (u / a) ** 2 + (v / bu) ** 2
        base = np.sqrt(np.clip(1 - q, 0, 1))
        estrias = np.sin(v * 3.0 + 1.5 * n(4.0)) * 0.5 + 0.5 * n(0.8)
        h = 8 * s * base + 0.25 * estrias * (base > 0)
        albedo = np.array([0.50, 0.30, 0.17]) * tono * np.clip(0.9 + 0.1 * estrias, 0.7, 1.1)[..., None]
        ks, brillo = 0.08, 12
        dentro = q < 1
    elif o.clase == "anacardo":
        R = 9.5 * s
        cy = R * 0.55
        phi_max = np.radians(62)
        dx, dy = u, v - cy
        rho = np.hypot(dx, dy)
        phi = np.arctan2(dx, -dy)
        t = lambda p: 4.3 * s * (1 - 0.3 * (p / phi_max) ** 2)
        d_arco = np.abs(rho - R)
        extremo = np.sign(phi) * phi_max
        ex, ey = R * np.sin(extremo), -R * np.cos(extremo)
        d_ext = np.hypot(dx - ex, dy - ey)
        en_rango = np.abs(phi) <= phi_max
        d = np.where(en_rango, d_arco, d_ext)
        grosor = np.where(en_rango, t(phi), t(phi_max))
        r = d / grosor
        h = 8 * s * np.sqrt(np.clip(1 - r ** 2, 0, 1))
        albedo = np.array([0.86, 0.76, 0.56]) * tono * np.clip(1 + 0.04 * n(1.5), 0.8, 1.2)[..., None]
        ks, brillo = 0.12, 20
        dentro = r < 1
    elif o.clase == "cacahuete":
        r1, r2 = 7.6 * s, 7.0 * s
        d1 = np.hypot(u + 5.4 * s, v * 1.05)
        d2 = np.hypot(u - 5.4 * s, v * 1.05)
        h1 = 12 * s * np.sqrt(np.clip(1 - (d1 / r1) ** 2, 0, 1))
        h2 = 11 * s * np.sqrt(np.clip(1 - (d2 / r2) ** 2, 0, 1))
        dentro = (d1 < r1) | (d2 < r2)
        h = np.where(dentro, _smax(h1, h2, 4.0), 0)
        f = 1.25 / s
        reticula = np.abs(np.sin((u + 0.6 * n(3)) * f)) * np.abs(np.sin((v + 0.6 * n(3)) * f))
        venas = np.clip(1 - reticula * 3.0, 0, 1) * np.clip(0.6 + 0.4 * n(2.0), 0, 1)            # líneas de la retícula
        h = h - 0.35 * venas * dentro
        albedo = np.array([0.74, 0.58, 0.40]) * tono * (1 - 0.15 * venas + 0.05 * n(1.0))[..., None]
        ks, brillo = 0.03, 6
    else:
        raise ValueError(o.clase)

    h = np.where(dentro, np.clip(h, 0.05, None), 0).astype(np.float32)
    albedo = np.clip(albedo, 0, 1).astype(np.float32)
    return h, albedo, ks, brillo


# --- render --------------------------------------------------------------------

def _fondo(cam, escena, rng):
    """Albedo de mesa de madera + tapete de fieltro verde, y su máscara."""
    w, h = cam.tam
    s = cam.mm_por_px
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    veta = np.sin(yy * s / 3.0 + 3 * ruido_suave((h, w), 40, rng)) * 0.5 + 0.5
    mesa = np.array([0.42, 0.28, 0.16]) * (0.85 + 0.25 * veta)[..., None]
    tw, th = escena.tapete_mm[0] / s, escena.tapete_mm[1] / s
    x0, y0 = (w - tw) / 2, (h - th) / 2
    en_tapete = (xx >= x0) & (xx < x0 + tw) & (yy >= y0) & (yy < y0 + th)
    fieltro = 1 + 0.05 * ruido_suave((h, w), 0.8, rng) + 0.025 * ruido_suave((h, w), 30, rng)
    verde = np.array([0.10, 0.30, 0.11]) * fieltro[..., None]
    albedo = np.where(en_tapete[..., None], verde, mesa).astype(np.float32)
    return albedo, (x0, y0)


def _sombra(H, luz, mm_px, paso_px=1.5):
    """Visibilidad (1 = iluminado) por trazado de rayos hacia la luz."""
    el = np.radians(luz.elevacion)
    az = np.radians(luz.azimut)
    if luz.elevacion >= 89:
        return np.ones_like(H)
    dx, dy = np.cos(az), np.sin(az)                 # dirección hacia la luz (px)
    tan_el = np.tan(el)
    h_max = float(H.max())
    if h_max <= 0:
        return np.ones_like(H)
    largo = h_max / tan_el / mm_px                  # longitud máxima de sombra (px)
    vis = np.ones_like(H)
    hgt, wid = H.shape
    t = paso_px
    while t <= largo + paso_px:
        M = np.float32([[1, 0, -dx * t], [0, 1, -dy * t]])
        # H desplazado: en cada píxel, la altura del punto situado t px hacia la luz.
        Hs = cv2.warpAffine(H, M, (wid, hgt), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        bloqueado = Hs > H + t * mm_px * tan_el + 0.05
        vis[bloqueado] = 0
        t += paso_px
    if luz.penumbra_px > 0:
        vis = cv2.GaussianBlur(vis, (0, 0), luz.penumbra_px)
    return vis


def render(escena, luz, cam=None, semilla=0, semilla_camara=None, con_mapa=False):
    """Devuelve (imagen BGR uint8, verdad) con verdad = lista de dicts
    {clase, x, y} (punto interior de cada fruto en px de la imagen final).

    `semilla_camara` fija la inclinación de la cámara: en una misma sesión la
    cámara no se mueve, así que todas sus fotos deben compartirla.
    Con `con_mapa` devuelve además el mapa de identidad (0 = tapete, k = fruto
    k-1 de la escena) en la imagen final, para diagnosticar cortes."""
    cam = cam or Camara()
    rng = np.random.default_rng(semilla)
    w, h = cam.tam
    s = cam.mm_por_px
    albedo, (x0, y0) = _fondo(cam, escena, rng)
    H = np.zeros((h, w), np.float32)
    ks = np.zeros((h, w), np.float32)
    brillo = np.ones((h, w), np.float32)
    ident = np.zeros((h, w), np.int32)

    for k, o in enumerate(escena.objetos, start=1):
        cx, cy = x0 + o.x_mm / s, y0 + o.y_mm / s
        amp = 1.0
        if cam.altura_mm:
            amp = cam.altura_mm / (cam.altura_mm - GROSOR_MM[o.clase] * o.escala / 2)
            cx, cy = w / 2 + (cx - w / 2) * amp, h / 2 + (cy - h / 2) * amp
        r = int(RADIO_MM[o.clase] * o.escala * amp * 1.4 / s)
        xa, xb = max(int(cx) - r, 0), min(int(cx) + r, w)
        ya, yb = max(int(cy) - r, 0), min(int(cy) + r, h)
        if xa >= xb or ya >= yb:
            continue
        yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
        a = np.radians(o.angulo)
        dxm, dym = (xx - cx) * s / amp, (yy - cy) * s / amp
        u = dxm * np.cos(a) + dym * np.sin(a)
        v = -dxm * np.sin(a) + dym * np.cos(a)
        hh, alb, kss, br = forma_fruto(o, u, v, s, np.random.default_rng(o.semilla))
        zona = H[ya:yb, xa:xb]
        encima = hh > zona
        zona[encima] = hh[encima]
        albedo[ya:yb, xa:xb][encima] = alb[encima]
        ks[ya:yb, xa:xb][encima] = kss
        brillo[ya:yb, xa:xb][encima] = br
        ident[ya:yb, xa:xb][encima] = k

    # Normales a partir del campo de alturas (pendientes en mm/mm).
    gy, gx = np.gradient(cv2.GaussianBlur(H, (0, 0), 0.8), s)
    nrm = np.dstack([-gx, -gy, np.ones_like(H)])
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    el, az = np.radians(luz.elevacion), np.radians(luz.azimut)
    L = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], np.float32)
    ndl = np.clip(nrm @ L, 0, None)
    vis = _sombra(H, luz, s)
    # Oclusión ambiental: el tapete junto a un fruto recibe menos luz ambiente.
    ocl = 1 - 0.45 * np.clip(cv2.GaussianBlur(H, (0, 0), 6 / s) / 6, 0, 1)
    ocl = np.where(H > 0, 1.0, ocl).astype(np.float32)

    # Campo de irradiancia no uniforme (foco, gradiente, viñeteado).
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    campo = np.ones((h, w), np.float32)
    if luz.foco > 0:
        fx, fy = luz.foco_pos[0] * w, luz.foco_pos[1] * h
        d2 = ((xx - fx) ** 2 + (yy - fy) ** 2) / (0.45 * max(w, h)) ** 2
        campo *= (1 - luz.foco) + luz.foco * 1.6 / (1 + d2) ** 1.5
    if luz.gradiente:
        g = (xx / w) * np.cos(az) + (yy / h) * np.sin(az)
        campo *= 1 - luz.gradiente * (g - g.min()) / (g.max() - g.min() + 1e-9)

    Hb = (L + np.array([0, 0, 1], np.float32))
    Hb /= np.linalg.norm(Hb)
    spec = ks * np.clip(nrm @ Hb, 0, None) ** brillo

    c_luz = np.array(luz.color, np.float32)
    c_amb = np.array(luz.color_ambiente, np.float32)
    directa = (luz.intensidad * campo * ndl * vis)[..., None] * c_luz
    if luz.intensidad2 > 0:
        from dataclasses import replace
        luz2 = replace(luz, elevacion=luz.elevacion2, azimut=luz.azimut2)
        el2, az2 = np.radians(luz.elevacion2), np.radians(luz.azimut2)
        L2 = np.array([np.cos(el2) * np.cos(az2), np.cos(el2) * np.sin(az2), np.sin(el2)],
                      np.float32)
        ndl2 = np.clip(nrm @ L2, 0, None)
        directa = directa + (luz.intensidad2 * ndl2 * _sombra(H, luz2, s))[..., None] * c_luz
    ambiente = (luz.ambiente * ocl * (0.75 + 0.25 * nrm[..., 2]))[..., None] * c_amb
    img = albedo * (directa + ambiente) + (spec * vis * campo * luz.intensidad)[..., None] * c_luz

    # Cámara: viñeteado, balance de blancos parcial, autoexposición, ruido.
    r2 = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / (0.5 * np.hypot(w, h)) ** 2
    img *= (1 - luz.viñeteado * r2)[..., None]
    blanco = c_luz * (luz.intensidad + luz.intensidad2) + c_amb * luz.ambiente
    gan = (blanco.mean() / blanco) ** luz.balance_blancos
    img *= gan
    lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    img *= 0.16 / (np.median(lum) + 1e-6) * luz.exposicion
    img += rng.normal(0, 1, img.shape).astype(np.float32) * (
        cam.ruido * np.sqrt(np.clip(img, 0, None) + 0.002))
    if cam.desenfoque > 0:
        img = cv2.GaussianBlur(img, (0, 0), cam.desenfoque)
    srgb = np.where(img <= 0.0031308, 12.92 * img, 1.055 * np.clip(img, 0, None) ** (1 / 2.4) - 0.055)
    bgr = np.clip(srgb * 255, 0, 255).astype(np.uint8)[..., ::-1].copy()

    # Ligera inclinación de la cámara (no perfectamente cenital).
    esq = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    rng_cam = np.random.default_rng(semilla if semilla_camara is None else semilla_camara)
    dest = esq + rng_cam.uniform(-1, 1, esq.shape).astype(np.float32) * cam.inclinacion * w
    Mh = cv2.getPerspectiveTransform(esq, dest)
    bgr = cv2.warpPerspective(bgr, Mh, (w, h), borderMode=cv2.BORDER_REPLICATE)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, cam.jpeg])
    bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    verdad = []
    for k, o in enumerate(escena.objetos, start=1):
        m = (ident == k).astype(np.uint8)
        if m.sum() < 30:
            continue
        dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
        py, px = np.unravel_index(int(np.argmax(dist)), dist.shape)
        p = cv2.perspectiveTransform(np.float32([[[px, py]]]), Mh)[0, 0]
        verdad.append({"clase": o.clase, "x": round(float(p[0]), 1), "y": round(float(p[1]), 1),
                       "indice": k - 1})
    if con_mapa:
        mapa = cv2.warpPerspective(ident, Mh, (w, h), flags=cv2.INTER_NEAREST)
        return bgr, verdad, mapa
    return bgr, verdad


# --- condiciones de luz y escenas aleatorias -----------------------------------

def condiciones_luz():
    """Condiciones de iluminación de prueba, de fácil a difícil."""
    return {
        "cenital_difusa": Luz("cenital_difusa", elevacion=85, ambiente=0.5, penumbra_px=6),
        "lateral_45": Luz("lateral_45", elevacion=45, ambiente=0.3),
        "rasante_25": Luz("rasante_25", elevacion=25, ambiente=0.22, penumbra_px=2),
        "rasante_15": Luz("rasante_15", elevacion=15, ambiente=0.18, penumbra_px=2),
        "foco_puntual": Luz("foco_puntual", elevacion=60, ambiente=0.15, foco=0.8,
                            foco_pos=(0.3, 0.35), penumbra_px=2),
        "calida_tenue": Luz("calida_tenue", elevacion=50, color=(1.0, 0.78, 0.52),
                            color_ambiente=(1.0, 0.8, 0.6), exposicion=0.6, balance_blancos=0.4),
        "fria_fluorescente": Luz("fria_fluorescente", elevacion=70, ambiente=0.5,
                                 color=(0.88, 0.96, 1.08), color_ambiente=(0.9, 0.97, 1.08),
                                 exposicion=1.3, penumbra_px=8),
        "mixta_ventana": Luz("mixta_ventana", elevacion=35, ambiente=0.35, color=(1.0, 0.85, 0.65),
                             color_ambiente=(0.75, 0.88, 1.15), gradiente=0.45, balance_blancos=0.5),
    }


def luz_variada(base, rng):
    """Copia de `base` con azimut aleatorio y pequeñas variaciones."""
    from dataclasses import replace
    return replace(base, azimut=float(rng.uniform(0, 360)),
                   elevacion=float(np.clip(base.elevacion + rng.normal(0, 4), 8, 89)),
                   exposicion=float(base.exposicion * rng.uniform(0.85, 1.15)))


def escena_aleatoria(rng, n, clases=CLASES, prob_contacto=0.0, tapete_mm=TAPETE_MM,
                     margen_mm=30):
    """n frutos sin solaparse; con prob_contacto, un fruto se pega a otro."""
    objs = []
    intentos = 0
    while len(objs) < n and intentos < 5000:
        intentos += 1
        c = clases[rng.integers(len(clases))]
        esc = float(rng.normal(1, 0.07))
        r = RADIO_MM[c] * esc
        if objs and rng.random() < prob_contacto:
            ref = objs[rng.integers(len(objs))]
            ang = rng.uniform(0, 2 * np.pi)
            dist = (RADIO_MM[ref.clase] * ref.escala + r) * 0.78
            x, y = ref.x_mm + dist * np.cos(ang), ref.y_mm + dist * np.sin(ang)
            minimo = 0.7
        else:
            x, y = rng.uniform(margen_mm, tapete_mm[0] - margen_mm), \
                rng.uniform(margen_mm, tapete_mm[1] - margen_mm)
            minimo = 1.05
        if not (margen_mm <= x <= tapete_mm[0] - margen_mm and
                margen_mm <= y <= tapete_mm[1] - margen_mm):
            continue
        if all(np.hypot(x - o.x_mm, y - o.y_mm) > minimo * (r + RADIO_MM[o.clase] * o.escala)
               for o in objs):
            objs.append(Objeto(c, float(x), float(y), float(rng.uniform(0, 360)), esc,
                               int(rng.integers(1 << 30))))
    return Escena(objs, tapete_mm)


def condiciones_estres():
    """Las 8 condiciones base más 4 extremas para el banco de estrés."""
    c = condiciones_luz()
    c.update({
        "dos_lamparas": Luz("dos_lamparas", elevacion=40, intensidad=0.7, ambiente=0.2,
                            intensidad2=0.55, elevacion2=35, azimut2=0, penumbra_px=2),
        "contraluz_10": Luz("contraluz_10", elevacion=10, ambiente=0.2, penumbra_px=2),
        "sobreexpuesta": Luz("sobreexpuesta", elevacion=60, ambiente=0.4, exposicion=2.1),
        "subexpuesta": Luz("subexpuesta", elevacion=55, ambiente=0.3, exposicion=0.3),
        "amarilla_sin_balance": Luz("amarilla_sin_balance", elevacion=55, color=(1.0, 0.7, 0.35),
                                    color_ambiente=(1.0, 0.75, 0.45), balance_blancos=0.0),
    })
    return c


def camaras():
    """Cámaras a distintas distancias/resoluciones; el tapete siempre entra entero."""
    return {
        "cerca": Camara(mm_por_px=0.30, tam=(2400, 1800), altura_mm=560),
        "media": Camara(mm_por_px=0.37, tam=(2000, 1500), altura_mm=700),
        "lejos": Camara(mm_por_px=0.50, tam=(2000, 1500), altura_mm=950),
        "webcam": Camara(mm_por_px=0.62, tam=(1280, 960), altura_mm=800, ruido=0.02,
                         jpeg=80, desenfoque=1.0),
        "webcam_baja": Camara(mm_por_px=0.80, tam=(960, 720), altura_mm=750, ruido=0.025,
                              jpeg=75, desenfoque=0.9),
    }
