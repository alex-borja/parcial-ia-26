"""Demostración: foto(s) o cámara en vivo -> imagen anotada + inventario.

Fotos:
    python scripts/demo.py escena.jpg [más.jpg ...] [--traza] [--mostrar]

Cámara del MÓVIL (misma wifi que el PC):
    python scripts/demo.py --ipwebcam 192.168.1.20      # app IP Webcam (Android)
    python scripts/demo.py --droidcam 192.168.1.20      # app DroidCam (Android/iOS)
    python scripts/demo.py --camara http://IP:PUERTO/video [--foto-url http://.../foto.jpg]
Webcam del PC (o móvil como webcam virtual por USB):
    python scripts/demo.py --camara 0

Opciones: --rotar 90|180|270 (si el móvil entrega la imagen girada),
          --guardar-en data/desarrollo/nuez (dónde guarda la tecla «g»).

Teclas en la ventana:
    c       calibrar con la imagen actual (¡tapete VACÍO!)
    espacio analizar la imagen actual
    m       alternar vista de la máscara de segmentación
    g       guardar la imagen (para fotos de desarrollo/test)
    q / Esc salir

Calibración, análisis y guardado usan la MISMA captura (con IP Webcam, una
foto fija a resolución completa), así la escala mm/px es coherente. Si el
móvil se mueve o cambia de resolución, vuelve a calibrar con «c».
"""
import argparse
import time
from pathlib import Path

import cv2
from _comun import RAIZ, leer, obtener_calibracion

from src.calibracion import calibrar, cargar_calibracion, guardar_calibracion
from src.camara import FuenteCamara, urls_app
from src.config import cargar_config
from src.interpretacion import resumen_texto
from src.pipeline import analizar
from src.segmentacion import segmentar
from src.visualizacion import imagen_resultado, superponer_mascara, texto


def informar(res, traza):
    print(resumen_texto(res.interpretacion))
    if traza:
        for a in res.objetos:
            print(f"  #{a.objeto.id}: {a.decision.texto_traza()}")
    for av in res.avisos:
        print(f"  AVISO: {av}")
    print("  tiempos (ms): " + ", ".join(f"{k}={v:.0f}" for k, v in res.tiempos_ms.items()))


def ajustar(img, ancho_max=1600):
    f = min(1.0, ancho_max / img.shape[1])
    return cv2.resize(img, None, fx=f, fy=f) if f < 1 else img


def modo_fotos(args, cfg):
    cal = obtener_calibracion(cfg, args.vacio)
    dir_out = Path(args.salida)
    dir_out.mkdir(parents=True, exist_ok=True)
    for ruta in args.fotos:
        res = analizar(leer(ruta), cal, cfg)
        print(f"\n=== {ruta}")
        informar(res, args.traza)
        img = imagen_resultado(res, cfg)
        destino = dir_out / f"{Path(ruta).stem}_resultado.png"
        cv2.imwrite(str(destino), img)
        print(f"  -> {destino}")
        if args.mostrar:
            cv2.imshow("resultado", ajustar(img))
            if cv2.waitKey(0) in (ord("q"), 27):
                break
    cv2.destroyAllWindows()


def abrir_fuente(args):
    if args.ipwebcam:
        video, foto = urls_app("ipwebcam", args.ipwebcam)
    elif args.droidcam:
        video, foto = urls_app("droidcam", args.droidcam)
    else:
        video, foto = args.camara, None
    foto = args.foto_url or foto
    print(f"Conectando con {video}" + (f" (fotos: {foto})" if foto else "") + " ...")
    try:
        return FuenteCamara(video, url_foto=foto, rotacion=args.rotar,
                            ancho=args.ancho, alto=args.alto)
    except IOError as e:
        raise SystemExit(str(e))


def modo_camara(args, cfg):
    cam = abrir_fuente(args)
    ruta_cal = RAIZ / cfg["calibracion"]["archivo_salida"]
    cal = cargar_calibracion(ruta_cal) if ruta_cal.exists() else None
    ver_mascara, resultado = False, None
    guardar_en = Path(args.guardar_en)
    guardar_en.mkdir(parents=True, exist_ok=True)
    print(__doc__)
    try:
        while True:
            frame, edad = cam.leer()
            if frame is None:
                time.sleep(0.05)
                continue
            vista = frame
            if ver_mascara and cal is not None:
                seg = segmentar(frame, cal, cfg)
                vista = superponer_mascara(seg.imagen, seg.mascara_objetos)
            vista = ajustar(vista, 1280)
            if cal is None:
                texto(vista, "Sin calibrar: tapete VACIO y pulsa 'c'", (20, 40), 0.9, (0, 0, 255))
            if edad > 2:
                texto(vista, f"Sin video desde hace {edad:.0f} s (reconectando...)",
                      (20, 80), 0.8, (0, 0, 255))
            cv2.imshow("camara", vista)
            if resultado is not None:
                cv2.imshow("resultado", ajustar(resultado))
            k = cv2.waitKey(15) & 0xFF
            if k in (ord("q"), 27):
                break
            if k not in (ord("c"), ord("g"), ord(" "), ord("m")):
                continue
            if k == ord("m"):
                ver_mascara = not ver_mascara
                continue
            if k == ord(" ") and cal is None:
                print("Primero calibra: tapete vacío y tecla «c»")
                continue
            try:
                img = cam.capturar()
            except IOError as e:
                print(f"No se pudo capturar: {e}")
                continue
            if k == ord("c"):
                try:
                    cal = calibrar(img, cfg)
                except ValueError as e:
                    print(f"Error de calibración: {e}")
                    continue
                guardar_calibracion(cal, ruta_cal)
                print(f"Calibrado con {img.shape[1]}×{img.shape[0]} px: "
                      f"{cal['mm_por_px_original']:.4f} mm/px, campo {cal['campo_vision_mm']} mm")
                for a in cal["avisos"]:
                    print(f"  AVISO: {a}")
            elif k == ord("g"):
                nombre = guardar_en / time.strftime("captura_%Y%m%d_%H%M%S.jpg")
                cv2.imwrite(str(nombre), img)
                print(f"Guardado {nombre} ({img.shape[1]}×{img.shape[0]} px)")
            else:
                res = analizar(img, cal, cfg)
                print("\n=== análisis")
                informar(res, args.traza)
                resultado = imagen_resultado(res, cfg)
                nombre = Path(args.salida) / time.strftime("demo_%H%M%S.png")
                nombre.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(nombre), resultado)
    finally:
        cam.cerrar()
        cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fotos", nargs="*")
    ap.add_argument("--camara", default=None,
                    help="índice de webcam (0, 1...) o URL de vídeo (http://IP:PUERTO/video)")
    ap.add_argument("--ipwebcam", metavar="IP[:PUERTO]", help="móvil con la app IP Webcam")
    ap.add_argument("--droidcam", metavar="IP[:PUERTO]", help="móvil con la app DroidCam")
    ap.add_argument("--foto-url", help="URL de foto fija a resolución completa (opcional)")
    ap.add_argument("--rotar", type=int, default=0, choices=[0, 90, 180, 270])
    ap.add_argument("--ancho", type=int, default=1920, help="solo webcams locales")
    ap.add_argument("--alto", type=int, default=1080, help="solo webcams locales")
    ap.add_argument("--vacio")
    ap.add_argument("--config", default=None)
    ap.add_argument("--traza", action="store_true", help="mostrar el recorrido del árbol")
    ap.add_argument("--mostrar", action="store_true")
    ap.add_argument("--salida", default=str(RAIZ / "salidas" / "demo"))
    ap.add_argument("--guardar-en", default=str(RAIZ / "data" / "capturas"))
    args = ap.parse_args()
    cfg = cargar_config(args.config)
    if args.camara is not None or args.ipwebcam or args.droidcam:
        modo_camara(args, cfg)
    elif args.fotos:
        modo_fotos(args, cfg)
    else:
        ap.error("indica fotos, --camara, --ipwebcam o --droidcam")


if __name__ == "__main__":
    main()
