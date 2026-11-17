"""Nivel 1 — Detección: máscara de objetos -> lista de objetos individuales.

1. Componentes conexas de la máscara; las menores que `area_min_mm2` son ruido,
   y las que tocan el borde del tapete sin forma de fruto (radio inscrito <
   `radio_min_borde_mm` o alargamiento > `alargamiento_max_borde`) son
   astillas y cuñas de mesa que deja un borde de tela ondulado.
2. Separación de frutos que se tocan (transformada de distancia):
   - La transformada de distancia da, en cada píxel, el radio del mayor
     círculo inscrito centrado en él. Cada fruto tiene un máximo (su centro).
   - Si una región tiene varios máximos, se mide el «cuello» entre cada par:
     el mayor radio t tal que ambos máximos siguen conectados en {dist >= t}.
   - Dos máximos son frutos distintos si el cuello es estrecho respecto a
     ellos: cuello < ratio_cuello · min(radio_a, radio_b). Así un cacahuete
     (cintura ancha, cuello ~0,7) no se parte y dos avellanas juntas sí.
   - Además, dos máximos con colores muy distintos (ΔE en CIELAB) son frutos
     distintos aunque el contacto sea ancho (nuez pegada a una almendra).
   - Los píxeles se reparten con un watershed sembrado en los máximos de
     cada grupo: por inundación de -dist (la frontera cae en el cuello) o,
     si la separación se decidió por color, sobre la imagen (cae en el
     cambio de color).
"""
import heapq
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Objeto:
    id: int
    mascara: np.ndarray       # uint8 0/255, recorte local
    x0: int                   # esquina del recorte en la imagen de trabajo
    y0: int
    contorno: np.ndarray      # contorno externo en coordenadas de trabajo
    area_px: int
    cuello_relativo: float    # 1.0 = un solo máximo; < 1 = tiene cintura
    contraste_interno: float  # mayor ΔE entre máximos del objeto (0 = uniforme)
    separado: bool = False    # True si sale de partir una región en contacto
    toca_borde: bool = False  # True si toca el borde del tapete (puede estar cortado)

    def mascara_completa(self, forma):
        m = np.zeros(forma[:2], np.uint8)
        h, w = self.mascara.shape
        m[self.y0:self.y0 + h, self.x0:self.x0 + w] = self.mascara
        return m


# --- máximos y cuellos de la transformada de distancia ----------------------

def maximos_distancia(dist, radio_min_px):
    """Máximos locales de `dist` con supresión de no-máximos.

    Un máximo q suprime a los candidatos que caen dentro de su círculo
    inscrito (distancia < dist[q]): en un objeto alargado la cresta de la
    transformada tiene muchos máximos casi iguales y solo interesan unos pocos.
    Devuelve lista de (y, x, radio) ordenada de mayor a menor radio.
    """
    dil = cv2.dilate(dist, np.ones((3, 3), np.uint8))
    cand = ((dist >= dil - 1e-6) & (dist >= radio_min_px)).astype(np.uint8)
    n, etiquetas = cv2.connectedComponents(cand, connectivity=8)
    puntos = []
    for i in range(1, n):
        ys, xs = np.nonzero(etiquetas == i)
        j = int(np.argmax(dist[ys, xs]))
        puntos.append((int(ys[j]), int(xs[j]), float(dist[ys[j], xs[j]])))
    puntos.sort(key=lambda p: -p[2])

    aceptados = []
    for y, x, r in puntos:
        if all(np.hypot(y - ya, x - xa) >= ra for ya, xa, ra in aceptados):
            aceptados.append((y, x, r))
    return aceptados


def prominentes(dist, maximos, prominencia=0.9):
    """Quita los máximos que no son centro de fruto.

    Un máximo p es poco prominente si se puede ir desde él hasta otro máximo
    mayor sin «bajar» apenas (cuello >= prominencia · radio_p). Ocurre, p.
    ej., en el cuello entre dos frutos pegados, que puede ser un máximo local
    y haría de puente uniéndolos.
    """
    quedan = []
    for i, p in enumerate(maximos):
        mayores = [q for q in maximos[:i]          # están ordenados de mayor a menor
                   if np.hypot(p[0] - q[0], p[1] - q[1]) <= 2 * (p[2] + q[2])]
        if all(cuello(dist, p, q) < prominencia * p[2] for q in mayores):
            quedan.append(p)
    return quedan


def cuello(dist, a, b, iteraciones=12):
    """Mayor t tal que a y b están conectados dentro de {dist >= t}."""
    bajo, alto = 0.0, min(a[2], b[2])
    for _ in range(iteraciones):
        t = (bajo + alto) / 2
        _, et = cv2.connectedComponents((dist >= t).astype(np.uint8), connectivity=8)
        if et[a[0], a[1]] == et[b[0], b[1]] and et[a[0], a[1]] != 0:
            bajo = t
        else:
            alto = t
    return bajo


def color_en(lab, mascara, punto):
    """Color Lab medio (L* 0-100, a*, b*) en un disco de radio r/2 alrededor
    de un máximo, dentro de la máscara."""
    y, x, r = punto
    disco = np.zeros(mascara.shape, np.uint8)
    cv2.circle(disco, (x, y), max(2, int(r / 2)), 255, -1)
    sel = (disco > 0) & (mascara > 0)
    c = lab[sel].astype(np.float64).mean(axis=0)
    return np.array([c[0] * 100 / 255, c[1] - 128, c[2] - 128])


def medir_pares(dist, maximos, colores=None):
    """Cuello relativo y ΔE de cada par de máximos vecinos: {(i, j): (rel, ΔE)}."""
    pares = {}
    for i in range(len(maximos)):
        for j in range(i + 1, len(maximos)):
            a, b = maximos[i], maximos[j]
            # Máximos muy lejanos no son vecinos directos: si pertenecen al
            # mismo fruto, se unirán a través de máximos intermedios.
            if np.hypot(a[0] - b[0], a[1] - b[1]) > 2 * (a[2] + b[2]):
                continue
            rel = cuello(dist, a, b) / min(a[2], b[2])
            de = float(np.linalg.norm(colores[i] - colores[j])) if colores is not None else 0.0
            pares[(i, j)] = (rel, de)
    return pares


def agrupar(n, pares, ratio_cuello, delta_e_max=None):
    """Une los máximos que pertenecen al mismo fruto.

    Dos máximos vecinos son el MISMO fruto si el cuello es ancho
    (relativo >= ratio_cuello) Y su color es parecido (ΔE < delta_e_max).
    El criterio de color resuelve contactos anchos entre frutos de distinto
    color (nuez clara pegada de lado a una almendra oscura), donde el cuello
    no se estrecha.

    Devuelve (grupos, cuellos, contrastes, por_color):
      grupos: listas de índices de máximos;
      cuellos / contrastes: por grupo, el menor cuello relativo y el mayor
        ΔE internos (1.0 y 0.0 si el grupo tiene un único máximo);
      por_color: True si alguna separación se debe solo al color.
    """
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for (i, j), (rel, de) in pares.items():
        if rel >= ratio_cuello and (delta_e_max is None or de < delta_e_max):
            padre[raiz(i)] = raiz(j)
    grupos = {}
    for i in range(n):
        grupos.setdefault(raiz(i), []).append(i)
    grupos = list(grupos.values())
    cuellos, contrastes = [], []
    for g in grupos:
        internos = [pares[(i, j)] for i in g for j in g if (i, j) in pares]
        cuellos.append(min(r for r, _ in internos) if internos else 1.0)
        contrastes.append(max(d for _, d in internos) if internos else 0.0)
    por_color = any(raiz(i) != raiz(j) and rel >= ratio_cuello
                    for (i, j), (rel, _) in pares.items())
    return grupos, cuellos, contrastes, por_color


def agrupar_maximos(dist, maximos, ratio_cuello, colores=None, delta_e_max=None):
    """agrupar() midiendo antes los pares (atajo)."""
    return agrupar(len(maximos), medir_pares(dist, maximos, colores), ratio_cuello, delta_e_max)


def watershed_color(mascara, img_bgr, maximos, grupos):
    """Watershed clásico de OpenCV sobre la imagen en color: la frontera cae
    donde cambia el color (para separaciones decididas por color)."""
    marcas = np.zeros(mascara.shape, np.int32)
    fondo = len(grupos) + 1
    marcas[mascara == 0] = fondo
    for et, g in enumerate(grupos, start=1):
        for i in g:
            y, x, r = maximos[i]
            cv2.circle(marcas, (x, y), max(1, int(0.3 * r)), et, -1)
    marcas[mascara == 0] = fondo
    cv2.watershed(img_bgr, marcas)
    marcas[(mascara == 0) | (marcas == fondo)] = 0
    marcas[marcas < 0] = 0
    return marcas


def inundar_cola(mascara, dist, semillas):
    """Watershed de Meyer exacto: cola de prioridad sobre −dist (lento en Python)."""
    h, w = mascara.shape
    etiquetas = np.zeros((h, w), np.int32)
    cola, orden = [], 0
    for et, pts in enumerate(semillas, start=1):
        for y, x in pts:
            etiquetas[y, x] = et
            heapq.heappush(cola, (-dist[y, x], orden, y, x))
            orden += 1
    dentro = mascara > 0
    while cola:
        _, _, y, x = heapq.heappop(cola)
        et = etiquetas[y, x]
        for vy, vx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= vy < h and 0 <= vx < w and dentro[vy, vx] and etiquetas[vy, vx] == 0:
                etiquetas[vy, vx] = et
                orden += 1
                heapq.heappush(cola, (-dist[vy, vx], orden, vy, vx))
    return etiquetas



def inundar(mascara, dist, semillas):
    """Watershed por inundación de −dist desde las semillas, por NIVELES.

    Se baja el nivel de la transformada de distancia de 1 en 1 px; en cada
    nivel, las etiquetas crecen (dilatación 3×3) solo dentro de {dist >= nivel}
    hasta estabilizarse. Equivale al watershed clásico de Meyer con
    resolución de 1 px, pero vectorizado (OpenCV) en vez de con una cola de
    prioridad en Python. Devuelve etiquetas int32 (0 fuera de la máscara).
    """
    etiquetas = np.zeros(mascara.shape, np.uint16)
    for et, pts in enumerate(semillas, start=1):
        for y, x in pts:
            etiquetas[y, x] = et
    dentro = mascara > 0
    # Cruz 4-conexa (como la cola de prioridad) y, en los empates, se alterna
    # la etiqueta mayor y la menor para no desplazar sistemáticamente la
    # frontera hacia un lado.
    k = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    tope = np.uint16(65535)
    paso = 0
    for nivel in np.arange(np.floor(dist.max()), -1, -1):
        permitido = dentro & (dist >= nivel)
        while True:
            if paso % 2 == 0:
                crecido = cv2.dilate(etiquetas, k)
            else:                          # mínimo de las etiquetas vecinas (> 0)
                inv = cv2.dilate(np.where(etiquetas > 0, tope - etiquetas, 0).astype(np.uint16), k)
                crecido = np.where(inv > 0, tope - inv, 0)
            paso += 1
            nuevos = permitido & (etiquetas == 0) & (crecido > 0)
            if not nuevos.any():
                break
            etiquetas[nuevos] = crecido[nuevos]
    return etiquetas.astype(np.int32)


def analizar_region(mascara, img_bgr, radio_min_px):
    """Transformada de distancia, centros (máximos prominentes) y pares."""
    dist = cv2.distanceTransform(mascara, cv2.DIST_L2, 5)
    maximos = prominentes(dist, maximos_distancia(dist, radio_min_px))
    if len(maximos) <= 1:
        return dist, maximos, {}
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    colores = [color_en(lab, mascara, m) for m in maximos]
    return dist, maximos, medir_pares(dist, maximos, colores)


def repartir(mascara, img_bgr, dist, maximos, grupos, por_color, metodo="niveles"):
    """Máscara de cada grupo de máximos (watershed)."""
    if por_color:
        etiquetas = watershed_color(mascara, img_bgr, maximos, grupos)
    else:
        flood = inundar_cola if metodo == "cola" else inundar
        etiquetas = flood(mascara, dist, [[maximos[i][:2] for i in g] for g in grupos])
    return [(etiquetas == k + 1).astype(np.uint8) * 255 for k in range(len(grupos))]


def separar_region(mascara, img_bgr, radio_min_px, ratio_cuello, delta_e_max, metodo="niveles"):
    """Parte una región binaria en frutos.

    Devuelve [(mascara, cuello_rel, contraste_dE)] por fruto.
    """
    dist, maximos, pares = analizar_region(mascara, img_bgr, radio_min_px)
    if len(maximos) <= 1:
        return [(mascara, 1.0, 0.0)]
    grupos, cuellos, contrastes, por_color = agrupar(len(maximos), pares, ratio_cuello,
                                                     delta_e_max)
    if len(grupos) == 1:
        return [(mascara, cuellos[0], contrastes[0])]
    partes = repartir(mascara, img_bgr, dist, maximos, grupos, por_color, metodo)
    return list(zip(partes, cuellos, contrastes))


def particiones_multiescala(mascara, img_bgr, radio_min_px, ratios, delta_e_max,
                            metodo="niveles"):
    """Particiones con varios umbrales de cuello (más permisivo = más frutos).

    La transformada de distancia, los centros y los cuellos se calculan UNA
    vez; con cada umbral solo se reagrupa, y solo se inundan las
    agrupaciones distintas.
    """
    dist, maximos, pares = analizar_region(mascara, img_bgr, radio_min_px)
    if len(maximos) <= 1:
        return []
    vistas, salida = set(), []
    for r in ratios:
        grupos, _, _, por_color = agrupar(len(maximos), pares, r, delta_e_max)
        clave = frozenset(frozenset(g) for g in grupos)
        if len(grupos) > 1 and clave not in vistas:
            vistas.add(clave)
            salida.append(repartir(mascara, img_bgr, dist, maximos, grupos, por_color, metodo))
    return salida


# --- detección --------------------------------------------------------------

def _contorno(mascara):
    cs, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cs, key=cv2.contourArea) if cs else None


@dataclass
class Region:
    """Componente conexa de la máscara (puede contener varios frutos)."""
    mascara: np.ndarray       # recorte local 0/255
    x0: int
    y0: int
    fuera_roi: np.ndarray     # recorte de «fuera del tapete» (para toca_borde)
    imagen: np.ndarray        # recorte BGR


def astilla_de_borde(mascara, fuera_roi, radio_min_px, alargamiento_max=None):
    """¿Región fina o muy alargada pegada al borde del tapete? (mesa colada
    por un borde ondulado, no un fruto)"""
    if radio_min_px is None or not cv2.countNonZero(cv2.bitwise_and(mascara, fuera_roi)):
        return False
    # Marco de ceros: si el tapete se sale de la foto, el borde de la imagen
    # también es borde (sin él, una tira pegada al marco parecía el doble de gruesa).
    r = cv2.distanceTransform(cv2.copyMakeBorder(mascara, 1, 1, 1, 1, cv2.BORDER_CONSTANT),
                              cv2.DIST_L2, 5).max()
    if r < radio_min_px:
        return True
    return alargamiento_max is not None and \
        cv2.countNonZero(mascara) / (np.pi * r ** 2) > alargamiento_max


def regiones_conexas(mascara_objetos, roi, img_bgr, mm_por_px, cfg):
    """Componentes conexas con área >= area_min_mm2 (sin astillas de borde), recortadas."""
    area_min_px = cfg["deteccion"]["area_min_mm2"] / mm_por_px ** 2
    r_borde = cfg["deteccion"].get("radio_min_borde_mm")
    r_borde_px = r_borde / mm_por_px if r_borde else None
    fuera_roi = cv2.dilate(cv2.bitwise_not(roi), np.ones((3, 3), np.uint8))
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(mascara_objetos, connectivity=8)
    pad = 2
    H, W = mascara_objetos.shape
    salida = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < area_min_px:
            continue
        x, y, w, h = stats[i, :4]
        x0, y0 = max(x - pad, 0), max(y - pad, 0)
        x1, y1 = min(x + w + pad, W), min(y + h + pad, H)
        mascara = (etiquetas[y0:y1, x0:x1] == i).astype(np.uint8) * 255
        if astilla_de_borde(mascara, fuera_roi[y0:y1, x0:x1], r_borde_px,
                            cfg["deteccion"].get("alargamiento_max_borde")):
            continue
        salida.append(Region(mascara, int(x0), int(y0), fuera_roi[y0:y1, x0:x1],
                             img_bgr[y0:y1, x0:x1]))
    return salida


def construir_objeto(region, parte, cuello_rel=1.0, contraste=0.0, separado=False):
    """Máscara de un fruto (en el recorte de `region`) -> Objeto | None."""
    c = _contorno(parte)
    if c is None:
        return None
    toca = bool(cv2.countNonZero(cv2.bitwise_and(parte, region.fuera_roi)))
    return Objeto(id=0, mascara=parte, x0=region.x0, y0=region.y0,
                  contorno=c + np.array([[region.x0, region.y0]], dtype=c.dtype),
                  area_px=int(cv2.countNonZero(parte)),
                  cuello_relativo=round(float(cuello_rel), 3),
                  contraste_interno=round(float(contraste), 2),
                  separado=separado, toca_borde=toca)


def separar_por_cuello_y_color(region, mm_por_px, cfg):
    """Partición de una región por el criterio de cuello + color."""
    d = cfg["deteccion"]
    if not d["separar_contactos"]:
        return [(region.mascara, 1.0, 0.0)]
    return separar_region(region.mascara, region.imagen, d["radio_min_mm"] / mm_por_px,
                          d["ratio_cuello"], d.get("delta_e_max"), d.get("inundacion", "niveles"))


def cortes_por_concavidad(mascara, mm_por_px, cfg):
    """Particiones candidatas de una región cortando por sus ENTRANTES.

    Dos frutos convexos que se tocan dejan entrantes en el contorno común
    (defectos de convexidad: puntos del contorno alejados de su envolvente
    convexa). Se proponen cortes rectos:
      - entre dos entrantes profundos (contacto visto por ambos lados);
      - desde un entrante, hacia dentro y perpendicular a la envolvente
        (contacto con un solo entrante visible, p. ej. un fruto montado).
    Devuelve una lista de particiones [masc_a, masc_b], de mejor a peor corte
    (corte corto respecto a la profundidad de los entrantes).
    """
    d = cfg["deteccion"]
    prof_min = d["profundidad_entrante_mm"] / mm_por_px
    area_min = d["area_min_mm2"] / mm_por_px ** 2
    c = _contorno(mascara)
    if c is None or len(c) < 12:
        return []
    try:
        casco = cv2.convexHull(c, returnPoints=False)
        defectos = cv2.convexityDefects(c, np.sort(casco, axis=0))
    except cv2.error:
        return []
    if defectos is None:
        return []
    pts = c[:, 0, :]
    entrantes = []
    for s_, e_, f_, prof in defectos.reshape(-1, 4):    # (N,1,4) u (N,4) según versión
        if prof / 256 >= prof_min:
            entrantes.append((pts[f_].astype(float), prof / 256, pts[s_].astype(float),
                              pts[e_].astype(float)))
    entrantes.sort(key=lambda t: -t[1])
    entrantes = entrantes[:d["max_entrantes"]]

    h, w = mascara.shape
    dentro = lambda p: 0 <= p[0] < w and 0 <= p[1] < h and mascara[int(p[1]), int(p[0])] > 0
    cortes = []
    for i in range(len(entrantes)):
        for j in range(i + 1, len(entrantes)):
            p, q = entrantes[i][0], entrantes[j][0]
            largo = np.linalg.norm(p - q)
            muestras = [p + t * (q - p) for t in np.linspace(0.1, 0.9, 9)]
            if largo > 1 and np.mean([dentro(m) for m in muestras]) >= 0.8:
                cortes.append((largo / (entrantes[i][1] + entrantes[j][1]), p, q))
    for f, prof, s_, e_ in entrantes:
        cuerda = e_ - s_
        normal = np.array([-cuerda[1], cuerda[0]]) / (np.linalg.norm(cuerda) + 1e-9)
        medio = (s_ + e_) / 2
        if np.dot(f - medio, normal) < 0:
            normal = -normal                       # hacia el interior
        q = f.copy()
        for _ in range(int(2 * max(h, w))):
            sig = q + normal
            if not dentro(sig):
                break
            q = sig
        largo = np.linalg.norm(q - f)
        if largo > 2:
            cortes.append((1.5 * largo / prof, f, q))   # penaliza cortes de un lado
    cortes.sort(key=lambda t: t[0])

    particiones = []
    for _, p, q in cortes:
        if len(particiones) >= d["max_cortes"]:
            break
        m = mascara.copy()
        cv2.line(m, tuple(int(v) for v in p), tuple(int(v) for v in q), 0, 2)
        n, et, st, _ = cv2.connectedComponentsWithStats(m, connectivity=4)
        grandes = [k for k in range(1, n) if st[k, cv2.CC_STAT_AREA] >= area_min]
        if len(grandes) != 2:
            continue
        piezas = [(et == k).astype(np.uint8) * 255 for k in grandes]
        particiones.append(piezas)
    return particiones


def detectar(mascara_objetos, roi, img_bgr, mm_por_px, cfg):
    """Máscara binaria (resolución de trabajo) -> lista de Objeto, solo con
    el criterio de cuello + color (sin verificación con el árbol; la
    verificación la hace pipeline.analizar).

    `img_bgr` (preprocesada, misma resolución) se usa para el criterio de
    color al separar frutos en contacto.
    """
    area_min_px = cfg["deteccion"]["area_min_mm2"] / mm_por_px ** 2
    objetos = []
    for reg in regiones_conexas(mascara_objetos, roi, img_bgr, mm_por_px, cfg):
        partes = separar_por_cuello_y_color(reg, mm_por_px, cfg)
        for parte, cuello_rel, contraste in partes:
            if cv2.countNonZero(parte) < area_min_px:
                continue
            o = construir_objeto(reg, parte, cuello_rel, contraste, len(partes) > 1)
            if o is not None:
                objetos.append(o)
    return numerar(objetos)


def numerar(objetos):
    """Numeración estable: de arriba abajo y de izquierda a derecha."""
    objetos.sort(key=lambda o: (o.contorno[:, 0, 1].mean(),
                                o.contorno[:, 0, 0].mean()))
    for k, o in enumerate(objetos, start=1):
        o.id = k
    return objetos


def diagnostico_contactos(mascara_objetos, img_bgr, mm_por_px, cfg):
    """Mide, SIN partir nada, el cuello y el contraste de cada región.

    Sirve para justificar `ratio_cuello` y `delta_e_max` con fotos reales:
    en regiones de un solo fruto (sueltos) el cuello mínimo debe ser alto y
    el contraste bajo; en regiones con frutos en contacto, al revés.
    Devuelve una lista de dicts por región.
    """
    d = cfg["deteccion"]
    area_min_px = d["area_min_mm2"] / mm_por_px ** 2
    radio_min_px = d["radio_min_mm"] / mm_por_px
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(mascara_objetos, connectivity=8)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    salida = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < area_min_px:
            continue
        x, y, w, h = stats[i, :4]
        region = (etiquetas[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        region = cv2.copyMakeBorder(region, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
        lab_r = cv2.copyMakeBorder(lab[y:y + h, x:x + w], 2, 2, 2, 2, cv2.BORDER_REPLICATE)
        dist = cv2.distanceTransform(region, cv2.DIST_L2, 5)
        maximos = prominentes(dist, maximos_distancia(dist, radio_min_px))
        rels, des = [], []
        colores = [color_en(lab_r, region, m) for m in maximos]
        for a in range(len(maximos)):
            for b in range(a + 1, len(maximos)):
                pa, pb = maximos[a], maximos[b]
                if np.hypot(pa[0] - pb[0], pa[1] - pb[1]) > 2 * (pa[2] + pb[2]):
                    continue
                rels.append(cuello(dist, pa, pb) / min(pa[2], pb[2]))
                des.append(float(np.linalg.norm(colores[a] - colores[b])))
        salida.append({
            "area_mm2": float(stats[i, cv2.CC_STAT_AREA] * mm_por_px ** 2),
            "n_maximos": len(maximos),
            "cuello_min": min(rels) if rels else 1.0,
            "delta_e_max": max(des) if des else 0.0,
        })
    return salida
