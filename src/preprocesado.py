"""Preprocesado común: reescalado a la resolución de trabajo + desenfoque."""
import cv2


def redimensionar(img, lado_max):
    """Reescala para que el lado mayor mida `lado_max` px (nunca amplía).

    Devuelve (imagen, escala) con escala = px de trabajo / px originales.
    """
    h, w = img.shape[:2]
    escala = lado_max / max(h, w)
    if escala >= 1.0:
        return img, 1.0
    nueva = cv2.resize(img, (round(w * escala), round(h * escala)),
                       interpolation=cv2.INTER_AREA)
    return nueva, escala


def preprocesar(img_bgr, cfg):
    """Reescala a la resolución de trabajo y aplica un desenfoque suave."""
    p = cfg["preprocesado"]
    img, escala = redimensionar(img_bgr, p["lado_max_px"])
    k = p["blur_kernel"]
    if k and k > 1:
        img = cv2.GaussianBlur(img, (k, k), 0)
    return img, escala
