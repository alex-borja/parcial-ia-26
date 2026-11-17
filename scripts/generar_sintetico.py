"""Genera un conjunto de prueba SINTÉTICO con iluminaciones variadas.

Estructura (una «sesión» = una luz fija + la misma cámara, como en el aula):
    data/sintetico/<sesion>/vacio.jpg                 tapete vacío para calibrar
    data/sintetico/<sesion>/desarrollo/<clase>/*.jpg  (solo sesiones de desarrollo)
    data/sintetico/<sesion>/desarrollo/contacto/*.jpg
    data/sintetico/<sesion>/test/*.jpg + etiquetas.json   (verdad exacta)

Las sesiones de DESARROLLO usan solo luces «normales»; las de TEST usan todas
(incluidas rasantes, foco y luz mixta que nunca se vieron al fijar umbrales),
para medir si el sistema generaliza a otras iluminaciones.

Uso:
    python scripts/generar_sintetico.py [--escenas-test 5] [--procesos 3]
AVISO: estos datos sirven para probar y comparar versiones del sistema; los
umbrales definitivos deben salir de fotos REALES.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from _comun import RAIZ, guardar_tapete

from simulador.render import (CLASES, TAPETE_MM, Escena, condiciones_luz, escena_aleatoria,
                              luz_variada, render)

SESIONES_DESARROLLO = ("cenital_difusa", "lateral_45", "calida_tenue")


def tarea(args):
    ruta, escena, luz, semilla, sem_cam = args
    img, verdad = render(escena, luz, semilla=semilla, semilla_camara=sem_cam)
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ruta), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return str(ruta), verdad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=str(RAIZ / "data" / "sintetico"))
    ap.add_argument("--escenas-test", type=int, default=5)
    ap.add_argument("--fotos-desarrollo", type=int, default=3, help="por clase y sesión")
    ap.add_argument("--procesos", type=int, default=3)
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--solo-test", action="store_true",
                    help="no generar fotos de desarrollo (conjunto de test final)")
    ap.add_argument("--tapete-mm", type=float, nargs=2, default=TAPETE_MM,
                    metavar=("ANCHO", "ALTO"), help="tapete simulado (mm)")
    args = ap.parse_args()
    tap = tuple(args.tapete_mm)

    rng = np.random.default_rng(args.semilla)
    base = Path(args.salida)
    tareas = []
    for i, (nombre, luz_base) in enumerate(condiciones_luz().items()):
        luz = luz_variada(luz_base, rng)            # luz fija durante la sesión
        sem_cam = int(rng.integers(1 << 30))        # cámara fija durante la sesión
        d = base / nombre
        nueva = lambda: int(rng.integers(1 << 30))
        guardar_tapete(d, tap)
        tareas.append((d / "vacio.jpg", Escena([], tap), luz, nueva(), sem_cam))
        if nombre in SESIONES_DESARROLLO and not args.solo_test:
            for c in CLASES:
                for k in range(args.fotos_desarrollo):
                    esc = escena_aleatoria(rng, int(rng.integers(7, 11)), clases=(c,), tapete_mm=tap)
                    tareas.append((d / "desarrollo" / c / f"{c}_{k}.jpg", esc, luz, nueva(), sem_cam))
            for k in range(2):
                esc = escena_aleatoria(rng, 10, prob_contacto=0.9, tapete_mm=tap)
                tareas.append((d / "desarrollo" / "contacto" / f"contacto_{k}.jpg", esc, luz,
                               nueva(), sem_cam))
        for k in range(args.escenas_test):
            esc = escena_aleatoria(rng, int(rng.integers(5, 14)), prob_contacto=0.25,
                                   tapete_mm=tap)
            tareas.append((d / "test" / f"escena_{k:02d}.jpg", esc, luz, nueva(), sem_cam))

    print(f"Generando {len(tareas)} imágenes con {args.procesos} procesos...")
    etiquetas = {}
    with ProcessPoolExecutor(args.procesos) as ex:
        for n, (ruta, verdad) in enumerate(ex.map(tarea, tareas), start=1):
            ruta = Path(ruta)
            if ruta.parent.name == "test":
                etiquetas.setdefault(ruta.parent, {})[ruta.name] = {
                    "objetos": verdad, "no_detectados": {}}
            if n % 10 == 0:
                print(f"  {n}/{len(tareas)}")
    for carpeta, et in etiquetas.items():
        (carpeta / "etiquetas.json").write_text(json.dumps(et, indent=1, ensure_ascii=False))
    print(f"Listo en {base}")


if __name__ == "__main__":
    main()
