import tkinter as tk
import customtkinter as ctk

SEPARADOR = "-"
TRANSPARENTE = "#010101"  # color que Windows vuelve transparente (esquinas redondeadas)
FUENTE = ("Segoe UI", 13)
AZUL = "#0a64d8"
TEXTO = ("#1c1c1c", "#f0f0f0")
TEXTO_ATAJO = ("#707070", "#9a9a9a")
HOVER_BARRA = ("#d0d0d0", "#404040")


class Desplegable(tk.Toplevel):
    """Menú desplegable con estilo propio."""

    def __init__(self, app, boton, items, cerrar):
        super().__init__(app)
        self._cerrar = cerrar
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=TRANSPARENTE)
        self.attributes("-transparentcolor", TRANSPARENTE)

        marco = ctk.CTkFrame(
            self, corner_radius=10, border_width=1, bg_color=TRANSPARENTE,
            fg_color=("#f6f6f6", "#2b2b2b"), border_color=("#c8c8c8", "#4a4a4a"),
        )
        marco.pack()

        ctk.CTkFrame(marco, height=4, fg_color="transparent").pack()
        for item in items:
            if item == SEPARADOR:
                ctk.CTkFrame(marco, height=1, fg_color=("#d4d4d4", "#4a4a4a")).pack(
                    fill="x", padx=12, pady=4)
            else:
                texto, atajo, comando = item
                self._fila(marco, texto, atajo, comando)
        ctk.CTkFrame(marco, height=4, fg_color="transparent").pack()

        self.update_idletasks()
        x = boton.winfo_rootx()
        y = boton.winfo_rooty() + boton.winfo_height() + 2
        self.geometry(f"+{x}+{y}")

    def _fila(self, marco, texto, atajo, comando):
        fila = ctk.CTkFrame(marco, height=26, corner_radius=6, fg_color="transparent")
        fila.pack(fill="x", padx=6)
        izq = ctk.CTkLabel(fila, text=texto, anchor="w", height=24, font=FUENTE)
        izq.pack(side="left", padx=(8, 24))
        der = ctk.CTkLabel(fila, text=atajo, anchor="e", height=24, font=FUENTE,
                           text_color=TEXTO_ATAJO)
        der.pack(side="right", padx=(0, 8))

        for w in (fila, izq, der):
            w.bind("<Enter>", lambda e: self._resaltar(fila, izq, der, True), add="+")
            w.bind("<Leave>", lambda e: self._resaltar(fila, izq, der, False), add="+")
            w.bind("<Button-1>", lambda e: self._elegir(comando), add="+")

    def _resaltar(self, fila, izq, der, activo):
        if activo:
            fila.configure(fg_color=AZUL)
            izq.configure(text_color="white")
            der.configure(text_color="white")
            return
        # Si el mouse sigue dentro de la fila (pasó a una etiqueta), no apagar
        x, y = self.winfo_pointerxy()
        w = self.winfo_containing(x, y)
        if w is not None and (str(w) == str(fila) or str(w).startswith(str(fila) + ".")):
            return
        fila.configure(fg_color="transparent")
        izq.configure(text_color=TEXTO)
        der.configure(text_color=TEXTO_ATAJO)

    def _elegir(self, comando):
        app = self.master
        app.after(10, lambda: (self._cerrar(), comando() if comando else None))


class MenuBar(ctk.CTkFrame):
    def __init__(self, app, menus):
        super().__init__(app, height=30, corner_radius=0, fg_color=("#ececec", "#2a2a2a"))
        self.app = app
        self.menus = menus
        self.botones = {}
        self.abierto = None
        self.desplegable = None

        for i, nombre in enumerate(menus):
            b = ctk.CTkButton(
                self, text=nombre, width=22 + 8 * len(nombre), height=24,
                corner_radius=6, fg_color="transparent", hover_color=HOVER_BARRA,
                text_color=TEXTO, font=FUENTE,
                command=lambda n=nombre: self.alternar(n),
            )
            b.pack(side="left", padx=(8 if i == 0 else 0, 0), pady=3)
            b.bind("<Enter>", lambda e, n=nombre: self._pasar(n), add="+")
            self.botones[nombre] = b

        app.bind("<Button-1>", self._clic_global, add="+")
        app.bind("<Escape>", lambda e: self.cerrar(), add="+")

    def alternar(self, nombre):
        if self.abierto == nombre:
            self.cerrar()
        else:
            self.abrir(nombre)

    def abrir(self, nombre):
        self.cerrar()
        items = self.menus[nombre]
        if callable(items):          # menú dinámico (ej. archivos recientes)
            items = items()
        self.abierto = nombre
        self.botones[nombre].configure(fg_color=HOVER_BARRA)
        self.desplegable = Desplegable(self.app, self.botones[nombre],
                                       items, self.cerrar)

    def cerrar(self):
        if self.desplegable is not None:
            self.desplegable.destroy()
            self.desplegable = None
        if self.abierto is not None:
            self.botones[self.abierto].configure(fg_color="transparent")
            self.abierto = None

    def _pasar(self, nombre):
        # Con un menú abierto, pasar el mouse sobre otro lo abre (como en Mac)
        if self.abierto is not None and self.abierto != nombre:
            self.abrir(nombre)

    def _clic_global(self, e):
        if self.abierto is None:
            return
        if str(e.widget).startswith(str(self) + "."):
            return  # clic en un botón del menú: lo maneja el botón
        self.cerrar()