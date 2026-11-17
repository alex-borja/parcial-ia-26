"""Evalúa el banco de estrés con desglose por racimo, cámara, luz y clase.

Uso:
    python scripts/evaluar_estres.py [data/estres] [--config X.yaml] [--nombre v1] [--procesos 2]

Cada sesión se calibra con su propio vacío. Métricas:
  - bien = fruto real detectado Y bien clasificado (por categoría);
  - inventario exacto = escena con conteo por clase perfecto;
  - falsos = detecciones que no corresponden a ningún fruto.
Salida: salidas/estres/<nombre>/resumen.md y detalle.json.
"""
import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
from _comun import RAIZ, calibrar_sesion, ruta_vacio

from src.config import cargar_config
from src.evaluacion import cargar_etiquetas, emparejar
from src.pipeline import analizar


def evaluar_sesion(args):
    ses, ruta_cfg = args
    cfg = cargar_config(ruta_cfg)
    ses = Path(ses)
    cal = calibrar_sesion(ruta_vacio(ses), cfg)
    et = cargar_etiquetas(ses / "test" / "etiquetas.json")
    meta = json.loads((ses / "test" / "meta.json").read_text())
    filas = []
    for nombre, e in sorted(et.items()):
        img = cv2.imread(str(ses / "test" / nombre))
        t0 = time.perf_counter()
        res = analizar(img, cal, cfg)
        ms = (time.perf_counter() - t0) * 1000
        r = emparejar(res, e, cfg)
        m = meta[nombre]
        exacta = all(r["reales"].get(c, 0) == r["predichos"].get(c, 0)
                     for c in set(r["reales"]) | set(r["predichos"]))
        filas.append({"sesion": ses.name, "imagen": nombre, "luz": m["luz"], "camara": m["camara"],
                      "ms": ms, "exacta": exacta, "falsos": len(r["falsos"]),
                      "objetos": [{"clase": g["clase"], "tam": mo["tam_racimo"],
                                   "pred": p} for g, mo, p in zip(e["objetos"], m["objetos"],
                                                                 r["por_objeto"])]})
    return filas


def pct(a, b):
    return f"{100 * a / b:5.1f} %" if b else "  —  "


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", nargs="?", default=str(RAIZ / "data" / "estres"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--nombre", default="actual")
    ap.add_argument("--procesos", type=int, default=2)
    ap.add_argument("--filtro", nargs="*", default=None,
                    help="evaluar solo las sesiones cuyo nombre contenga alguno de estos textos")
    args = ap.parse_args()

    sesiones = sorted(p for p in Path(args.carpeta).iterdir() if (p / "test" / "meta.json").exists())
    if args.filtro:
        sesiones = [p for p in sesiones if any(f in p.name for f in args.filtro)]
    with ProcessPoolExecutor(args.procesos) as ex:
        filas = [f for fs in ex.map(evaluar_sesion, [(str(s), args.config) for s in sesiones])
                 for f in fs]

    def agrega(clave_obj=None, clave_escena=None):
        tabla = defaultdict(lambda: [0, 0, 0, 0, 0])   # bien, total, escenas exactas, escenas, falsos
        for f in filas:
            if clave_escena:
                k = clave_escena(f)
                tabla[k][2] += f["exacta"]
                tabla[k][3] += 1
                tabla[k][4] += f["falsos"]
            for o in f["objetos"]:
                k = clave_obj(o, f) if clave_obj else clave_escena(f)
                tabla[k][0] += o["pred"] == o["clase"]
                tabla[k][1] += 1
        return tabla

    tot_bien = sum(o["pred"] == o["clase"] for f in filas for o in f["objetos"])
    tot = sum(len(f["objetos"]) for f in filas)
    perdidos = sum(o["pred"] is None for f in filas for o in f["objetos"])
    desconocidos = sum(o["pred"] == "desconocido" for f in filas for o in f["objetos"])
    falsos = sum(f["falsos"] for f in filas)
    exactas = sum(f["exacta"] for f in filas)
    ms = sorted(f["ms"] for f in filas)
    l = [f"# Banco de estrés — versión `{args.nombre}`\n",
         f"{len(filas)} escenas, {tot} frutos, {len(sesiones)} sesiones.\n",
         "| métrica | valor |", "|---|---|",
         f"| detectado y bien clasificado | **{pct(tot_bien, tot)}** ({tot_bien}/{tot}) |",
         f"| escenas con inventario exacto | **{pct(exactas, len(filas))}** |",
         f"| no detectados (fusionados/perdidos) | {perdidos} |",
         f"| detectados como «desconocido» | {desconocidos} |",
         f"| falsos positivos | {falsos} |",
         f"| tiempo por imagen (mediana / máx) | {ms[len(ms) // 2]:.0f} / {ms[-1]:.0f} ms |\n"]
    secciones = [
        ("Por tamaño de racimo (1 = suelto)", lambda o, f: o["tam"], None),
        ("Por clase", lambda o, f: o["clase"], None),
        ("Por cámara (distancia / resolución)", None, lambda f: f["camara"]),
        ("Por luz", None, lambda f: f["luz"]),
    ]
    for titulo, co, ce in secciones:
        t = agrega(co, ce)
        l += [f"## {titulo}\n", "| categoría | bien | n | inventario exacto | falsos |",
              "|---|---|---|---|---|"]
        for k in sorted(t, key=lambda x: (str(type(x)), x)):
            b, n, e, ne, fp = t[k]
            l.append(f"| {k} | {pct(b, n)} | {n} | {pct(e, ne) if ne else '—'} | "
                     f"{fp if ne else '—'} |")
        l.append("")
    conf = defaultdict(int)
    for f in filas:
        for o in f["objetos"]:
            if o["pred"] != o["clase"]:
                conf[f"{o['clase']} -> {o['pred'] or 'no detectado'}"] += 1
    l += ["## Errores más frecuentes\n"] + [f"- {k}: {v}" for k, v in
                                            sorted(conf.items(), key=lambda x: -x[1])[:15]]
    dir_out = RAIZ / "salidas" / "estres" / args.nombre
    dir_out.mkdir(parents=True, exist_ok=True)
    (dir_out / "resumen.md").write_text("\n".join(l) + "\n", encoding="utf-8")
    (dir_out / "detalle.json").write_text(json.dumps(filas, ensure_ascii=False))
    print("\n".join(l))


if __name__ == "__main__":
    main()
