"""Composición de escenas con CONTACTO FÍSICO entre frutos.

Cada fruto ocupa su huella real (la de `forma_fruto`) en una rejilla del
tapete de 0,5 mm. Para pegar un fruto a otro se le acerca desde fuera, paso
a paso, hasta que su huella toca la del racimo (holgura <= 0,5 mm): no se
interpenetran, como en la realidad. Con `prob_apilado` se le empuja un poco
más (1-3 mm), simulando un fruto ligeramente montado sobre otro.
"""
import numpy as np

from .render import CLASES, RADIO_MM, TAPETE_MM, Escena, Objeto, forma_fruto

CELDA_MM = 0.5


class Tapete:
    """Rejilla de ocupación del tapete (True = hay fruto)."""

    def __init__(self, tapete_mm=TAPETE_MM, margen_mm=25):
        self.w, self.h = tapete_mm
        self.margen = margen_mm
        self.ocupado = np.zeros((int(self.h / CELDA_MM), int(self.w / CELDA_MM)), bool)

    def huella(self, o):
        """(máscara, fila0, col0) de la huella de `o` en la rejilla."""
        r = RADIO_MM[o.clase] * o.escala * 1.3
        n = int(2 * r / CELDA_MM) + 1
        t = (np.arange(n) - n / 2) * CELDA_MM
        dy, dx = np.meshgrid(t, t, indexing="ij")
        a = np.radians(o.angulo)
        u = dx * np.cos(a) + dy * np.sin(a)
        v = -dx * np.sin(a) + dy * np.cos(a)
        h, *_ = forma_fruto(o, u, v, CELDA_MM, np.random.default_rng(o.semilla))
        f0 = int(round((o.y_mm - n * CELDA_MM / 2) / CELDA_MM))
        c0 = int(round((o.x_mm - n * CELDA_MM / 2) / CELDA_MM))
        return h > 0, f0, c0

    def _ventana(self, m, f0, c0):
        H, W = self.ocupado.shape
        fa, ca = max(f0, 0), max(c0, 0)
        fb, cb = min(f0 + m.shape[0], H), min(c0 + m.shape[1], W)
        if fa >= fb or ca >= cb:
            return None, None
        return (slice(fa, fb), slice(ca, cb)), m[fa - f0:fb - f0, ca - c0:cb - c0]

    def dentro(self, o):
        r = RADIO_MM[o.clase] * o.escala
        return (self.margen + r <= o.x_mm <= self.w - self.margen - r and
                self.margen + r <= o.y_mm <= self.h - self.margen - r)

    def solape(self, o):
        """Nº de celdas de la huella de `o` ya ocupadas."""
        m, f0, c0 = self.huella(o)
        ven, mm = self._ventana(m, f0, c0)
        if ven is None:
            return 10 ** 6
        return int((self.ocupado[ven] & mm).sum())

    def poner(self, o):
        m, f0, c0 = self.huella(o)
        ven, mm = self._ventana(m, f0, c0)
        self.ocupado[ven] |= mm


def _nuevo(rng, clase, x, y, racimo=0, var_tam=0.12):
    return Objeto(clase, float(x), float(y), float(rng.uniform(0, 360)),
                  float(np.clip(rng.normal(1, var_tam / 2), 1 - var_tam, 1 + var_tam)),
                  int(rng.integers(1 << 30)), racimo)


def _separacion_libre(tap, o, holgura_mm):
    """True si `o` no toca nada aunque se ensanche `holgura_mm` en cada dirección."""
    if not tap.dentro(o) or tap.solape(o):
        return False
    for ang in np.linspace(0, 2 * np.pi, 8, endpoint=False):
        p = Objeto(o.clase, o.x_mm + holgura_mm * np.cos(ang), o.y_mm + holgura_mm * np.sin(ang),
                   o.angulo, o.escala, o.semilla)
        if tap.solape(p):
            return False
    return True


def poner_suelto(tap, rng, clase, holgura_mm=4, intentos=300):
    for _ in range(intentos):
        o = _nuevo(rng, clase, rng.uniform(0, tap.w), rng.uniform(0, tap.h))
        if _separacion_libre(tap, o, holgura_mm):
            tap.poner(o)
            return o
    return None


def acercar_hasta_tocar(tap, o, destino, prob_apilado, rng, max_solape_otros=0):
    """Mueve `o` hacia `destino` (x, y) hasta tocar. Devuelve True si queda
    en contacto sin solaparse (o apilado levemente)."""
    dx, dy = destino[0] - o.x_mm, destino[1] - o.y_mm
    d = np.hypot(dx, dy)
    if d < 1e-6:
        return False
    ux, uy = dx / d, dy / d
    paso = CELDA_MM
    tocado = False
    for _ in range(int(d / paso)):
        o.x_mm += ux * paso
        o.y_mm += uy * paso
        if tap.solape(o) > 0:
            tocado = True
            break
    if not tocado:
        return False
    o.x_mm -= ux * paso                      # justo antes de tocar
    o.y_mm -= uy * paso
    if rng.random() < prob_apilado:          # leve montado (1-3 mm)
        extra = rng.uniform(1, 3)
        o.x_mm += ux * extra
        o.y_mm += uy * extra
    elif tap.solape(o) > max_solape_otros:
        return False
    return tap.dentro(o)


def poner_racimo(tap, rng, clases_racimo, id_racimo, modo="compacto", prob_apilado=0.1,
                 intentos=60, holgura_mm=4):
    """Racimo de len(clases_racimo) frutos en contacto. Devuelve la lista.

    El racimo se compone sobre su PROPIA rejilla (cada fruto se acerca hasta
    tocar a los del racimo) y cada pieza debe quedar separada `holgura_mm` de
    los objetos ya puestos en `tap`, para que los racimos no se mezclen.
    """
    for _ in range(intentos):
        propio = Tapete((tap.w, tap.h), tap.margen)
        semilla = None
        for _ in range(200):
            o = _nuevo(rng, clases_racimo[0], rng.uniform(0, tap.w), rng.uniform(0, tap.h),
                       id_racimo)
            if _separacion_libre(tap, o, 30):
                semilla = o
                break
        if semilla is None:
            continue
        propio.poner(semilla)
        miembros = [semilla]
        direccion = rng.uniform(0, 2 * np.pi)
        ok = True
        for clase in clases_racimo[1:]:
            colocado = False
            for _ in range(25):
                if modo == "linea":
                    ancla = miembros[-1]
                    ang = direccion + rng.normal(0, 0.25)
                    cx, cy = ancla.x_mm, ancla.y_mm
                else:                        # compacto: hacia el centro del racimo
                    ang = rng.uniform(0, 2 * np.pi)
                    cx = np.mean([m.x_mm for m in miembros])
                    cy = np.mean([m.y_mm for m in miembros])
                lejos = 40 + 12 * len(miembros)
                o = _nuevo(rng, clase, cx + lejos * np.cos(ang), cy + lejos * np.sin(ang), id_racimo)
                if (acercar_hasta_tocar(propio, o, (cx, cy), prob_apilado, rng)
                        and _separacion_libre(tap, o, holgura_mm)):
                    propio.poner(o)
                    miembros.append(o)
                    colocado = True
                    break
            if not colocado:
                ok = False
                break
        if ok:
            for m in miembros:
                tap.poner(m)
            return miembros
    return []


def escena_racimos(rng, tamanos, n_sueltos, clases=CLASES, mezclar=True, modo=None,
                   prob_apilado=0.1, tapete_mm=TAPETE_MM):
    """Escena con racimos de los tamaños dados + frutos sueltos.

    mezclar=False: cada racimo es de una sola clase (p. ej. 4 avellanas).
    """
    tap = Tapete(tapete_mm)
    objetos = []
    for i, n in enumerate(tamanos, start=1):
        if mezclar:
            cl = [clases[rng.integers(len(clases))] for _ in range(n)]
        else:
            cl = [clases[rng.integers(len(clases))]] * n
        m = modo or ("linea" if rng.random() < 0.3 else "compacto")
        objetos += poner_racimo(tap, rng, cl, i, m, prob_apilado)
    for _ in range(n_sueltos):
        o = poner_suelto(tap, rng, clases[rng.integers(len(clases))])
        if o is not None:
            objetos.append(o)
    return Escena(objetos, tapete_mm)
