"""Pipeline completo del compilador.

    Código ASM 8086
         │
         ▼
    1. Lexer    (lexer.py)     ──► lista de Tokens
         │
         ▼
    2. Parser   (parser.py)    ──► AST (Árbol de Sintaxis Abstracta)
         │
         ▼
    3. Semantic (semantic.py)  ──► Tabla de Símbolos + tipos/tamaños validados
         │
         ▼
    4. CodeGen  (codegen.py)   ──► código intermedio → optimización → opcodes reales

Cada etapa solo se ejecuta si las anteriores terminaron sin errores.
"""
from dataclasses import dataclass

from .codegen import generar_codigo
from .errores import (Diagnosticos, ERROR, LEXICO, SINTACTICO, SEMANTICO, CODEGEN)
from .lexer import analizar_lexico
from .parser import analizar_sintaxis
from .semantic import analizar_semantica


@dataclass
class Resultado:
    fuente: str
    diagnosticos: Diagnosticos
    tokens: object = None          # etapa 1
    programa: object = None        # etapa 2 (AST)
    tabla: object = None           # etapa 3
    origen: int = 0x100
    codegen: object = None         # etapa 4
    fase_fallida: str = ""

    @property
    def codigo(self):
        return self.codegen.codigo if self.codegen else None

    @property
    def exito(self):
        return self.codigo is not None and not self.diagnosticos.hay_errores


def _etapa(res, nombre, funcion):
    """Ejecuta una etapa; si falla por un bug interno lo reporta en vez de cerrar el programa."""
    try:
        return funcion()
    except Exception as e:  # noqa: BLE001 - el IDE nunca debe cerrarse por un error del compilador
        res.diagnosticos.error(nombre, f"error interno del compilador ({type(e).__name__}: {e})")
        return None


def compilar(fuente):
    fuente = fuente.replace("\r\n", "\n").replace("\r", "\n")
    diag = Diagnosticos()
    res = Resultado(fuente, diag)

    # ---- 1. Lexer ----
    res.tokens = _etapa(res, LEXICO, lambda: analizar_lexico(fuente, diag))
    if res.tokens is None:
        res.fase_fallida = LEXICO
        return res
    lineas_con_error_lexico = {d.linea for d in diag if d.fase == LEXICO and d.gravedad == ERROR}

    # ---- 2. Parser ----
    diag_sintaxis = Diagnosticos()
    res.programa = _etapa(res, SINTACTICO, lambda: analizar_sintaxis(res.tokens, diag_sintaxis))
    for d in diag_sintaxis:      # evita errores en cascada en líneas que ya fallaron en el lexer
        if d.linea not in lineas_con_error_lexico:
            diag.append(d)
    if diag.hay_errores or res.programa is None:
        res.fase_fallida = diag.primera_fase_con_errores() or SINTACTICO
        return res

    # ---- 3. Semantic ----
    r = _etapa(res, SEMANTICO, lambda: analizar_semantica(res.programa, diag))
    if r is not None:
        res.tabla, res.origen = r
    if diag.hay_errores or res.tabla is None:
        res.fase_fallida = diag.primera_fase_con_errores() or SEMANTICO
        return res

    # ---- 4. CodeGen ----
    res.codegen = _etapa(res, CODEGEN,
                         lambda: generar_codigo(res.programa, res.tabla, res.origen, diag, fuente))
    if diag.hay_errores or res.codegen is None:
        res.fase_fallida = diag.primera_fase_con_errores() or CODEGEN
    return res
