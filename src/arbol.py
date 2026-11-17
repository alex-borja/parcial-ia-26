"""Nivel 2 — Identificación con un árbol de decisión EXPLÍCITO.

El árbol no está escrito como una cadena de `if` en el código: se declara en
config.yaml (sección `arbol`), donde cada nodo lleva su característica, su
umbral y la justificación. Este módulo solo lo recorre y devuelve la clase
junto con la traza de decisiones, para poder explicar cada resultado.
"""
from dataclasses import dataclass, field

from .caracteristicas import CATALOGO

DESCONOCIDO = "desconocido"
OPERADORES = {">": lambda v, u: v > u, "<": lambda v, u: v < u}


@dataclass
class Decision:
    clase: str
    traza: list = field(default_factory=list)   # [(id, carac, valor, op, umbral, bool)]
    clase_arbol: str = ""                        # hoja alcanzada (antes de validar)
    motivo: str = ""                             # por qué es «desconocido»

    def texto_traza(self):
        pasos = [f"{i}: {c}={v:.3g} {op} {u} -> {'sí' if r else 'no'}"
                 for i, c, v, op, u, r in self.traza]
        fin = self.clase if not self.motivo else f"{self.clase} ({self.motivo})"
        return " | ".join(pasos + [fin])


def es_hoja(nodo):
    return "clase" in nodo


def validar_arbol(arbol, clases):
    """Comprueba la estructura del árbol. Lanza ValueError si algo falla."""
    ids = set()

    def visitar(n, ruta):
        if es_hoja(n):
            if n["clase"] not in clases:
                raise ValueError(f"{ruta}: clase {n['clase']!r} no está en `clases`")
            for c, r in (n.get("validar") or {}).items():
                if c not in CATALOGO:
                    raise ValueError(f"{ruta}: validar usa característica desconocida {c!r}")
                if len(r) != 2 or r[0] > r[1]:
                    raise ValueError(f"{ruta}: rango de validar mal formado: {r}")
            return
        for k in ("id", "caracteristica", "operador", "umbral", "si", "sino"):
            if k not in n:
                raise ValueError(f"{ruta}: al nodo le falta {k!r}")
        if n["id"] in ids:
            raise ValueError(f"id de nodo repetido: {n['id']}")
        ids.add(n["id"])
        if n["caracteristica"] not in CATALOGO:
            raise ValueError(f"{n['id']}: característica desconocida {n['caracteristica']!r}")
        if n["operador"] not in OPERADORES:
            raise ValueError(f"{n['id']}: operador {n['operador']!r} (usa '>' o '<')")
        visitar(n["si"], f"{n['id']}.si")
        visitar(n["sino"], f"{n['id']}.sino")

    visitar(arbol, "raíz")


def clasificar(caracteristicas, arbol):
    """Recorre el árbol con las características de un objeto -> Decision."""
    nodo, traza = arbol, []
    while not es_hoja(nodo):
        c, op, u = nodo["caracteristica"], nodo["operador"], nodo["umbral"]
        v = caracteristicas[c]
        r = OPERADORES[op](v, u)
        traza.append((nodo["id"], c, v, op, u, r))
        nodo = nodo["si"] if r else nodo["sino"]

    clase = nodo["clase"]
    for c, (lo, hi) in (nodo.get("validar") or {}).items():
        v = caracteristicas[c]
        if not lo <= v <= hi:
            return Decision(DESCONOCIDO, traza, clase,
                            f"{c}={v:.3g} fuera del rango medido de {clase} [{lo}, {hi}]")
    return Decision(clase, traza, clase)


def nodos(arbol):
    """Lista de nodos internos en preorden."""
    if es_hoja(arbol):
        return []
    return [arbol] + nodos(arbol["si"]) + nodos(arbol["sino"])


def clases_bajo(nodo):
    """Conjunto de clases alcanzables desde `nodo`."""
    if es_hoja(nodo):
        return {nodo["clase"]}
    return clases_bajo(nodo["si"]) | clases_bajo(nodo["sino"])


def a_mermaid(arbol):
    """Diagrama del árbol en sintaxis Mermaid (para el informe)."""
    lineas = ["flowchart TD"]
    contador = [0]

    def nombre_hoja():
        contador[0] += 1
        return f"H{contador[0]}"

    def visitar(n):
        if es_hoja(n):
            h = nombre_hoja()
            val = n.get("validar") or {}
            extra = "".join(f"<br/><small>{c} ∈ [{a}, {b}]</small>" for c, (a, b) in val.items())
            lineas.append(f'    {h}(["<b>{n["clase"].upper()}</b>{extra}"])')
            return h
        i = n["id"]
        op = {">": "#gt;", "<": "#lt;"}[n["operador"]]   # entidades de Mermaid
        lineas.append(f'    {i}{{"{i}: {n.get("pregunta", "")}<br/>'
                      f'{n["caracteristica"]} {op} {n["umbral"]}"}}')
        si, no = visitar(n["si"]), visitar(n["sino"])
        lineas.append(f"    {i} -->|sí| {si}")
        lineas.append(f"    {i} -->|no| {no}")
        return i

    visitar(arbol)
    return "\n".join(lineas)
