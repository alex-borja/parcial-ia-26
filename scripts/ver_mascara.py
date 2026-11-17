"""Muestra la segmentación y la detección de una o varias fotos (diagnóstico).

Uso:
    python scripts/ver_mascara.py data/desarrollo/nuez/*.jpg [--vacio vacio.jpg] [--mostrar]

Guarda un mosaico (preprocesada | máscara verde | ROI | objetos) por foto en
salidas/mascaras/.
"""
import argparse
from pathlib import Path

import cv2
from _comun import RAIZ, leer, obtener_calibracion

from src.config import cargar_config
from src.pipeline import analizar
from src.visualizacion import panel_segmentacion


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fotos", nargs="+")
    ap.add_argument("--vacio")
    ap.add_argument("--config", default=None)
    ap.add_argument("--salida", default=str(RAIZ / "salidas" / "mascaras"))
    ap.add_argument("--mostrar", action="store_true")
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    cal = obtener_calibracion(cfg, args.vacio)
    dir_salida = Path(args.salida)
    dir_salida.mkdir(parents=True, exist_ok=True)
    for ruta in args.fotos:
        res = analizar(leer(ruta), cal, cfg, clasificar_objetos=False)
        areas = sorted(round(a.caracteristicas["area_mm2"]) for a in res.objetos)
        print(f"{ruta}: {len(res.objetos)} objetos, áreas mm²={areas} "
              f"({res.tiempos_ms['total']:.0f} ms)")
        for a in res.avisos:
            print(f"  AVISO: {a}")
        panel = panel_segmentacion(res.segmentacion)
        cv2.imwrite(str(dir_salida / f"{Path(ruta).stem}_mascara.png"), panel)
        if args.mostrar:
            cv2.imshow(Path(ruta).name, cv2.resize(panel, None, fx=0.5, fy=0.5))
            cv2.waitKey(0)
            cv2.destroyAllWindows()
    print(f"Mosaicos en {dir_salida}")


if __name__ == "__main__":
    main()
