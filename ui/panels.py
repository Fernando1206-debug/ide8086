import customtkinter as ctk

FUENTE_TITULO = ("Segoe UI", 13, "bold")
MONO = ("Consolas", 13)
FONDO_CODIGO = ("#ffffff", "#1e1e1e")
FONDO_PANEL = ("#f6f6f6", "#262626")
TEXTO_CODIGO = ("#1c1c1c", "#d4d4d4")
TEXTO_SUAVE = ("#707070", "#9a9a9a")

REGISTROS = ["AX", "BX", "CX", "DX", "SI", "DI", "BP", "SP"]
BANDERAS = ["ZF", "CF", "SF", "OF"]


class Encabezado(ctk.CTkFrame):
    """Título del panel con un botón opcional a la derecha."""

    def __init__(self, master, titulo, boton=None, comando=None):
        super().__init__(master, height=32, fg_color="transparent")
        self.pack_propagate(False)
        ctk.CTkLabel(self, text=titulo, font=FUENTE_TITULO).pack(side="left", padx=10)
        if boton:
            ctk.CTkButton(
                self, text=boton, width=70, height=22, corner_radius=6,
                font=("Segoe UI", 12), fg_color=("#e0e0e0", "#3a3a3a"),
                hover_color=("#cfcfcf", "#505050"), text_color=("#1c1c1c", "#f0f0f0"),
                command=comando,
            ).pack(side="right", padx=6)


class EditorPanel(ctk.CTkFrame):
    """Marcador del editor (el editor real se construye en la Fase 3)."""

    def __init__(self, master):
        super().__init__(master, corner_radius=10, fg_color=FONDO_CODIGO)
        Encabezado(self, "sin_titulo.asm").pack(fill="x", padx=4, pady=(6, 0))
        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.pack(fill="both", expand=True)
        ctk.CTkLabel(self.cuerpo, text="Aquí irá el editor", font=("Segoe UI", 16),
                     text_color=TEXTO_SUAVE).pack(expand=True)


class TerminalPanel(ctk.CTkFrame):
    """Terminal de salida: aquí se mostrará la compilación y la ejecución."""

    def __init__(self, master):
        super().__init__(master, corner_radius=10, fg_color=FONDO_CODIGO)
        Encabezado(self, "Terminal", "Limpiar", self.limpiar).pack(
            fill="x", padx=4, pady=(6, 0))
        self.texto = ctk.CTkTextbox(
            self, font=MONO, corner_radius=8, wrap="word", height=80,
            fg_color=FONDO_CODIGO, text_color=TEXTO_CODIGO,
        )
        self.texto.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.texto.configure(state="disabled")
        self.escribir("IDE 8086 - terminal lista\n")

    def escribir(self, texto):
        self.texto.configure(state="normal")
        self.texto.insert("end", texto)
        self.texto.see("end")
        self.texto.configure(state="disabled")

    def limpiar(self):
        self.texto.configure(state="normal")
        self.texto.delete("1.0", "end")
        self.texto.configure(state="disabled")


class VariablesPanel(ctk.CTkFrame):
    """Panel lateral: registros, banderas y variables del programa."""

    def __init__(self, master):
        super().__init__(master, width=260, corner_radius=10, fg_color=FONDO_PANEL)
        self.pack_propagate(False)

        Encabezado(self, "Variables", "Limpiar", self.limpiar).pack(
            fill="x", padx=4, pady=(6, 0))

        self._seccion("Registros")
        self.regs = self._rejilla(REGISTROS, "0000")

        self._seccion("Banderas")
        self.flags = self._rejilla(BANDERAS, "0")

        self._seccion("Variables del programa")
        self.lista = ctk.CTkTextbox(
            self, font=MONO, height=120, corner_radius=8, wrap="none",
            fg_color=FONDO_CODIGO, text_color=TEXTO_CODIGO,
        )
        self.lista.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.limpiar()

    # ---------- Construcción ----------
    def _seccion(self, texto):
        ctk.CTkLabel(self, text=texto.upper(), font=("Segoe UI", 11, "bold"),
                     text_color=TEXTO_SUAVE, anchor="w").pack(
            fill="x", padx=14, pady=(12, 4))

    def _rejilla(self, nombres, inicial):
        rejilla = ctk.CTkFrame(self, fg_color="transparent")
        rejilla.pack(fill="x", padx=14)
        etiquetas = {}
        for i, nombre in enumerate(nombres):
            fila, col = divmod(i, 2)
            ctk.CTkLabel(rejilla, text=nombre, font=FUENTE_TITULO, width=34,
                         anchor="w").grid(row=fila, column=col * 2, sticky="w", pady=2)
            valor = ctk.CTkLabel(rejilla, text=inicial, font=MONO, width=64, anchor="w")
            valor.grid(row=fila, column=col * 2 + 1, sticky="w", padx=(0, 14), pady=2)
            etiquetas[nombre] = valor
        return etiquetas

    def _poner_lista(self, texto):
        self.lista.configure(state="normal")
        self.lista.delete("1.0", "end")
        self.lista.insert("1.0", texto)
        self.lista.configure(state="disabled")

    # ---------- Para usar desde la ejecución (Fase 5) ----------
    def actualizar_registros(self, regs):
        for nombre, etiqueta in self.regs.items():
            if nombre in regs:
                etiqueta.configure(text=f"{regs[nombre] & 0xFFFF:04X}")

    def actualizar_banderas(self, flags):
        for nombre, etiqueta in self.flags.items():
            if nombre in flags:
                etiqueta.configure(text="1" if flags[nombre] else "0")

    def actualizar_variables(self, variables):
        self._poner_lista("\n".join(f"{k} = {v}" for k, v in variables.items()))

    def limpiar(self):
        for etiqueta in self.regs.values():
            etiqueta.configure(text="0000")
        for etiqueta in self.flags.values():
            etiqueta.configure(text="0")
        self._poner_lista("(sin datos todavía)")