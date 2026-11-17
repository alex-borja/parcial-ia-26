"""Banco de pruebas de ESTRÉS: racimos, distancias de cámara y luces extremas.

Cada sesión = una luz + una cámara fijas, con su tapete vacío:
    data/estres/<sesion>/vacio.jpg
    data/estres/<sesion>/test/*.jpg + etiquetas.json + meta.json
`meta.json` guarda, por foto, la luz, la cámara, los mm/px y, por cada fruto
de la verdad, su racimo y el tamaño del racimo (1 = suelto), para desglosar.

Escenas: racimos mezclados, racimos de una sola clase, muchos racimos
pequeños, y escenas solo de frutos sueltos (para vigilar regresiones).
Contacto físico real entre frutos (simulador/escenas.py), ±12 % de tamaño.

Uso:
    python scripts/generar_estres.py [--salida data/estres] [--semilla 11] [--escenas 9]
Para un test RESERVADO usa otra semilla y otra carpeta, y no lo mires al ajustar.
"""
import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from _comun import RAIZ, guardar_tapete

from simulador.escenas import escena_racimos
from simulador.render import TAPETE_MM, Escena, camaras, condiciones_estres, luz_variada, render


def receta(rng):
    """(tamaños de racimo, nº sueltos, mezclar) de una escena aleatoria."""
    t = rng.random()
    if t < 0.5:
        return list(rng.integers(2, 7, rng.integers(1, 4))), int(rng.integers(2, 7)), True
    if t < 0.7:
        return list(rng.integers(3, 7, rng.integers(1, 3))), int(rng.integers(0, 4)), False
    if t < 0.85:
        return list(rng.integers(2, 4, 4)), int(rng.integers(0, 3)), True
    return [], int(rng.integers(6, 13)), True


SESIONES_DESARROLLO = [("cenital_difusa", "cerca"), ("lateral_45", "media"),
                       ("calida_tenue", "lejos"), ("cenital_difusa", "webcam"),
                       ("lateral_45", "webcam_baja"), ("fria_fluorescente", "media")]


def generar_desarrollo(args):
    """<salida>/<sesion>/vacio.jpg + desarrollo/<clase>/*.jpg + desarrollo/contacto/."""
    from simulador.render import CLASES
    rng = np.random.default_rng(args.semilla)
    luces, cams = condiciones_estres(), camaras()
    tareas = []
    for luz_n, cam_n in SESIONES_DESARROLLO:
        luz, cam = luz_variada(luces[luz_n], rng), cams[cam_n]
        sem_cam = int(rng.integers(1 << 30))
        d = Path(args.salida) / f"{luz_n}__{cam_n}"
        guardar_tapete(d, args.tapete_mm)
        tareas.append((d / "vacio.jpg", Escena([], args.tapete_mm), luz, cam,
                       int(rng.integers(1 << 30)), sem_cam))
        for c in CLASES:
            for k in range(2):
                esc = escena_racimos(rng, [], int(rng.integers(8, 12)), clases=(c,),
                                     tapete_mm=args.tapete_mm)
                tareas.append((d / "desarrollo" / c / f"{c}_{k}.jpg", esc, luz, cam,
                               int(rng.integers(1 << 30)), sem_cam))
        esc = escena_racimos(rng, [2, 2, 3, 2], 0, tapete_mm=args.tapete_mm)
        tareas.append((d / "desarrollo" / "contacto" / "contacto_0.jpg", esc, luz, cam,
                       int(rng.integers(1 << 30)), sem_cam))
    print(f"Generando {len(tareas)} imágenes de desarrollo...")
    with ProcessPoolExecutor(args.procesos) as ex:
        list(ex.map(tarea, tareas))
    print(f"Listo en {args.salida}")


def tarea(args):
    ruta, escena, luz, cam, semilla, sem_cam = args
    img, verdad = render(escena, luz, cam, semilla=semilla, semilla_camara=sem_cam)
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ruta), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return str(ruta), verdad


def plan_estres(base, semilla, n_escenas, tapete_mm=TAPETE_MM):
    """Tareas de render (ruta, escena, luz, cámara, semilla, semilla_cámara) y
    metadatos del banco. Determinista: misma semilla (y mismo tapete) = mismas
    escenas, lo que permite volver a renderizarlas con el mapa de identidad
    para diagnóstico."""
    rng = np.random.default_rng(semilla)
    luces, cams = condiciones_estres(), camaras()
    nombres_cam = list(cams)
    sesiones = [(l, nombres_cam[i % len(nombres_cam)]) for i, l in enumerate(luces)]
    sesiones += [("cenital_difusa", c) for c in nombres_cam if ("cenital_difusa", c) not in sesiones]
    tareas, metas = [], {}
    for luz_n, cam_n in sesiones:
        luz = luz_variada(luces[luz_n], rng)
        cam = cams[cam_n]
        sem_cam = int(rng.integers(1 << 30))
        d = base / f"{luz_n}__{cam_n}"
        tareas.append((d / "vacio.jpg", Escena([], tapete_mm), luz, cam,
                       int(rng.integers(1 << 30)), sem_cam))
        for k in range(n_escenas):
            tam, sueltos, mezclar = receta(rng)
            esc = escena_racimos(rng, tam, sueltos, mezclar=mezclar, tapete_mm=tapete_mm)
            ruta = d / "test" / f"escena_{k:02d}.jpg"
            tam_racimo = Counter(o.racimo for o in esc.objetos if o.racimo)
            metas[str(ruta)] = {"luz": luz_n, "camara": cam_n, "mm_por_px": cam.mm_por_px,
                                "objetos": [{"clase": o.clase, "racimo": o.racimo,
                                             "tam_racimo": tam_racimo[o.racimo] if o.racimo else 1}
                                            for o in esc.objetos]}
            tareas.append((ruta, esc, luz, cam, int(rng.integers(1 << 30)), sem_cam))
    return tareas, metas, sesiones


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=str(RAIZ / "data" / "estres"))
    ap.add_argument("--semilla", type=int, default=11)
    ap.add_argument("--escenas", type=int, default=9, help="por sesión")
    ap.add_argument("--procesos", type=int, default=2)
    ap.add_argument("--desarrollo", action="store_true",
                    help="generar fotos de DESARROLLO (una clase por foto, frutos sueltos) "
                         "con varias cámaras y luces normales, para medir umbrales")
    ap.add_argument("--tapete-mm", type=float, nargs=2, default=TAPETE_MM,
                    metavar=("ANCHO", "ALTO"), help="tapete simulado (mm)")
    args = ap.parse_args()
    args.tapete_mm = tuple(args.tapete_mm)
    if args.desarrollo:
        return generar_desarrollo(args)

    tareas, metas, sesiones = plan_estres(Path(args.salida), args.semilla, args.escenas,
                                          args.tapete_mm)
    for d in {t[0].parent for t in tareas if t[0].name == "vacio.jpg"}:
        guardar_tapete(d, args.tapete_mm)
    print(f"Generando {len(tareas)} imágenes ({len(sesiones)} sesiones) con {args.procesos} procesos...")
    etiquetas, meta_dir = {}, {}
    with ProcessPoolExecutor(args.procesos) as ex:
        for n, (ruta, verdad) in enumerate(ex.map(tarea, tareas), start=1):
            ruta = Path(ruta)
            if ruta.parent.name == "test":
                etiquetas.setdefault(ruta.parent, {})[ruta.name] = {"objetos": verdad,
                                                                    "no_detectados": {}}
                m = metas[str(ruta)]
                # Meta alineada con la verdad (los frutos tapados del todo no están).
                meta_dir.setdefault(ruta.parent, {})[ruta.name] = {
                    **{k: v for k, v in m.items() if k != "objetos"},
                    "objetos": [m["objetos"][v["indice"]] for v in verdad]}
            if n % 20 == 0:
                print(f"  {n}/{len(tareas)}")
    for carpeta, et in etiquetas.items():
        (carpeta / "etiquetas.json").write_text(json.dumps(et, indent=1, ensure_ascii=False))
        (carpeta / "meta.json").write_text(json.dumps(meta_dir[carpeta], indent=1, ensure_ascii=False))
    print(f"Listo en {args.salida}")


if __name__ == "__main__":
    main()
