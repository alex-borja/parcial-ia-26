"""Justificación experimental de los umbrales (entregable 7).

Mide las características de objetos REALES de clase conocida y propone, para
cada nodo del árbol, el umbral que mejor separa las clases de cada rama.

Organización de las fotos (cada foto contiene UNA sola clase, frutos sueltos):
    data/desarrollo/nuez/*.jpg
    data/desarrollo/avellana/*.jpg   ...
    data/desarrollo/contacto/*.jpg   (opcional: frutos TOCÁNDOSE, mezclados;
                                      sirve para justificar ratio_cuello)

Uso:
    python scripts/medir_umbrales.py [--vacio data/calibracion/vacio.jpg]
    # Fotos de VARIAS sesiones (días/luces distintos), cada una con su vacío:
    python scripts/medir_umbrales.py --sesion ses1 --sesion ses2
      (cada sesión: <dir>/vacio.jpg (o .png) + <dir>/desarrollo/<clase>/*.jpg)

Objetos mal segmentados (dos frutos fusionados, un fruto partido) se excluyen
listándolos en <desarrollo>/excluir.txt («<clase>/<archivo> <id> <motivo>»);
el resumen los enumera con su motivo.

Salida en salidas/umbrales/: medidas.csv, resumen.md (tablas y umbrales
propuestos), histogramas por característica y por nodo, dispersiones.
NO modifica config.yaml: copia a mano los umbrales que decidas usar.
"""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from _comun import RAIZ, imagenes_en, leer, obtener_calibracion, ruta_vacio  # noqa: E402

from src.arbol import clases_bajo, nodos  # noqa: E402
from src.caracteristicas import CATALOGO  # noqa: E402
from src.config import cargar_config  # noqa: E402
from src.deteccion import diagnostico_contactos  # noqa: E402
from src.pipeline import analizar  # noqa: E402

PRINCIPALES = ["area_mm2", "longitud_mm", "anchura_mm", "relacion_aspecto",
               "circularidad", "excentricidad", "solidez", "L_media", "a_media",
               "b_media", "L_desv", "rojo_rel", "L_rel", "cuello_relativo",
               "entrante1_mm", "entrante2_mm"]
NUMERICAS = [k for k in CATALOGO if k not in ("orientacion_grados",)]
# Características de los rangos `validar`: (relativo|absoluto, margen, límites).
# Solo características que no dependen de la luz (L_rel sí depende del ángulo).
VALIDAR = {"area_mm2": ("rel", 0.15, None), "solidez": ("abs", 0.05, (0, 1)),
           "excentricidad": ("abs", 0.08, (0, 1)), "rojo_rel": ("abs", 0.04, (0, 1)),
           "entrante1_mm": ("abs", 0.8, (0, None)), "entrante2_mm": ("abs", 0.8, (0, None))}


def color_mpl(cfg, clase):
    b, g, r = cfg["clases"][clase]["color_bgr"]
    return (r / 255, g / 255, b / 255)


# --- búsqueda del umbral de un nodo -----------------------------------------

def mejor_umbral(si, no, operador):
    """Umbral que separa las muestras de la rama «si» de las de la rama «sino».

    Prueba todos los puntos medios entre valores consecutivos; elige el de
    menos errores y, a igualdad, el de mayor margen (más lejos de la muestra
    más cercana). Devuelve (umbral, errores, margen).
    """
    si, no = np.asarray(si, float), np.asarray(no, float)
    valores = np.unique(np.concatenate([si, no]))
    if len(valores) < 2:
        return float(valores[0]) if len(valores) else 0.0, 0, 0.0
    candidatos = (valores[:-1] + valores[1:]) / 2
    mejor = None
    for u in candidatos:
        if operador == ">":
            err = int((si <= u).sum() + (no > u).sum())
        else:
            err = int((si >= u).sum() + (no < u).sum())
        margen = float(np.min(np.abs(np.concatenate([si, no]) - u)))
        clave = (err, -margen)
        if mejor is None or clave < mejor[0]:
            mejor = (clave, float(u), err, margen)
    return mejor[1], mejor[2], mejor[3]


def errores_con(si, no, operador, u):
    si, no = np.asarray(si, float), np.asarray(no, float)
    if operador == ">":
        return int((si <= u).sum() + (no > u).sum())
    return int((si >= u).sum() + (no < u).sum())


def separabilidad(si, no):
    """Para comparar características en un nodo: (errores mínimos con la mejor
    dirección, hueco normalizado = distancia entre grupos / desv. conjunta)."""
    res = []
    for op in (">", "<"):
        u, err, _ = mejor_umbral(si, no, op)
        res.append((err, op, u))
    err, op, u = min(res)
    si, no = np.asarray(si, float), np.asarray(no, float)
    desv = np.sqrt((si.var() + no.var()) / 2) or 1e-9
    if op == ">":
        hueco = si.min() - no.max()
    else:
        hueco = no.min() - si.max()
    return err, op, u, hueco / desv


# --- recogida de medidas ------------------------------------------------------

def leer_exclusiones(dir_dev):
    """{(clase/archivo, id): motivo} de <dir_dev>/excluir.txt (si existe)."""
    ruta = Path(dir_dev) / "excluir.txt"
    excl = {}
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip() and not linea.lstrip().startswith("#"):
                archivo, ident, *motivo = linea.split(maxsplit=2)
                excl[(archivo, int(ident))] = motivo[0] if motivo else ""
    return excl


def medir(cfg, cal, dir_dev, sesion=""):
    filas, diag = [], {"sueltos": [], "contacto": []}
    excl = leer_exclusiones(dir_dev)
    excluidos = []
    clases = list(cfg["clases"])
    for clase in clases + ["contacto"]:
        carpeta = dir_dev / clase
        if not carpeta.is_dir():
            continue
        for ruta in imagenes_en(carpeta):
            res = analizar(leer(ruta), cal, cfg, clasificar_objetos=False)
            for a in res.avisos:
                print(f"  {ruta.name}: AVISO {a}")
            seg = res.segmentacion
            d = diagnostico_contactos(seg.mascara_objetos, seg.imagen, res.mm_por_px, cfg)
            diag["contacto" if clase == "contacto" else "sueltos"] += [
                dict(x, clase=clase, archivo=ruta.name) for x in d]
            if clase == "contacto":
                continue
            for a in res.objetos:
                if a.objeto.toca_borde:
                    continue
                motivo = excl.get((f"{clase}/{ruta.name}", a.objeto.id))
                if motivo is not None:
                    excluidos.append(f"{sesion + '/' if sesion else ''}{clase}/{ruta.name} "
                                     f"obj {a.objeto.id}: {motivo}")
                    continue
                f = {k: a.caracteristicas[k] for k in NUMERICAS}
                filas.append({"sesion": sesion, "archivo": ruta.name, "clase": clase,
                              "id": a.objeto.id,
                              "separado": a.objeto.separado, **f})
            print(f"{clase}/{ruta.name}: {len(res.objetos)} objetos")
    diag["excluidos"] = excluidos
    return filas, diag


# --- informe ------------------------------------------------------------------

def tabla_estadisticas(filas, clases, caracteristicas):
    lineas = []
    for c in caracteristicas:
        lineas.append(f"\n**{c}** ({CATALOGO[c][0]}) — {CATALOGO[c][2]}\n")
        lineas.append("| clase | n | media | desv | mín | p5 | p95 | máx |")
        lineas.append("|---|---|---|---|---|---|---|---|")
        for k in clases:
            v = np.array([f[c] for f in filas if f["clase"] == k], float)
            if len(v) == 0:
                continue
            lineas.append(f"| {k} | {len(v)} | {v.mean():.3g} | {v.std():.3g} | {v.min():.3g} | "
                          f"{np.percentile(v, 5):.3g} | {np.percentile(v, 95):.3g} | {v.max():.3g} |")
    return lineas


def histograma(filas, clases, c, cfg, ruta, umbrales=()):
    fig, ax = plt.subplots(figsize=(7, 3.6))
    todos = np.array([f[c] for f in filas], float)
    bins = np.linspace(todos.min(), todos.max(), 40) if len(todos) else 10
    for k in clases:
        v = [f[c] for f in filas if f["clase"] == k]
        if v:
            ax.hist(v, bins=bins, alpha=0.6, label=f"{k} (n={len(v)})", color=color_mpl(cfg, k))
    for etiqueta, u, estilo in umbrales:
        ax.axvline(u, color="k", linestyle=estilo, label=f"{etiqueta} = {u:.3g}")
    ax.set_xlabel(f"{c} ({CATALOGO[c][0]})")
    ax.set_ylabel("nº de objetos")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(ruta, dpi=110)
    plt.close(fig)


def dispersion(filas, clases, cx, cy, cfg, ruta):
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    for k in clases:
        xs = [f[cx] for f in filas if f["clase"] == k]
        ys = [f[cy] for f in filas if f["clase"] == k]
        if xs:
            ax.scatter(xs, ys, s=14, label=k, color=color_mpl(cfg, k))
    ax.set_xlabel(cx)
    ax.set_ylabel(cy)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(ruta, dpi=110)
    plt.close(fig)


def informe_nodos(filas, cfg, dir_out):
    lineas = ["\n## Umbrales por nodo del árbol\n",
              "Para cada nodo se usan solo los objetos de las clases que llegan a él; "
              "«sí» = clases de la rama `si`, «no» = clases de la rama `sino`. "
              "Umbral propuesto = menos errores y, a igualdad, máximo margen.\n"]
    propuestas = {}
    for n in nodos(cfg["arbol"]):
        c_si, c_no = clases_bajo(n["si"]), clases_bajo(n["sino"])
        car, op, u_actual = n["caracteristica"], n["operador"], n["umbral"]
        si = [f[car] for f in filas if f["clase"] in c_si]
        no = [f[car] for f in filas if f["clase"] in c_no]
        lineas.append(f"### {n['id']}: {n.get('pregunta', '')}  (`{car} {op} umbral`)\n")
        lineas.append(f"- sí: {', '.join(sorted(c_si))} (n={len(si)}) · "
                      f"no: {', '.join(sorted(c_no))} (n={len(no)})")
        if not si or not no:
            lineas.append("- **Faltan medidas de alguna rama**: no se puede proponer umbral.\n")
            continue
        u, err, margen = mejor_umbral(si, no, op)
        propuestas[n["id"]] = u
        lineas.append(f"- rango «sí»: [{min(si):.3g}, {max(si):.3g}] · rango «no»: "
                      f"[{min(no):.3g}, {max(no):.3g}]")
        lineas.append(f"- umbral actual {u_actual}: **{errores_con(si, no, op, u_actual)} errores**")
        lineas.append(f"- umbral propuesto **{u:.4g}**: {err} errores, margen {margen:.3g}"
                      + (" (clases separables)" if err == 0 else ""))
        # ¿Hay otra característica que separe mejor esta rama?
        ranking = []
        for c in NUMERICAS:
            vs = [f[c] for f in filas if f["clase"] in c_si]
            vn = [f[c] for f in filas if f["clase"] in c_no]
            e, o, uu, h = separabilidad(vs, vn)
            ranking.append((e, -h, c, o, uu))
        ranking.sort()
        lineas.append("\n| característica | errores | hueco normalizado | regla |")
        lineas.append("|---|---|---|---|")
        for e, h, c, o, uu in ranking[:5]:
            marca = " ← en uso" if c == car else ""
            lineas.append(f"| {c}{marca} | {e} | {-h:.2f} | {c} {o} {uu:.4g} |")
        lineas.append("")
        img = dir_out / f"nodo_{n['id']}.png"
        # Histograma del nodo con los dos grupos.
        fig, ax = plt.subplots(figsize=(7, 3.4))
        bins = np.linspace(min(si + no), max(si + no), 40)
        ax.hist(si, bins=bins, alpha=0.6, label="rama sí: " + ", ".join(sorted(c_si)))
        ax.hist(no, bins=bins, alpha=0.6, label="rama no: " + ", ".join(sorted(c_no)))
        ax.axvline(u_actual, color="k", linestyle="--", label=f"actual = {u_actual}")
        ax.axvline(u, color="r", label=f"propuesto = {u:.3g}")
        ax.set_title(f"{n['id']}: {car} {op} umbral")
        ax.set_xlabel(car)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(img, dpi=110)
        plt.close(fig)
        lineas.append(f"![{n['id']}]({img.name})\n")
    return lineas, propuestas


def informe_deteccion(filas, diag, cfg):
    d = cfg["deteccion"]
    lineas = ["\n## Detección\n"]
    areas = [f["area_mm2"] for f in filas]
    if areas:
        lineas.append(f"- Área mínima de un fruto medido: {min(areas):.0f} mm² → "
                      f"`area_min_mm2` propuesto ≈ {0.5 * min(areas):.0f} (actual {d['area_min_mm2']}).")
    sueltos = [x for x in diag["sueltos"] if x["n_maximos"] > 1]
    contacto = [x for x in diag["contacto"] if x["n_maximos"] > 1]
    if sueltos:
        cs = [x["cuello_min"] for x in sueltos]
        de = [x["delta_e_max"] for x in sueltos]
        lineas.append(f"- Frutos SUELTOS con varios máximos: {len(sueltos)}. "
                      f"cuello_min ∈ [{min(cs):.2f}, {max(cs):.2f}], "
                      f"ΔE interno máx = {max(de):.1f}.")
        lineas.append(f"  → `ratio_cuello` debe ser < {min(cs):.2f} (actual {d['ratio_cuello']}); "
                      f"`delta_e_max` debe ser > {max(de):.1f} (actual {d.get('delta_e_max')}).")
    if contacto:
        cc = [x["cuello_min"] for x in contacto]
        lineas.append(f"- Regiones CON CONTACTO: {len(contacto)}. cuello_min ∈ "
                      f"[{min(cc):.2f}, {max(cc):.2f}].")
        if sueltos:
            lo, hi = max(cc), min(x["cuello_min"] for x in sueltos)
            if lo < hi:
                lineas.append(f"  → separables: `ratio_cuello` propuesto = {(lo + hi) / 2:.2f}.")
            else:
                lineas.append("  → se solapan: el cuello solo no basta en todos los casos "
                              "(el criterio de color ayuda si los frutos son de distinto color).")
    else:
        lineas.append("- Sin fotos en data/desarrollo/contacto/: no se puede medir el cuello "
                      "de frutos que se tocan.")
    return lineas


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vacio")
    ap.add_argument("--config", default=None)
    ap.add_argument("--desarrollo", default=str(RAIZ / "data" / "desarrollo"))
    ap.add_argument("--sesion", action="append", default=[],
                    help="carpeta de sesión con vacio.jpg y desarrollo/ (repetible)")
    ap.add_argument("--salida", default=str(RAIZ / "salidas" / "umbrales"))
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    dir_out = Path(args.salida)
    dir_out.mkdir(parents=True, exist_ok=True)

    if args.sesion:
        filas, diag = [], {"sueltos": [], "contacto": [], "excluidos": []}
        for d in map(Path, args.sesion):
            cal = obtener_calibracion(cfg, ruta_vacio(d))
            f, dg = medir(cfg, cal, d / "desarrollo", sesion=d.name)
            filas += f
            for k in diag:
                diag[k] += dg[k]
    else:
        cal = obtener_calibracion(cfg, args.vacio)
        filas, diag = medir(cfg, cal, Path(args.desarrollo))
    if not filas:
        raise SystemExit("No hay objetos medidos: pon fotos en data/desarrollo/<clase>/")
    clases = [c for c in cfg["clases"] if any(f["clase"] == c for f in filas)]

    with open(dir_out / "medidas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)

    lineas = ["# Medidas de desarrollo y umbrales propuestos\n",
              f"Sesiones: {', '.join(sorted({f['sesion'] or '-' for f in filas}))}. "
              f"Objetos medidos: {len(filas)}.\n"]
    if diag["excluidos"]:
        lineas.append(f"Excluidos ({len(diag['excluidos'])}, ver excluir.txt):\n")
        lineas += [f"- {e}" for e in diag["excluidos"]] + [""]
    # Posibles fusiones: área muy superior a la mediana de su clase.
    for k in clases:
        v = [f for f in filas if f["clase"] == k]
        med = np.median([f["area_mm2"] for f in v])
        raros = [f for f in v if f["area_mm2"] > 1.6 * med]
        for f in raros:
            lineas.append(f"- AVISO: {k} en {f['archivo']} (obj {f['id']}) tiene área "
                          f"{f['area_mm2']:.0f} mm² (> 1,6 × mediana): ¿dos frutos fusionados?")

    lineas += informe_deteccion(filas, diag, cfg)
    l_nodos, propuestas = informe_nodos(filas, cfg, dir_out)
    lineas += l_nodos

    lineas.append("\n## Rangos `validar` propuestos (para las hojas del árbol)\n")
    lineas.append("Rango medido de cada clase ensanchado con un margen (las fotos de "
                  "desarrollo no recogen toda la variabilidad). Sirven para detectar "
                  "objetos extraños y frutos pegados (bucle de verificación).\n")
    lineas.append("```yaml")
    for k in clases:
        partes = []
        for c, (tipo, margen, lim) in VALIDAR.items():
            v = np.array([f[c] for f in filas if f["clase"] == k], float)
            lo, hi = (v.min() * (1 - margen), v.max() * (1 + margen)) if tipo == "rel" \
                else (v.min() - margen, v.max() + margen)
            if lim is not None:
                lo = max(lo, lim[0])
                hi = hi if lim[1] is None else min(hi, lim[1])
            dec = 0 if c == "area_mm2" else 2
            partes.append(f"{c}: [{lo:.{dec}f}, {hi:.{dec}f}]")
        lineas.append(f"{k}: {{{', '.join(partes)}}}")
    lineas.append("```")

    lineas.append("\n## Estadísticas por clase\n")
    lineas += tabla_estadisticas(filas, clases, PRINCIPALES)

    lineas.append("\n## Histogramas y dispersiones\n")
    for c in PRINCIPALES:
        ruta = dir_out / f"hist_{c}.png"
        histograma(filas, clases, c, cfg, ruta)
        lineas.append(f"![{c}]({ruta.name})")
    for cx, cy in (("area_mm2", "relacion_aspecto"), ("area_mm2", "L_media"),
                   ("relacion_aspecto", "L_media"), ("area_mm2", "solidez")):
        ruta = dir_out / f"disp_{cx}_{cy}.png"
        dispersion(filas, clases, cx, cy, cfg, ruta)
        lineas.append(f"![{cx} vs {cy}]({ruta.name})")

    (dir_out / "resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"\n{len(filas)} objetos medidos. Umbrales propuestos: "
          + ", ".join(f"{k}={v:.4g}" for k, v in propuestas.items()))
    print(f"Informe en {dir_out / 'resumen.md'}")


if __name__ == "__main__":
    main()
