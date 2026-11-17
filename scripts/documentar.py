"""Genera la documentación del árbol y de las características desde el código
y config.yaml, para que el informe nunca se desincronice del sistema real.

Uso:
    python scripts/documentar.py

Escribe docs/arbol.md (diagrama Mermaid + tabla de nodos con umbral y
justificación) y docs/caracteristicas.md (tabla de características).
"""
import argparse

from _comun import RAIZ

from src.arbol import a_mermaid, es_hoja, nodos, validar_arbol
from src.caracteristicas import CATALOGO
from src.config import cargar_config


def hojas(n):
    return [n] if es_hoja(n) else hojas(n["si"]) + hojas(n["sino"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = cargar_config(args.config)
    validar_arbol(cfg["arbol"], cfg["clases"])
    docs = RAIZ / "docs"
    docs.mkdir(exist_ok=True)

    l = ["# Árbol de decisión\n",
         "_Generado por `scripts/documentar.py` a partir de `config.yaml`._\n",
         "```mermaid", a_mermaid(cfg["arbol"]), "```\n",
         "## Nodos\n",
         "| nodo | pregunta | regla (sí →) | justificación |",
         "|---|---|---|---|"]
    for n in nodos(cfg["arbol"]):
        just = " ".join(str(n.get("justificacion", "")).split())
        l.append(f"| {n['id']} | {n.get('pregunta', '')} | "
                 f"`{n['caracteristica']} {n['operador']} {n['umbral']}` | {just} |")
    l += ["\n## Hojas y rangos de validación\n",
          "Si un objeto llega a una hoja pero alguna característica cae fuera del "
          "rango medido de esa clase, se clasifica como **desconocido**.\n",
          "| clase | validar |", "|---|---|"]
    for h in hojas(cfg["arbol"]):
        v = h.get("validar") or {}
        l.append(f"| {h['clase']} | " + (", ".join(f"{c} ∈ [{a}, {b}]" for c, (a, b) in v.items())
                                          or "—") + " |")
    (docs / "arbol.md").write_text("\n".join(l) + "\n", encoding="utf-8")

    usadas = {n["caracteristica"] for n in nodos(cfg["arbol"])}
    l = ["# Características extraídas\n",
         "_Generado por `scripts/documentar.py` a partir de `src/caracteristicas.py`._\n",
         "Tamaños en mm/mm² usando la escala de la calibración. Color medido en la "
         "máscara erosionada (sin borde mezclado con el tapete).\n",
         "| característica | unidad | cálculo | qué separa | en el árbol |",
         "|---|---|---|---|---|"]
    for k, (u, calc, uso) in CATALOGO.items():
        l.append(f"| `{k}` | {u} | {calc} | {uso} | {'**sí**' if k in usadas else ''} |")
    (docs / "caracteristicas.md").write_text("\n".join(l) + "\n", encoding="utf-8")
    print(f"Escritos {docs / 'arbol.md'} y {docs / 'caracteristicas.md'}")


if __name__ == "__main__":
    main()
