"""Nivel 3: conteo, distribución y lote."""
import pytest

from src.interpretacion import interpretar, resumen_texto


def test_conteo_y_distribucion(cfg):
    r = interpretar(["nuez", "nuez", "avellana", "almendra"], cfg)
    assert r["total"] == 4
    assert r["conteo"]["nuez"] == 2 and r["conteo"]["anacardo"] == 0
    assert sum(r["distribucion_pct"].values()) == pytest.approx(100)
    assert r["distribucion_pct"]["nuez"] == pytest.approx(50)
    assert sum(r["distribucion_peso_pct"].values()) == pytest.approx(100)
    assert r["mayoritarias"] == ["nuez"]


def test_desconocidos_no_cuentan_en_la_distribucion(cfg):
    r = interpretar(["nuez", "desconocido"], cfg)
    assert r["total"] == 1 and r["desconocidos"] == 1
    assert r["distribucion_pct"]["nuez"] == pytest.approx(100)


def test_escena_vacia(cfg):
    r = interpretar([], cfg)
    assert r["total"] == 0 and r["mayoritarias"] == []
    assert "Total: 0" in resumen_texto(r)


def test_lote_correcto_e_incorrecto(cfg):
    cfg["interpretacion"]["lote_esperado"] = {"nuez": 1, "avellana": 2}
    ok = interpretar(["nuez", "avellana", "avellana"], cfg)
    assert ok["lote"]["correcto"]
    mal = interpretar(["nuez", "avellana", "almendra"], cfg)
    assert not mal["lote"]["correcto"]
    assert mal["lote"]["faltan"] == {"avellana": 1}
    assert mal["lote"]["sobran"] == {"almendra": 1}
    assert "INCORRECTO" in resumen_texto(mal)


def test_objeto_extrano_invalida_el_lote(cfg):
    cfg["interpretacion"]["lote_esperado"] = {"nuez": 1}
    assert not interpretar(["nuez", "desconocido"], cfg)["lote"]["correcto"]
