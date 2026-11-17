"""Calibra la sesión con una foto del tapete VACÍO: rango HSV del verde y
escala mm/px. Hazlo al empezar cada sesión (y en el aula, con su luz).

Uso:
    python scripts/calibrar.py data/calibracion/vacio.jpg
    python scripts/calibrar.py vacio.jpg --mm-por-px 0.31     # escala medida a mano

Imprime el campo de visión y la resolución espacial resultante, que es la
justificación experimental del montaje (requisito del enunciado).
"""
import argparse
import copy

from _comun import RAIZ, leer

from src.calibracion import calibrar, cubre_tapete, guardar_calibracion
from src.config import cargar_config


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("foto", help="foto del tapete vacío")
    ap.add_argument("--config", default=None)
    ap.add_argument("--mm-por-px", type=float, default=None,
                    help="escala fija (mm por px de la foto ORIGINAL)")
    ap.add_argument("--salida", default=None)
    args = ap.parse_args()

    cfg = copy.deepcopy(cargar_config(args.config))
    if args.mm_por_px:
        cfg["escala"].update({"modo": "fijo", "mm_por_px_original": args.mm_por_px})
    img = leer(args.foto)
    cal = calibrar(img, cfg)

    print(f"Verde HSV: media={cal['media']} desv={cal['desv']}")
    print(f"  rango bajo={cal['bajo']} alto={cal['alto']}")
    mm = cal["mm_por_px_original"]
    print(f"Escala: {mm:.4f} mm/px (foto original {cal['tam_original'][0]}×{cal['tam_original'][1]} px)")
    campo, tap = cal["campo_vision_mm"], cal["tapete_mm"]
    print(f"Campo de visión: {campo[0]:.0f} × {campo[1]:.0f} mm, tapete {tap[0]:.0f} × {tap[1]:.0f} mm"
          + ("  (OK, el tapete entra entero)"
             if cubre_tapete(campo, tap) and not any("borde" in a for a in cal["avisos"])
             else "  (el tapete NO entra entero: ver avisos)"))
    print(f"  el tapete ocupa el {100 * tap[0] * tap[1] / (campo[0] * campo[1]):.0f} % de la foto "
          "(cuanto más, mejor resolución; deja un margen de mesa alrededor)")
    lado = max(cal["tam_original"])
    escala_trabajo = min(1.0, cfg["preprocesado"]["lado_max_px"] / lado)
    mm_trabajo = mm / escala_trabajo
    print(f"Resolución de trabajo: {mm_trabajo:.3f} mm/px")
    for nombre, tam_mm in (("avellana (objeto más pequeño, ~15 mm)", 15),
                           ("detalle mínimo de forma, ~2 mm", 2)):
        print(f"  {nombre}: {tam_mm / mm_trabajo:.0f} px")
    for a in cal["avisos"]:
        print(f"AVISO: {a}")

    salida = args.salida or RAIZ / cfg["calibracion"]["archivo_salida"]
    guardar_calibracion(cal, salida)
    print(f"Calibración guardada en {salida}")


if __name__ == "__main__":
    main()
