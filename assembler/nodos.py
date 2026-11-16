"""Nodos del Árbol de Sintaxis Abstracta (AST).

El parser construye estos nodos; el análisis semántico los "decora" con
información extra (tamaños, si un valor es constante, etc.); el codegen los
recorre para generar código.
"""
from dataclasses import dataclass, field


# ======================= Expresiones =======================
@dataclass
class Num:
    valor: int
    linea: int = 0
    col: int = 0
    texto: str = ""           # cómo se escribió (ej. "09h"); vacío si lo calculó el compilador


@dataclass
class Cadena:
    texto: str
    linea: int = 0
    col: int = 0


@dataclass
class Simbolo:
    nombre: str
    linea: int = 0
    col: int = 0
    calificado: str = ""      # lo llena el semantic (nombre completo si es etiqueta local)


@dataclass
class Aqui:                   # el símbolo '$' (dirección actual)
    linea: int = 0
    col: int = 0


@dataclass
class Unario:
    op: str
    e: object
    linea: int = 0
    col: int = 0


@dataclass
class Binario:
    op: str
    i: object
    d: object
    linea: int = 0
    col: int = 0


# ======================= Operandos =======================
@dataclass
class OpReg:
    nombre: str
    num: int
    tam: int                  # 1 = 8 bits, 2 = 16 bits
    es_seg: bool = False
    linea: int = 0
    col: int = 0


@dataclass
class OpImm:
    expr: object
    modif: str = ""           # "short" o "near" (solo en saltos)
    linea: int = 0
    col: int = 0
    # --- los llena el semantic ---
    pura: bool = False        # True si es una constante (no depende de direcciones)
    valor: object = None      # valor numérico si es constante


@dataclass
class OpMem:
    regs: list                # registros dentro de los corchetes, ej. ["bx", "si"]
    disp: object              # expresión del desplazamiento (o None)
    tam_decl: object = None   # tamaño escrito por el usuario: byte/word
    linea: int = 0
    col: int = 0
    # --- los llena el semantic ---
    tam: object = None        # tamaño final (declarado o inferido de la variable)
    rm: object = None         # campo r/m del ModR/M (None = dirección directa)
    directa: bool = False     # [etiqueta] sin registros
    disp_pura: bool = True
    disp_valor: int = 0


# ======================= Sentencias =======================
@dataclass
class Instruccion:
    mnem: str
    operandos: list
    prefijo: str = ""
    linea: int = 0
    col: int = 0
    tam: object = None        # tamaño de la operación (lo llena el semantic)
    cuenta: str = ""          # en desplazamientos: "1" o "cl"


@dataclass
class Datos:                  # db / dw (con times opcional)
    tam: int                  # 1 = db, 2 = dw
    items: list
    veces: object = None
    linea: int = 0
    col: int = 0
    veces_valor: int = 1


@dataclass
class Reserva:                # resb / resw
    tam: int
    cantidad: object
    linea: int = 0
    col: int = 0
    cantidad_valor: int = 0


@dataclass
class Equ:
    nombre: str
    expr: object
    linea: int = 0
    col: int = 0
    calificado: str = ""


@dataclass
class Org:
    expr: object
    linea: int = 0
    col: int = 0
    valor: object = None


@dataclass
class Bits:
    valor: int
    linea: int = 0
    col: int = 0


# --- dialecto MASM ---
@dataclass
class Modelo:                 # .model small
    nombre: str = ""
    linea: int = 0
    col: int = 0


@dataclass
class Pila:                   # .stack 64
    expr: object = None
    linea: int = 0
    col: int = 0


@dataclass
class Seccion:                # .data / .code
    nombre: str = ""
    linea: int = 0
    col: int = 0


@dataclass
class ProcIni:                # nombre proc [far|near]
    nombre: str = ""
    distancia: str = ""
    linea: int = 0
    col: int = 0


@dataclass
class ProcFin:                # nombre endp
    nombre: str = ""
    linea: int = 0
    col: int = 0


@dataclass
class Fin:                    # end [etiqueta]
    etiqueta: str = ""
    linea: int = 0
    col: int = 0


@dataclass
class Linea:
    num: int
    etiqueta: object = None
    etiqueta_col: int = 0
    sentencia: object = None
    ambito: str = ""               # etiqueta global vigente (para etiquetas locales)
    seccion: str = ""              # "code" / "data" (dialecto MASM)
    etiqueta_calificada: str = ""


@dataclass
class Programa:
    lineas: list = field(default_factory=list)
    masm: bool = False             # True si el programa usa '.model' (dialecto MASM)
