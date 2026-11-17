"""Generador de escenas SINTÉTICAS para probar el código.

AVISO: estas imágenes solo sirven para comprobar que el código hace lo que
debe (que el watershed separa, que las fórmulas dan lo esperado, que la
cadena no se rompe). NO justifican ningún umbral de config.yaml: los
umbrales salen de fotos reales de data/desarrollo/.

Las formas imitan las dimensiones típicas (en mm) de cada clase y todo se
dibuja a una escala conocida (mm/px) para poder comprobar las medidas.
"""
import cv2
import numpy as np

VERDE_BGR = (55, 125, 45)
MESA_BGR = (90, 110, 140)

# Color base BGR de cada clase (aprox. al real).
COLOR = {
    "nuez": (85, 135, 180),
    "avellana": (35, 70, 125),
    "almendra": (50, 90, 145),
    "anacardo": (165, 205, 228),
    "cacahuete": (120, 168, 205),
}


def _forma(clase, cx, cy, ang, s):
    """Máscara (lista de primitivas) de una clase centrada en (cx, cy) px.

    s = px por mm. Devuelve una función que dibuja la forma con un color.
    """
    def pt(dx_mm, dy_mm):
        a = np.radians(ang)
        x = dx_mm * np.cos(a) - dy_mm * np.sin(a)
        y = dx_mm * np.sin(a) + dy_mm * np.cos(a)
        return int(round(cx + x * s)), int(round(cy + y * s))

    def dibujar(img, color):
        if clase == "nuez":
            cv2.ellipse(img, (int(cx), int(cy)), (int(17 * s), int(15 * s)), ang, 0, 360, color, -1, cv2.LINE_AA)
        elif clase == "avellana":
            cv2.ellipse(img, (int(cx), int(cy)), (int(8.5 * s), int(7.5 * s)), ang, 0, 360, color, -1, cv2.LINE_AA)
        elif clase == "almendra":
            cv2.ellipse(img, (int(cx), int(cy)), (int(12 * s), int(7 * s)), ang, 0, 360, color, -1, cv2.LINE_AA)
        elif clase == "anacardo":
            # Arco grueso (media luna) de radio 9 mm y grosor 7 mm.
            r = 9
            pts = [pt(r * np.sin(t), -r * np.cos(t) + r / 2)
                   for t in np.radians(np.linspace(-60, 60, 40))]
            cv2.polylines(img, [np.array(pts, np.int32)], False, color, int(7 * s), cv2.LINE_AA)
        elif clase == "cacahuete":
            # Dos lóbulos de r = 7,5 mm con centros a 11 mm: cintura marcada.
            for d in (-5.5, 5.5):
                cv2.circle(img, pt(d, 0), int(7.5 * s), color, -1, cv2.LINE_AA)
        else:
            raise ValueError(clase)
    return dibujar


def escena(objetos=(), mm_por_px=0.4, tapete_mm=500, margen_px=40,
           luz=1.0, gradiente=0.2, ruido=5, sombra=True, semilla=0):
    """Tapete verde sobre una mesa con frutos secos.

    objetos: iterable de (clase, x_mm, y_mm, angulo_grados), coordenadas en
    mm desde la esquina superior izquierda del tapete.
    """
    rng = np.random.default_rng(semilla)
    s = 1 / mm_por_px
    lado = int(round(tapete_mm * s))
    tam = lado + 2 * margen_px
    img = np.full((tam, tam, 3), MESA_BGR, dtype=np.float64)
    img[margen_px:margen_px + lado, margen_px:margen_px + lado] = VERDE_BGR

    # Sombras primero (verde más oscuro, desplazado), luego los objetos.
    formas = []
    for clase, x, y, ang in objetos:
        cx, cy = margen_px + x * s, margen_px + y * s
        formas.append((clase, _forma(clase, cx, cy, ang, s)))
        if sombra:
            _forma(clase, cx + 2.5 * s, cy + 2.5 * s, ang, s)(
                img, tuple(0.55 * c for c in VERDE_BGR))
    for clase, dibujar in formas:
        capa = np.zeros(img.shape[:2], np.uint8)
        dibujar(capa, 255)
        sel = capa > 0
        base = np.array(COLOR[clase], dtype=np.float64)
        # Textura: rugosa en la nuez y el cacahuete, casi lisa en el resto.
        amp = 28 if clase in ("nuez", "cacahuete") else 6
        tex = cv2.GaussianBlur(rng.normal(0, amp, img.shape[:2]), (0, 0), 1.5)
        img[sel] = base + tex[sel, None]

    perfil = 1.0 - gradiente * np.linspace(0, 1, tam)
    img *= luz * perfil[None, :, None]
    img += rng.normal(0, ruido, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def tapete_vacio(**kw):
    return escena(objetos=(), **kw)


ESCENA_EJEMPLO = [
    ("nuez", 100, 100, 0), ("nuez", 380, 400, 40),
    ("avellana", 250, 90, 0), ("avellana", 160, 300, 0), ("avellana", 420, 150, 0),
    ("almendra", 300, 250, 30), ("almendra", 90, 420, 100),
    ("anacardo", 200, 200, 15), ("anacardo", 440, 280, 200),
    ("cacahuete", 300, 420, 60), ("cacahuete", 120, 230, 135),
]


if __name__ == "__main__":
    from pathlib import Path
    out = Path(__file__).resolve().parent.parent / "salidas" / "sinteticas"
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "vacio.png"), tapete_vacio())
    cv2.imwrite(str(out / "escena.png"), escena(ESCENA_EJEMPLO))
    # Frutos en contacto.
    cv2.imwrite(str(out / "contacto.png"), escena([
        ("avellana", 200, 200, 0), ("avellana", 216, 200, 0),
        ("nuez", 300, 300, 0), ("almendra", 300, 330, 0)]))
    print(f"Ejemplos sintéticos en {out}")
