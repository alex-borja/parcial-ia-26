"""Emparejamiento detección-etiqueta y métricas."""
from src.evaluacion import emparejar, metricas, punto_interior
from src.pipeline import analizar
from tests.sinteticas import escena

OBJS = [("nuez", 100, 100, 0), ("avellana", 300, 100, 0), ("anacardo", 200, 300, 30)]


def etiqueta_perfecta(res):
    e = []
    for a in res.objetos:
        x, y = punto_interior(a.objeto)
        e.append({"x": x / res.segmentacion.escala, "y": y / res.segmentacion.escala,
                  "clase": a.clase})
    return {"objetos": e}


def test_todo_correcto(cfg, calib):
    res = analizar(escena(OBJS), calib, cfg)
    r = emparejar(res, etiqueta_perfecta(res), cfg)
    m = metricas([r], list(cfg["clases"]))
    assert m["deteccion"]["precision"] == 1 and m["deteccion"]["recall"] == 1
    assert m["clasificacion"]["exactitud"] == 1
    assert m["escenas_inventario_exacto"] == 1


def test_errores_contados(cfg, calib):
    res = analizar(escena(OBJS), calib, cfg)
    et = etiqueta_perfecta(res)
    et["objetos"][0]["clase"] = "almendra"            # error de clasificación
    falso = et["objetos"].pop()                          # detección sin etiqueta -> FP
    et["no_detectados"] = {"cacahuete": 1}               # fruto no detectado -> FN
    r = emparejar(res, et, cfg)
    m = metricas([r], list(cfg["clases"]))
    assert m["deteccion"] == {**m["deteccion"], "tp": 2, "fp": 1, "fn": 1}
    assert m["clasificacion"]["aciertos"] == 1
    assert m["escenas_inventario_exacto"] == 0
    assert falso["clase"] in r["falsos"]


def test_punto_interior_del_anacardo_esta_dentro(cfg, calib):
    import cv2
    res = analizar(escena([("anacardo", 250, 250, 0)]), calib, cfg)
    o = res.objetos[0].objeto
    assert cv2.pointPolygonTest(o.contorno, punto_interior(o), False) > 0
