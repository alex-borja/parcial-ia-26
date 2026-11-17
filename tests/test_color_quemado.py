"""Color con píxeles quemados (exceso de luz)."""
import numpy as np

from src.caracteristicas import sin_quemar


def test_sin_quemar_descarta_los_pixeles_recortados():
    beige = np.tile(np.float32([0.5, 0.4, 0.25]), (80, 1))
    quemado = np.tile(np.float32([1.0, 0.9, 0.6]), (20, 1))     # R recortado
    pix = sin_quemar(np.vstack([beige, quemado]), 225)
    assert len(pix) == 80 and np.allclose(pix, beige[0])


def test_sin_quemar_no_toca_un_fruto_casi_todo_quemado():
    """Lo que queda sin quemar (grietas, borde) no representa al fruto."""
    pix = np.vstack([np.tile(np.float32([1.0, 1.0, 0.8]), (90, 1)),
                     np.tile(np.float32([0.2, 0.1, 0.05]), (10, 1))])
    assert len(sin_quemar(pix, 225)) == 100
