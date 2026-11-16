"""Formas de codificación: cómo se convierte cada instrucción en opcodes reales.

Una "forma" describe la plantilla de bytes de una instrucción 8086:

    [prefijo] opcode [ModR/M + desplazamiento] [inmediato | desplazamiento relativo]

Por ejemplo  ADD r/m16, imm8  ->  83 /0 ib  (opcode 83, campo reg del ModR/M = 0,
y un inmediato de 1 byte).  El codegen elige la forma (esta tabla) y luego
rellena los huecos con los valores reales.
"""
from dataclasses import dataclass, replace

from . import tablas
from .nodos import OpReg, OpImm, OpMem


@dataclass(frozen=True)
class Forma:
    texto: str                 # descripción legible, ej. "ADD r/m16, imm8"
    opcode: bytes              # bytes fijos al inicio
    modrm: object = None       # None = sin ModR/M | "reg" = campo reg es un registro | 0..7 = extensión /n
    op_rm: int = 0             # índice del operando que va en r/m
    op_reg: int = 1            # índice del operando que va en el campo reg
    op_en_opcode: int = -1     # índice del registro que se suma al último byte del opcode
    op_imm: int = -1           # índice del operando inmediato
    tam_imm: int = 0           # tamaño del inmediato (1 o 2 bytes)
    rel: int = 0               # desplazamiento relativo de salto: 0 = no, 1 = rel8, 2 = rel16
    op_moffs: int = -1         # operando de memoria directa codificado como dirección de 16 bits

    def codificacion(self):
        """Notación estilo manual de Intel: 83 /0 ib, B0+r ib, 8B /r, EB cb…"""
        partes = [f"{b:02X}" for b in self.opcode]
        if self.op_en_opcode >= 0 and partes:
            partes[-1] += "+r"
        if self.modrm is not None:
            partes.append("/r" if self.modrm == "reg" else f"/{self.modrm}")
        if self.op_moffs >= 0:
            partes.append("dw")
        if self.op_imm >= 0:
            partes.append("ib" if self.tam_imm == 1 else "iw")
        if self.rel:
            partes.append("cb" if self.rel == 1 else "cw")
        return " ".join(partes)


def _cabe_en_imm8(v):
    """¿Se puede escribir como inmediato de 8 bits con extensión de signo?"""
    return v is not None and (-128 <= v <= 127 or 0xFF80 <= v <= 0xFFFF)


def _sfx(t):
    return "8" if t == 1 else "16"


def elegir_forma(inst, largo=False):
    """Elige la forma de codificación de una instrucción ya validada por el semantic.

    largo=True pide la versión de salto de mayor alcance (la usa la optimización).
    """
    f = _base(inst, largo)
    if inst.prefijo:
        f = replace(f, opcode=bytes([tablas.PREFIJOS[inst.prefijo]]) + f.opcode,
                    texto=f"{inst.prefijo.upper()} {f.texto}")
    return f


def _base(inst, largo):
    m = inst.mnem
    ops = inst.operandos
    t = inst.tam
    M = m.upper()

    if m in tablas.SIN_OPERANDOS:
        return Forma(M, tablas.SIN_OPERANDOS[m])
    if m in tablas.ALU:
        return _alu(m, ops, t)
    if m == "mov":
        return _mov(ops, t)
    if m in tablas.INCDEC:
        k = tablas.INCDEC[m]
        if isinstance(ops[0], OpReg) and t == 2:
            return Forma(f"{M} r16", bytes([0x40 + 8 * k]), op_en_opcode=0)
        return Forma(f"{M} r/m{_sfx(t)}", b"\xFE" if t == 1 else b"\xFF", modrm=k, op_rm=0)
    if m in tablas.GRUPO3:
        return Forma(f"{M} r/m{_sfx(t)}", b"\xF6" if t == 1 else b"\xF7",
                     modrm=tablas.GRUPO3[m], op_rm=0)
    if m in tablas.DESPLAZ:
        k = tablas.DESPLAZ[m]
        w = 0 if t == 1 else 1
        if inst.cuenta == "cl":
            return Forma(f"{M} r/m{_sfx(t)}, CL", bytes([0xD2 + w]), modrm=k, op_rm=0)
        return Forma(f"{M} r/m{_sfx(t)}, 1", bytes([0xD0 + w]), modrm=k, op_rm=0)
    if m == "test":
        return _test(ops, t)
    if m == "xchg":
        return _xchg(ops, t)
    if m == "lea":
        return Forma("LEA r16, m", b"\x8D", modrm="reg", op_rm=1, op_reg=0)
    if m in ("push", "pop"):
        return _pila(m, ops[0])
    if m in ("jmp", "call"):
        if isinstance(ops[0], OpImm):
            if m == "call":
                return Forma("CALL rel16", b"\xE8", rel=2)
            if largo:
                return Forma("JMP near rel16", b"\xE9", rel=2)
            return Forma("JMP short rel8", b"\xEB", rel=1)
        return Forma(f"{M} r/m16 (indirecto)", b"\xFF",
                     modrm=4 if m == "jmp" else 2, op_rm=0)
    if m in tablas.JCC:
        op = tablas.JCC[m]
        if largo:   # el 8086 solo tiene saltos condicionales cortos: se invierte la condición y se salta con JMP
            return Forma(f"{M} lejano (salto corto inverso + JMP rel16)",
                         bytes([op ^ 1, 0x03, 0xE9]), rel=2)
        return Forma(f"{M} short rel8", bytes([op]), rel=1)
    if m in tablas.LOOPS:
        return Forma(f"{M} rel8", bytes([tablas.LOOPS[m]]), rel=1)
    if m == "int":
        return Forma("INT imm8", b"\xCD", op_imm=0, tam_imm=1)
    if m == "ret":
        if ops:
            return Forma("RET imm16", b"\xC2", op_imm=0, tam_imm=2)
        return Forma("RET", b"\xC3")
    if m == "retf":
        if ops:
            return Forma("RETF imm16", b"\xCA", op_imm=0, tam_imm=2)
        return Forma("RETF", b"\xCB")
    raise ValueError(f"no hay forma de codificación para '{m}'")


def _alu(m, ops, t):
    n = tablas.ALU[m]
    M = m.upper()
    d, s = ops
    sfx = _sfx(t)
    if isinstance(s, OpImm):
        if t == 1:
            if isinstance(d, OpReg) and d.nombre == "al":
                return Forma(f"{M} AL, imm8", bytes([n * 8 + 4]), op_imm=1, tam_imm=1)
            return Forma(f"{M} r/m8, imm8", b"\x80", modrm=n, op_rm=0, op_imm=1, tam_imm=1)
        if s.pura and _cabe_en_imm8(s.valor):
            return Forma(f"{M} r/m16, imm8", b"\x83", modrm=n, op_rm=0, op_imm=1, tam_imm=1)
        if isinstance(d, OpReg) and d.nombre == "ax":
            return Forma(f"{M} AX, imm16", bytes([n * 8 + 5]), op_imm=1, tam_imm=2)
        return Forma(f"{M} r/m16, imm16", b"\x81", modrm=n, op_rm=0, op_imm=1, tam_imm=2)
    w = 0 if t == 1 else 1
    if isinstance(d, OpMem) or isinstance(s, OpReg):
        return Forma(f"{M} r/m{sfx}, r{sfx}", bytes([n * 8 + w]), modrm="reg", op_rm=0, op_reg=1)
    return Forma(f"{M} r{sfx}, r/m{sfx}", bytes([n * 8 + 2 + w]), modrm="reg", op_rm=1, op_reg=0)


def _mov(ops, t):
    d, s = ops
    if isinstance(d, OpReg) and d.es_seg:
        return Forma("MOV sreg, r/m16", b"\x8E", modrm="reg", op_rm=1, op_reg=0)
    if isinstance(s, OpReg) and s.es_seg:
        return Forma("MOV r/m16, sreg", b"\x8C", modrm="reg", op_rm=0, op_reg=1)
    sfx = _sfx(t)
    if isinstance(s, OpImm):
        if isinstance(d, OpReg):
            return Forma(f"MOV r{sfx}, imm{sfx}", bytes([0xB0 if t == 1 else 0xB8]),
                         op_en_opcode=0, op_imm=1, tam_imm=t)
        return Forma(f"MOV r/m{sfx}, imm{sfx}", b"\xC6" if t == 1 else b"\xC7",
                     modrm=0, op_rm=0, op_imm=1, tam_imm=t)
    # AL/AX <-> memoria directa: existe una forma más corta (A0..A3)
    if (isinstance(d, OpReg) and d.nombre in ("al", "ax")
            and isinstance(s, OpMem) and s.directa):
        return Forma(f"MOV {d.nombre.upper()}, [dirección]",
                     b"\xA0" if t == 1 else b"\xA1", op_moffs=1)
    if (isinstance(s, OpReg) and s.nombre in ("al", "ax")
            and isinstance(d, OpMem) and d.directa):
        return Forma(f"MOV [dirección], {s.nombre.upper()}",
                     b"\xA2" if t == 1 else b"\xA3", op_moffs=0)
    w = 0 if t == 1 else 1
    if isinstance(d, OpMem) or isinstance(s, OpReg):
        return Forma(f"MOV r/m{sfx}, r{sfx}", bytes([0x88 + w]), modrm="reg", op_rm=0, op_reg=1)
    return Forma(f"MOV r{sfx}, r/m{sfx}", bytes([0x8A + w]), modrm="reg", op_rm=1, op_reg=0)


def _test(ops, t):
    d, s = ops
    sfx = _sfx(t)
    if isinstance(s, OpImm):
        if isinstance(d, OpReg) and d.nombre in ("al", "ax"):
            return Forma(f"TEST {d.nombre.upper()}, imm{sfx}", b"\xA8" if t == 1 else b"\xA9",
                         op_imm=1, tam_imm=t)
        return Forma(f"TEST r/m{sfx}, imm{sfx}", b"\xF6" if t == 1 else b"\xF7",
                     modrm=0, op_rm=0, op_imm=1, tam_imm=t)
    w = 0 if t == 1 else 1
    if isinstance(d, OpReg) and isinstance(s, OpMem):
        return Forma(f"TEST r/m{sfx}, r{sfx}", bytes([0x84 + w]), modrm="reg", op_rm=1, op_reg=0)
    return Forma(f"TEST r/m{sfx}, r{sfx}", bytes([0x84 + w]), modrm="reg", op_rm=0, op_reg=1)


def _xchg(ops, t):
    a, b = ops
    if t == 2:
        for i, o in enumerate((a, b)):
            otro = b if i == 0 else a
            if isinstance(o, OpReg) and o.nombre == "ax" and isinstance(otro, OpReg):
                return Forma("XCHG AX, r16", b"\x90", op_en_opcode=1 - i)
    sfx = _sfx(t)
    w = 0 if t == 1 else 1
    if isinstance(a, OpMem):
        rm, reg = 0, 1          # XCHG mem, reg
    else:
        rm, reg = 1, 0          # XCHG reg, mem  y  XCHG reg, reg (como hace NASM)
    return Forma(f"XCHG r/m{sfx}, r{sfx}", bytes([0x86 + w]), modrm="reg", op_rm=rm, op_reg=reg)


def _pila(m, o):
    M = m.upper()
    if isinstance(o, OpReg) and o.es_seg:
        base = 0x06 if m == "push" else 0x07
        return Forma(f"{M} {o.nombre.upper()}", bytes([base + 8 * o.num]))
    if isinstance(o, OpReg):
        return Forma(f"{M} r16", b"\x50" if m == "push" else b"\x58", op_en_opcode=0)
    if m == "push":
        return Forma("PUSH r/m16", b"\xFF", modrm=6, op_rm=0)
    return Forma("POP r/m16", b"\x8F", modrm=0, op_rm=0)
