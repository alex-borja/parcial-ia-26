"""Evalúa el sistema en varias sesiones de iluminación y resume por sesión.

Cada sesión es una carpeta con vacio.jpg (o .png) y test/ (+ test/etiquetas.json),
como las de scripts/generar_sintetico.py. Dos protocolos:
  - por_sesion:        se calibra con el vacío de la propia sesión (lo
                       normal: se calibra al empezar, con la luz del aula).
  - calibracion_unica: se calibra UNA vez con el vacío de --referencia y la
                       luz cambia después (prueba de robustez a la luz).

Uso:
    python scripts/evaluar_sesiones.py data/sintetico/* --referencia data/sintetico/cenital_difusa \\
        [--nombre v1] [--salida salidas/sesiones]
"""
import argparse
import json
from pathlib import Path

from _comun import RAIZ, obtener_calibracion, ruta_vacio

from src.config import cargar_config
from src.evaluacion import cargar_etiquetas, evaluar_carpeta


def pct(x):
    return f"{100 * x:5.1f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sesiones", nargs="+")
    ap.add_argument("--referencia", help="sesión cuyo vacío se usa en calibracion_unica")
    ap.add_argument("--config", default=None)
    ap.add_argument("--nombre", default="actual", help="nombre de la versión evaluada")
    ap.add_argument("--salida", default=str(RAIZ / "salidas" / "sesiones"))
    ap.add_argument("--imagenes", action="store_true", help="guardar imágenes anotadas")
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    dir_out = Path(args.salida) / args.nombre
    dir_out.mkdir(parents=True, exist_ok=True)
    protocolos = {"por_sesion": None}
    if args.referencia:
        protocolos["calibracion_unica"] = obtener_calibracion(
            cfg, ruta_vacio(args.referencia))

    tabla, detalle = [], {}
    for ses in sorted(map(Path, args.sesiones)):
        et = cargar_etiquetas(ses / "test" / "etiquetas.json")
        if not et:
            continue
        for prot, cal_ref in protocolos.items():
            cal = cal_ref or obtener_calibracion(cfg, ruta_vacio(ses))
            dir_img = None
            if args.imagenes:
                dir_img = dir_out / prot / ses.name
                dir_img.mkdir(parents=True, exist_ok=True)
            m, filas, _ = evaluar_carpeta(ses / "test", et, cal, cfg, dir_img)
            fila = {"sesion": ses.name, "protocolo": prot,
                    "det_P": m["deteccion"]["precision"], "det_R": m["deteccion"]["recall"],
                    "clasif": m["clasificacion"]["exactitud"],
                    "extremo": m["extremo_a_extremo"],
                    "inventario": m["escenas_inventario_exacto"],
                    "n": m["deteccion"]["tp"] + m["deteccion"]["fn"]}
            tabla.append(fila)
            detalle[f"{ses.name}/{prot}"] = {"metricas": m, "imagenes": filas}
            confus = [f["confusiones"] for f in filas if f["confusiones"]]
            print(f"{ses.name:<18} {prot:<17} detP={pct(fila['det_P'])} detR={pct(fila['det_R'])} "
                  f"clasif={pct(fila['clasif'])} inv={pct(fila['inventario'])}"
                  + (f"  [{'; '.join(confus)}]" if confus else ""))

    lineas = [f"# Evaluación por sesión de iluminación — versión `{args.nombre}`\n",
              "| sesión | protocolo | n | det. precisión | det. exhaust. | clasificación | "
              "detectado y bien clasificado | escenas con inventario exacto |",
              "|---|---|---|---|---|---|---|---|"]
    for f in tabla:
        lineas.append(f"| {f['sesion']} | {f['protocolo']} | {f['n']} | {pct(f['det_P'])} % | "
                      f"{pct(f['det_R'])} % | {pct(f['clasif'])} % | {pct(f['extremo'])} % | "
                      f"{pct(f['inventario'])} % |")
    for prot in protocolos:
        filas = [f for f in tabla if f["protocolo"] == prot]
        if filas:
            n = sum(f["n"] for f in filas)
            media = lambda k: sum(f[k] * f["n"] for f in filas) / n
            lineas.append(f"| **TOTAL** | {prot} | {n} | {pct(media('det_P'))} % | "
                          f"{pct(media('det_R'))} % | {pct(media('clasif'))} % | "
                          f"{pct(media('extremo'))} % | {pct(media('inventario'))} % |")
    (dir_out / "resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    (dir_out / "detalle.json").write_text(json.dumps(detalle, indent=1, ensure_ascii=False,
                                                     default=str))
    print(f"\nResumen en {dir_out / 'resumen.md'}")


if __name__ == "__main__":
    main()
