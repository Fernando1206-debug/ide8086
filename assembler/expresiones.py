"""Expresiones aritméticas: recorrer, evaluar, mostrar y plegar constantes.

Las usan el semantic (para saber si un valor es constante), el codegen (para
calcular valores finales) y la optimización (plegado de constantes).
"""
from .nodos import (Num, Cadena, Simbolo, Aqui, Unario, Binario,
                    OpReg, OpImm, OpMem)


class ErrorExpresion(Exception):
    """Problema al evaluar una expresión (símbolo no definido, división entre 0…)."""


def recorrer(expr):
    """Genera todos los nodos de una expresión (recorrido en preorden)."""
    yield expr
    if isinstance(expr, Unario):
        yield from recorrer(expr.e)
    elif isinstance(expr, Binario):
        yield from recorrer(expr.i)
        yield from recorrer(expr.d)


def bytes_de_cadena(texto):
    """Bytes de una cadena en la página de códigos de DOS (CP437)."""
    try:
        return texto.encode("cp437")
    except UnicodeEncodeError as e:
        raise ErrorExpresion(
            f"el carácter '{texto[e.start]}' no existe en la página de códigos de DOS (CP437)")


def evaluar(expr, valor_simbolo, aqui=None):
    """Calcula el valor entero de una expresión.

    valor_simbolo(nodo) -> int   resuelve un símbolo.
    aqui                          valor de '$' (None si no se permite).
    """
    if isinstance(expr, Num):
        return expr.valor
    if isinstance(expr, Cadena):
        b = bytes_de_cadena(expr.texto)
        if len(b) == 0:
            raise ErrorExpresion("una cadena vacía no tiene valor numérico")
        if len(b) > 2:
            raise ErrorExpresion(
                "una cadena usada como número admite máximo 2 caracteres (16 bits)")
        return int.from_bytes(b, "little")
    if isinstance(expr, Simbolo):
        if valor_simbolo is None:
            raise ErrorExpresion(f"no se puede usar el símbolo '{expr.nombre}' aquí")
        return valor_simbolo(expr)
    if isinstance(expr, Aqui):
        if aqui is None:
            raise ErrorExpresion("'$' no se puede usar aquí")
        return aqui
    if isinstance(expr, Unario):
        v = evaluar(expr.e, valor_simbolo, aqui)
        return -v if expr.op == "-" else v
    if isinstance(expr, Binario):
        a = evaluar(expr.i, valor_simbolo, aqui)
        b = evaluar(expr.d, valor_simbolo, aqui)
        if expr.op == "+":
            return a + b
        if expr.op == "-":
            return a - b
        if expr.op == "*":
            return a * b
        if expr.op in ("/", "%"):
            if b == 0:
                raise ErrorExpresion("división entre cero")
            q = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                q = -q
            return q if expr.op == "/" else a - q * b
    raise ErrorExpresion("expresión no válida")


# ---------- Mostrar expresiones y operandos como texto ----------
def _par(e):
    t = expr_a_texto(e)
    return f"({t})" if isinstance(e, Binario) else t


def expr_a_texto(e):
    if isinstance(e, Num):
        return e.texto or str(e.valor)
    if isinstance(e, Cadena):
        return '"' + e.texto + '"'
    if isinstance(e, Simbolo):
        return e.nombre
    if isinstance(e, Aqui):
        return "$"
    if isinstance(e, Unario):
        return f"{e.op}{_par(e.e)}"
    if isinstance(e, Binario):
        return f"{_par(e.i)} {e.op} {_par(e.d)}"
    return "?"


def texto_operando(op):
    if isinstance(op, OpReg):
        return op.nombre.upper()
    if isinstance(op, OpImm):
        return (op.modif + " " if op.modif else "") + expr_a_texto(op.expr)
    if isinstance(op, OpMem):
        partes = [r.upper() for r in op.regs]
        if op.disp is not None:
            partes.append(expr_a_texto(op.disp))
        cuerpo = "+".join(partes).replace("+-", "-")
        prefijo = {1: "byte ", 2: "word "}.get(op.tam_decl, "")
        return f"{prefijo}[{cuerpo}]"
    return "?"


def texto_instruccion(inst):
    ops = ", ".join(texto_operando(o) for o in inst.operandos)
    pref = inst.prefijo.upper() + " " if inst.prefijo else ""
    return f"{pref}{inst.mnem.upper()}" + (f" {ops}" if ops else "")


# ---------- Optimización: plegado de constantes ----------
def plegar(expr, valor_constante):
    """Reemplaza los subárboles constantes por un solo número.

    valor_constante(nodo_simbolo) -> int | None   (valor de una constante 'equ').
    Devuelve (nueva_expresion, cantidad_de_reemplazos).
    """
    if isinstance(expr, Binario):
        i, ci = plegar(expr.i, valor_constante)
        d, cd = plegar(expr.d, valor_constante)
        if isinstance(i, (Num, Cadena)) and isinstance(d, (Num, Cadena)):
            try:
                v = evaluar(Binario(expr.op, i, d), None)
                return Num(v, expr.linea, expr.col), ci + cd + 1
            except ErrorExpresion:
                pass
        return Binario(expr.op, i, d, expr.linea, expr.col), ci + cd
    if isinstance(expr, Unario):
        e, c = plegar(expr.e, valor_constante)
        if isinstance(e, (Num, Cadena)):
            try:
                v = evaluar(Unario(expr.op, e), None)
                return Num(v, expr.linea, expr.col), c + 1
            except ErrorExpresion:
                pass
        return Unario(expr.op, e, expr.linea, expr.col), c
    if isinstance(expr, Simbolo):
        v = valor_constante(expr)
        if v is not None:
            return Num(v, expr.linea, expr.col), 1
    return expr, 0
