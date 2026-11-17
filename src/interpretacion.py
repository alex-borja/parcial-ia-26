"""Nivel 3 — Interpretación de la escena.

A partir de la clase de cada objeto:
  - conteo por clase y total;
  - distribución por unidades (%) y por peso estimado (%), con el peso medio
    por unidad de config.yaml;
  - clase mayoritaria y objetos «desconocidos» (objeto extraño en el tapete);
  - si se define `lote_esperado`: unidades que faltan/sobran y si el lote es
    correcto.
"""
from collections import Counter

from .arbol import DESCONOCIDO


def interpretar(clases_objetos, cfg):
    clases = list(cfg["clases"])
    cuenta = Counter(clases_objetos)
    conteo = {c: cuenta.get(c, 0) for c in clases}
    desconocidos = cuenta.get(DESCONOCIDO, 0)
    total = sum(conteo.values())

    distribucion = {c: (100 * n / total if total else 0.0) for c, n in conteo.items()}
    pesos = {c: conteo[c] * cfg["clases"][c].get("peso_medio_g", 0.0) for c in clases}
    peso_total = sum(pesos.values())
    distribucion_peso = {c: (100 * p / peso_total if peso_total else 0.0)
                         for c, p in pesos.items()}

    mayor = max(conteo.values()) if total else 0
    mayoritarias = [c for c, n in conteo.items() if n == mayor and n > 0]

    resultado = {
        "total": total,
        "desconocidos": desconocidos,
        "conteo": conteo,
        "distribucion_pct": distribucion,
        "peso_g": pesos,
        "peso_total_g": peso_total,
        "distribucion_peso_pct": distribucion_peso,
        "mayoritarias": mayoritarias,
        "lote": None,
    }

    esperado = (cfg.get("interpretacion") or {}).get("lote_esperado") or {}
    if esperado:
        diferencias = {c: conteo.get(c, 0) - esperado.get(c, 0)
                       for c in set(clases) | set(esperado)}
        resultado["lote"] = {
            "esperado": esperado,
            "faltan": {c: -d for c, d in diferencias.items() if d < 0},
            "sobran": {c: d for c, d in diferencias.items() if d > 0},
            "correcto": all(d == 0 for d in diferencias.values()) and desconocidos == 0,
        }
    return resultado


def resumen_texto(interp):
    """Resumen legible para la terminal/vídeo."""
    lineas = [f"Total: {interp['total']} frutos secos"
              + (f" + {interp['desconocidos']} desconocido(s)" if interp["desconocidos"] else "")]
    for c, n in interp["conteo"].items():
        lineas.append(f"  {c:<10} {n:>3}  {interp['distribucion_pct'][c]:5.1f} % uds"
                      f"  ~{interp['peso_g'][c]:6.1f} g ({interp['distribucion_peso_pct'][c]:5.1f} % peso)")
    lineas.append(f"Peso estimado: {interp['peso_total_g']:.1f} g")
    if interp["mayoritarias"]:
        lineas.append(f"Mayoritaria: {', '.join(interp['mayoritarias'])}")
    lote = interp["lote"]
    if lote:
        if lote["correcto"]:
            lineas.append("Lote: CORRECTO")
        else:
            partes = [f"faltan {n} {c}" for c, n in lote["faltan"].items()]
            partes += [f"sobran {n} {c}" for c, n in lote["sobran"].items()]
            if interp["desconocidos"]:
                partes.append(f"{interp['desconocidos']} objeto(s) extraño(s)")
            lineas.append("Lote: INCORRECTO — " + ", ".join(partes))
    return "\n".join(lineas)
