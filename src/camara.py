"""Fuente de vídeo: webcam local o cámara del MÓVIL por wifi/USB.

El móvil se usa con una app que publica la cámara como vídeo por HTTP:
  - IP Webcam (Android):  vídeo  http://IP:8080/video
                          foto   http://IP:8080/photo.jpg  (resolución completa, con autofoco)
  - DroidCam (Android/iOS): vídeo http://IP:4747/video
  - Cualquier app que cree una webcam virtual (DroidCam/Iriun con su cliente
    de PC): se usa como webcam normal, por índice (0, 1, ...).

Dos canales:
  - `leer()`: último fotograma del vídeo, para la vista previa. Se lee en un
    hilo aparte y se descartan los viejos: con streams de red, OpenCV acumula
    fotogramas en un búfer y la imagen iría con segundos de retraso.
  - `capturar()`: imagen para ANALIZAR, CALIBRAR o GUARDAR. Si hay URL de
    foto, descarga una foto fija a resolución completa (más detalle que el
    vídeo); si no, usa el último fotograma. Calibración y análisis usan
    siempre este mismo canal, así la escala mm/px es coherente.
"""
import threading
import time
import urllib.request

import cv2
import numpy as np

ROTACIONES = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
              270: cv2.ROTATE_90_COUNTERCLOCKWISE}

# Rutas de vídeo y de foto fija de las apps habituales (puerto por defecto).
APPS = {
    "ipwebcam": (8080, "/video", "/photo.jpg"),
    "droidcam": (4747, "/video", None),
}


def urls_app(app, direccion):
    """'192.168.1.20' o '192.168.1.20:8080' -> (url_video, url_foto | None)."""
    puerto, ruta_video, ruta_foto = APPS[app]
    direccion = direccion.removeprefix("http://").rstrip("/")
    if ":" not in direccion:
        direccion = f"{direccion}:{puerto}"
    base = f"http://{direccion}"
    return base + ruta_video, (base + ruta_foto if ruta_foto else None)


def interpretar_fuente(fuente):
    """'0' -> 0 (índice de webcam); cualquier otra cosa se deja como URL/ruta."""
    if isinstance(fuente, int):
        return fuente
    return int(fuente) if str(fuente).isdigit() else str(fuente)


def rotar(img, grados):
    codigo = ROTACIONES[grados]
    return img if codigo is None or img is None else cv2.rotate(img, codigo)


def descargar_imagen(url, timeout=10.0):
    """GET de una imagen JPEG/PNG -> BGR. Lanza IOError si falla."""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        datos = np.frombuffer(r.read(), np.uint8)
    img = cv2.imdecode(datos, cv2.IMREAD_COLOR)
    if img is None:
        raise IOError(f"{url} no devolvió una imagen válida")
    return img


class FuenteCamara:
    def __init__(self, fuente, url_foto=None, rotacion=0, ancho=None, alto=None,
                 timeout_s=8.0):
        if rotacion not in ROTACIONES:
            raise ValueError(f"rotación {rotacion}: usa 0, 90, 180 o 270")
        self.fuente = interpretar_fuente(fuente)
        self.url_foto = url_foto
        self.rotacion = rotacion
        self.ancho, self.alto = ancho, alto
        self.es_red = isinstance(self.fuente, str) and "://" in self.fuente
        self._frame = None
        self._t_frame = 0.0
        self._lock = threading.Lock()
        self._parar = threading.Event()
        self._cap = self._abrir()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        # Esperar al primer fotograma para fallar pronto con un mensaje claro.
        t0 = time.monotonic()
        while self._frame is None and time.monotonic() - t0 < timeout_s:
            time.sleep(0.05)
        if self._frame is None:
            self.cerrar()
            raise IOError(self._ayuda_conexion())

    def _abrir(self):
        cap = cv2.VideoCapture(self.fuente)
        if not self.es_red and self.ancho:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _ayuda_conexion(self):
        if self.es_red:
            return (f"No llega vídeo de {self.fuente}. Comprueba que la app del "
                    "móvil está emitiendo, que el móvil y el PC están en la misma "
                    "wifi y que la URL abre en el navegador del PC.")
        return f"No se pudo abrir la cámara {self.fuente}"

    def _bucle(self):
        fallos = 0
        while not self._parar.is_set():
            ok, frame = self._cap.read() if self._cap is not None else (False, None)
            if ok:
                fallos = 0
                with self._lock:
                    self._frame = frame
                    self._t_frame = time.monotonic()
                continue
            fallos += 1
            if not self.es_red and fallos > 50:
                break
            # Stream de red caído (wifi, pantalla del móvil apagada): reconectar.
            time.sleep(min(2.0, 0.1 * fallos))
            if self.es_red and fallos % 10 == 0:
                if self._cap is not None:
                    self._cap.release()
                self._cap = self._abrir()

    def leer(self):
        """(fotograma de vista previa | None, segundos desde que llegó)."""
        with self._lock:
            f = None if self._frame is None else self._frame.copy()
            edad = time.monotonic() - self._t_frame
        return rotar(f, self.rotacion), edad

    def capturar(self):
        """Imagen para analizar/calibrar/guardar (foto fija si hay URL)."""
        if self.url_foto:
            return rotar(descargar_imagen(self.url_foto), self.rotacion)
        f, _ = self.leer()
        if f is None:
            raise IOError("Todavía no hay fotogramas de la cámara")
        return f

    def cerrar(self):
        self._parar.set()
        if self._hilo.is_alive() and threading.current_thread() is not self._hilo:
            self._hilo.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
