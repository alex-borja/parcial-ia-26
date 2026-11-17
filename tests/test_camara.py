"""Fuente de cámara: se simula el móvil con un servidor HTTP local que emite
vídeo MJPEG (como IP Webcam / DroidCam) y sirve una foto fija."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import pytest

from src.camara import FuenteCamara, interpretar_fuente, rotar, urls_app
from tests.sinteticas import escena

VIDEO = cv2.resize(escena([("nuez", 250, 250, 0)]), (640, 480))
FOTO = escena([("nuez", 250, 250, 0)])[:, :1200]      # «resolución completa», apaisada


class MovilFalso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/photo.jpg":
            datos = cv2.imencode(".jpg", FOTO)[1].tobytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
        elif self.path == "/video":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            jpg = cv2.imencode(".jpg", VIDEO)[1].tobytes()
            try:
                for _ in range(300):
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                     + f"Content-Length: {len(jpg)}\r\n\r\n".encode()
                                     + jpg + b"\r\n")
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)


@pytest.fixture
def movil():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), MovilFalso)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_urls_de_las_apps():
    assert urls_app("ipwebcam", "192.168.1.20") == (
        "http://192.168.1.20:8080/video", "http://192.168.1.20:8080/photo.jpg")
    assert urls_app("ipwebcam", "http://10.0.0.5:9000/") == (
        "http://10.0.0.5:9000/video", "http://10.0.0.5:9000/photo.jpg")
    assert urls_app("droidcam", "192.168.1.20") == ("http://192.168.1.20:4747/video", None)


def test_interpretar_fuente():
    assert interpretar_fuente("0") == 0 and interpretar_fuente(2) == 2
    assert interpretar_fuente("http://x/video") == "http://x/video"


def test_rotar():
    img = np.zeros((10, 20, 3), np.uint8)
    assert rotar(img, 90).shape == (20, 10, 3)
    assert rotar(img, 0) is img


def test_video_y_foto_del_movil(movil):
    video, foto = urls_app("ipwebcam", movil)
    cam = FuenteCamara(video, url_foto=foto)
    try:
        frame, edad = cam.leer()
        assert frame.shape[:2] == (480, 640) and edad < 2
        img = cam.capturar()                       # foto fija, no el vídeo
        assert img.shape[:2] == FOTO.shape[:2]
    finally:
        cam.cerrar()


def test_sin_url_de_foto_captura_del_video(movil):
    video, _ = urls_app("droidcam", movil)
    cam = FuenteCamara(video, rotacion=90)
    try:
        assert cam.capturar().shape[:2] == (640, 480)   # girado
    finally:
        cam.cerrar()


def test_movil_inalcanzable_da_error_claro():
    with pytest.raises(IOError, match="wifi"):
        FuenteCamara("http://127.0.0.1:1/video", timeout_s=1.0)
