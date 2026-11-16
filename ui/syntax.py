import re
import tkinter as tk

MARGEN = 60  # líneas extra arriba y abajo de lo visible que también se colorean

INSTRUCCIONES = set("""
mov add adc sub sbb mul imul div idiv inc dec neg cmp and or xor not test
shl shr sal sar rol ror rcl rcr push pop pushf popf lea lds les xchg xlat xlatb
in out cbw cwd clc stc cmc cld std cli sti nop hlt wait lahf sahf daa das aaa
aas aam aad movsb movsw cmpsb cmpsw scasb scasw lodsb lodsw stosb stosw rep repe
repne repz repnz lock
""".split())

SALTOS = set("""
jmp je jne jz jnz ja jae jb jbe jg jge jl jle jc jnc jo jno js jns jp jnp jpe jpo
jna jnae jnb jnbe jng jnge jnl jnle jcxz loop loope loopne loopz loopnz
call ret retf int into iret
""".split())

REGISTROS = set("""
ax bx cx dx si di bp sp ah al bh bl ch cl dh dl cs ds es ss ip flags
""".split())

DIRECTIVAS = set("""
org db dw dd dq dt resb resw resd equ times section segment bits global extern cpu
byte word dword ptr offset short near far incbin
""".split())

DEFINE_VARIABLE = {"db", "dw", "dd", "dq", "dt", "equ", "resb", "resw", "resd"}

ETIQUETAS = ("comentario", "cadena", "numero", "instruccion", "salto",
             "registro", "directiva", "etiqueta", "variable")

COLORES_SINTAXIS = {
    "Dark": {
        "comentario": "#6a9955", "cadena": "#ce9178", "numero": "#b5cea8",
        "instruccion": "#569cd6", "salto": "#c586c0", "registro": "#4ec9b0",
        "directiva": "#d19a66", "etiqueta": "#dcdcaa", "variable": "#9cdcfe",
    },
    "Light": {
        "comentario": "#008000", "cadena": "#a31515", "numero": "#098658",
        "instruccion": "#0000ff", "salto": "#af00db", "registro": "#267f99",
        "directiva": "#b5651d", "etiqueta": "#795e26", "variable": "#001080",
    },
}

# El orden importa: primero cadenas y comentarios, así un ';' dentro de
# una cadena no se toma como comentario.
PATRON = re.compile(
    r"(?P<cadena>\"[^\"\n]*\"?|'[^'\n]*'?)"
    r"|(?P<comentario>;[^\n]*)"
    r"|(?P<numero>\b(?:0[xX][0-9A-Fa-f]+|[0-9][0-9A-Fa-f]*[hH]|[01]+[bB]|[0-9]+)\b)"
    r"|(?P<palabra>[A-Za-z_.@$%][\w.@$]*)"
)


def _clasificar(linea, m):
    """Decide de qué tipo es una palabra de la línea."""
    palabra = m.group()
    bajo = palabra.lower()
    al_inicio = not linea[: m.start()].strip()

    if al_inicio:
        if linea[m.end(): m.end() + 1] == ":":
            return "etiqueta"
        resto = linea[m.end():].split(None, 1)
        if resto and resto[0].lower() in DEFINE_VARIABLE:
            return "variable"

    if bajo in SALTOS:
        return "salto"
    if bajo in INSTRUCCIONES:
        return "instruccion"
    if bajo in REGISTROS:
        return "registro"
    if bajo in DIRECTIVAS or palabra.startswith("%"):
        return "directiva"
    return None


class Resaltador:
    """Colorea el texto del editor. Solo trabaja sobre las líneas visibles
    (más un margen), así sigue rápido aunque el archivo sea grande."""

    def __init__(self, texto, colores):
        self.t = texto
        self._job = None
        for nombre in ETIQUETAS:
            texto.tag_configure("sx_" + nombre, foreground=colores[nombre])
        texto.bind("<<Edicion>>", self.programar, add="+")

    def programar(self, _=None):
        if self._job is None:
            self._job = self.t.after(15, self._ejecutar)

    def _ejecutar(self):
        self._job = None
        try:
            self.resaltar_visible()
        except tk.TclError:
            pass

    def resaltar_visible(self):
        t = self.t
        total = int(t.index("end-1c").split(".")[0])
        primera = int(t.index("@0,0").split(".")[0])
        ultima = int(t.index(f"@0,{max(t.winfo_height(), 1)}").split(".")[0])
        self.resaltar_lineas(max(1, primera - MARGEN), min(total, ultima + MARGEN))

    def resaltar_lineas(self, desde, hasta):
        t = self.t
        inicio = f"{desde}.0"
        fin = f"{hasta}.0 lineend"
        for nombre in ETIQUETAS:
            t.tag_remove("sx_" + nombre, inicio, fin)

        rangos = {nombre: [] for nombre in ETIQUETAS}
        for i, linea in enumerate(t.get(inicio, fin).split("\n")):
            n = desde + i
            for m in PATRON.finditer(linea):
                tipo = m.lastgroup
                if tipo == "palabra":
                    tipo = _clasificar(linea, m)
                    if tipo is None:
                        continue
                rangos[tipo].append(f"{n}.{m.start()}")
                rangos[tipo].append(f"{n}.{m.end()}")

        for nombre, lista in rangos.items():
            if lista:
                t.tag_add("sx_" + nombre, *lista)