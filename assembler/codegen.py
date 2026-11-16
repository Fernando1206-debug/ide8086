"""ETAPA 4 — CodeGen (generación de código).

Entrada : el AST decorado y la tabla de símbolos del semantic.
Salida  : código intermedio y el ensamblado a opcodes reales (bytes de un .COM).

Subetapas:

  4.1 Código intermedio : cada línea del AST se convierte en un "item" con la
      forma de codificación elegida (ej. ADD r/m16, imm8 -> 83 /0 ib).
  4.2 Optimización      : (a) plegado de constantes: 2*3+1 -> 7
                          (b) relajación de saltos: cada JMP/Jcc usa la forma corta
                              (2 bytes) y solo pasa a la larga si el destino está lejos.
                              Como alargar un salto mueve las direcciones de todo lo
                              que sigue, se repite hasta que nada cambia (punto fijo).
  4.3 Opcodes           : con las direcciones finales se calculan los bytes reales:
                          opcode + ModR/M + desplazamiento + inmediato.
  4.4 Listado           : tabla  línea | dirección | bytes | fuente, y volcado hexadecimal.
"""
from dataclasses import dataclass, field

from . import tablas
from .errores import CODEGEN
from .expresiones import (ErrorExpresion, evaluar, plegar, expr_a_texto,
                          texto_instruccion, bytes_de_cadena)
from .formas import elegir_forma
from .nodos import (Cadena, OpReg, OpImm, OpMem, Instruccion, Datos, Reserva, Equ)


class ErrorGeneracion(Exception):
    """Problema al generar los bytes (salto fuera de alcance, valor que no cabe…)."""


# =============================================================================
# 4.1  CÓDIGO INTERMEDIO
# =============================================================================
@dataclass
class ItemIR:
    indice: int
    linea: int
    tipo: str                     # "etiqueta" | "inst" | "datos" | "reserva" | "equ"
    nodo: object = None
    texto: str = ""
    forma: object = None          # Forma elegida (solo instrucciones)
    nombre: str = ""              # etiquetas y constantes: nombre calificado
    relajable: bool = False       # JMP / Jcc con etiqueta: puede ser corto o largo
    largo: bool = False
    dir: int = 0                  # dirección asignada
    tam: int = 0                  # tamaño en bytes
    bytes_: bytes = b""


def generar_intermedio(programa):
    """Convierte el AST en una lista lineal de items con su forma de codificación."""
    items = []

    def nuevo(linea, tipo, nodo=None, **kw):
        it = ItemIR(len(items), linea, tipo, nodo, **kw)
        items.append(it)
        return it

    for linea in programa.lineas:
        if linea.etiqueta_calificada:
            nuevo(linea.num, "etiqueta", nombre=linea.etiqueta_calificada,
                  texto=f"{linea.etiqueta}:")
        s = linea.sentencia
        if isinstance(s, Instruccion):
            it = nuevo(linea.num, "inst", s, forma=elegir_forma(s), texto=texto_instruccion(s))
            if s.operandos and isinstance(s.operandos[0], OpImm) and \
                    (s.mnem == "jmp" or s.mnem in tablas.JCC):
                it.relajable = True
                if s.operandos[0].modif == "near":
                    it.largo = True
                    it.forma = elegir_forma(s, largo=True)
        elif isinstance(s, Datos):
            cuerpo = ", ".join(expr_a_texto(i) for i in s.items)
            pref = f"TIMES {expr_a_texto(s.veces)} " if s.veces is not None else ""
            nuevo(linea.num, "datos", s, texto=f"{pref}{'DB' if s.tam == 1 else 'DW'} {cuerpo}")
        elif isinstance(s, Reserva):
            nuevo(linea.num, "reserva", s,
                  texto=f"{'RESB' if s.tam == 1 else 'RESW'} {expr_a_texto(s.cantidad)}")
        elif isinstance(s, Equ):
            nuevo(linea.num, "equ", s, nombre=s.calificado,
                  texto=f"{s.nombre} EQU {expr_a_texto(s.expr)}")
    return items


# =============================================================================
# 4.3  OPCODES  (se define antes porque la optimización necesita medir tamaños)
# =============================================================================
def _le(valor, n):
    """Entero a n bytes little-endian, comprobando que quepa."""
    lo, hi = (-128, 255) if n == 1 else (-32768, 65535)
    if not lo <= valor <= hi:
        raise ErrorGeneracion(f"el valor {valor} no cabe en {n * 8} bits")
    return (valor & ((1 << (8 * n)) - 1)).to_bytes(n, "little")


def _valor_desplazamiento(op, resolver, aqui):
    if op.disp is None:
        return 0
    return op.disp_valor if op.disp_pura else resolver(op.disp, aqui)


def _modrm(reg, rm_op, resolver, aqui):
    """Byte ModR/M (+ desplazamiento) para un operando registro o memoria.

    ModR/M = mod(2 bits) | reg(3 bits) | r/m(3 bits)
      mod=11  r/m es un registro
      mod=00  memoria sin desplazamiento (rm=110 -> dirección directa de 16 bits)
      mod=01  memoria + desplazamiento de 8 bits
      mod=10  memoria + desplazamiento de 16 bits
    """
    if isinstance(rm_op, OpReg):
        return bytes([0xC0 | (reg << 3) | rm_op.num])
    if rm_op.rm is None:                                   # [dirección]
        d = _valor_desplazamiento(rm_op, resolver, aqui)
        return bytes([(reg << 3) | 0x06]) + _le(d, 2)
    rm = rm_op.rm
    if rm_op.disp is None or (rm_op.disp_pura and rm_op.disp_valor == 0):
        if rm == 6:                                        # [bp] no existe sin desplazamiento
            return bytes([0x40 | (reg << 3) | rm, 0])
        return bytes([(reg << 3) | rm])
    if rm_op.disp_pura and -128 <= rm_op.disp_valor <= 127:
        return bytes([0x40 | (reg << 3) | rm]) + _le(rm_op.disp_valor, 1)
    d = _valor_desplazamiento(rm_op, resolver, aqui)
    return bytes([0x80 | (reg << 3) | rm]) + _le(d, 2)


def codificar(item, resolver, verificar=True):
    """Bytes de una instrucción: opcode + ModR/M + inmediato / desplazamiento relativo."""
    forma = item.forma
    ops = item.nodo.operandos
    salida = bytearray(forma.opcode)
    if forma.op_en_opcode >= 0:                             # registro dentro del opcode (ej. B8+r)
        salida[-1] += ops[forma.op_en_opcode].num
    if forma.modrm is not None:
        reg = forma.modrm if isinstance(forma.modrm, int) else ops[forma.op_reg].num
        salida += _modrm(reg, ops[forma.op_rm], resolver, item.dir)
    if forma.op_moffs >= 0:
        salida += _le(_valor_desplazamiento(ops[forma.op_moffs], resolver, item.dir), 2)
    if forma.op_imm >= 0:
        op = ops[forma.op_imm]
        valor = op.valor if op.pura else resolver(op.expr, item.dir)
        if forma.tam_imm == 1 and item.nodo.tam == 2:
            # forma "r/m16, imm8": el CPU extiende el signo del byte a 16 bits
            # (la forma solo se elige si el valor es -128..127 ó FF80h..FFFFh)
            salida.append(valor & 0xFF)
        else:
            salida += _le(valor, forma.tam_imm)
    if forma.rel:
        destino = resolver(ops[0].expr, item.dir)
        desp = destino - (item.dir + len(salida) + forma.rel)   # relativo al fin de la instrucción
        if forma.rel == 1:
            if verificar and not -128 <= desp <= 127:
                raise ErrorGeneracion(
                    f"el salto está demasiado lejos ({desp} bytes; el alcance corto es de -128 a 127). "
                    "Use JMP para llegar a destinos lejanos")
            salida += _le(max(-128, min(127, desp)), 1)
        else:
            salida += _le(desp & 0xFFFF, 2)
    return bytes(salida)


def bytes_datos(item, resolver):
    s = item.nodo
    una = bytearray()
    for it in s.items:
        if isinstance(it, Cadena) and s.tam == 1:
            una += bytes_de_cadena(it.texto)
        else:
            una += _le(resolver(it, item.dir), s.tam)
    return bytes(una) * (s.veces_valor if s.veces is not None else 1)


def _sin_valores(expr, aqui):
    return 0


def tam_item(item):
    """Tamaño en bytes de un item. No depende de los valores, solo de la forma elegida."""
    if item.tipo == "inst":
        return len(codificar(item, _sin_valores, verificar=False))
    if item.tipo == "datos":
        return len(bytes_datos(item, _sin_valores))
    if item.tipo == "reserva":
        return item.nodo.tam * item.nodo.cantidad_valor
    return 0


def asignar_direcciones(items, tabla, origen):
    """Recorre los items asignando direcciones. Devuelve el tamaño total."""
    d = origen
    for it in items:
        it.dir = d
        if it.tipo == "etiqueta":
            tabla.buscar(it.nombre).valor = d
        elif it.tipo == "equ":
            ent = tabla.buscar(it.nombre)
            ent.aqui = d
            if not ent.pura:
                ent.valor = None
        it.tam = tam_item(it)
        d += it.tam
    return d - origen


def crear_resolver(tabla):
    """Función que evalúa una expresión usando los valores de la tabla de símbolos."""
    def valor(nodo):
        ent = tabla.buscar(nodo.calificado)
        if ent is None:
            raise ErrorExpresion(f"símbolo '{nodo.nombre}' no definido")
        return tabla.valor_de(ent)

    def resolver(expr, aqui):
        return evaluar(expr, valor, aqui)
    return resolver


# =============================================================================
# 4.2  OPTIMIZACIÓN
# =============================================================================
@dataclass
class InfoOptimizacion:
    plegados: list = field(default_factory=list)    # (línea, antes, después)
    pasadas: int = 0
    ampliados: list = field(default_factory=list)   # (línea, instrucción, distancia)
    saltos: list = field(default_factory=list)      # (línea, instrucción, "corto"/"largo", bytes)
    tam_total: int = 0


def _plegar_constantes(items, tabla, info):
    def valor_constante(nodo):
        ent = tabla.buscar(nodo.calificado)
        try:
            if ent is not None and ent.tipo == "constante" and tabla.es_pura(ent):
                return tabla.valor_de(ent)
        except ErrorExpresion:
            pass
        return None

    def plegar_expr(expr, linea):
        nueva, n = plegar(expr, valor_constante)
        if n:
            info.plegados.append((linea, expr_a_texto(expr), expr_a_texto(nueva)))
        return nueva

    for it in items:
        s = it.nodo
        if it.tipo == "inst":
            for op in s.operandos:
                if isinstance(op, OpImm):
                    op.expr = plegar_expr(op.expr, it.linea)
                elif isinstance(op, OpMem) and op.disp is not None:
                    op.disp = plegar_expr(op.disp, it.linea)
        elif it.tipo == "datos":
            s.items = [i if isinstance(i, Cadena) else plegar_expr(i, it.linea) for i in s.items]


def _relajar_saltos(items, tabla, origen, info, diag):
    saltos = [it for it in items if it.relajable]
    resolver = crear_resolver(tabla)
    while True:
        info.pasadas += 1
        info.tam_total = asignar_direcciones(items, tabla, origen)
        cambio = False
        for it in saltos:
            if it.largo:
                continue
            op = it.nodo.operandos[0]
            try:
                destino = resolver(op.expr, it.dir)
            except ErrorExpresion as e:
                diag.error(CODEGEN, str(e), it.linea)
                return
            distancia = destino - (it.dir + it.tam)
            if -128 <= distancia <= 127 or op.modif == "short":
                continue
            it.largo = True
            it.forma = elegir_forma(it.nodo, largo=True)
            info.ampliados.append((it.linea, it.texto, distancia))
            cambio = True
        if not cambio:
            break
    info.saltos = [(it.linea, it.texto, "largo" if it.largo else "corto", it.tam)
                   for it in saltos]


def optimizar(items, tabla, origen, diag):
    info = InfoOptimizacion()
    _plegar_constantes(items, tabla, info)
    _relajar_saltos(items, tabla, origen, info, diag)
    return info


# =============================================================================
# 4.3  ENSAMBLADO FINAL
# =============================================================================
def ensamblar(items, tabla, origen, diag):
    """Genera los bytes definitivos. Devuelve bytes o None si hubo errores."""
    asignar_direcciones(items, tabla, origen)
    resolver = crear_resolver(tabla)
    salida = bytearray()
    ok = True
    for it in items:
        try:
            if it.tipo == "inst":
                it.bytes_ = codificar(it, resolver)
            elif it.tipo == "datos":
                it.bytes_ = bytes_datos(it, resolver)
            elif it.tipo == "reserva":
                it.bytes_ = bytes(it.tam)
            elif it.tipo == "equ":
                tabla.valor_de(tabla.buscar(it.nombre))
                it.bytes_ = b""
            else:
                it.bytes_ = b""
        except (ErrorExpresion, ErrorGeneracion) as e:
            diag.error(CODEGEN, str(e), it.linea)
            ok = False
            continue
        if len(it.bytes_) != it.tam:
            diag.error(CODEGEN, f"error interno: se calcularon {it.tam} bytes pero se "
                       f"generaron {len(it.bytes_)}", it.linea)
            ok = False
            continue
        salida += it.bytes_
    if ok and origen + len(salida) > 0x10000:
        diag.error(CODEGEN, "el programa no cabe en un segmento de 64 KB", 0)
        ok = False
    return bytes(salida) if ok else None


# =============================================================================
# 4.4  LISTADO Y VOLCADO
# =============================================================================
def hex_bytes(b):
    return " ".join(f"{x:02X}" for x in b)


def listado(items, fuente):
    """Tabla: nº de línea | dirección | bytes | texto fuente."""
    lineas = fuente.split("\n")
    por_linea = {}
    for it in items:
        e = por_linea.setdefault(it.linea, [it.dir, b""])
        e[1] += it.bytes_
    salida = [" Línea  Dir.   Bytes             Fuente",
              "-----  -----  ----------------  " + "-" * 30]
    for n, texto in enumerate(lineas, 1):
        if n == len(lineas) and texto == "":
            break
        if n in por_linea and por_linea[n][1]:
            dir_, datos = por_linea[n]
            filas = [datos[i:i + 6] for i in range(0, len(datos), 6)]
            salida.append(f"{n:5d}  {dir_:04X}   {hex_bytes(filas[0]):<16}  {texto}")
            for k, fila in enumerate(filas[1:], 1):
                if len(filas) > 4 and k == 3:        # líneas con muchísimos bytes: se resumen
                    salida.append(f"       ....   ({len(datos) - 18} bytes más)")
                    break
                salida.append(f"       {dir_ + 6 * k:04X}   {hex_bytes(fila):<16}")
        elif n in por_linea:
            salida.append(f"{n:5d}  {por_linea[n][0]:04X}   {'':<16}  {texto}")
        else:
            salida.append(f"{n:5d}                              {texto}")
    return "\n".join(salida)


def volcado_hex(codigo, origen):
    """Volcado estilo editor hexadecimal: dirección | 16 bytes | texto ASCII."""
    filas = []
    for i in range(0, len(codigo), 16):
        trozo = codigo[i:i + 16]
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in trozo)
        filas.append(f"{origen + i:04X}  {hex_bytes(trozo):<47}  {ascii_}")
    return "\n".join(filas)


# =============================================================================
# Fachada
# =============================================================================
@dataclass
class ResultadoCodegen:
    items: list
    optimizacion: InfoOptimizacion
    codigo: object = None          # bytes del .COM (None si hubo errores)
    listado: str = ""
    origen: int = 0x100


def generar_codigo(programa, tabla, origen, diag, fuente):
    items = generar_intermedio(programa)                 # 4.1
    info = optimizar(items, tabla, origen, diag)         # 4.2
    codigo = None
    texto = ""
    if not diag.hay_errores:
        codigo = ensamblar(items, tabla, origen, diag)   # 4.3
        if codigo is not None:
            texto = listado(items, fuente)               # 4.4
    return ResultadoCodegen(items, info, codigo, texto, origen)
