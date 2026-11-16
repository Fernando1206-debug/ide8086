"""Panel inferior: terminal + una pestaña por cada etapa del compilador."""
import customtkinter as ctk

from assembler import reportes
from ui.panels import TerminalPanel, FONDO_CODIGO, TEXTO_CODIGO

MONO_PEQ = ("Consolas", 12)

# Nombres de las pestañas
TERMINAL = "Terminal"
LEXER = "1 · Lexer"
PARSER = "2 · Parser"
SEMANTIC = "3 · Semantic"
CODEGEN = "4 · CodeGen"


class TerminalClicable(TerminalPanel):
    """Terminal con texto de colores y enlaces (para saltar a la línea de un error)."""

    def __init__(self, master):
        super().__init__(master)
        self._n = 0
        oscuro = ctk.get_appearance_mode() == "Dark"
        tb = self.texto._textbox          # el tk.Text real que hay dentro del CTkTextbox
        colores = {
            "ok": "#3fb950" if oscuro else "#1a7f37",
            "error": "#ff7b72" if oscuro else "#cf222e",
            "aviso": "#d29922" if oscuro else "#9a6700",
            "suave": "#8b949e" if oscuro else "#6e7781",
        }
        for nombre, color in colores.items():
            tb.tag_configure(nombre, foreground=color)
        tb.tag_configure("enlace", foreground="#58a6ff" if oscuro else "#0969da", underline=True)
        tb.tag_bind("enlace", "<Enter>", lambda e: tb.configure(cursor="hand2"))
        tb.tag_bind("enlace", "<Leave>", lambda e: tb.configure(cursor="xterm"))

    def escribir(self, texto, etiqueta=None):
        tb = self.texto._textbox
        tb.configure(state="normal")
        tb.insert("end", texto, (etiqueta,) if etiqueta else ())
        tb.see("end")
        tb.configure(state="disabled")

    def escribir_enlace(self, texto, comando):
        tb = self.texto._textbox
        self._n += 1
        etiqueta = f"enlace{self._n}"
        tb.configure(state="normal")
        tb.insert("end", texto, ("enlace", etiqueta))
        tb.tag_bind(etiqueta, "<Button-1>", lambda e: comando())
        tb.see("end")
        tb.configure(state="disabled")

    def limpiar(self):
        super().limpiar()
        tb = self.texto._textbox
        for nombre in tb.tag_names():
            if nombre.startswith("enlace") and nombre != "enlace":
                tb.tag_delete(nombre)


class FasesPanel(ctk.CTkFrame):
    PESTANAS = [TERMINAL, LEXER, PARSER, SEMANTIC, CODEGEN]

    def __init__(self, master):
        super().__init__(master, corner_radius=10, fg_color=FONDO_CODIGO)
        self.tabs = ctk.CTkTabview(self, corner_radius=8, fg_color=FONDO_CODIGO, height=100)
        self.tabs.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.cajas = {}
        for nombre in self.PESTANAS:
            tab = self.tabs.add(nombre)
            if nombre == TERMINAL:
                self.terminal = TerminalClicable(tab)
                self.terminal.pack(fill="both", expand=True)
            else:
                caja = ctk.CTkTextbox(tab, font=MONO_PEQ, wrap="none", corner_radius=8,
                                      fg_color=FONDO_CODIGO, text_color=TEXTO_CODIGO)
                caja.pack(fill="both", expand=True)
                self.cajas[nombre] = caja
                self._poner(caja, "(Compile con F7 para ver el resultado de esta etapa)")
        self.tabs.set(TERMINAL)

    @staticmethod
    def _poner(caja, texto):
        caja.configure(state="normal")
        caja.delete("1.0", "end")
        caja.insert("1.0", texto)
        caja.configure(state="disabled")

    def mostrar(self, res):
        """Llena las pestañas con el resultado de cada etapa."""
        self._poner(self.cajas[LEXER], reportes.texto_lexico(res))
        self._poner(self.cajas[PARSER], reportes.texto_sintactico(res))
        self._poner(self.cajas[SEMANTIC], reportes.texto_semantico(res))
        self._poner(self.cajas[CODEGEN], reportes.texto_codegen(res))

    def seleccionar(self, nombre):
        self.tabs.set(nombre)
