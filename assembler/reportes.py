"""Textos que muestran el resultado de cada etapa en la interfaz.

Cada función recibe el Resultado de compilar() y devuelve un texto listo para
mostrarse en una pestaña (Lexer, Parser, Semantic, CodeGen).
"""
from .codegen import hex_bytes, volcado_hex
from .errores import LEXICO, SINTACTICO, SEMANTICO, CODEGEN
from .expresiones import expr_a_texto, texto_instruccion, texto_operando
from .lexer import NL, EOF, NUM, CADENA
from .nodos import (Num, Cadena, Simbolo, Aqui, Unario, Binario, OpReg, OpImm, OpMem,
                    Instruccion, Datos, Reserva, Equ, Org, Bits, Linea, Programa)

LINEA = "═" * 78


def _titulo(texto, subtitulo=""):
    s = f"{LINEA}\n  {texto}\n"
    if subtitulo:
        s += f"  {subtitulo}\n"
    return s + f"{LINEA}\n"


def _diagnosticos_de(res, fase):
    ds = res.diagnosticos.de_fase(fase)
    if not ds:
        return "\n✓ Sin errores ni avisos en esta etapa.\n"
    return "\n" + "\n".join(("✗ " if d.gravedad == "error" else "⚠ ") + str(d) for d in ds) + "\n"


def _no_ejecutada(res, nombre):
    return (_titulo(nombre) +
            f"\n(Esta etapa no se ejecutó porque la etapa «{res.fase_fallida}» tuvo errores.\n"
            " Corrija esos errores y vuelva a compilar.)\n")


# ======================= Etapa 1: Lexer =======================
def _valor_token(t):
    if t.tipo == NUM:
        return f"{t.valor}  (0x{t.valor:X})"
    if t.tipo == CADENA:
        return repr(t.valor)
    return "" if t.valor is None or t.valor == t.lexema else str(t.valor)


def texto_lexico(res):
    if res.tokens is None:
        return _no_ejecutada(res, "ETAPA 1 — LEXER")
    toks = res.tokens
    util = [t for t in toks if t.tipo not in (NL, EOF)]
    s = _titulo("ETAPA 1 — LEXER (análisis léxico)",
                f"Texto fuente  ──►  lista de tokens   ({len(util)} tokens)")
    s += f"\n{'#':>4}  {'Pos':<7} {'Tipo':<8} {'Lexema':<22} Valor\n"
    s += f"{'-' * 4}  {'-' * 7} {'-' * 8} {'-' * 22} {'-' * 20}\n"
    for i, t in enumerate(toks, 1):
        if t.tipo == EOF:
            lex = "(fin del archivo)"
        elif t.tipo == NL:
            lex = "↵ fin de línea"
        else:
            lex = t.lexema if len(t.lexema) <= 22 else t.lexema[:19] + "..."
        s += f"{i:>4}  {f'{t.linea}:{t.col}':<7} {t.tipo:<8} {lex:<22} {_valor_token(t)}\n"
    return s + _diagnosticos_de(res, LEXICO)


# ======================= Etapa 2: Parser =======================
def _desc(n, dec):
    if isinstance(n, str):
        return n
    if isinstance(n, Programa):
        return f"Programa  ({len(n.lineas)} líneas con contenido)"
    if isinstance(n, Linea):
        return f"Línea {n.num}" + (f"   etiqueta «{n.etiqueta}»" if n.etiqueta else "")
    if isinstance(n, Instruccion):
        ext = f"   [tamaño de la operación: {n.tam * 8} bits]" if dec and n.tam else ""
        return f"Instrucción {n.prefijo.upper() + ' ' if n.prefijo else ''}{n.mnem.upper()}{ext}"
    if isinstance(n, OpReg):
        tipo = "segmento" if n.es_seg else f"{n.tam * 8} bits"
        return f"Operando registro {n.nombre.upper()} ({tipo})"
    if isinstance(n, OpImm):
        ext = ""
        if dec:
            ext = f"   → constante = {n.valor}" if n.pura else "   → depende de una dirección"
        modif = f" {n.modif}" if n.modif else ""
        return f"Operando inmediato{modif}{ext}"
    if isinstance(n, OpMem):
        ext = ""
        if dec:
            ext = f"   → {n.tam * 8} bits" if n.tam else "   → tamaño no determinado"
        decl = f" {'byte' if n.tam_decl == 1 else 'word'}" if n.tam_decl else ""
        return f"Operando memoria{decl}{ext}"
    if isinstance(n, Datos):
        pref = f"times {expr_a_texto(n.veces)} " if n.veces is not None else ""
        return f"Directiva {pref}{'DB' if n.tam == 1 else 'DW'}"
    if isinstance(n, Reserva):
        return f"Directiva {'RESB' if n.tam == 1 else 'RESW'}"
    if isinstance(n, Equ):
        return f"Directiva EQU  (constante «{n.nombre}»)"
    if isinstance(n, Org):
        return "Directiva ORG"
    if isinstance(n, Bits):
        return f"Directiva BITS {n.valor}"
    if isinstance(n, Num):
        return f"Número {n.valor}"
    if isinstance(n, Cadena):
        return f"Cadena \"{n.texto}\""
    if isinstance(n, Simbolo):
        return f"Símbolo «{n.nombre}»"
    if isinstance(n, Aqui):
        return "Posición actual ($)"
    if isinstance(n, Unario):
        return f"Operador unario «{n.op}»"
    if isinstance(n, Binario):
        return f"Operador «{n.op}»"
    return type(n).__name__


def _hijos(n):
    if isinstance(n, Programa):
        return list(n.lineas)
    if isinstance(n, Linea):
        return [n.sentencia] if n.sentencia is not None else []
    if isinstance(n, Instruccion):
        return list(n.operandos)
    if isinstance(n, OpImm):
        return [n.expr]
    if isinstance(n, OpMem):
        return [f"Registro {r.upper()}" for r in n.regs] + ([n.disp] if n.disp is not None else [])
    if isinstance(n, Datos):
        return list(n.items)
    if isinstance(n, Reserva):
        return [n.cantidad]
    if isinstance(n, (Equ, Org)):
        return [n.expr]
    if isinstance(n, Unario):
        return [n.e]
    if isinstance(n, Binario):
        return [n.i, n.d]
    return []


def _arbol(nodo, dec, salida, prefijo="", ultimo=True, raiz=True):
    if raiz:
        salida.append(_desc(nodo, dec))
        nuevo = ""
    else:
        salida.append(prefijo + ("└─ " if ultimo else "├─ ") + _desc(nodo, dec))
        nuevo = prefijo + ("   " if ultimo else "│  ")
    hijos = _hijos(nodo)
    for i, h in enumerate(hijos):
        _arbol(h, dec, salida, nuevo, i == len(hijos) - 1, raiz=False)


def texto_sintactico(res):
    if res.programa is None:
        return _no_ejecutada(res, "ETAPA 2 — PARSER")
    dec = res.tabla is not None
    s = _titulo("ETAPA 2 — PARSER (análisis sintáctico)",
                "Lista de tokens  ──►  AST (Árbol de Sintaxis Abstracta)")
    if dec:
        s += "  (el árbol ya incluye las anotaciones del análisis semántico: → ...)\n"
    s += "\n"
    lineas = []
    _arbol(res.programa, dec, lineas)
    return s + "\n".join(lineas) + "\n" + _diagnosticos_de(res, SINTACTICO)


# ======================= Etapa 3: Semantic =======================
def _clase(op):
    if isinstance(op, OpReg):
        return "sreg" if op.es_seg else f"reg{op.tam * 8}"
    if isinstance(op, OpImm):
        return f"imm = {op.valor}" if op.pura else "imm = dirección"
    tam = f"{op.tam * 8}b" if op.tam else "?"
    modo = "directa" if op.directa else "+".join(op.regs)
    return f"mem{tam} ({modo})"


def texto_semantico(res):
    if res.tabla is None:
        return _no_ejecutada(res, "ETAPA 3 — SEMANTIC")
    s = _titulo("ETAPA 3 — SEMANTIC (análisis semántico)",
                "AST  ──►  Tabla de Símbolos + tipos/tamaños validados")
    s += "\nTABLA DE SÍMBOLOS\n"
    s += f"  {'Nombre':<22} {'Tipo':<10} {'Tamaño':<8} {'Valor/Dir.':<11} {'Línea':>5} {'Usos':>5}\n"
    s += f"  {'-' * 22} {'-' * 10} {'-' * 8} {'-' * 11} {'-' * 5} {'-' * 5}\n"
    if len(res.tabla) == 0:
        s += "  (no hay símbolos definidos)\n"
    for e in res.tabla:
        tam = f"{e.tam * 8} bits" if e.tam else "-"
        v = res.tabla.valor_seguro(e)
        if v is None:
            val = "-"
        elif e.tipo == "constante":
            val = str(v)
        else:
            val = f"{v:04X}h"
        s += f"  {e.nombre:<22} {e.tipo:<10} {tam:<8} {val:<11} {e.linea:>5} {e.usos:>5}\n"

    s += "\nVERIFICACIÓN DE TIPOS Y TAMAÑOS (instrucciones)\n"
    s += f"  {'Línea':>5}  {'Instrucción':<30} {'Operandos validados':<44} Tamaño\n"
    s += f"  {'-' * 5}  {'-' * 30} {'-' * 44} {'-' * 8}\n"
    hay = False
    for linea in res.programa.lineas:
        i = linea.sentencia
        if isinstance(i, Instruccion):
            hay = True
            clases = ", ".join(_clase(o) for o in i.operandos) or "(sin operandos)"
            tam = f"{i.tam * 8} bits" if i.tam else "-"
            s += f"  {linea.num:>5}  {texto_instruccion(i):<30} {clases:<44} {tam}\n"
    if not hay:
        s += "  (no hay instrucciones)\n"
    s += f"\nOrigen del programa: {res.origen:04X}h\n"
    return s + _diagnosticos_de(res, SEMANTICO)


# ======================= Etapa 4: CodeGen =======================
def texto_codegen(res):
    cg = res.codegen
    if cg is None:
        return _no_ejecutada(res, "ETAPA 4 — CODEGEN")
    info = cg.optimizacion
    s = _titulo("ETAPA 4 — CODEGEN (generación de código)",
                "AST decorado  ──►  código intermedio  ──►  optimización  ──►  opcodes reales")

    s += "\n4.1  CÓDIGO INTERMEDIO  (forma de codificación elegida para cada instrucción)\n"
    s += f"  {'#':>3} {'Línea':>5}  {'Elemento':<9} {'Intermedio':<30} {'Forma  →  Codificación'}\n"
    s += f"  {'-' * 3} {'-' * 5}  {'-' * 9} {'-' * 30} {'-' * 36}\n"
    for it in cg.items:
        if it.forma is not None:
            extra = f"{it.forma.texto}  →  {it.forma.codificacion()}"
            if it.relajable:
                extra += f"   [{'larga' if it.largo else 'corta'}]"
        else:
            extra = ""
        s += f"  {it.indice + 1:>3} {it.linea:>5}  {it.tipo:<9} {it.texto[:30]:<30} {extra}\n"

    s += "\n4.2  OPTIMIZACIÓN\n"
    s += f"  a) Plegado de constantes: {len(info.plegados)} expresión(es) simplificada(s)\n"
    for linea, antes, despues in info.plegados:
        s += f"       línea {linea}:  {antes}   →   {despues}\n"
    s += (f"  b) Relajación de saltos: {info.pasadas} pasada(s) hasta que ningún salto cambia de tamaño\n")
    for linea, texto, dist in info.ampliados:
        s += (f"       línea {linea}: {texto} pasó a forma larga "
              f"(el destino está a {dist} bytes; el alcance corto es -128..127)\n")
    if info.saltos:
        for linea, texto, forma, tam in info.saltos:
            s += f"       línea {linea:>3}  {texto:<28} forma {forma:<5} ({tam} bytes)\n"
    else:
        s += "       (no hay saltos que optimizar)\n"
    s += f"  Tamaño total del programa: {info.tam_total} bytes\n"

    if cg.codigo is None:
        return s + _diagnosticos_de(res, CODEGEN)
    s += "\n4.3  OPCODES  (listado: línea, dirección, bytes generados)\n\n"
    s += cg.listado + "\n"
    s += "\n4.4  VOLCADO HEXADECIMAL DEL ARCHIVO .COM\n\n"
    s += volcado_hex(cg.codigo, res.origen) + "\n"
    s += f"\nTotal: {len(cg.codigo)} bytes   (carga en {res.origen:04X}h, termina en " \
         f"{res.origen + len(cg.codigo) - 1:04X}h)\n" if cg.codigo else ""
    return s + _diagnosticos_de(res, CODEGEN)
