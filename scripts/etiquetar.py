"""Etiqueta a mano las escenas de prueba (data/test/) para poder evaluar.

Para cada foto sin etiquetar: detecta los objetos (SIN clasificarlos, para no
sesgar la etiqueta), guarda una imagen numerada en salidas/etiquetado/ (y la
muestra si hay pantalla) y pide en la terminal la clase de cada número.

Teclas de clase (config.yaml -> clases.*.tecla), más:
    x  = esa detección NO es un fruto (sombra, mota...) -> se contará como falso positivo
    ?  = objeto extraño que el sistema debería marcar como «desconocido»
Después pregunta por frutos NO detectados o fusionados (ej.: "a2 n1" =
2 almendras y 1 nuez sin detección propia).

Uso:
    python scripts/etiquetar.py [data/test] [--rehacer] [--mostrar]
"""
import argparse
from pathlib import Path

import cv2
from _comun import RAIZ, imagenes_en, leer, obtener_calibracion

from src.arbol import DESCONOCIDO
from src.config import cargar_config
from src.evaluacion import cargar_etiquetas, guardar_etiquetas, punto_interior
from src.pipeline import analizar
from src.visualizacion import anotar_objetos


def pedir(prompt, valido):
    while True:
        r = input(prompt).strip()
        err = valido(r)
        if err is None:
            return r
        print(f"  {err}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", nargs="?", default=str(RAIZ / "data" / "test"))
    ap.add_argument("--vacio")
    ap.add_argument("--config", default=None)
    ap.add_argument("--rehacer", action="store_true", help="re-etiquetar las ya hechas")
    ap.add_argument("--mostrar", action="store_true", help="abrir ventana con los números")
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    cal = obtener_calibracion(cfg, args.vacio)
    carpeta = Path(args.carpeta)
    ruta_et = carpeta / "etiquetas.json"
    etiquetas = cargar_etiquetas(ruta_et)
    teclas = {v["tecla"]: c for c, v in cfg["clases"].items()}
    teclas["?"] = DESCONOCIDO
    ayuda = ", ".join(f"{t}={c}" for t, c in teclas.items()) + ", x=no es fruto"
    dir_img = RAIZ / "salidas" / "etiquetado"
    dir_img.mkdir(parents=True, exist_ok=True)

    for ruta in imagenes_en(carpeta):
        if ruta.name in etiquetas and not args.rehacer:
            continue
        res = analizar(leer(ruta), cal, cfg, clasificar_objetos=False)
        img = anotar_objetos(res, cfg, numeros_solo=True)
        destino = dir_img / f"{ruta.stem}_numeros.png"
        cv2.imwrite(str(destino), img)
        print(f"\n{ruta.name}: {len(res.objetos)} detecciones -> {destino}")
        if args.mostrar:
            cv2.imshow("etiquetar", cv2.resize(img, None, fx=0.6, fy=0.6))
            cv2.waitKey(500)

        n = len(res.objetos)
        cadena = pedir(f"Clases de 1..{n} en orden ({ayuda}): ",
                       lambda r: None if len(r.replace(" ", "")) == n and
                       all(ch in teclas or ch == "x" for ch in r.replace(" ", ""))
                       else f"escribe exactamente {n} teclas válidas")
        cadena = cadena.replace(" ", "")

        def valida_faltan(r):
            for t in r.split():
                if t[0] not in teclas or not t[1:].isdigit():
                    return "formato: <tecla><número>, p. ej. 'a2 n1'"
            return None
        faltan = pedir("Frutos no detectados/fusionados (Enter = ninguno): ", valida_faltan)

        objetos = []
        for a, ch in zip(res.objetos, cadena):
            if ch == "x":
                continue
            x, y = punto_interior(a.objeto)
            objetos.append({"x": round(x / res.segmentacion.escala, 1),
                            "y": round(y / res.segmentacion.escala, 1),
                            "clase": teclas[ch]})
        no_det = {}
        for t in faltan.split():
            no_det[teclas[t[0]]] = no_det.get(teclas[t[0]], 0) + int(t[1:])
        etiquetas[ruta.name] = {"objetos": objetos, "no_detectados": no_det}
        guardar_etiquetas(etiquetas, ruta_et)        # se guarda tras cada foto
        print(f"  guardado ({len(objetos)} frutos + {sum(no_det.values())} no detectados)")
    cv2.destroyAllWindows()
    print(f"Etiquetas en {ruta_et}")


if __name__ == "__main__":
    main()
