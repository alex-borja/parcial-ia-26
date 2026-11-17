"""Robustez a la iluminación sobre las FOTOS REALES de desarrollo.

Cada foto de data/desarrollo/<clase>/ (una sola clase, frutos sueltos) se
vuelve a analizar tras simularle otra luz. La simulación se hace en RGB
LINEAL (como actúa la luz) y después se vuelve a codificar como lo haría la
cámara (gamma sRGB, recorte a 8 bits, ruido de sensor):
  - ganancia global: poca luz (con ruido) o exceso de luz (píxeles quemados);
  - solo flash: foco centrado que cae hacia los bordes del tapete;
  - dominante de color: luz cálida o fría sin balance de blancos.

Para cada condición se cuenta cuántos frutos salen con su clase. La verdad es
el nº de frutos de la foto SIN alterar (todos de la clase de la carpeta).

Uso:
    python scripts/evaluar_luz.py [--vacio "data/calibracion/vacio(1).jpeg"]
        [--solo solo_flash,x3.0] [--detalle] [--guardar salidas/luz]
NO sustituye a probar con la cámara real: el móvil aplica además su propio
procesado (HDR, balance de blancos) que aquí no se simula.
"""
import argparse
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from _comun import RAIZ, imagenes_en, leer, obtener_calibracion

from src.config import cargar_config
from src.pipeline import analizar
from src.preprocesado import redimensionar
from src.segmentacion import linealizar


def codificar(lin):
    """RGB lineal (0-1, se recorta) -> BGR uint8 con gamma sRGB."""
    lin = np.clip(lin, 0, 1)
    s = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return (s[..., ::-1] * 255 + 0.5).astype(np.uint8)


def foco(forma, centro=1.6, borde=0.35, cx=0.5, cy=0.5):
    """Mapa de iluminación de un flash: `centro`× en (cx, cy), `borde`× en la
    esquina más lejana (caída suave tipo cos⁴)."""
    h, w = forma[:2]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    r2 = ((x - cx * w) ** 2 + (y - cy * h) ** 2)
    r2 /= r2.max()
    k = (centro / borde) ** 0.5 - 1
    return (centro / (1 + k * r2) ** 2)[..., None]


def simular(img, ganancia=1.0, mapa=None, tinte=(1, 1, 1), ruido=0.0, semilla=0):
    """Otra luz sobre `img` (BGR): ganancia · mapa · tinte en lineal + ruido."""
    lin = linealizar(img) * ganancia * np.asarray(tinte, np.float32)
    if mapa is not None:
        lin = lin * mapa
    if ruido:
        rng = np.random.default_rng(semilla)
        # Ruido de disparo (∝ √señal) + de lectura, en unidades lineales.
        lin = lin + rng.normal(0, 1, lin.shape).astype(np.float32) * (
            ruido * np.sqrt(np.clip(lin, 0, 1)) + ruido * 0.2)
    return codificar(lin)


# nombre -> parámetros de `simular` («foco»: parámetros de `foco`).
CONDICIONES = {
    "original": {},
    "x0.10 (casi a oscuras)": dict(ganancia=0.10, ruido=0.02),
    "x0.25 (poca luz)": dict(ganancia=0.25, ruido=0.02),
    "x0.50": dict(ganancia=0.50, ruido=0.01),
    "x1.5": dict(ganancia=1.5),
    "x2.0 (exceso)": dict(ganancia=2.0),
    "x3.0 (muy quemada)": dict(ganancia=3.0),
    "solo flash": dict(foco=dict(centro=1.6, borde=0.35), ruido=0.01),
    "solo flash fuerte": dict(foco=dict(centro=2.5, borde=0.30), ruido=0.01),
    "solo flash descentrado": dict(foco=dict(centro=1.8, borde=0.25, cx=0.3, cy=0.35), ruido=0.01),
    "flash débil a oscuras": dict(foco=dict(centro=0.5, borde=0.08), ruido=0.02),
    "luz cálida": dict(tinte=(1.25, 1.0, 0.70)),
    "luz fría": dict(tinte=(0.80, 1.0, 1.25)),
    "cálida + exceso": dict(ganancia=1.8, tinte=(1.25, 1.0, 0.70)),
}


def aplicar(img, p):
    p = dict(p)
    f = p.pop("foco", None)
    if not p and f is None:
        return img
    return simular(img, mapa=foco(img.shape, **f) if f else None, **p)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vacio", default=str(RAIZ / "data" / "calibracion" / "vacio(1).jpeg"))
    ap.add_argument("--desarrollo", default=str(RAIZ / "data" / "desarrollo"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--solo", default=None, help="condiciones (subcadenas) separadas por comas")
    ap.add_argument("--detalle", action="store_true", help="motivo de cada fallo")
    ap.add_argument("--guardar", default=None, help="carpeta donde guardar las fotos simuladas")
    args = ap.parse_args()
    cfg = cargar_config(args.config)
    cal = obtener_calibracion(cfg, args.vacio)
    conds = {n: p for n, p in CONDICIONES.items()
             if not args.solo or n == "original" or any(s in n for s in args.solo.split(","))}

    fotos = []
    for clase in cfg["clases"]:
        carpeta = Path(args.desarrollo) / clase
        if carpeta.is_dir():
            for ruta in imagenes_en(carpeta):
                img, _ = redimensionar(leer(ruta), cfg["preprocesado"]["lado_max_px"])
                fotos.append((clase, ruta, img))

    verdad, total = {}, 0
    print(f"{'condición':28s} {'aciertos':>10s}  fallos (clase real: lo que salió)")
    for nombre, p in conds.items():
        ok, fallos, motivos = 0, Counter(), []
        for clase, ruta, img in fotos:
            sim = aplicar(img, p)
            if args.guardar:
                d = Path(args.guardar) / nombre.split(" (")[0].replace(" ", "_")
                d.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(d / f"{clase}_{ruta.stem}.jpg"), sim)
            res = analizar(sim, cal, cfg)
            salida = Counter(a.clase for a in res.objetos)
            if nombre == "original":
                verdad[ruta] = len(res.objetos)
                total += len(res.objetos)
            n = verdad[ruta]
            ok += min(salida[clase], n)
            for c, k in salida.items():
                if c != clase:
                    fallos[f"{clase}: {c}"] += k
            if len(res.objetos) != n:
                fallos[f"{clase}: nº {len(res.objetos) - n:+d}"] += 1
            motivos += [f"    {ruta.name} #{a.objeto.id}: {a.decision.texto_traza()}"
                        for a in res.objetos if a.clase != clase]
        txt = ", ".join(f"{k} ×{v}" for k, v in sorted(fallos.items()))
        print(f"{nombre:28s} {ok:4d}/{total:<4d}  {txt}", flush=True)
        if args.detalle:
            print("\n".join(motivos))


if __name__ == "__main__":
    main()
