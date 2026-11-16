"""Emulador del 8086 para ejecutar programas .COM.

Un solo segmento de 64 KB (CS=DS=ES=SS), el .COM se carga en 0100h.
Soporta INT 21h (01, 02, 08, 09, 0A, 2C, 4C), INT 20h, INT 10h (modo texto y
modo gráfico 13h de 320x200 con 256 colores), INT 16h (teclado) e INT 1Ah (reloj),
además del conjunto de instrucciones que genera assembler/ (sin BCD ni E/S de puertos).

Uso:
    cpu = Emulador(codigo)
    while not cpu.terminado:
        cpu.paso()            # o cpu.correr(n)
        if cpu.esperando:     # el programa pide una tecla
            cpu.dar_tecla("5")
"""

import time

ANCHO, ALTO = 320, 200


def paleta_vga():
    """Paleta de 256 colores del modo 13h: 16 colores CGA, 16 grises y rampas de color."""
    base = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170),
            (170, 85, 0), (170, 170, 170), (85, 85, 85), (85, 85, 255), (85, 255, 85),
            (85, 255, 255), (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255)]
    pal = list(base)
    pal += [(i * 255 // 15,) * 3 for i in range(16)]
    import colorsys
    for sat, val in ((1.0, 1.0), (0.5, 1.0), (0.25, 1.0), (1.0, 0.5), (0.5, 0.5),
                     (0.25, 0.5), (1.0, 0.25), (0.5, 0.25), (0.25, 0.25)):
        for k in range(24):
            r, g, b = colorsys.hsv_to_rgb(k / 24, sat, val)
            pal.append((int(r * 255), int(g * 255), int(b * 255)))
    pal += [(0, 0, 0)] * (256 - len(pal))
    return pal[:256]


PALETA = paleta_vga()
MASCARA = (0xFF, 0xFFFF)          # índice = tamaño - 1 (1 = byte, 2 = word)
SIGNO = (0x80, 0x8000)
REG16 = ["ax", "cx", "dx", "bx", "sp", "bp", "si", "di"]
CONDICIONES = 16


class ErrorEmulador(Exception):
    pass


def _par(v):
    return bin(v & 0xFF).count("1") % 2 == 0


class Emulador:
    def __init__(self, codigo, origen=0x100):
        self.mem = bytearray(65536)
        self.mem[origen:origen + len(codigo)] = codigo
        self.r = {n: 0 for n in REG16}
        self.r["sp"] = 0xFFFE
        self.ip = origen
        self.cf = self.pf = self.af = self.zf = self.sf = self.of = 0
        self.df = self.if_ = 0
        self.salida = []           # texto producido (lista de str)
        self.entrada = []          # teclas pendientes
        self.esperando = False
        self.terminado = False
        self.codigo_salida = 0
        self.pasos = 0
        self.turbo = 1             # >1: los bucles 'loop' largos (esperas) se acortan N veces
        self._linea = None         # estado de INT 21h/0Ah
        # pantalla gráfica (modo 13h) y área modificada desde la última lectura
        self.modo_grafico = False
        self.pantalla = bytearray(ANCHO * ALTO)
        self.sucio = None          # (x0, y0, x1, y1) o None
        self.pantalla_borrada = False
        self._t0 = time.time()
        # el programa termina con RET al PSP: [0000]=CD 20 (INT 20h)
        self.mem[0] = 0xCD
        self.mem[1] = 0x20
        self.mem[0xFFFE] = 0
        self.mem[0xFFFF] = 0

    # ---------- registros ----------
    def reg(self, n, tam):
        if tam == 2:
            return self.r[REG16[n]]
        r = self.r[REG16[n & 3]]
        return (r >> 8) & 0xFF if n & 4 else r & 0xFF

    def set_reg(self, n, tam, v):
        if tam == 2:
            self.r[REG16[n]] = v & 0xFFFF
            return
        k = REG16[n & 3]
        if n & 4:
            self.r[k] = (self.r[k] & 0x00FF) | ((v & 0xFF) << 8)
        else:
            self.r[k] = (self.r[k] & 0xFF00) | (v & 0xFF)

    # ---------- memoria ----------
    def rd(self, dir_, tam):
        dir_ &= 0xFFFF
        if tam == 1:
            return self.mem[dir_]
        return self.mem[dir_] | (self.mem[(dir_ + 1) & 0xFFFF] << 8)

    def wr(self, dir_, tam, v):
        dir_ &= 0xFFFF
        self.mem[dir_] = v & 0xFF
        if tam == 2:
            self.mem[(dir_ + 1) & 0xFFFF] = (v >> 8) & 0xFF

    def fetch(self, tam=1):
        v = self.rd(self.ip, tam)
        self.ip = (self.ip + tam) & 0xFFFF
        return v

    def push(self, v):
        self.r["sp"] = (self.r["sp"] - 2) & 0xFFFF
        self.wr(self.r["sp"], 2, v)

    def pop(self):
        v = self.rd(self.r["sp"], 2)
        self.r["sp"] = (self.r["sp"] + 2) & 0xFFFF
        return v

    # ---------- ModR/M ----------
    def modrm(self):
        b = self.fetch()
        mod, reg, rm = b >> 6, (b >> 3) & 7, b & 7
        if mod == 3:
            return mod, reg, rm, None
        r = self.r
        if mod == 0 and rm == 6:
            return mod, reg, rm, self.fetch(2)
        base = (r["bx"] + r["si"], r["bx"] + r["di"], r["bp"] + r["si"],
                r["bp"] + r["di"], r["si"], r["di"], r["bp"], r["bx"])[rm]
        if mod == 1:
            d = self.fetch()
            base += d - 256 if d & 0x80 else d
        elif mod == 2:
            base += self.fetch(2)
        return mod, reg, rm, base & 0xFFFF

    def leer_rm(self, rm, dir_, tam):
        return self.reg(rm, tam) if dir_ is None else self.rd(dir_, tam)

    def escribir_rm(self, rm, dir_, tam, v):
        if dir_ is None:
            self.set_reg(rm, tam, v)
        else:
            self.wr(dir_, tam, v)

    # ---------- flags ----------
    def _zsp(self, v, tam):
        v &= MASCARA[tam - 1]
        self.zf = int(v == 0)
        self.sf = int(bool(v & SIGNO[tam - 1]))
        self.pf = int(_par(v))
        return v

    def alu(self, op, a, b, tam):
        """op: 0 add,1 or,2 adc,3 sbb,4 and,5 sub,6 xor,7 cmp. Devuelve resultado."""
        m, s = MASCARA[tam - 1], SIGNO[tam - 1]
        a &= m
        b &= m
        if op in (0, 2):
            c = self.cf if op == 2 else 0
            t = a + b + c
            r = t & m
            self.cf = int(t > m)
            self.af = int(((a & 15) + (b & 15) + c) > 15)
            self.of = int(bool((~(a ^ b)) & (a ^ r) & s))
        elif op in (3, 5, 7):
            c = self.cf if op == 3 else 0
            t = a - b - c
            r = t & m
            self.cf = int(t < 0)
            self.af = int(((a & 15) - (b & 15) - c) < 0)
            self.of = int(bool((a ^ b) & (a ^ r) & s))
        else:
            r = (a | b) if op == 1 else (a & b) if op == 4 else (a ^ b)
            self.cf = self.of = self.af = 0
        self._zsp(r, tam)
        return r

    def condicion(self, c):
        base = (self.of, self.cf, self.zf, self.cf or self.zf, self.sf, self.pf,
                self.sf != self.of, self.zf or (self.sf != self.of))[c >> 1]
        return bool(base) != bool(c & 1)

    # ---------- desplazamientos ----------
    def desplazar(self, op, v, n, tam):
        bits = 8 * tam
        m, s = MASCARA[tam - 1], SIGNO[tam - 1]
        v &= m
        n &= 0xFF
        if n == 0:
            return v
        original = v
        if op in (0, 1, 2, 3):          # rol ror rcl rcr
            for _ in range(n):
                if op == 0:
                    self.cf = int(bool(v & s))
                    v = ((v << 1) | self.cf) & m
                elif op == 1:
                    self.cf = v & 1
                    v = (v >> 1) | (self.cf << (bits - 1))
                elif op == 2:
                    c = self.cf
                    self.cf = int(bool(v & s))
                    v = ((v << 1) | c) & m
                else:
                    c = self.cf
                    self.cf = v & 1
                    v = (v >> 1) | (c << (bits - 1))
            if op in (0, 2):
                self.of = int(bool(v & s)) ^ self.cf
            else:
                self.of = int(bool(v & s)) ^ int(bool(v & (s >> 1)))
            return v
        # shl/sal(4), shr(5), sar(7)
        for _ in range(n):
            if op == 4 or op == 6:
                self.cf = int(bool(v & s))
                v = (v << 1) & m
            elif op == 5:
                self.cf = v & 1
                v >>= 1
            else:
                self.cf = v & 1
                v = (v >> 1) | (v & s)
        if op in (4, 6):
            self.of = int(bool(v & s)) ^ self.cf
        elif op == 5:
            self.of = int(bool(original & s)) if n == 1 else 0
        else:
            self.of = 0
        self._zsp(v, tam)
        self.af = 0
        return v

    # ---------- E/S ----------
    def imprimir(self, texto):
        self.salida.append(texto)

    def dar_tecla(self, c):
        self.entrada.append(c)

    def _tecla(self):
        return self.entrada.pop(0) if self.entrada else None

    def _dos(self):
        ah = self.reg(4, 1)
        al = self.reg(0, 1)
        if ah in (0x01, 0x08):
            t = self._tecla()
            if t is None:
                self.esperando = True
                return False
            b = t.encode("cp437", "replace")[:1] or b"?"
            self.set_reg(0, 1, b[0])
            if ah == 0x01:
                self.imprimir(t if t != "\r" else "\n")
        elif ah == 0x02:
            self.imprimir(bytes([self.reg(2, 1)]).decode("cp437"))
        elif ah == 0x09:
            d = self.r["dx"]
            out = bytearray()
            while self.mem[d] != 0x24 and len(out) < 65536:
                out.append(self.mem[d])
                d = (d + 1) & 0xFFFF
            self.imprimir(out.decode("cp437"))
        elif ah == 0x0A:
            d = self.r["dx"]
            maxl = self.mem[d]
            if self._linea is None:
                self._linea = []
            while True:
                t = self._tecla()
                if t is None:
                    self.esperando = True
                    return False
                if t in ("\r", "\n"):
                    self.imprimir("\n")
                    datos = self._linea
                    self._linea = None
                    self.mem[(d + 1) & 0xFFFF] = len(datos)
                    for i, ch in enumerate(datos):
                        self.mem[(d + 2 + i) & 0xFFFF] = ch
                    self.mem[(d + 2 + len(datos)) & 0xFFFF] = 0x0D
                    break
                if t == "\b":
                    if self._linea:
                        self._linea.pop()
                        self.imprimir("\b \b")
                elif len(self._linea) < max(maxl - 1, 0):
                    self._linea.append(t.encode("cp437", "replace")[0])
                    self.imprimir(t)
        elif ah == 0x2C:                                 # hora del sistema
            lt = time.localtime()
            frac = int((time.time() % 1) * 100)
            self.set_reg(5, 1, lt.tm_hour)
            self.set_reg(1, 1, lt.tm_min)
            self.set_reg(6, 1, lt.tm_sec)
            self.set_reg(2, 1, frac)
        elif ah == 0x4C:
            self.codigo_salida = al
            self.terminado = True
        elif ah == 0x00:
            self.terminado = True
        else:
            raise ErrorEmulador(f"INT 21h función {ah:02X}h no soportada")
        return True

    # ---------- pantalla gráfica ----------
    def poner_pixel(self, x, y, color):
        if 0 <= x < ANCHO and 0 <= y < ALTO:
            self.pantalla[y * ANCHO + x] = color
            s = self.sucio
            self.sucio = (x, y, x, y) if s is None else (
                min(s[0], x), min(s[1], y), max(s[2], x), max(s[3], y))

    def tomar_sucio(self):
        """Devuelve y reinicia el rectángulo modificado (x0, y0, x1, y1) o None."""
        s, self.sucio = self.sucio, None
        return s

    def _video(self):
        ah = self.reg(4, 1)
        al = self.reg(0, 1)
        if ah == 0x00:                                   # fijar modo de video
            self.modo_grafico = (al & 0x7F) == 0x13
            self.pantalla = bytearray(ANCHO * ALTO)
            self.sucio = (0, 0, ANCHO - 1, ALTO - 1)
            self.pantalla_borrada = True
        elif ah == 0x0C:                                 # escribir píxel
            self.poner_pixel(self.r["cx"], self.r["dx"], al)
        elif ah == 0x0D:                                 # leer píxel
            x, y = self.r["cx"], self.r["dx"]
            self.set_reg(0, 1, self.pantalla[y * ANCHO + x]
                         if 0 <= x < ANCHO and 0 <= y < ALTO else 0)
        elif ah in (0x0E, 0x0A, 0x09):                   # escribir carácter
            if not self.modo_grafico:
                self.imprimir(bytes([al]).decode("cp437"))
        # 01h, 02h, 03h, 06h, 07h, 0Fh...: cursor/desplazar no hacen nada visible aquí

    def _teclado(self):
        ah = self.reg(4, 1)
        if ah in (0x00, 0x10):                           # esperar una tecla
            t = self._tecla()
            if t is None:
                self.esperando = True
                return False
            b = t.encode("cp437", "replace")[:1] or b"?"
            self.set_reg(0, 2, b[0])
        elif ah in (0x01, 0x11):                         # ¿hay tecla? (no la quita)
            if self.entrada:
                b = self.entrada[0].encode("cp437", "replace")[:1] or b"?"
                self.set_reg(0, 2, b[0])
                self.zf = 0
            else:
                self.zf = 1
        elif ah == 0x02:
            self.set_reg(0, 1, 0)
        return True

    def _ticks(self):
        return int((time.time() - self._t0) * 18.2065) % 0x1800B0

    def _int(self, n):
        if n == 0x10:
            return self._video() or True
        if n == 0x16:
            return self._teclado()
        if n == 0x1A:
            if self.reg(4, 1) == 0:
                t = self._ticks()
                self.r["cx"], self.r["dx"] = (t >> 16) & 0xFFFF, t & 0xFFFF
                self.set_reg(0, 1, 0)
            return True
        if n == 0x21:
            return self._dos()
        if n == 0x20:
            self.terminado = True
            return True
        raise ErrorEmulador(f"INT {n:02X}h no soportada")

    # ---------- ejecución ----------
    def correr(self, maximo):
        for _ in range(maximo):
            if self.esperando and self.entrada:
                self.esperando = False       # llegó la tecla que se esperaba
            if self.terminado or self.esperando:
                break
            self.paso()

    def paso(self):
        if self.terminado:
            return
        self.esperando = False
        inicio = self.ip
        rep = None
        self.pasos += 1
        op = self.fetch()
        while op in (0xF2, 0xF3, 0x26, 0x2E, 0x36, 0x3E, 0xF0):
            if op in (0xF2, 0xF3):
                rep = op
            op = self.fetch()
        try:
            ok = self._ejecutar(op, rep)
        except ErrorEmulador:
            raise
        if ok is False:          # esperando una tecla: repetir la instrucción
            self.ip = inicio
            self.pasos -= 1

    def _ejecutar(self, op, rep):
        r = self.r
        # ---- camino rápido: las instrucciones más frecuentes de los bucles ----
        if op == 0xE2:                                  # loop
            d = self.fetch()
            if d == 0xFE and r["cx"] > 1:               # 'loop $': espera activa -> se adelanta
                self.pasos += r["cx"] - 1
                r["cx"] = 1
            if self.turbo > 1 and r["cx"] > 0x1000:      # acelera los bucles de espera largos
                r["cx"] = max(1, r["cx"] - self.turbo + 1)
            r["cx"] = (r["cx"] - 1) & 0xFFFF
            if r["cx"]:
                self.ip = (self.ip + (d - 256 if d & 0x80 else d)) & 0xFFFF
            return True
        if op == 0xE8:                                  # call rel16
            d = self.fetch(2)
            self.push(self.ip)
            self.ip = (self.ip + d) & 0xFFFF
            return True
        if op == 0xC3:                                  # ret
            self.ip = self.pop()
            return True
        if op == 0xB4:                                  # mov ah, imm8
            r["ax"] = (r["ax"] & 0x00FF) | (self.fetch() << 8)
            return True
        if 0x70 <= op <= 0x7F:                          # jcc rel8
            d = self.fetch()
            if self.condicion(op & 15):
                self.ip = (self.ip + (d - 256 if d & 0x80 else d)) & 0xFFFF
            return True
        # ALU r/m,reg  reg,r/m  acc,imm  (00-3F)
        if op < 0x40 and (op & 7) < 6:
            o = op >> 3
            f = op & 7
            if f < 4:
                tam = 1 if f % 2 == 0 else 2
                _, reg, rm, d = self.modrm()
                if f < 2:
                    res = self.alu(o, self.leer_rm(rm, d, tam), self.reg(reg, tam), tam)
                    if o != 7:
                        self.escribir_rm(rm, d, tam, res)
                else:
                    res = self.alu(o, self.reg(reg, tam), self.leer_rm(rm, d, tam), tam)
                    if o != 7:
                        self.set_reg(reg, tam, res)
            else:
                tam = 1 if f == 4 else 2
                res = self.alu(o, self.reg(0, tam), self.fetch(tam), tam)
                if o != 7:
                    self.set_reg(0, tam, res)
            return True
        if 0x40 <= op <= 0x4F:                      # inc/dec reg16
            n = op & 7
            cf = self.cf
            v = self.alu(5 if op >= 0x48 else 0, r[REG16[n]], 1, 2)
            self.cf = cf
            r[REG16[n]] = v
            return True
        if 0x50 <= op <= 0x57:
            # PUSH SP en 8086 empuja el valor ya decrementado
            self.push((r["sp"] - 2) & 0xFFFF if op == 0x54 else r[REG16[op & 7]])
            return True
        if 0x58 <= op <= 0x5F:
            v = self.pop()
            r[REG16[op & 7]] = v
            return True
        if 0x70 <= op <= 0x7F:
            d = self.fetch()
            if self.condicion(op & 15):
                self.ip = (self.ip + (d - 256 if d & 0x80 else d)) & 0xFFFF
            return True
        if 0x80 <= op <= 0x83:
            tam = 1 if op in (0x80, 0x82) else 2
            _, o, rm, d = self.modrm()
            if op == 0x81:
                imm = self.fetch(2)
            else:
                imm = self.fetch(1)
                if op == 0x83 and imm & 0x80:
                    imm |= 0xFF00
            res = self.alu(o, self.leer_rm(rm, d, tam), imm, tam)
            if o != 7:
                self.escribir_rm(rm, d, tam, res)
            return True
        if op in (0x84, 0x85):
            tam = 1 if op == 0x84 else 2
            _, reg, rm, d = self.modrm()
            self.alu(4, self.leer_rm(rm, d, tam), self.reg(reg, tam), tam)
            return True
        if op in (0x86, 0x87):
            tam = 1 if op == 0x86 else 2
            _, reg, rm, d = self.modrm()
            a, b = self.leer_rm(rm, d, tam), self.reg(reg, tam)
            self.escribir_rm(rm, d, tam, b)
            self.set_reg(reg, tam, a)
            return True
        if 0x88 <= op <= 0x8B:
            tam = 1 if op % 2 == 0 else 2
            _, reg, rm, d = self.modrm()
            if op < 0x8A:
                self.escribir_rm(rm, d, tam, self.reg(reg, tam))
            else:
                self.set_reg(reg, tam, self.leer_rm(rm, d, tam))
            return True
        if op in (0x8C, 0x8E):                      # mov con registros de segmento
            _, reg, rm, d = self.modrm()
            if op == 0x8C:
                self.escribir_rm(rm, d, 2, 0)       # segmento único (valor ficticio)
            return True
        if op == 0x8D:
            _, reg, rm, d = self.modrm()
            if d is None:
                raise ErrorEmulador("LEA necesita un operando de memoria")
            r[REG16[reg]] = d
            return True
        if op == 0x8F:
            _, _, rm, d = self.modrm()
            self.escribir_rm(rm, d, 2, self.pop())
            return True
        if op == 0x90:
            return True
        if 0x91 <= op <= 0x97:
            n = op & 7
            r["ax"], r[REG16[n]] = r[REG16[n]], r["ax"]
            return True
        if op == 0x98:
            self.set_reg(0, 2, (self.reg(0, 1) | 0xFF00) if self.reg(0, 1) & 0x80 else self.reg(0, 1))
            return True
        if op == 0x99:
            r["dx"] = 0xFFFF if r["ax"] & 0x8000 else 0
            return True
        if op == 0x9B:
            return True
        if op == 0x9C:
            self.push(self._flags())
            return True
        if op == 0x9D:
            self._set_flags(self.pop())
            return True
        if op == 0x9E:
            self._set_flags((self._flags() & 0xFF00) | self.reg(4, 1))
            return True
        if op == 0x9F:
            self.set_reg(4, 1, self._flags() & 0xFF)
            return True
        if 0xA0 <= op <= 0xA3:
            tam = 1 if op % 2 == 0 else 2
            d = self.fetch(2)
            if op < 0xA2:
                self.set_reg(0, tam, self.rd(d, tam))
            else:
                self.wr(d, tam, self.reg(0, tam))
            return True
        if op in (0xA4, 0xA5, 0xA6, 0xA7, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF):
            self._cadena(op, rep)
            return True
        if op in (0xA8, 0xA9):
            tam = 1 if op == 0xA8 else 2
            self.alu(4, self.reg(0, tam), self.fetch(tam), tam)
            return True
        if 0xB0 <= op <= 0xB7:
            self.set_reg(op & 7, 1, self.fetch())
            return True
        if 0xB8 <= op <= 0xBF:
            r[REG16[op & 7]] = self.fetch(2)
            return True
        if op in (0xC2, 0xC3):
            n = self.fetch(2) if op == 0xC2 else 0
            self.ip = self.pop()
            r["sp"] = (r["sp"] + n) & 0xFFFF
            return True
        if op in (0xC6, 0xC7):
            tam = 1 if op == 0xC6 else 2
            _, _, rm, d = self.modrm()
            self.escribir_rm(rm, d, tam, self.fetch(tam))
            return True
        if op == 0xCD:
            n = self.fetch()
            return self._int(n)
        if op == 0xCF:
            self.ip = self.pop()
            self.pop()
            self._set_flags(self.pop())
            return True
        if 0xD0 <= op <= 0xD3:
            tam = 1 if op % 2 == 0 else 2
            _, o, rm, d = self.modrm()
            n = 1 if op < 0xD2 else self.reg(1, 1)
            self.escribir_rm(rm, d, tam, self.desplazar(o, self.leer_rm(rm, d, tam), n, tam))
            return True
        if op in (0xD7,):
            self.set_reg(0, 1, self.rd(r["bx"] + self.reg(0, 1), 1))
            return True
        if op in (0xE0, 0xE1, 0xE2, 0xE3):
            d = self.fetch()
            salto = d - 256 if d & 0x80 else d
            if op == 0xE3:
                tomar = r["cx"] == 0
            else:
                r["cx"] = (r["cx"] - 1) & 0xFFFF
                tomar = r["cx"] != 0
                if op == 0xE0:
                    tomar = tomar and not self.zf
                elif op == 0xE1:
                    tomar = tomar and bool(self.zf)
            if tomar:
                self.ip = (self.ip + salto) & 0xFFFF
            return True
        if op == 0xE8:
            d = self.fetch(2)
            self.push(self.ip)
            self.ip = (self.ip + d) & 0xFFFF
            return True
        if op == 0xE9:
            d = self.fetch(2)
            self.ip = (self.ip + d) & 0xFFFF
            return True
        if op == 0xEB:
            d = self.fetch()
            self.ip = (self.ip + (d - 256 if d & 0x80 else d)) & 0xFFFF
            return True
        if op == 0xF4:
            self.terminado = True
            return True
        if op == 0xF5:
            self.cf ^= 1
            return True
        if op in (0xF8, 0xF9):
            self.cf = op & 1
            return True
        if op in (0xFA, 0xFB):
            self.if_ = op & 1
            return True
        if op in (0xFC, 0xFD):
            self.df = op & 1
            return True
        if op in (0xF6, 0xF7):
            return self._grupo3(0 if op == 0xF6 else 1)
        if op in (0xFE, 0xFF):
            return self._grupo45(op)
        raise ErrorEmulador(f"opcode {op:02X}h no soportado (IP={self.ip - 1:04X}h)")

    def _grupo3(self, w):
        tam = 1 + w
        _, o, rm, d = self.modrm()
        m = MASCARA[tam - 1]
        v = self.leer_rm(rm, d, tam)
        if o in (0, 1):
            self.alu(4, v, self.fetch(tam), tam)
        elif o == 2:
            self.escribir_rm(rm, d, tam, ~v & m)
        elif o == 3:
            res = self.alu(5, 0, v, tam)
            self.cf = int(v != 0)
            self.escribir_rm(rm, d, tam, res)
        elif o in (4, 5):                       # mul / imul
            a = self.reg(0, tam)
            if o == 5:
                a = self._con_signo(a, tam)
                v = self._con_signo(v, tam)
            p = a * v
            bits = 8 * tam
            if tam == 1:
                self.set_reg(0, 2, p)
            else:
                self.r["ax"], self.r["dx"] = p & 0xFFFF, (p >> 16) & 0xFFFF
            if o == 4:
                self.cf = self.of = int((p >> bits) != 0)
            else:
                self.cf = self.of = int(self._con_signo(p & ((1 << bits) - 1), tam) != p)
        else:                                   # div / idiv
            if v == 0:
                raise ErrorEmulador("división entre cero")
            bits = 8 * tam
            num = self.reg(0, 2) if tam == 1 else (self.r["dx"] << 16) | self.r["ax"]
            if o == 7:
                num = self._con_signo(num, tam * 2)
                v = self._con_signo(v, tam)
                q = abs(num) // abs(v)
                if (num < 0) != (v < 0):
                    q = -q
                rem = num - q * v
                if not (-(1 << (bits - 1)) <= q < (1 << (bits - 1))):
                    raise ErrorEmulador("desbordamiento en la división (cociente muy grande)")
            else:
                q, rem = divmod(num, v)
                if q > m:
                    raise ErrorEmulador("desbordamiento en la división (cociente muy grande)")
            if tam == 1:
                self.set_reg(0, 1, q)
                self.set_reg(4, 1, rem)
            else:
                self.r["ax"], self.r["dx"] = q & 0xFFFF, rem & 0xFFFF
        return True

    @staticmethod
    def _con_signo(v, tam):
        bits = 8 * tam
        v &= (1 << bits) - 1
        return v - (1 << bits) if v >> (bits - 1) else v

    def _grupo45(self, op):
        tam = 1 if op == 0xFE else 2
        _, o, rm, d = self.modrm()
        if o in (0, 1):
            cf = self.cf
            res = self.alu(0 if o == 0 else 5, self.leer_rm(rm, d, tam), 1, tam)
            self.cf = cf
            self.escribir_rm(rm, d, tam, res)
        elif op == 0xFF and o == 2:
            v = self.leer_rm(rm, d, 2)
            self.push(self.ip)
            self.ip = v
        elif op == 0xFF and o == 4:
            self.ip = self.leer_rm(rm, d, 2)
        elif op == 0xFF and o == 6:
            self.push(self.leer_rm(rm, d, 2))
        else:
            raise ErrorEmulador("instrucción FE/FF no soportada")
        return True

    def _cadena(self, op, rep):
        tam = 1 if op % 2 == 0 else 2
        paso = -tam if self.df else tam
        r = self.r
        while True:
            if rep and r["cx"] == 0:
                break
            if op in (0xA4, 0xA5):
                self.wr(r["di"], tam, self.rd(r["si"], tam))
                r["si"] = (r["si"] + paso) & 0xFFFF
                r["di"] = (r["di"] + paso) & 0xFFFF
            elif op in (0xAA, 0xAB):
                self.wr(r["di"], tam, self.reg(0, tam))
                r["di"] = (r["di"] + paso) & 0xFFFF
            elif op in (0xAC, 0xAD):
                self.set_reg(0, tam, self.rd(r["si"], tam))
                r["si"] = (r["si"] + paso) & 0xFFFF
            elif op in (0xA6, 0xA7):
                self.alu(7, self.rd(r["si"], tam), self.rd(r["di"], tam), tam)
                r["si"] = (r["si"] + paso) & 0xFFFF
                r["di"] = (r["di"] + paso) & 0xFFFF
            else:                                    # scas
                self.alu(7, self.reg(0, tam), self.rd(r["di"], tam), tam)
                r["di"] = (r["di"] + paso) & 0xFFFF
            if not rep:
                break
            r["cx"] = (r["cx"] - 1) & 0xFFFF
            if op in (0xA6, 0xA7, 0xAE, 0xAF):
                if rep == 0xF3 and not self.zf:
                    break
                if rep == 0xF2 and self.zf:
                    break

    def _flags(self):
        return (0xF002 | self.cf | (self.pf << 2) | (self.af << 4) | (self.zf << 6)
                | (self.sf << 7) | (self.if_ << 9) | (self.df << 10) | (self.of << 11))

    def _set_flags(self, v):
        self.cf, self.pf, self.af = v & 1, (v >> 2) & 1, (v >> 4) & 1
        self.zf, self.sf = (v >> 6) & 1, (v >> 7) & 1
        self.if_, self.df, self.of = (v >> 9) & 1, (v >> 10) & 1, (v >> 11) & 1
