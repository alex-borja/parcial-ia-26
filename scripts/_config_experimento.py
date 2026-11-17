"""Crea una config de experimento: copia config.yaml cambiando umbrales.

Uso: python scripts/_config_experimento.py salida.yaml N1=521 N2=1.18 deteccion.delta_e_max=20
(Ni = umbral del nodo; seccion.clave = parámetro)."""
import sys

import yaml
from _comun import RAIZ

from src.arbol import nodos


def main():
    salida, cambios = sys.argv[1], sys.argv[2:]
    cfg = yaml.safe_load(open(RAIZ / "config.yaml", encoding="utf-8"))
    por_id = {n["id"]: n for n in nodos(cfg["arbol"])}
    for c in cambios:
        k, v = c.split("=", 1)
        v = yaml.safe_load(v)
        if k in por_id:
            if isinstance(v, (int, float)):
                por_id[k]["umbral"] = v
            else:
                por_id[k].update(v)
        else:
            sec, clave = k.split(".", 1)
            cfg[sec][clave] = v
    yaml.safe_dump(cfg, open(salida, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
    print(f"Config de experimento en {salida}")


if __name__ == "__main__":
    main()
