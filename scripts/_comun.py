"""Utilidades compartidas por los scripts."""
import copy
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cv2  # noqa: E402

from src.calibracion import calibrar, cargar_calibracion  # noqa: E402

EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def leer(ruta):
    img = cv2.imread(str(ruta))
    if img is None:
        sys.exit(f"No se pudo leer {ruta}")
    return img


def ruta_vacio(carpeta):
    """Foto del tapete vacío de una carpeta de sesión: vacio.jpg, vacio.png..."""
    for p in sorted(Path(carpeta).glob("vacio.*")):
        if p.suffix.lower() in EXTENSIONES:
            return p
    sys.exit(f"No hay foto del tapete vacío (vacio.jpg / vacio.png) en {carpeta}")


def imagenes_en(carpeta):
    return sorted(p for p in Path(carpeta).iterdir() if p.suffix.lower() in EXTENSIONES)


def guardar_tapete(carpeta, tapete_mm):
    """Anota en la sesión el tamaño del tapete con que se generó (sintéticas)."""
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    (Path(carpeta) / "tapete.json").write_text(
        json.dumps({"tapete_mm": [float(v) for v in tapete_mm]}) + "\n")


def tapete_sesion(carpeta):
    """Tapete (ancho, alto mm) anotado en la sesión, o None si no lo trae."""
    ruta = Path(carpeta) / "tapete.json"
    return tuple(json.loads(ruta.read_text())["tapete_mm"]) if ruta.exists() else None


def cfg_sesion(cfg, carpeta):
    """Config para calibrar una sesión: si la carpeta trae `tapete.json`
    (bancos sintéticos, p. ej. los antiguos de 500×500), sus medidas mandan
    sobre `escala.tapete_mm`; si no, se usa config.yaml (tapete real)."""
    tapete = tapete_sesion(carpeta)
    if tapete is None:
        return cfg
    c = copy.deepcopy(cfg)
    c["escala"]["tapete_mm"] = list(tapete)
    return c


def calibrar_sesion(vacio, cfg):
    """Calibra con la foto del tapete vacío y el tapete de SU sesión."""
    return calibrar(leer(vacio), cfg_sesion(cfg, Path(vacio).parent))


def obtener_calibracion(cfg, vacio=None):
    """Calibra al vuelo con `vacio` o carga la guardada por calibrar.py."""
    if vacio:
        return calibrar_sesion(vacio, cfg)
    ruta = RAIZ / cfg["calibracion"]["archivo_salida"]
    if not ruta.exists():
        sys.exit(f"No hay calibración en {ruta}. Ejecuta scripts/calibrar.py "
                 "con una foto del tapete vacío o pasa --vacio.")
    return cargar_calibracion(ruta)
