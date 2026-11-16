"""Tablas del lenguaje ensamblador 8086.

Todas las etapas consultan estas tablas: el lexer para clasificar palabras
(registro, instrucción, directiva…), el semantic para validar operandos y el
codegen para elegir los opcodes.
"""

# ---------- Registros (nombre -> número de 3 bits que se usa en el opcode) ----------
REG8 = {"al": 0, "cl": 1, "dl": 2, "bl": 3, "ah": 4, "ch": 5, "dh": 6, "bh": 7}
REG16 = {"ax": 0, "cx": 1, "dx": 2, "bx": 3, "sp": 4, "bp": 5, "si": 6, "di": 7}
SEGMENTO = {"es": 0, "cs": 1, "ss": 2, "ds": 3}
REGISTROS = {**REG8, **REG16, **SEGMENTO}

# ---------- Palabras reservadas que no son instrucciones ----------
TAMANOS = {"byte": 1, "word": 2}
MODIFICADORES = {"short", "near"}
DIRECTIVAS = {"org", "bits", "db", "dw", "equ", "resb", "resw", "times"}
# Dialecto MASM / emu8086 (se activa con '.model')
DIRECTIVAS_MASM = {".model", ".stack", ".data", ".code", "proc", "endp", "end",
                   "far", "offset", "ptr"}
DIRECTIVAS = DIRECTIVAS | DIRECTIVAS_MASM
PREFIJOS = {"rep": 0xF3, "repe": 0xF3, "repz": 0xF3, "repne": 0xF2, "repnz": 0xF2}

# ---------- Instrucciones sin operandos: mnemónico -> bytes ----------
SIN_OPERANDOS = {
    "nop": b"\x90", "hlt": b"\xF4", "wait": b"\x9B",
    "clc": b"\xF8", "stc": b"\xF9", "cmc": b"\xF5",
    "cld": b"\xFC", "std": b"\xFD", "cli": b"\xFA", "sti": b"\xFB",
    "cbw": b"\x98", "cwd": b"\x99",
    "pushf": b"\x9C", "popf": b"\x9D", "lahf": b"\x9F", "sahf": b"\x9E",
    "xlat": b"\xD7", "xlatb": b"\xD7",
    "movsb": b"\xA4", "movsw": b"\xA5", "cmpsb": b"\xA6", "cmpsw": b"\xA7",
    "stosb": b"\xAA", "stosw": b"\xAB", "lodsb": b"\xAC", "lodsw": b"\xAD",
    "scasb": b"\xAE", "scasw": b"\xAF",
    "daa": b"\x27", "das": b"\x2F", "aaa": b"\x37", "aas": b"\x3F",
    "aam": b"\xD4\x0A", "aad": b"\xD5\x0A",
    "iret": b"\xCF", "into": b"\xCE", "int3": b"\xCC",
}

# Instrucciones de cadena (las únicas que aceptan el prefijo rep/repe/repne)
CADENA = {"movsb", "movsw", "cmpsb", "cmpsw", "scasb", "scasw",
          "lodsb", "lodsw", "stosb", "stosw"}

# ---------- Familias de instrucciones (mnemónico -> número de extensión /n) ----------
ALU = {"add": 0, "or": 1, "adc": 2, "sbb": 3, "and": 4, "sub": 5, "xor": 6, "cmp": 7}
DESPLAZ = {"rol": 0, "ror": 1, "rcl": 2, "rcr": 3, "shl": 4, "sal": 4, "shr": 5, "sar": 7}
GRUPO3 = {"not": 2, "neg": 3, "mul": 4, "imul": 5, "div": 6, "idiv": 7}
INCDEC = {"inc": 0, "dec": 1}

# ---------- Saltos condicionales (opcode de la forma corta rel8) ----------
JCC = {
    "jo": 0x70, "jno": 0x71,
    "jb": 0x72, "jc": 0x72, "jnae": 0x72,
    "jnb": 0x73, "jae": 0x73, "jnc": 0x73,
    "je": 0x74, "jz": 0x74,
    "jne": 0x75, "jnz": 0x75,
    "jbe": 0x76, "jna": 0x76,
    "ja": 0x77, "jnbe": 0x77,
    "js": 0x78, "jns": 0x79,
    "jp": 0x7A, "jpe": 0x7A, "jnp": 0x7B, "jpo": 0x7B,
    "jl": 0x7C, "jnge": 0x7C,
    "jge": 0x7D, "jnl": 0x7D,
    "jle": 0x7E, "jng": 0x7E,
    "jg": 0x7F, "jnle": 0x7F,
}
LOOPS = {"loopne": 0xE0, "loopnz": 0xE0, "loope": 0xE1, "loopz": 0xE1,
         "loop": 0xE2, "jcxz": 0xE3}

OTROS = {"mov", "test", "xchg", "lea", "push", "pop", "jmp", "call",
         "ret", "retf", "int"}

MNEMONICOS = (set(SIN_OPERANDOS) | set(ALU) | set(DESPLAZ) | set(GRUPO3) |
              set(INCDEC) | set(JCC) | set(LOOPS) | OTROS)

# ---------- Direccionamiento: (base, índice) -> campo r/m del byte ModR/M ----------
RM_DIRECCION = {
    ("bx", "si"): 0, ("bx", "di"): 1, ("bp", "si"): 2, ("bp", "di"): 3,
    (None, "si"): 4, (None, "di"): 5, ("bp", None): 6, ("bx", None): 7,
}


def todas_las_instrucciones():
    """Lista ordenada de mnemónicos soportados (para el menú Ayuda)."""
    return sorted(MNEMONICOS | set(PREFIJOS))
