"""Evaluación cuantitativa sobre escenas etiquetadas (entregables 8 y 9).

Uso:
    python scripts/evaluar.py [data/test] [--vacio vacio.jpg]

Requiere data/test/etiquetas.json (scripts/etiquetar.py). Escribe en
salidas/evaluacion/: informe.md, matriz_confusion.png, resultados.csv y la
imagen anotada de cada escena.
"""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from _comun import RAIZ, leer, obtener_calibracion  # noqa: E402

from src.config import cargar_config  # noqa: E402
from src.evaluacion import cargar_etiquetas, evaluar_carpeta  # noqa: E402


def pct(x):
    return "—" if x is None else f"{100 * x:.1f} %"


def dibujar_matriz(m, ruta):
    cm = np.array(m["matriz_confusion"])
    et = m["etiquetas_matriz"]
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(et)), et, rotation=45, ha="right")
    ax.set_yticks(range(len(et)), et)
    ax.set_xlabel("predicha")
    ax.set_ylabel("real")
    for i in range(len(et)):
        for j in range(len(et)):
            if cm[i, j]:
                ax.text(j, i, cm[i, j], ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_title("Matriz de confusión (objetos emparejados)")
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", nargs="?", default=str(RAIZ / "data" / "test"))
    ap.add_argument("--vacio")
    ap.add_argument("--config", default=None)
    ap.add_argument("--salida", default=str(RAIZ / "salidas" / "evaluacion"))
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    cal = obtener_calibracion(cfg, args.vacio)
    carpeta = Path(args.carpeta)
    etiquetas = cargar_etiquetas(carpeta / "etiquetas.json")
    if not etiquetas:
        raise SystemExit(f"No hay etiquetas en {carpeta / 'etiquetas.json'}: "
                         "ejecuta scripts/etiquetar.py")
    dir_out = Path(args.salida)
    dir_out.mkdir(parents=True, exist_ok=True)

    m, filas, tiempos = evaluar_carpeta(carpeta, etiquetas, cal, cfg, dir_out, verbose=True)
    with open(dir_out / "resultados.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    dibujar_matriz(m, dir_out / "matriz_confusion.png")

    d, c = m["deteccion"], m["clasificacion"]
    lineas = [
        "# Resultados de evaluación\n",
        f"Imágenes: {m['n_imagenes']} · tiempo medio {np.mean(tiempos):.0f} ms/imagen\n",
        "## Nivel 1 — Detección\n",
        "| TP | FN (no detectados) | FP (falsos) | precisión | exhaustividad | F1 |",
        "|---|---|---|---|---|---|",
        f"| {d['tp']} | {d['fn']} | {d['fp']} | {pct(d['precision'])} | "
        f"{pct(d['recall'])} | {pct(d['f1'])} |\n",
        "## Nivel 2 — Identificación (sobre objetos bien detectados)\n",
        f"Exactitud: **{pct(c['exactitud'])}** ({c['aciertos']}/{c['evaluados']})\n",
        "| clase | n | precisión | exhaustividad |",
        "|---|---|---|---|",
    ]
    for k, v in c["por_clase"].items():
        if v["n"] or v["precision"] is not None:
            lineas.append(f"| {k} | {v['n']} | {pct(v['precision'])} | {pct(v['recall'])} |")
    lineas += [
        "\n![matriz](matriz_confusion.png)\n",
        "## Nivel 3 — Interpretación\n",
        f"- Frutos reales detectados Y bien clasificados: **{pct(m['extremo_a_extremo'])}**",
        f"- Escenas con inventario exacto (conteo por clase perfecto): "
        f"**{pct(m['escenas_inventario_exacto'])}**",
        f"- Error medio de conteo por escena: {m['error_conteo_medio']:.2f} unidades\n",
        "## Por imagen\n",
        "| " + " | ".join(filas[0]) + " |",
        "|" + "---|" * len(filas[0]),
    ] + ["| " + " | ".join(str(v) for v in f.values()) + " |" for f in filas]
    (dir_out / "informe.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    print(f"\nDetección: P={pct(d['precision'])} R={pct(d['recall'])} · "
          f"Clasificación: {pct(c['exactitud'])} · "
          f"Inventario exacto: {pct(m['escenas_inventario_exacto'])}")
    print(f"Informe en {dir_out / 'informe.md'}")


if __name__ == "__main__":
    main()
