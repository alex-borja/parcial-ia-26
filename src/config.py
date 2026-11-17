"""Carga de config.yaml (único lugar con parámetros del sistema)."""
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RAIZ / "config.yaml"


def cargar_config(ruta=None):
    ruta = Path(ruta) if ruta else RUTA_CONFIG
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)
