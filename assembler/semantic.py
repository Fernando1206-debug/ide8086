"""ETAPA 3 — Semantic (análisis semántico).

Entrada : el AST del parser.
Salida  : la Tabla de Símbolos y el AST "decorado" con tipos/tamaños validados.

El parser solo comprueba que el programa tenga la forma correcta. Aquí se
comprueba que además tenga sentido:

  Pasada 1 (declaraciones): se registran todas las etiquetas, variables y
      constantes en la tabla de símbolos y se detectan los duplicados.
  Pasada 2 (verificación): para cada sentencia se comprueba
      - que los símbolos usados existan,
      - que los operandos sean del tipo permitido por la instrucción,
      - que los tamaños (8/16 bits) sean compatibles,
      - que los valores inmediatos quepan en el tamaño de la operación,
      - que los modos de direccionamiento existan en el 8086.
  Además se decide qué expresiones son constantes y se infiere el tamaño de
  las variables ([mensaje] es de tamaño byte porque se declaró con db).
"""
from dataclasses import dataclass

from . import tablas
from .errores import SEMANTICO
from .expresiones import ErrorExpresion, evaluar, recorrer, bytes_de_cadena
from .nodos import (Num, Seccion, Cadena, Simbolo, Aqui, OpReg, OpImm, OpMem, Instruccion,
                    Datos, Reserva, Equ, Org, Bits)


# ======================= Tabla de símbolos =======================
@dataclass
class EntradaSimbolo:
    nombre: str
    tipo: str                  # "etiqueta" | "dato" | "constante"
    tam: object                # 1 o 2 si es una variable (db/dw); None en otro caso
    linea: int                 # línea donde se definió
    expr: object = None        # expresión (solo constantes 'equ')
    ambito: str = ""           # etiqueta global a la que pertenece
    pura: object = None        # constantes: True si no depende de direcciones
    valor: object = None       # dirección (etiquetas) o valor (constantes)
    aqui: object = None        # constantes: valor de '$' en su línea
    usos: int = 0              # cuántas veces se usa


class TablaSimbolos:
    def __init__(self):
        self.entradas = {}

    def definir(self, entrada):
        self.entradas[entrada.nombre] = entrada

    def buscar(self, nombre):
        return self.entradas.get(nombre)

    def __iter__(self):
        return iter(self.entradas.values())

    def __len__(self):
        return len(self.entradas)

    # --- ¿es una constante pura? (no depende de ninguna dirección) ---
    def es_pura(self, ent, pila=()):
        if ent.tipo != "constante":
            return False
        if ent.pura is not None:
            return ent.pura
        if ent.nombre in pila:
            raise ErrorExpresion(f"definición circular de '{ent.nombre}'")
        ent.pura = self.expr_pura(ent.expr, pila + (ent.nombre,))
        return ent.pura

    def expr_pura(self, expr, pila=()):
        for nodo in recorrer(expr):
            if isinstance(nodo, Aqui):
                return False
            if isinstance(nodo, Simbolo):
                ent = self.buscar(nodo.calificado)
                if ent is None or not self.es_pura(ent, pila):
                    return False
        return True

    # --- valor de un símbolo ---
    def valor_de(self, ent, pila=()):
        if ent.valor is not None and (ent.tipo != "constante" or ent.pura):
            return ent.valor
        if ent.tipo != "constante":
            raise ErrorExpresion(f"la dirección de '{ent.nombre}' todavía no se conoce")
        if ent.nombre in pila:
            raise ErrorExpresion(f"definición circular de '{ent.nombre}'")
        nueva = pila + (ent.nombre,)

        def val(nodo):
            e = self.buscar(nodo.calificado)
            if e is None:
                raise ErrorExpresion(f"símbolo '{nodo.nombre}' no definido")
            return self.valor_de(e, nueva)

        v = evaluar(ent.expr, val, ent.aqui)
        if ent.pura:
            ent.valor = v
        return v

    def valor_seguro(self, ent):
        """Valor para mostrar en pantalla (None si no se puede calcular)."""
        try:
            return self.valor_de(ent)
        except ErrorExpresion:
            return None


# ======================= Análisis semántico =======================
def _describir(op):
    if isinstance(op, OpReg):
        return f"{op.nombre.upper()} ({op.tam * 8} bits)"
    if isinstance(op, OpMem):
        return "un operando de memoria" + (f" de {op.tam * 8} bits" if op.tam else "")
    return "un valor inmediato"


def _tam(op):
    if isinstance(op, (OpReg, OpMem)):
        return op.tam
    return None


class Semantico:
    def __init__(self, programa, diag):
        self.programa = programa
        self.diag = diag
        self.tabla = TablaSimbolos()
        self.origen = None
        self._linea_org = 0
        self._hay_codigo = False
        self._ambito = ""

    def analizar(self):
        if self.programa.masm:
            self._ordenar_secciones()
            # '@data' (segmento de datos): un solo segmento, vale 0
            self.tabla.definir(EntradaSimbolo("@data", "constante", None, 0, expr=Num(0),
                                              pura=True))
        self._declarar()
        self._verificar()
        return self.tabla

    def _ordenar_secciones(self):
        """Dialecto MASM: todo vive en un solo segmento de 64 KB (como un .COM).

        El código se coloca primero y los datos después, así el programa empieza en
        la primera instrucción aunque '.data' vaya antes de '.code' en el fuente.
        """
        seccion = "code"
        for linea in self.programa.lineas:
            if isinstance(linea.sentencia, Seccion):
                seccion = linea.sentencia.nombre
            linea.seccion = seccion
        orden = {"code": 0}                      # lo demás (data, stack…) va después
        self.programa.lineas.sort(key=lambda l: orden.get(l.seccion, 1))   # sort es estable

    def _datos_como_memoria(self, inst):
        """MASM: usar el nombre de una variable como operando significa LEER su contenido
        (mov ax, var  ==  mov ax, [var]). Con 'offset var' se obtiene su dirección."""
        for i, op in enumerate(inst.operandos):
            if not isinstance(op, OpImm) or op.modif:
                continue
            for nodo in recorrer(op.expr):
                if isinstance(nodo, Simbolo):
                    nombre = self._calificar(nodo.nombre, self._ambito, nodo.linea, nodo.col)
                    ent = self.tabla.buscar(nombre) if nombre else None
                    if ent is not None and ent.tipo == "dato":
                        inst.operandos[i] = OpMem([], op.expr, None, op.linea, op.col)
                        break

    def _err(self, mensaje, linea, col=0):
        self.diag.error(SEMANTICO, mensaje, linea, col)

    def _aviso(self, mensaje, linea, col=0):
        self.diag.aviso(SEMANTICO, mensaje, linea, col)

    # ---------- nombres (etiquetas locales) ----------
    def _calificar(self, nombre, ambito, linea, col):
        """Las etiquetas que empiezan con '.' pertenecen a la última etiqueta global."""
        if nombre.startswith("."):
            if not ambito:
                self._err(f"la etiqueta local '{nombre}' necesita una etiqueta global antes", linea, col)
                return None
            return ambito + nombre
        return nombre

    # ---------- Pasada 1: declaraciones ----------
    def _definir(self, ent, col):
        previa = self.tabla.buscar(ent.nombre)
        if previa is not None:
            self._err(f"el símbolo '{ent.nombre}' ya fue definido en la línea {previa.linea}",
                      ent.linea, col)
            return False
        self.tabla.definir(ent)
        return True

    def _declarar(self):
        ambito = ""
        pendientes = []          # etiquetas que esperan saber si preceden a un dato
        for linea in self.programa.lineas:
            s = linea.sentencia
            if linea.etiqueta:
                nombre = self._calificar(linea.etiqueta, ambito, linea.num, linea.etiqueta_col)
                if nombre:
                    if not linea.etiqueta.startswith("."):
                        ambito = linea.etiqueta
                    ent = EntradaSimbolo(nombre, "etiqueta", None, linea.num, ambito=ambito)
                    if self._definir(ent, linea.etiqueta_col):
                        pendientes.append(ent)
                    linea.etiqueta_calificada = nombre
            linea.ambito = ambito
            if isinstance(s, Equ):
                nombre = self._calificar(s.nombre, ambito, linea.num, s.col)
                if nombre:
                    s.calificado = nombre
                    self._definir(EntradaSimbolo(nombre, "constante", None, linea.num,
                                                 expr=s.expr, ambito=ambito), s.col)
            elif isinstance(s, (Datos, Reserva)):
                for ent in pendientes:      # una etiqueta antes de db/dw es una variable
                    ent.tipo = "dato"
                    ent.tam = s.tam
                pendientes = []
            elif s is not None and not isinstance(s, (Org, Bits)):
                pendientes = []

    # ---------- Pasada 2: verificación ----------
    def _verificar(self):
        for linea in self.programa.lineas:
            self._ambito = linea.ambito
            s = linea.sentencia
            if isinstance(s, Instruccion):
                self._instruccion(s)
                self._hay_codigo = True
            elif isinstance(s, Datos):
                self._datos(s)
                self._hay_codigo = True
            elif isinstance(s, Reserva):
                self._reserva(s)
                self._hay_codigo = True
            elif isinstance(s, Equ):
                self._equ(s)
            elif isinstance(s, Org):
                self._org(s)
            elif isinstance(s, Bits):
                if s.valor != 16:
                    self._err("solo se admite 'bits 16' (el 8086 es de 16 bits)", s.linea, s.col)
        if self.origen is None:
            self.origen = 0x100
            if not self.programa.masm:
                self._aviso("no se encontró 'org 100h': se asume 100h (formato .COM)", 0)

    # --- símbolos y valores en expresiones ---
    def _resolver(self, expr):
        """Comprueba que los símbolos existan y los marca como usados."""
        ok = True
        for nodo in recorrer(expr):
            if isinstance(nodo, Simbolo):
                nombre = self._calificar(nodo.nombre, self._ambito, nodo.linea, nodo.col)
                if nombre is None:
                    ok = False
                    continue
                ent = self.tabla.buscar(nombre)
                if ent is None:
                    self._err(f"el símbolo '{nodo.nombre}' no está definido", nodo.linea, nodo.col)
                    ok = False
                else:
                    nodo.calificado = nombre
                    ent.usos += 1
        return ok

    def _val_simbolo(self, nodo):
        return self.tabla.valor_de(self.tabla.buscar(nodo.calificado))

    def _info(self, expr, linea, col):
        """Devuelve (es_constante, valor) o None si hay un error."""
        try:
            if self.tabla.expr_pura(expr):
                return True, evaluar(expr, self._val_simbolo, None)
            return False, None
        except ErrorExpresion as e:
            self._err(str(e), linea, col)
            return None

    def _constante(self, expr, linea, col, que):
        """Evalúa una expresión que obligatoriamente debe ser constante."""
        if not self._resolver(expr):
            return None
        r = self._info(expr, linea, col)
        if r is None:
            return None
        pura, valor = r
        if not pura:
            self._err(f"{que} debe ser una constante (no puede depender de direcciones)", linea, col)
            return None
        return valor

    # --- operandos ---
    def _preparar(self, op):
        if isinstance(op, OpReg):
            return True
        if isinstance(op, OpImm):
            if not self._resolver(op.expr):
                return False
            r = self._info(op.expr, op.linea, op.col)
            if r is None:
                return False
            op.pura, op.valor = r
            return True
        return self._preparar_mem(op)

    def _preparar_mem(self, op):
        ok = True
        for r in op.regs:
            if r not in tablas.REG16:
                self._err(f"'{r.upper()}' no se puede usar para direccionar memoria "
                          "(use BX, BP, SI o DI)", op.linea, op.col)
                ok = False
            elif r in ("ax", "cx", "dx", "sp"):
                self._err(f"{r.upper()} no puede direccionar memoria en el 8086: "
                          "solo BX, BP, SI y DI", op.linea, op.col)
                ok = False
        if ok and op.regs:
            bases = [r for r in op.regs if r in ("bx", "bp")]
            indices = [r for r in op.regs if r in ("si", "di")]
            if len(op.regs) > 2 or len(bases) > 1 or len(indices) > 1:
                self._err("combinación de registros inválida en 8086: use como máximo una base "
                          "(BX o BP) y un índice (SI o DI), por ejemplo [bx+si]", op.linea, op.col)
                ok = False
            else:
                op.rm = tablas.RM_DIRECCION[(bases[0] if bases else None,
                                             indices[0] if indices else None)]
        op.directa = not op.regs
        if op.disp is not None:
            if not self._resolver(op.disp):
                ok = False
            else:
                r = self._info(op.disp, op.linea, op.col)
                if r is None:
                    ok = False
                else:
                    op.disp_pura, op.disp_valor = r[0], (r[1] if r[0] else 0)
        # tamaño: el declarado (byte/word) o el de la variable (db/dw)
        op.tam = op.tam_decl or self._tam_inferido(op.disp)
        return ok

    def _tam_inferido(self, disp):
        if disp is None:
            return None
        vistos = [self.tabla.buscar(n.calificado) for n in recorrer(disp)
                  if isinstance(n, Simbolo) and n.calificado]
        datos = [e for e in vistos if e is not None and e.tipo == "dato"]
        return datos[0].tam if len(datos) == 1 else None

    def _rango(self, op, t, que):
        """Comprueba que un inmediato quepa en t bytes."""
        if op.pura:
            lo, hi = (-128, 255) if t == 1 else (-32768, 65535)
            if not lo <= op.valor <= hi:
                self._err(f"el valor {op.valor} no cabe en {t * 8} bits ({que})",
                          op.linea, op.col)
                return False
        elif t == 1:
            self._err(f"una dirección (16 bits) no cabe en un operando de 8 bits ({que})",
                      op.linea, op.col)
            return False
        return True

    # --- instrucciones ---
    def _n_ops(self, inst, n):
        if len(inst.operandos) != n:
            if n == 0:
                self._err(f"'{inst.mnem}' no lleva operandos", inst.linea, inst.col)
            else:
                self._err(f"'{inst.mnem}' necesita {n} operando{'s' if n > 1 else ''}, "
                          f"pero se escribieron {len(inst.operandos)}", inst.linea, inst.col)
            return False
        return True

    def _instruccion(self, inst):
        m = inst.mnem
        if self.programa.masm and m not in tablas.JCC and m not in tablas.LOOPS:
            self._datos_como_memoria(inst)
        listos = [self._preparar(op) for op in inst.operandos]   # reporta todos los errores
        if not all(listos):
            return
        if inst.prefijo and m not in tablas.CADENA:
            self._err(f"'{inst.prefijo}' solo se puede usar con instrucciones de cadena "
                      "(movsb, stosb, lodsb, cmpsb, scasb…)", inst.linea, inst.col)
            return
        if m in tablas.SIN_OPERANDOS:
            self._n_ops(inst, 0)
        elif m in tablas.ALU or m in ("mov", "test"):
            self._binaria(inst)
        elif m in tablas.INCDEC or m in tablas.GRUPO3:
            self._unaria(inst)
        elif m in tablas.DESPLAZ:
            self._desplazamiento(inst)
        elif m == "xchg":
            self._xchg(inst)
        elif m == "lea":
            self._lea(inst)
        elif m in ("push", "pop"):
            self._pila(inst)
        elif m in ("jmp", "call"):
            self._salto(inst, indirecto=True)
        elif m in tablas.JCC or m in tablas.LOOPS:
            self._salto(inst, indirecto=False)
        elif m == "int":
            self._int(inst)
        elif m in ("ret", "retf"):
            self._ret(inst)

    def _binaria(self, inst):
        """mov, add, sub, cmp, and, or, xor, adc, sbb, test: dos operandos."""
        if not self._n_ops(inst, 2):
            return
        d, s = inst.operandos
        M = inst.mnem.upper()
        if inst.mnem == "mov" and any(isinstance(o, OpReg) and o.es_seg for o in (d, s)):
            return self._mov_segmento(inst)
        for o in (d, s):
            if isinstance(o, OpReg) and o.es_seg:
                self._err(f"'{M}' no admite registros de segmento (solo MOV, PUSH y POP)",
                          inst.linea, inst.col)
                return
        if isinstance(d, OpImm):
            self._err(f"el destino de '{M}' no puede ser un valor inmediato", inst.linea, inst.col)
            return
        if isinstance(d, OpMem) and isinstance(s, OpMem):
            self._err("no se pueden usar dos operandos de memoria en una instrucción "
                      "(pase el dato por un registro)", inst.linea, inst.col)
            return
        td, ts = _tam(d), _tam(s)
        if td is not None and ts is not None and td != ts:
            pista = ""
            if any(isinstance(o, OpMem) and o.tam_decl is None for o in (d, s)):
                pista = (" (el tamaño de la variable viene de su declaración db/dw; "
                         "para forzar otro escriba 'byte [..]' o 'word [..]')")
            self._err(f"tamaños incompatibles: {_describir(d)} y {_describir(s)}{pista}",
                      inst.linea, inst.col)
            return
        t = td if td is not None else ts
        if t is None:
            self._err(f"tamaño ambiguo en '{M}': escriba 'byte' o 'word' antes de [ ] "
                      "(ej. 'byte [bx]')", inst.linea, inst.col)
            return
        if isinstance(s, OpImm) and not self._rango(s, t, M):
            return
        inst.tam = t

    def _mov_segmento(self, inst):
        d, s = inst.operandos
        if isinstance(d, OpReg) and d.es_seg:
            if d.nombre == "cs":
                self._err("no se puede cargar CS con MOV", inst.linea, inst.col)
                return
            if isinstance(s, OpImm):
                self._err("no se puede cargar un valor inmediato en un registro de segmento; "
                          "use un registro de 16 bits (mov ax, 5 / mov ds, ax)", inst.linea, inst.col)
                return
            if isinstance(s, OpReg) and (s.es_seg or s.tam != 2):
                self._err("el origen debe ser un registro de 16 bits o memoria", inst.linea, inst.col)
                return
            otro = s
        else:
            if isinstance(d, OpImm) or (isinstance(d, OpReg) and (d.es_seg or d.tam != 2)):
                self._err("el destino debe ser un registro de 16 bits o memoria", inst.linea, inst.col)
                return
            otro = d
        if isinstance(otro, OpMem):
            if otro.tam == 1:
                self._err("los registros de segmento son de 16 bits: use 'word [..]'",
                          inst.linea, inst.col)
                return
            otro.tam = 2
        inst.tam = 2

    def _unaria(self, inst):
        if not self._n_ops(inst, 1):
            return
        o = inst.operandos[0]
        M = inst.mnem.upper()
        if isinstance(o, OpImm):
            self._err(f"'{M}' no admite un valor inmediato", inst.linea, inst.col)
        elif isinstance(o, OpReg) and o.es_seg:
            self._err(f"'{M}' no admite registros de segmento", inst.linea, inst.col)
        elif _tam(o) is None:
            self._err(f"tamaño ambiguo en '{M}': escriba 'byte' o 'word' antes de [ ]",
                      inst.linea, inst.col)
        else:
            inst.tam = _tam(o)

    def _desplazamiento(self, inst):
        if not self._n_ops(inst, 2):
            return
        d, c = inst.operandos
        M = inst.mnem.upper()
        if isinstance(d, OpImm) or (isinstance(d, OpReg) and d.es_seg):
            self._err(f"el primer operando de '{M}' debe ser un registro o memoria", inst.linea, inst.col)
            return
        if _tam(d) is None:
            self._err(f"tamaño ambiguo en '{M}': escriba 'byte' o 'word' antes de [ ]",
                      inst.linea, inst.col)
            return
        if isinstance(c, OpReg) and c.nombre == "cl":
            inst.cuenta = "cl"
        elif isinstance(c, OpImm) and c.pura and c.valor == 1:
            inst.cuenta = "1"
        else:
            self._err(f"el 8086 solo permite desplazar 1 bit ('{inst.mnem} ax, 1') o la cantidad "
                      f"indicada en CL ('{inst.mnem} ax, cl')", inst.linea, inst.col)
            return
        inst.tam = _tam(d)

    def _xchg(self, inst):
        if not self._n_ops(inst, 2):
            return
        a, b = inst.operandos
        for o in (a, b):
            if isinstance(o, OpImm) or (isinstance(o, OpReg) and o.es_seg):
                self._err("'XCHG' solo acepta registros de uso general y memoria", inst.linea, inst.col)
                return
        if isinstance(a, OpMem) and isinstance(b, OpMem):
            self._err("no se pueden usar dos operandos de memoria en una instrucción",
                      inst.linea, inst.col)
            return
        ta, tb = _tam(a), _tam(b)
        if ta is not None and tb is not None and ta != tb:
            self._err(f"tamaños incompatibles: {_describir(a)} y {_describir(b)}", inst.linea, inst.col)
            return
        inst.tam = ta if ta is not None else tb

    def _lea(self, inst):
        if not self._n_ops(inst, 2):
            return
        d, s = inst.operandos
        if not (isinstance(d, OpReg) and not d.es_seg and d.tam == 2):
            self._err("el destino de 'LEA' debe ser un registro de 16 bits", inst.linea, inst.col)
        elif not isinstance(s, OpMem):
            self._err("el origen de 'LEA' debe ser una dirección de memoria, ej. lea dx, [mensaje]",
                      inst.linea, inst.col)
        else:
            inst.tam = 2

    def _pila(self, inst):
        if not self._n_ops(inst, 1):
            return
        o = inst.operandos[0]
        M = inst.mnem.upper()
        if isinstance(o, OpImm):
            self._err(f"el 8086 no permite '{M}' con un valor inmediato (cárguelo antes en un registro)",
                      inst.linea, inst.col)
        elif isinstance(o, OpReg) and not o.es_seg and o.tam != 2:
            self._err(f"'{M}' solo trabaja con registros de 16 bits", inst.linea, inst.col)
        elif isinstance(o, OpReg) and o.nombre == "cs" and inst.mnem == "pop":
            self._err("no se puede hacer POP CS", inst.linea, inst.col)
        elif isinstance(o, OpMem) and o.tam == 1:
            self._err(f"'{M}' trabaja con 16 bits: use 'word [..]'", inst.linea, inst.col)
        else:
            if isinstance(o, OpMem):
                o.tam = 2
            inst.tam = 2

    def _salto(self, inst, indirecto):
        if not self._n_ops(inst, 1):
            return
        o = inst.operandos[0]
        M = inst.mnem.upper()
        if isinstance(o, OpImm):
            return
        if not indirecto:
            self._err(f"'{M}' solo admite una etiqueta como destino", inst.linea, inst.col)
        elif isinstance(o, OpReg) and (o.es_seg or o.tam != 2):
            self._err(f"el salto indirecto necesita un registro de 16 bits", inst.linea, inst.col)
        elif isinstance(o, OpMem) and o.tam == 1:
            self._err(f"el salto indirecto usa una palabra de 16 bits: use 'word [..]'",
                      inst.linea, inst.col)
        elif isinstance(o, OpMem):
            o.tam = 2

    def _int(self, inst):
        if not self._n_ops(inst, 1):
            return
        o = inst.operandos[0]
        if not (isinstance(o, OpImm) and o.pura and 0 <= o.valor <= 255):
            self._err("'INT' necesita un número constante entre 0 y 255, ej. int 21h",
                      inst.linea, inst.col)

    def _ret(self, inst):
        if len(inst.operandos) == 0:
            return
        if not self._n_ops(inst, 1):
            return
        o = inst.operandos[0]
        if not (isinstance(o, OpImm) and o.pura and 0 <= o.valor <= 65535):
            self._err(f"'{inst.mnem.upper()}' admite solo un número constante de 0 a 65535",
                      inst.linea, inst.col)

    # --- datos y directivas ---
    def _datos(self, s):
        if s.veces is not None:
            v = self._constante(s.veces, s.linea, s.col, "el contador de 'times'")
            if v is not None:
                if v < 0:
                    self._err("el contador de 'times' no puede ser negativo", s.linea, s.col)
                else:
                    s.veces_valor = v
        nombre = "db" if s.tam == 1 else "dw"
        for item in s.items:
            if isinstance(item, Cadena):
                try:
                    b = bytes_de_cadena(item.texto)
                except ErrorExpresion as e:
                    self._err(str(e), item.linea, item.col)
                    continue
                if s.tam == 2 and not 1 <= len(b) <= 2:
                    self._err("'dw' solo admite cadenas de 1 o 2 caracteres; use 'db' para texto largo",
                              item.linea, item.col)
                continue
            if not self._resolver(item):
                continue
            r = self._info(item, s.linea, s.col)
            if r is None:
                continue
            pura, valor = r
            lo, hi = (-128, 255) if s.tam == 1 else (-32768, 65535)
            if pura and not lo <= valor <= hi:
                self._err(f"el valor {valor} no cabe en '{nombre}' ({s.tam * 8} bits)", s.linea, s.col)
            elif not pura and s.tam == 1:
                self._err("una dirección (16 bits) no cabe en 'db'; use 'dw'", s.linea, s.col)

    def _reserva(self, s):
        v = self._constante(s.cantidad, s.linea, s.col, "la cantidad de 'resb/resw'")
        if v is not None:
            if v < 0:
                self._err("la cantidad a reservar no puede ser negativa", s.linea, s.col)
            else:
                s.cantidad_valor = v

    def _equ(self, s):
        if not s.calificado:
            return
        if not self._resolver(s.expr):
            return
        ent = self.tabla.buscar(s.calificado)
        try:
            if self.tabla.es_pura(ent):
                self.tabla.valor_de(ent)
        except ErrorExpresion as e:
            self._err(str(e), s.linea, s.col)

    def _org(self, s):
        if self.origen is not None:
            self._err(f"'org' ya fue declarado en la línea {self._linea_org}", s.linea, s.col)
            return
        if self._hay_codigo:
            self._err("'org' debe ir antes de cualquier instrucción o dato", s.linea, s.col)
            return
        v = self._constante(s.expr, s.linea, s.col, "el valor de 'org'")
        if v is None:
            return
        if not 0 <= v <= 0xFFFF:
            self._err("'org' debe estar entre 0 y FFFFh", s.linea, s.col)
            return
        s.valor = v
        self.origen = v
        self._linea_org = s.linea
        if v != 0x100:
            self._aviso(f"los programas .COM de DOS se cargan en 100h (se usó org {v:X}h)",
                        s.linea, s.col)


def analizar_semantica(programa, diag):
    """Devuelve (tabla_de_simbolos, origen_del_programa)."""
    sem = Semantico(programa, diag)
    tabla = sem.analizar()
    return tabla, sem.origen
