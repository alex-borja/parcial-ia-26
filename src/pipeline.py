"""Cadena completa: imagen RGB -> resultado interpretado.

RGB -> preprocesado -> segmentación -> detección -> características
    -> árbol de decisión -> identificación -> interpretación
"""
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from .arbol import DESCONOCIDO, clasificar, validar_arbol
from .calibracion import mm_por_px_trabajo
from .caracteristicas import Conversiones, extraer
from .deteccion import (construir_objeto, cortes_por_concavidad, detectar, numerar,
                        particiones_multiescala, regiones_conexas,
                        separar_por_cuello_y_color)
from .interpretacion import interpretar
from .caracteristicas import color_tapete_iluminado
from .segmentacion import linealizar, segmentar


@dataclass
class ObjetoAnalizado:
    objeto: object            # deteccion.Objeto
    caracteristicas: dict
    decision: object          # arbol.Decision

    @property
    def clase(self):
        return self.decision.clase


@dataclass
class Resultado:
    segmentacion: object
    mm_por_px: float
    objetos: list
    interpretacion: dict
    tiempos_ms: dict
    avisos: list = field(default_factory=list)


class Verificador:
    """Bucle de verificación segmentación <-> árbol (Nivel 1 apoyado en el 2).

    Un fruto real debe ser coherente con su clase: llegar a una hoja del
    árbol y cumplir su rango `validar` (área, solidez, entrantes...). Si una
    pieza no lo cumple («desconocido»), probablemente son varios frutos
    pegados (o un fruto partido de más) y se generan HIPÓTESIS de partición:
      - particiones por la transformada de distancia a varias escalas
        (umbral de cuello cada vez más permisivo: más centros = más frutos);
      - cortes rectos por los entrantes del contorno;
    cada pieza resultante se verifica a su vez (recursivamente).

    Se elige la partición que deja MENOS ÁREA SIN EXPLICAR (área de piezas
    desconocidas) y, a igualdad, la de MENOS piezas: partir un fruto válido
    no reduce el área sin explicar, así que no se premia. Las astillas
    (piezas menores que `pieza_min_mm2`) se unen a su vecina, y un
    presupuesto de evaluaciones por región acota el tiempo.
    """

    def __init__(self, seg, mm_px, cfg, tapete, color_global):
        self.seg, self.mm_px, self.cfg = seg, mm_px, cfg
        self.tapete, self.color_global = tapete, color_global
        self.conv = Conversiones(seg.imagen)
        d = cfg["deteccion"]
        self.max_prof = d["max_profundidad_cortes"] if d.get("verificar_con_arbol", True) else 0
        self.presupuesto = d.get("presupuesto_evaluaciones", 300)
        self.ratios = d.get("ratios_hipotesis", [])
        self.area_min_px = d["area_min_mm2"] / mm_px ** 2
        self.pieza_min_px = d.get("pieza_min_mm2", d["area_min_mm2"]) / mm_px ** 2
        self.restante = self.presupuesto
        self.fusion = d.get("fusionar_validas", True)
        self.entrante_mm = d.get("profundidad_entrante_mm", 1.5)
        self.banda_px = round(d.get("banda_refinado_mm", 0) / mm_px)
        self._cache = {}
        # Límite de tiempo por IMAGEN para la búsqueda (demo en vivo).
        self.limite = time.perf_counter() + d.get("tiempo_max_busqueda_s", 2.0)

    def analizar_parte(self, region, parte, cuello=1.0, contraste=0.0, separado=False):
        clave = (region.x0, region.y0, hash(parte.tobytes()))
        if clave in self._cache:
            return self._cache[clave]
        self.restante -= 1
        o = construir_objeto(region, parte, cuello, contraste, separado)
        a = None
        if o is not None:
            f = extraer(o, self.seg.imagen, self.mm_px, self.cfg, self.tapete, self.color_global,
                        self.conv)
            a = ObjetoAnalizado(o, f, clasificar(f, self.cfg["arbol"]))
        self._cache[clave] = a
        return a

    @staticmethod
    def puntuar(lista):
        """(fracción de área desconocida, nº de piezas): menor es mejor."""
        total = sum(a.objeto.area_px for a in lista) or 1
        desc = sum(a.objeto.area_px for a in lista if a.clase == DESCONOCIDO)
        return (round(desc / total, 3), len(lista))

    def hipotesis(self, region, parte):
        """Particiones candidatas de `parte` (listas de máscaras)."""
        d = self.cfg["deteccion"]
        salida = particiones_multiescala(parte, region.imagen, d["radio_min_mm"] / self.mm_px,
                                         self.ratios, d.get("delta_e_max"),
                                         d.get("inundacion", "niveles"))
        salida += cortes_por_concavidad(parte, self.mm_px, self.cfg)
        # Las astillas (no hay frutos tan pequeños) se unen a su vecina.
        salida = [fundir_astillas(p, self.pieza_min_px) for p in salida]
        return [p for p in salida if len(p) > 1]

    def resolver(self, region, parte, prof=0, separado=False):
        """Mejor partición de `parte` (máscara en el recorte de `region`)."""
        entero = self.analizar_parte(region, parte, separado=separado)
        if entero is None:
            return []
        if (entero.clase != DESCONOCIDO or prof >= self.max_prof or self.restante <= 0
                or time.perf_counter() > self.limite):
            return [entero]
        mejor, puntos = [entero], self.puntuar([entero])
        for particion in self.hipotesis(region, parte):
            if self.restante <= 0 or time.perf_counter() > self.limite:
                break
            sub = []
            for p in particion:
                sub += self.resolver(region, p, prof + 1, separado=True)
            if sub and self.puntuar(sub) < puntos:
                mejor, puntos = sub, self.puntuar(sub)
                if puntos[0] == 0:         # todo explicado: no hace falta buscar más
                    break
        return mejor

    def fusionar(self, region, lista):
        """Une piezas VECINAS mientras su unión sea un fruto válido y mejore
        la puntuación (misma área sin explicar con una pieza menos, o menos
        área sin explicar). Deshace el troceado de un fruto en dos mitades
        que por separado parecen válidas (nuez -> 2 «cacahuetes»): la búsqueda
        se detiene en la primera partición que lo explica todo. Dos frutos
        distintos pegados no se unen: su unión deja dos entrantes hondos (uno a
        cada lado del contacto) y queda fuera de los rangos `validar`."""
        if not self.fusion or len(lista) < 2:
            return lista
        k = np.ones((3, 3), np.uint8)
        while len(lista) > 1:
            base, mejor = self.puntuar(lista), None
            zonas = zonas_cercanas(region.mascara, [a.objeto.mascara for a in lista])
            for i in range(len(lista)):
                borde = cv2.dilate(zonas[i], k)
                for j in range(i + 1, len(lista)):
                    contacto = cv2.countNonZero(borde & zonas[j])
                    if not contacto:
                        continue
                    a = self.analizar_parte(region, zonas[i] | zonas[j], separado=True)
                    if a is None or a.clase == DESCONOCIDO:
                        continue
                    # Si ambas ya eran frutos válidos, la unión no puede tener
                    # el segundo entrante hondo que dejan dos frutos al tocarse.
                    if (DESCONOCIDO not in (lista[i].clase, lista[j].clase)
                            and a.caracteristicas["entrante2_mm"] >= self.entrante_mm):
                        continue
                    nueva = [x for t, x in enumerate(lista) if t not in (i, j)] + [a]
                    clave = (self.puntuar(nueva), -contacto)
                    if clave[0] < base and (mejor is None or clave < mejor[0]):
                        mejor = (clave, nueva)
            if mejor is None:
                break
            lista = mejor[1]
        return lista

    def refinar(self, region, lista):
        """Ajusta las fronteras entre piezas a la IMAGEN: watershed de OpenCV
        sobre el color con los núcleos de cada pieza como marcadores (cada
        pieza erosionada `banda_refinado_mm`). La frontera elegida por la
        geometría (cuello de la distancia, corte recto) puede caer a unos mm
        del contacto real; el watershed la lleva al cambio de color/sombra
        entre los dos frutos. Se acepta solo si no empeora la puntuación."""
        if not self.banda_px or len(lista) < 2:
            return lista
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * self.banda_px + 1,) * 2)
        marcas = np.zeros(region.mascara.shape, np.int32)
        fondo = len(lista) + 1
        marcas[region.mascara == 0] = fondo
        for i, a in enumerate(lista, start=1):
            nucleo = cv2.erode(a.objeto.mascara, k)
            if not cv2.countNonZero(nucleo):
                nucleo = a.objeto.mascara
            marcas[nucleo > 0] = i
        cv2.watershed(region.imagen, marcas)
        piezas = [np.where(marcas == i, 255, 0).astype(np.uint8)
                  for i in range(1, len(lista) + 1)]
        # Líneas de frontera (-1) y lo que reclamó el fondo vuelven a su pieza.
        piezas = zonas_cercanas(region.mascara, piezas)
        nueva = []
        for p, a in zip(piezas, lista):
            if cv2.countNonZero(p) < self.pieza_min_px:
                return lista
            b = self.analizar_parte(region, p, separado=True)
            if b is None:
                return lista
            nueva.append(b)
        return nueva if self.puntuar(nueva) <= self.puntuar(lista) else lista

    def region(self, region):
        lista = self.fusionar(region, self._region(region))
        return self.fusionar(region, self.refinar(region, lista))

    def _region(self, region):
        self.restante = self.presupuesto
        partes = separar_por_cuello_y_color(region, self.mm_px, self.cfg)
        partes = [p for p in partes if cv2.countNonZero(p[0]) >= self.area_min_px]
        # 1) Partición por cuello + color, verificando cada pieza.
        opcion = []
        for parte, cuello, contraste in partes:
            a = self.analizar_parte(region, parte, cuello, contraste, len(partes) > 1)
            if a is None:
                continue
            if a.clase == DESCONOCIDO and self.max_prof > 0:
                opcion += self.resolver(region, parte, 1 if len(partes) > 1 else 0,
                                        separado=len(partes) > 1)
            else:
                opcion.append(a)
        if self.max_prof == 0 or self.puntuar(opcion)[0] == 0:
            return opcion
        # 2) Si queda área sin explicar, probar también la región entera
        #    (deshace cortes erróneos del watershed) y sus hipótesis.
        if len(partes) > 1:
            alternativa = self.resolver(region, region.mascara)
            if self.puntuar(alternativa) < self.puntuar(opcion):
                return alternativa
        return opcion


def zonas_cercanas(mascara, piezas):
    """Reparte TODA la `mascara` entre las piezas por cercanía: los píxeles que
    no son de ninguna (líneas y cuñas de corte) van a la pieza más próxima.
    Así la unión de dos mitades de un fruto es el fruto entero."""
    dist = np.stack([cv2.distanceTransform(cv2.bitwise_not(p), cv2.DIST_L2, 3) for p in piezas])
    duena = np.argmin(dist, axis=0)
    return [np.where((duena == i) & (mascara > 0), 255, 0).astype(np.uint8)
            for i in range(len(piezas))]


def fundir_astillas(piezas, area_min_px):
    """Une cada pieza menor que `area_min_px` a la vecina con la que comparte
    más borde (un corte o una semilla espuria no deben crear un «fruto»)."""
    piezas = [p.copy() for p in piezas]
    k = np.ones((3, 3), np.uint8)
    while len(piezas) > 1:
        areas = [cv2.countNonZero(p) for p in piezas]
        i = int(np.argmin(areas))
        if areas[i] >= area_min_px:
            break
        borde = cv2.dilate(piezas[i], k, iterations=2)
        contacto = [cv2.countNonZero(borde & p) if j != i else -1 for j, p in enumerate(piezas)]
        j = int(np.argmax(contacto))
        if contacto[j] <= 0:
            piezas.pop(i)                 # aislada: se descarta
            continue
        piezas[j] = piezas[j] | piezas[i]
        piezas.pop(i)
    return piezas


def analizar(img_bgr, calib, cfg, clasificar_objetos=True):
    """Analiza una foto. `calib` es el dict de scripts/calibrar.py.

    Con clasificar_objetos=False (etiquetado manual) no se usa el árbol ni,
    por tanto, el bucle de verificación: solo cuello + color.
    """
    validar_arbol(cfg["arbol"], cfg["clases"])
    t = {}
    t0 = time.perf_counter()
    seg = segmentar(img_bgr, calib, cfg)
    t["segmentacion"] = (time.perf_counter() - t0) * 1000

    if seg.mm_por_px:                         # escala medida en esta foto
        mm_px, aviso = seg.mm_por_px, None
    else:
        mm_px, aviso = mm_por_px_trabajo(calib, seg.escala, img_bgr.shape)
    avisos = list(seg.avisos) + ([aviso] if aviso else [])

    t0 = time.perf_counter()
    tapete = cv2.bitwise_and(seg.mascara_verde, seg.roi)
    paso = 4                                  # submuestreo: basta para una media
    color_global = color_tapete_iluminado(linealizar(seg.imagen[::paso, ::paso]),
                                          tapete[::paso, ::paso])
    # Exposición: fuera de estos límites el resultado es menos fiable.
    nivel = np.median(seg.imagen[::paso, ::paso][tapete[::paso, ::paso] > 0], axis=0).max() \
        if cv2.countNonZero(tapete) else 0
    if 0 < nivel < 45:
        avisos.append(f"Foto muy oscura (tapete a nivel {nivel:.0f} de 255): sube la exposición "
                      "o acerca la luz; las sombras pueden engordar los frutos")
    quemado = (seg.imagen[seg.mascara_objetos > 0].max(axis=1) >= 250).mean() \
        if cv2.countNonZero(seg.mascara_objetos) else 0
    if quemado > 0.5:
        avisos.append(f"Frutos quemados por exceso de luz ({quemado:.0%} de sus píxeles): "
                      "baja la exposición; el color ya no distingue bien")
    if clasificar_objetos:
        ver = Verificador(seg, mm_px, cfg, tapete, color_global)
        analizados = []
        for reg in regiones_conexas(seg.mascara_objetos, seg.roi, seg.imagen, mm_px, cfg):
            analizados += ver.region(reg)
        numerar([a.objeto for a in analizados])
        analizados.sort(key=lambda a: a.objeto.id)
    else:
        analizados = [ObjetoAnalizado(o, extraer(o, seg.imagen, mm_px, cfg, tapete, color_global),
                                      None)
                      for o in detectar(seg.mascara_objetos, seg.roi, seg.imagen, mm_px, cfg)]
    for a in analizados:
        if a.objeto.toca_borde:
            avisos.append(f"Objeto {a.objeto.id} toca el borde del tapete (puede estar cortado)")
    t["deteccion_y_clasificacion"] = (time.perf_counter() - t0) * 1000

    interp = interpretar([a.clase for a in analizados], cfg) if clasificar_objetos else {}
    t["total"] = sum(t.values())
    return Resultado(seg, mm_px, analizados, interp, t, avisos)
