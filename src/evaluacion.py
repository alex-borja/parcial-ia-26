"""Medida cuantitativa de aciertos y errores (entregables 8 y 9).

Etiquetas (data/test/etiquetas.json), coordenadas en px de la foto ORIGINAL:
    {
      "escena01.jpg": {
        "objetos": [{"x": 812, "y": 455, "clase": "nuez"}, ...],
        "no_detectados": {"almendra": 1}
      }
    }
`objetos` son puntos dentro de cada fruto real; `no_detectados` cuenta los
frutos reales que el sistema no separó o no vio al etiquetar (p. ej. dos
frutos fusionados en una detección: uno va a `objetos`, otro aquí).

Emparejamiento: un punto etiquetado casa con la detección que lo contiene
(o que está a menos de `evaluacion.tolerancia_mm`), una a una.
"""
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from .arbol import DESCONOCIDO


def cargar_etiquetas(ruta):
    ruta = Path(ruta)
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def guardar_etiquetas(etiquetas, ruta):
    Path(ruta).write_text(json.dumps(etiquetas, indent=2, ensure_ascii=False), encoding="utf-8")


def punto_interior(obj):
    """Punto del objeto más alejado del borde (siempre dentro, incluso en
    formas cóncavas como el anacardo, cuyo centroide puede caer fuera)."""
    dist = cv2.distanceTransform(obj.mascara, cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(np.argmax(dist)), dist.shape)
    return obj.x0 + int(x), obj.y0 + int(y)


def emparejar(res, etiqueta, cfg):
    """Empareja detecciones con etiquetas de una imagen.

    Devuelve dict con pares [(clase_real, clase_predicha)], no_emparejados
    (reales sin detección), falsos (detecciones sin fruto real) y conteos.
    """
    escala = res.segmentacion.escala
    tol_px = cfg["evaluacion"]["tolerancia_mm"] / res.mm_por_px
    libres = set(range(len(res.objetos)))
    pares, perdidos, por_objeto = [], [], []
    for e in etiqueta.get("objetos", []):
        px, py = e["x"] * escala, e["y"] * escala
        mejor, mejor_d = None, None
        for i in libres:
            # >0 dentro, <0 fuera (distancia con signo al contorno).
            d = cv2.pointPolygonTest(res.objetos[i].objeto.contorno, (px, py), True)
            if d >= -tol_px and (mejor_d is None or d > mejor_d):
                mejor, mejor_d = i, d
        if mejor is None:
            perdidos.append(e["clase"])
            por_objeto.append(None)
        else:
            libres.discard(mejor)
            pares.append((e["clase"], res.objetos[mejor].clase))
            por_objeto.append(res.objetos[mejor].clase)

    reales = Counter(e["clase"] for e in etiqueta.get("objetos", []))
    reales.update(etiqueta.get("no_detectados", {}))
    predichos = Counter(a.clase for a in res.objetos)
    return {
        "pares": pares,
        "perdidos": perdidos + [c for c, n in etiqueta.get("no_detectados", {}).items()
                                for _ in range(n)],
        "falsos": [res.objetos[i].clase for i in sorted(libres)],
        "reales": dict(reales),
        "predichos": dict(predichos),
        # Por cada fruto etiquetado (mismo orden): clase predicha o None.
        "por_objeto": por_objeto,
    }


def metricas(resultados, clases):
    """Agrega los emparejamientos de todas las imágenes."""
    etiquetas_cm = list(clases) + [DESCONOCIDO]
    idx = {c: i for i, c in enumerate(etiquetas_cm)}
    cm = np.zeros((len(etiquetas_cm), len(etiquetas_cm)), int)
    tp = fn = fp = 0
    escenas_ok = 0
    err_conteo = []
    for r in resultados:
        for real, pred in r["pares"]:
            cm[idx[real], idx.get(pred, idx[DESCONOCIDO])] += 1
        tp += len(r["pares"])
        fn += len(r["perdidos"])
        fp += len(r["falsos"])
        ok = all(r["reales"].get(c, 0) == r["predichos"].get(c, 0) for c in etiquetas_cm)
        escenas_ok += ok
        err_conteo.append(sum(abs(r["reales"].get(c, 0) - r["predichos"].get(c, 0))
                              for c in etiquetas_cm))

    aciertos = int(np.trace(cm))
    total_reales = tp + fn
    por_clase = {}
    for c, i in idx.items():
        col, fila = cm[:, i].sum(), cm[i, :].sum()
        por_clase[c] = {
            "precision": cm[i, i] / col if col else None,
            "recall": cm[i, i] / fila if fila else None,
            "n": int(fila),
        }
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return {
        "n_imagenes": len(resultados),
        "deteccion": {"tp": tp, "fn": fn, "fp": fp, "precision": p, "recall": rc,
                      "f1": 2 * p * rc / (p + rc) if p + rc else 0.0},
        "clasificacion": {"aciertos": aciertos, "evaluados": tp,
                          "exactitud": aciertos / tp if tp else 0.0,
                          "por_clase": por_clase},
        "extremo_a_extremo": aciertos / total_reales if total_reales else 0.0,
        "escenas_inventario_exacto": escenas_ok / len(resultados) if resultados else 0.0,
        "error_conteo_medio": float(np.mean(err_conteo)) if err_conteo else 0.0,
        "matriz_confusion": cm.tolist(),
        "etiquetas_matriz": etiquetas_cm,
    }


def evaluar_carpeta(carpeta, etiquetas, cal, cfg, dir_imagenes=None, verbose=False):
    """Analiza y empareja todas las imágenes etiquetadas de `carpeta`.

    Devuelve (metricas, filas_por_imagen, tiempos_ms). Si `dir_imagenes`,
    guarda allí la imagen anotada de cada escena.
    """
    from .pipeline import analizar
    from .visualizacion import imagen_resultado

    carpeta = Path(carpeta)
    resultados, filas, tiempos = [], [], []
    for nombre, et in sorted(etiquetas.items()):
        ruta = carpeta / nombre
        img = cv2.imread(str(ruta))
        if img is None:
            if verbose:
                print(f"{nombre}: falta la imagen, se omite")
            continue
        res = analizar(img, cal, cfg)
        r = emparejar(res, et, cfg)
        resultados.append(r)
        tiempos.append(res.tiempos_ms["total"])
        if dir_imagenes is not None:
            cv2.imwrite(str(Path(dir_imagenes) / f"{ruta.stem}_resultado.png"),
                        imagen_resultado(res, cfg))
        bien = sum(a == b for a, b in r["pares"])
        exacta = all(r["reales"].get(c, 0) == r["predichos"].get(c, 0)
                     for c in set(r["reales"]) | set(r["predichos"]))
        n_reales = sum(r["reales"].values())
        filas.append({"imagen": nombre, "reales": n_reales,
                      "detectados": len(res.objetos), "emparejados": len(r["pares"]),
                      "bien_clasificados": bien, "no_detectados": len(r["perdidos"]),
                      "falsos": len(r["falsos"]), "inventario_exacto": exacta,
                      "confusiones": "; ".join(f"{a}->{b}" for a, b in r["pares"] if a != b),
                      "ms": round(res.tiempos_ms["total"])})
        if verbose:
            print(f"{nombre}: {bien}/{n_reales} correctos, {len(r['falsos'])} falsos, "
                  f"{len(r['perdidos'])} perdidos" + ("  [inventario exacto]" if exacta else ""))
    return metricas(resultados, list(cfg["clases"])), filas, tiempos
