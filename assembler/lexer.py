"""ETAPA 1 — Lexer (análisis léxico).

Entrada : el texto del programa en ensamblador.
Salida  : una lista de Tokens.

El lexer lee el texto carácter por carácter y lo agrupa en "palabras" con
significado (tokens): registros, instrucciones, números, cadenas, símbolos…
Los comentarios (desde ';' hasta el fin de línea) y los espacios se descartan.
Si encuentra algo que no pertenece al lenguaje, reporta un error léxico y sigue.
"""
import re
from dataclasses import dataclass

from . import tablas
from .errores import LEXICO

# ---------- Tipos de token ----------
IDENT = "IDENT"          # nombre definido por el usuario: etiqueta, variable…
INSTR = "INSTR"          # instrucción: mov, add, jmp…
REG = "REG"              # registro: ax, bl, ds…
DIRECT = "DIRECT"        # directiva: org, db, dw, equ…
TAMANO = "TAMANO"        # byte / word
MODIF = "MODIF"          # short / near
PREFIJO = "PREFIJO"      # rep, repe, repne…
NUM = "NUM"              # número
CADENA = "CADENA"        # "texto" o 'A'
COMA, DOSPUNTOS = ",", ":"
LCORCH, RCORCH = "[", "]"
LPAREN, RPAREN = "(", ")"
MAS, MENOS, POR, DIV, MOD = "+", "-", "*", "/", "%"
DOLAR = "$"
NL = "NL"                # fin de línea
EOF = "EOF"              # fin del archivo

_SIMBOLOS = {",": COMA, ":": DOSPUNTOS, "[": LCORCH, "]": RCORCH, "(": LPAREN,
             ")": RPAREN, "+": MAS, "-": MENOS, "*": POR, "/": DIV, "%": MOD}

_RE_IDENT = re.compile(r"[A-Za-z_.?@][A-Za-z0-9_.?@$#~]*")
_RE_NUMERO = re.compile(r"[0-9][0-9A-Za-z_]*")


@dataclass
class Token:
    tipo: str
    lexema: str       # el texto tal como se escribió
    valor: object     # número, texto de la cadena o nombre normalizado
    linea: int
    col: int


def _convertir_numero(texto):
    """Convierte 123, 0x1F, 1Fh, 1010b, 0b1010 o 12d. Devuelve None si está mal formado."""
    s = texto.lower()
    if "_" in s:
        return None
    try:
        if s.startswith("0x") and len(s) > 2:
            return int(s[2:], 16)
        if s.endswith("h") and len(s) > 1:
            return int(s[:-1], 16)
        if s.startswith("0b") and len(s) > 2 and set(s[2:]) <= set("01"):
            return int(s[2:], 2)
        if s.endswith("b") and len(s) > 1 and set(s[:-1]) <= set("01"):
            return int(s[:-1], 2)
        if s.endswith("d") and len(s) > 1:
            return int(s[:-1], 10)
        return int(s, 10)
    except ValueError:
        return None


def _clasificar(lexema):
    """Decide si una palabra es registro, instrucción, directiva… o un nombre del usuario."""
    bajo = lexema.lower()
    if bajo in tablas.REGISTROS:
        return REG, bajo
    if bajo in tablas.PREFIJOS:
        return PREFIJO, bajo
    if bajo in tablas.MNEMONICOS:
        return INSTR, bajo
    if bajo in tablas.DIRECTIVAS:
        return DIRECT, bajo
    if bajo in tablas.TAMANOS:
        return TAMANO, bajo
    if bajo in tablas.MODIFICADORES:
        return MODIF, bajo
    return IDENT, lexema


def analizar_lexico(fuente, diag):
    """Convierte el texto fuente en una lista de tokens (termina con EOF)."""
    tokens = []
    # Dialecto MASM: si hay '.model', los nombres no distinguen mayúsculas de minúsculas
    masm = re.search(r"^[ \t]*\.model\b", fuente, re.I | re.M) is not None
    n = len(fuente)
    i = 0
    linea = 1
    inicio_linea = 0

    def col(pos):
        return pos - inicio_linea + 1

    while i < n:
        c = fuente[i]

        if c == "\n":
            tokens.append(Token(NL, "\\n", None, linea, col(i)))
            i += 1
            linea += 1
            inicio_linea = i
            continue

        if c in " \t\r\f\v":                 # espacios: se ignoran
            i += 1
            continue

        if c == ";":                         # comentario: hasta el fin de línea
            while i < n and fuente[i] != "\n":
                i += 1
            continue

        if c in "'\"":                       # cadena entre comillas
            fin_linea = fuente.find("\n", i + 1)
            if fin_linea == -1:
                fin_linea = n
            j = fuente.find(c, i + 1)
            if j == -1 or j > fin_linea:
                diag.error(LEXICO, "cadena sin cerrar (falta la comilla de cierre)",
                           linea, col(i))
                i = fin_linea
                continue
            tokens.append(Token(CADENA, fuente[i:j + 1], fuente[i + 1:j], linea, col(i)))
            i = j + 1
            continue

        if c.isdigit() and c.isascii():      # número
            m = _RE_NUMERO.match(fuente, i)
            lexema = m.group()
            valor = _convertir_numero(lexema)
            if valor is None:
                diag.error(LEXICO, f"número mal formado '{lexema}' "
                           "(use 123, 0x1F, 1Fh, 1010b)", linea, col(i))
            else:
                tokens.append(Token(NUM, lexema, valor, linea, col(i)))
            i = m.end()
            continue

        if c == "$":                         # '$' = dirección actual
            if fuente[i + 1:i + 2] == "$":
                diag.error(LEXICO, "'$$' no está soportado", linea, col(i))
                i += 2
            else:
                tokens.append(Token(DOLAR, "$", None, linea, col(i)))
                i += 1
            continue

        m = _RE_IDENT.match(fuente, i)
        if m and c.isascii():                # palabra: registro, instrucción o nombre
            lexema = m.group()
            tipo, valor = _clasificar(lexema)
            if tipo == IDENT and masm:
                valor = lexema.lower()
            tokens.append(Token(tipo, lexema, valor, linea, col(i)))
            i = m.end()
            continue

        if c in _SIMBOLOS:                   # símbolos de un carácter
            tokens.append(Token(_SIMBOLOS[c], c, None, linea, col(i)))
            i += 1
            continue

        diag.error(LEXICO, f"carácter no válido '{c}'", linea, col(i))
        i += 1

    tokens.append(Token(EOF, "", None, linea, col(i)))
    return tokens
