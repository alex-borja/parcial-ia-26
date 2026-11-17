"""Diagnóstico de errores del banco de estrés con la VERDAD por píxel.

Vuelve a renderizar las escenas (el banco es determinista por semilla) con el
mapa de identidad de cada fruto y clasifica cada error en:
  - mezcla: la pieza detectada cubre a la vez una parte grande de OTRO fruto
    (corte que no separa, o frontera desplazada);
  - troceado: el fruto real quedó partido en varias piezas (la suya cubre
    menos del 75 % del fruto);
  - clasificacion: partición correcta (pieza ≈ fruto) pero clase errónea;
  - perdido: ninguna pieza lo cubre.
Los falsos positivos se clasifican igual (astilla de un fruto, sombra...).

Uso (solo sobre VALIDACIÓN, nunca sobre el test reservado):
    python scripts/diagnosticar_estres.py [--semilla 11] [--filtro webcam] [--config X]
Salida: salidas/estres_diagnostico/<nombre>/resumen.md (+ recortes de los errores).
"""
import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from _comun import RAIZ, calibrar_sesion, tapete_sesion
from generar_estres import plan_estres

from simulador.render import render
from src.config import cargar_config
from src.arbol import clasificar
from src.caracteristicas import color_tapete_iluminado, extraer
from src.deteccion import Region, construir_objeto
from src.pipeline import analizar
from src.segmentacion import linealizar


def tipo_error(pieza, mapa, k):
    """(tipo, fracción del fruto k cubierta, fracción de la pieza de otro fruto)."""
    fruto = mapa == k
    inter = np.count_nonzero(pieza & fruto)
    cubre = inter / max(np.count_nonzero(fruto), 1)
    ids, n = np.unique(mapa[pieza & (mapa > 0)], return_counts=True)
    otros = sum(c for i, c in zip(ids, n) if i != k)
    ajena = otros / max(np.count_nonzero(pieza), 1)
    if ajena > 0.15:
        return "mezcla", cubre, ajena
    if cubre < 0.75:
        return "troceado", cubre, ajena
    return "clasificacion", cubre, ajena


def diagnosticar(args):
    ruta_vacio, tareas_ses, ruta_cfg, dir_out = args
    cfg = cargar_config(ruta_cfg)
    cal = calibrar_sesion(ruta_vacio, cfg)
    filas = []
    for ruta, esc, luz, cam, sem, sem_cam in tareas_ses:
        img, verdad, mapa = render(esc, luz, cam, semilla=sem, semilla_camara=sem_cam,
                                   con_mapa=True)
        # Igual que la foto guardada del banco (generar_estres.tarea: JPEG 92).
        img = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])[1],
                           cv2.IMREAD_COLOR)
        res = analizar(img, cal, cfg)
        e = res.segmentacion.escala
        if e != 1.0:
            mapa = cv2.resize(mapa.astype(np.int32), None, fx=e, fy=e,
                              interpolation=cv2.INTER_NEAREST)
        h, w = mapa.shape
        piezas = []
        for a in res.objetos:
            piezas.append(a.objeto.mascara_completa((h, w)) > 0)
        # Cada pieza se asigna al fruto que más área le aporta.
        duena = []
        for p in piezas:
            ids, n = np.unique(mapa[p & (mapa > 0)], return_counts=True)
            duena.append(int(ids[np.argmax(n)]) if len(ids) else 0)
        seg = res.segmentacion
        tapete = cv2.bitwise_and(seg.mascara_verde, seg.roi)
        color_global = color_tapete_iluminado(linealizar(seg.imagen[::4, ::4]), tapete[::4, ::4])
        reg_total = Region(seg.mascara_objetos, 0, 0, np.zeros_like(seg.roi), seg.imagen)

        def oraculo(k):
            """Clase y rasgos de la máscara VERDADERA del fruto (lo visible)."""
            parte = ((mapa == k) & (seg.mascara_objetos > 0)).astype(np.uint8) * 255
            o = construir_objeto(reg_total, parte, separado=True)
            if o is None:
                return None, {}
            f = extraer(o, seg.imagen, res.mm_por_px, cfg, tapete, color_global)
            return clasificar(f, cfg["arbol"]).clase, f

        usadas = set()
        for v in verdad:
            k = v["indice"] + 1
            cand = [i for i, d in enumerate(duena) if d == k]
            if not cand:
                tipo, cubre, ajena, pred = "perdido", 0.0, 0.0, None
            else:
                i = max(cand, key=lambda i: np.count_nonzero(piezas[i] & (mapa == k)))
                usadas.add(i)
                pred = res.objetos[i].clase
                tipo, cubre, ajena = tipo_error(piezas[i], mapa, k)
            fila = {"imagen": str(ruta), "clase": v["clase"], "pred": pred, "tipo": tipo,
                    "cubre": round(cubre, 2), "ajena": round(ajena, 2),
                    "camara": cam_nombre(ruta), "falso": False}
            if pred != v["clase"]:
                fila["oraculo"], fo = oraculo(k)
                fila["rasgos_oraculo"] = {r: round(float(fo[r]), 3) for r in RASGOS if r in fo}
                if cand:
                    fp = res.objetos[i].caracteristicas
                    fila["rasgos_pieza"] = {r: round(float(fp[r]), 3) for r in RASGOS if r in fp}
                    fila["traza"] = str(res.objetos[i].decision)
            filas.append(fila)
        for i, a in enumerate(res.objetos):
            if i not in usadas:
                filas.append({"imagen": str(ruta), "clase": None, "pred": a.clase,
                              "tipo": "falso", "camara": cam_nombre(ruta), "falso": True,
                              "cubre": 0.0, "ajena": 0.0})
        errores = [f for f in filas[-len(verdad):] if f["pred"] != f["clase"]]
        if errores and dir_out:
            vis = res.segmentacion.imagen.copy()
            for a in res.objetos:
                col = (0, 0, 255) if a.clase == "desconocido" else (255, 255, 0)
                cv2.drawContours(vis, [a.objeto.contorno], -1, col, 1)
                x, y = a.objeto.contorno.reshape(-1, 2).mean(0)
                cv2.putText(vis, a.clase[:3], (int(x) - 8, int(y)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.35, (255, 255, 255), 1)
            nombre = f"{Path(ruta).parent.parent.name}_{Path(ruta).stem}.jpg"
            cv2.imwrite(str(Path(dir_out) / nombre), vis)
    return filas


RASGOS = ["area_mm2", "excentricidad", "solidez", "rojo_rel", "L_rel", "entrante1_mm",
          "entrante2_mm"]


def cam_nombre(ruta):
    return Path(ruta).parent.parent.name.split("__")[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--semilla", type=int, default=11)
    ap.add_argument("--escenas", type=int, default=9)
    ap.add_argument("--carpeta", default=str(RAIZ / "data" / "estres"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--nombre", default="actual")
    ap.add_argument("--filtro", nargs="*", default=None)
    ap.add_argument("--procesos", type=int, default=4)
    args = ap.parse_args()
    if args.semilla == 4242:
        raise SystemExit("La semilla 4242 es el test RESERVADO: no se diagnostica.")

    # Mismo tapete con que se generó el banco (si no, las escenas re-renderizadas
    # no serían las del disco).
    tapetes = {tapete_sesion(p) for p in Path(args.carpeta).iterdir() if p.is_dir()} - {None}
    if len(tapetes) != 1:
        raise SystemExit(f"{args.carpeta}: falta tapete.json (o no es único) en sus sesiones")
    tareas, _, _ = plan_estres(Path(args.carpeta), args.semilla, args.escenas, tapetes.pop())
    por_sesion = defaultdict(list)
    for t in tareas:
        if t[0].name != "vacio.jpg":
            por_sesion[t[0].parent.parent].append(t)
    if args.filtro:
        por_sesion = {k: v for k, v in por_sesion.items() if any(f in k.name for f in args.filtro)}
    dir_out = RAIZ / "salidas" / "estres_diagnostico" / args.nombre
    dir_out.mkdir(parents=True, exist_ok=True)
    trabajos = [(ses / "vacio.jpg", ts, args.config, str(dir_out)) for ses, ts in por_sesion.items()]
    with ProcessPoolExecutor(args.procesos) as ex:
        filas = [f for fs in ex.map(diagnosticar, trabajos) for f in fs]

    reales = [f for f in filas if not f["falso"]]
    err = [f for f in reales if f["pred"] != f["clase"]]
    l = [f"# Diagnóstico — `{args.nombre}`\n",
         f"{len(reales)} frutos, {len(err)} errores, "
         f"{sum(f['falso'] for f in filas)} falsos positivos.\n",
         "## Errores por tipo\n"]
    for t, n in Counter(f["tipo"] for f in err).most_common():
        l.append(f"- **{t}**: {n}")
        for k, m in Counter(f"{f['clase']} -> {f['pred']}" for f in err
                            if f["tipo"] == t).most_common(8):
            l.append(f"  - {k}: {m}")
    l += ["\n## ¿Acertaría con la máscara verdadera? (oráculo de partición)\n"]
    for t in ("clasificacion", "troceado", "mezcla"):
        sub = [f for f in err if f["tipo"] == t]
        if sub:
            ok = sum(f.get("oraculo") == f["clase"] for f in sub)
            l.append(f"- {t}: {ok}/{len(sub)} se acertarían con la máscara verdadera")
    l += ["\n## Falsos positivos por clase predicha\n"]
    l += [f"- {k}: {n}" for k, n in Counter(f["pred"] for f in filas if f["falso"]).most_common()]
    l += ["\n## Errores por cámara y tipo\n"]
    for c in sorted({f["camara"] for f in err}):
        l.append(f"- {c}: " + ", ".join(f"{t} {n}" for t, n in
                                        Counter(f["tipo"] for f in err if f["camara"] == c).most_common()))
    (dir_out / "resumen.md").write_text("\n".join(l) + "\n", encoding="utf-8")
    (dir_out / "filas.json").write_text(json.dumps(filas, ensure_ascii=False))
    print("\n".join(l))


if __name__ == "__main__":
    main()
