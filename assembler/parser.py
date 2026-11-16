"""ETAPA 2 — Parser (análisis sintáctico).

Entrada : la lista de tokens del lexer.
Salida  : un AST (Árbol de Sintaxis Abstracta) definido en nodos.py.

Es un parser de descenso recursivo: cada regla de la gramática es un método.

Gramática (EBNF):

    programa    := { linea }
    linea       := [ ETIQUETA ':' ] [ sentencia ] FIN_LINEA
                 | NOMBRE ( 'db' | 'dw' | 'resb' | 'resw' ) ...   (dato con nombre)
                 | NOMBRE 'equ' expresion                        (constante)
    sentencia   := [ PREFIJO ] INSTRUCCION [ operando { ',' operando } ]
                 | 'org' expresion | 'bits' NUMERO
                 | ( 'db' | 'dw' ) elemento { ',' elemento }
                 | ( 'resb' | 'resw' ) expresion
                 | 'times' expresion ( 'db' | 'dw' ) elemento { ',' elemento }
    operando    := REGISTRO | [ 'short' | 'near' ] expresion | [ TAMAÑO ] memoria
    memoria     := '[' termino_dir { ('+' | '-') termino_dir } ']'
    termino_dir := REGISTRO | termino
    expresion   := termino { ('+' | '-') termino }
    termino     := unario { ('*' | '/' | '%') unario }
    unario      := ('-' | '+') unario | primario
    primario    := NUMERO | CADENA | NOMBRE | '$' | '(' expresion ')'

Si hay un error de sintaxis, se reporta y el parser se "sincroniza": descarta
el resto de la línea y continúa con la siguiente (así encuentra varios errores).
"""
from difflib import get_close_matches

from . import tablas
from .errores import SINTACTICO
from .lexer import (IDENT, INSTR, REG, DIRECT, TAMANO, MODIF, PREFIJO, NUM, CADENA,
                    COMA, DOSPUNTOS, LCORCH, RCORCH, LPAREN, RPAREN,
                    MAS, MENOS, POR, DIV, MOD, DOLAR, NL, EOF)
from .nodos import (Num, Cadena, Simbolo, Aqui, Unario, Binario, OpReg, OpImm, OpMem,
                    Instruccion, Datos, Reserva, Equ, Org, Bits, Linea, Programa,
                    Modelo, Pila, Seccion, ProcIni, ProcFin, Fin)


class ErrorSintaxis(Exception):
    def __init__(self, mensaje, tok):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.tok = tok


def _describir(tok):
    return "el fin de la línea" if tok.tipo in (NL, EOF) else f"'{tok.lexema}'"


class Parser:
    def __init__(self, tokens, diag):
        self.t = tokens
        self.i = 0
        self.diag = diag
        self.masm = False

    # ---------- utilidades ----------
    def _tok(self):
        return self.t[self.i]

    def _sig(self):
        tok = self.t[self.i]
        if tok.tipo != EOF:
            self.i += 1
        return tok

    def _es(self, *tipos):
        return self.t[self.i].tipo in tipos

    def _esperar(self, tipo, que):
        if not self._es(tipo):
            raise ErrorSintaxis(f"se esperaba {que}, se encontró {_describir(self._tok())}",
                                self._tok())
        return self._sig()

    def _fin_linea(self):
        if not self._es(NL, EOF):
            raise ErrorSintaxis(
                f"se esperaba el fin de la línea, se encontró {_describir(self._tok())}",
                self._tok())
        if self._es(NL):
            self._sig()

    def _sincronizar(self):
        """Recuperación de errores: descarta tokens hasta el fin de la línea."""
        while not self._es(NL, EOF):
            self._sig()
        if self._es(NL):
            self._sig()

    # ---------- programa y líneas ----------
    def analizar(self):
        lineas = []
        while not self._es(EOF):
            if self._es(NL):
                self._sig()
                continue
            try:
                linea = self._linea()
                lineas.append(linea)
                if isinstance(linea.sentencia, Fin):      # 'end': lo que siga se ignora
                    break
            except ErrorSintaxis as e:
                self.diag.error(SINTACTICO, e.mensaje, e.tok.linea, e.tok.col)
                self._sincronizar()
        return Programa(lineas, masm=self.masm)

    def _mensaje_desconocido(self, tok):
        msg = f"'{tok.lexema}' no es una instrucción ni una directiva conocida"
        candidatos = sorted(tablas.MNEMONICOS | tablas.DIRECTIVAS)
        cerca = get_close_matches(tok.lexema.lower(), candidatos, n=1, cutoff=0.7)
        if cerca:
            return msg + f"; ¿quiso decir '{cerca[0]}'?"
        return msg + " (si es una etiqueta, termínela con ':')"

    def _linea(self):
        tok = self._tok()
        linea = Linea(num=tok.linea)

        sig0 = self.t[self.i + 1]
        if tok.tipo == DIRECT and tok.valor == "proc" and sig0.tipo == IDENT:   # proc nombre
            self._sig()
            self._sig()
            linea.etiqueta, linea.etiqueta_col = sig0.valor, sig0.col
            linea.sentencia = ProcIni(sig0.valor, self._distancia(), tok.linea, tok.col)
            self._fin_linea()
            return linea

        if tok.tipo == IDENT:
            sig = self.t[self.i + 1]
            if sig.tipo == DIRECT and sig.valor == "proc":    # nombre proc [far|near]
                self._sig()
                self._sig()
                linea.etiqueta, linea.etiqueta_col = tok.valor, tok.col
                linea.sentencia = ProcIni(tok.valor, self._distancia(), tok.linea, tok.col)
                self._fin_linea()
                return linea
            if sig.tipo == DIRECT and sig.valor == "endp":    # nombre endp
                self._sig()
                self._sig()
                linea.sentencia = ProcFin(tok.valor, tok.linea, tok.col)
                self._fin_linea()
                return linea
            if sig.tipo == DOSPUNTOS:                         # etiqueta:
                linea.etiqueta = tok.valor
                linea.etiqueta_col = tok.col
                self._sig()
                self._sig()
                if self._es(DIRECT) and self._tok().valor == "equ":   # nombre: equ valor
                    self._sig()
                    linea.etiqueta = None
                    linea.sentencia = Equ(tok.valor, self._expresion(), tok.linea, tok.col)
                    self._fin_linea()
                    return linea
            elif sig.tipo == DIRECT and sig.valor == "equ":    # nombre equ valor
                self._sig()
                self._sig()
                linea.sentencia = Equ(tok.valor, self._expresion(), tok.linea, tok.col)
                self._fin_linea()
                return linea
            elif sig.tipo == DIRECT and sig.valor in ("db", "dw", "resb", "resw", "times"):
                linea.etiqueta = tok.valor                     # nombre db ...
                linea.etiqueta_col = tok.col
                self._sig()
            else:
                raise ErrorSintaxis(self._mensaje_desconocido(tok), tok)

        if not self._es(NL, EOF):
            linea.sentencia = self._sentencia()
        self._fin_linea()
        return linea

    # ---------- sentencias ----------
    def _sentencia(self):
        tok = self._tok()
        if tok.tipo == PREFIJO:
            self._sig()
            if not self._es(INSTR):
                raise ErrorSintaxis(
                    f"después de '{tok.lexema}' debe ir una instrucción de cadena "
                    "(movsb, stosb, lodsb, cmpsb, scasb…)", self._tok())
            inst = self._instruccion()
            inst.prefijo = tok.valor
            return inst
        if tok.tipo == INSTR:
            return self._instruccion()
        if tok.tipo == DIRECT:
            return self._directiva()
        raise ErrorSintaxis(
            f"se esperaba una instrucción o directiva, se encontró {_describir(tok)}", tok)

    def _instruccion(self):
        tok = self._sig()
        ops = []
        if not self._es(NL, EOF):
            ops.append(self._operando())
            while self._es(COMA):
                self._sig()
                if len(ops) == 2:
                    raise ErrorSintaxis(
                        "demasiados operandos: el 8086 admite como máximo 2", self._tok())
                ops.append(self._operando())
        if self.masm and self._es(DOSPUNTOS) and ops and isinstance(ops[-1], OpImm):
            extra = self._sig()                   # 'je etiqueta:' -> sobra el ':'
            self.diag.aviso(SINTACTICO, "se ignoró el ':' que sobra después del operando",
                            extra.linea, extra.col)
        return Instruccion(tok.valor, ops, "", tok.linea, tok.col)

    def _directiva(self):
        tok = self._sig()
        d = tok.valor
        if d == "org":
            return Org(self._expresion(), tok.linea, tok.col)
        if d == "bits":
            n = self._esperar(NUM, "un número (por ejemplo 'bits 16')")
            return Bits(n.valor, tok.linea, tok.col)
        if d in ("db", "dw"):
            return self._datos(tok)
        if d in ("resb", "resw"):
            return Reserva(1 if d == "resb" else 2, self._expresion(), tok.linea, tok.col)
        if d == "times":
            veces = self._expresion()
            if not (self._es(DIRECT) and self._tok().valor in ("db", "dw")):
                raise ErrorSintaxis(
                    f"después de 'times' se esperaba 'db' o 'dw', se encontró "
                    f"{_describir(self._tok())}", self._tok())
            return self._datos(self._sig(), veces)
        if d in (".model", ".stack", ".data", ".code"):
            return self._directiva_masm(tok)
        if d == "endp":
            nombre = self._sig().valor if self._es(IDENT) else ""
            return ProcFin(nombre, tok.linea, tok.col)
        if d == "end":
            etiqueta = self._sig().valor if self._es(IDENT) else ""
            return Fin(etiqueta, tok.linea, tok.col)
        if d == "proc":
            raise ErrorSintaxis("'proc' necesita un nombre: 'nombre proc' o 'proc nombre'", tok)
        if d == "equ":
            raise ErrorSintaxis("'equ' necesita un nombre: 'nombre equ valor'", tok)
        raise ErrorSintaxis(f"'{tok.lexema}' no se puede usar aquí", tok)

    def _distancia(self):
        """Después de 'proc': far / near (se aceptan y se ignoran: un solo segmento)."""
        if self._es(DIRECT, MODIF) and self._tok().valor in ("far", "near"):
            return self._sig().valor
        return ""

    def _directiva_masm(self, tok):
        self.masm = True
        d = tok.valor
        if d == ".stack":
            expr = None if self._es(NL, EOF) else self._expresion()
            return Pila(expr, tok.linea, tok.col)
        nombre = self._tok().lexema if not self._es(NL, EOF) else ""
        while not self._es(NL, EOF):          # '.model small', '.data ...': se ignora el resto
            self._sig()
        if d == ".model":
            return Modelo(nombre, tok.linea, tok.col)
        return Seccion(d[1:], tok.linea, tok.col)

    def _datos(self, tok, veces=None):
        tam = 1 if tok.valor == "db" else 2
        items = []
        while True:
            t = self._tok()
            if t.tipo == CADENA and self.t[self.i + 1].tipo in (COMA, NL, EOF):
                self._sig()
                items.append(Cadena(t.valor, t.linea, t.col))
            else:
                e = self._expresion()
                if self._es(IDENT) and self._tok().valor.lower() == "dup" and not items:
                    self._sig()                       # n dup (valor, ...)
                    self._esperar(LPAREN, "'(' después de 'dup'")
                    dentro = self._datos(tok).items
                    self._esperar(RPAREN, "')'")
                    return Datos(tam, dentro, e, tok.linea, tok.col)
                items.append(e)
            if self._es(COMA):
                self._sig()
                continue
            break
        return Datos(tam, items, veces, tok.linea, tok.col)

    # ---------- operandos ----------
    def _operando(self):
        tok = self._tok()
        if tok.tipo == MODIF:
            self._sig()
            op = self._operando()
            if not isinstance(op, OpImm):
                raise ErrorSintaxis(f"'{tok.lexema}' solo se usa antes de la etiqueta de un salto", tok)
            op.modif = tok.valor
            return op
        if tok.tipo == DIRECT and tok.valor == "offset":      # offset variable
            self._sig()
            return OpImm(self._expresion(), "offset", tok.linea, tok.col)
        if tok.tipo == TAMANO:
            self._sig()
            if self._es(DIRECT) and self._tok().valor == "ptr":    # word ptr [bx]
                self._sig()
            if self._es(IDENT) and self.t[self.i + 1].tipo == LCORCH:
                mem = self._memoria_con_nombre()
                mem.tam_decl = tablas.TAMANOS[tok.valor]
                mem.linea, mem.col = tok.linea, tok.col
                return mem
            if not self._es(LCORCH):
                raise ErrorSintaxis(
                    f"después de '{tok.lexema}' se esperaba '[' (dirección de memoria)",
                    self._tok())
            mem = self._memoria()
            mem.tam_decl = tablas.TAMANOS[tok.valor]
            mem.linea, mem.col = tok.linea, tok.col
            return mem
        if tok.tipo == REG:
            self._sig()
            if self._es(MAS, MENOS, POR, DIV, MOD):
                raise ErrorSintaxis(
                    f"el registro '{tok.lexema}' no puede formar parte de una expresión "
                    "fuera de [ ]", self._tok())
            nombre = tok.valor
            if nombre in tablas.REG8:
                return OpReg(nombre, tablas.REG8[nombre], 1, False, tok.linea, tok.col)
            if nombre in tablas.REG16:
                return OpReg(nombre, tablas.REG16[nombre], 2, False, tok.linea, tok.col)
            return OpReg(nombre, tablas.SEGMENTO[nombre], 2, True, tok.linea, tok.col)
        if tok.tipo == LCORCH:
            return self._memoria()
        if tok.tipo == IDENT and self.t[self.i + 1].tipo == LCORCH:    # variable[2], tabla[bx]
            return self._memoria_con_nombre()
        return OpImm(self._expresion(), "", tok.linea, tok.col)

    def _memoria_con_nombre(self):
        nombre = self._sig()
        sym = Simbolo(nombre.valor, nombre.linea, nombre.col)
        mem = self._memoria()
        mem.disp = sym if mem.disp is None else Binario("+", sym, mem.disp, nombre.linea, nombre.col)
        mem.linea, mem.col = nombre.linea, nombre.col
        return mem

    def _memoria(self):
        ini = self._esperar(LCORCH, "'['")
        regs = []
        disp = None
        primero = True
        while True:
            tok = self._tok()
            signo = 1
            if tok.tipo in (MAS, MENOS):
                signo = 1 if tok.tipo == MAS else -1
                self._sig()
                tok = self._tok()
            elif not primero:
                raise ErrorSintaxis("se esperaba '+', '-' o ']' dentro de la dirección", tok)
            if tok.tipo == REG:
                if signo < 0:
                    raise ErrorSintaxis("no se puede restar un registro en una dirección", tok)
                regs.append(tok.valor)
                self._sig()
            else:
                t = self._termino()
                if signo > 0:
                    disp = t if disp is None else Binario("+", disp, t, tok.linea, tok.col)
                else:
                    disp = (Unario("-", t, tok.linea, tok.col) if disp is None
                            else Binario("-", disp, t, tok.linea, tok.col))
            primero = False
            if self._es(RCORCH):
                self._sig()
                break
            if not self._es(MAS, MENOS):
                raise ErrorSintaxis(
                    "se esperaba '+', '-' o ']' dentro de la dirección", self._tok())
        return OpMem(regs, disp, None, ini.linea, ini.col)

    # ---------- expresiones ----------
    def _expresion(self):
        izq = self._termino()
        while self._es(MAS, MENOS):
            op = self._sig()
            izq = Binario(op.lexema, izq, self._termino(), op.linea, op.col)
        return izq

    def _termino(self):
        izq = self._unario()
        while self._es(POR, DIV, MOD):
            op = self._sig()
            izq = Binario(op.lexema, izq, self._unario(), op.linea, op.col)
        return izq

    def _unario(self):
        if self._es(MENOS, MAS):
            op = self._sig()
            return Unario(op.lexema, self._unario(), op.linea, op.col)
        return self._primario()

    def _primario(self):
        tok = self._tok()
        if tok.tipo == NUM:
            self._sig()
            return Num(tok.valor, tok.linea, tok.col, tok.lexema)
        if tok.tipo == CADENA:
            self._sig()
            return Cadena(tok.valor, tok.linea, tok.col)
        if tok.tipo == IDENT:
            self._sig()
            if tok.lexema == "?":                 # dato sin inicializar (MASM): vale 0
                return Num(0, tok.linea, tok.col, "?")
            return Simbolo(tok.valor, tok.linea, tok.col)
        if tok.tipo == DOLAR:
            self._sig()
            return Aqui(tok.linea, tok.col)
        if tok.tipo == LPAREN:
            self._sig()
            e = self._expresion()
            self._esperar(RPAREN, "')'")
            return e
        if tok.tipo == REG:
            raise ErrorSintaxis(f"el registro '{tok.lexema}' no puede usarse aquí", tok)
        raise ErrorSintaxis(
            f"se esperaba un valor o expresión, se encontró {_describir(tok)}", tok)


def analizar_sintaxis(tokens, diag):
    """Construye el AST a partir de los tokens."""
    return Parser(tokens, diag).analizar()
