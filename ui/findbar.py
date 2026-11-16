import re
import tkinter as tk
from bisect import bisect_right

import customtkinter as ctk

FUENTE = ("Segoe UI", 12)
TEXTO = ("#1c1c1c", "#f0f0f0")
TEXTO_SUAVE = ("#707070", "#9a9a9a")
ROJO = "#e5534b"
ACTIVO = "#0a64d8"
INACTIVO = ("#dcdcdc", "#3a3a3a")
HOVER = ("#cfcfcf", "#505050")
ANCHO_ETIQUETA = 84


def _boton(master, texto, ancho, comando):
    return ctk.CTkButton(
        master, text=texto, width=ancho, height=26, corner_radius=6, font=FUENTE,
        fg_color=INACTIVO, hover_color=HOVER, text_color=TEXTO, command=comando)


class BarraBuscar(ctk.CTkFrame):
    """Barra de buscar / reemplazar / ir a línea para el editor."""

    def __init__(self, editor):
        super().__init__(editor, corner_radius=8, fg_color=("#ececec", "#2b2b2b"))
        self.ed = editor
        self.t = editor.texto
        self.modo = None          # "buscar", "reemplazar" o "linea"
        self.visible = False
        self.coin = []            # coincidencias (objetos de re.Match)
        self.actual = -1
        self._inicios = [0]
        self._job = None
        self._mala = False

        self.caso = tk.BooleanVar(value=False)    # True = distinguir mayúsculas
        self.regex = tk.BooleanVar(value=False)   # True = expresión regular
        self.v_buscar = tk.StringVar()
        self.v_reemplazar = tk.StringVar()
        self.v_linea = tk.StringVar()

        # ---------- Fila: buscar ----------
        self.f_buscar = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.f_buscar, text="Buscar", width=ANCHO_ETIQUETA,
                     anchor="w", font=FUENTE).pack(side="left")
        self.e_buscar = ctk.CTkEntry(self.f_buscar, textvariable=self.v_buscar,
                                     height=28, font=FUENTE)
        self.e_buscar.pack(side="left", fill="x", expand=True)
        self.lbl_cont = ctk.CTkLabel(self.f_buscar, text="", width=96, font=FUENTE,
                                     text_color=TEXTO_SUAVE)
        self.lbl_cont.pack(side="left", padx=6)
        _boton(self.f_buscar, "▲", 30, lambda: self.siguiente(-1)).pack(
            side="left", padx=(0, 4))
        _boton(self.f_buscar, "▼", 30, lambda: self.siguiente(1)).pack(side="left")
        self.b_caso = _boton(self.f_buscar, "Aa", 34,
                             lambda: self._alternar(self.caso, self.b_caso))
        self.b_caso.pack(side="left", padx=(8, 4))
        self.b_regex = _boton(self.f_buscar, ".*", 34,
                              lambda: self._alternar(self.regex, self.b_regex))
        self.b_regex.pack(side="left")
        _boton(self.f_buscar, "✕", 30, self.cerrar).pack(side="left", padx=(8, 0))

        # ---------- Fila: reemplazar ----------
        self.f_reemplazar = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.f_reemplazar, text="Reemplazar", width=ANCHO_ETIQUETA,
                     anchor="w", font=FUENTE).pack(side="left")
        self.e_reemplazar = ctk.CTkEntry(self.f_reemplazar, textvariable=self.v_reemplazar,
                                         height=28, font=FUENTE)
        self.e_reemplazar.pack(side="left", fill="x", expand=True)
        _boton(self.f_reemplazar, "Reemplazar", 90, self.reemplazar_uno).pack(
            side="left", padx=(8, 4))
        _boton(self.f_reemplazar, "Reemplazar todo", 120, self.reemplazar_todo).pack(
            side="left")

        # ---------- Fila: ir a línea ----------
        self.f_linea = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.f_linea, text="Ir a línea", width=ANCHO_ETIQUETA,
                     anchor="w", font=FUENTE).pack(side="left")
        self.e_linea = ctk.CTkEntry(self.f_linea, textvariable=self.v_linea,
                                    width=110, height=28, font=FUENTE)
        self.e_linea.pack(side="left")
        _boton(self.f_linea, "Ir", 40, self._ir).pack(side="left", padx=(8, 8))
        self.lbl_info = ctk.CTkLabel(self.f_linea, text="", font=FUENTE,
                                     text_color=TEXTO_SUAVE)
        self.lbl_info.pack(side="left")
        _boton(self.f_linea, "✕", 30, self.cerrar).pack(side="right")

        # ---------- Eventos ----------
        self.v_buscar.trace_add("write", lambda *a: self.actualizar(True))
        self.t.bind("<<Edicion>>", self._al_editar, add="+")

        self.e_buscar.bind("<Return>", lambda e: self._brk(lambda: self.siguiente(1)))
        self.e_buscar.bind("<Shift-Return>", lambda e: self._brk(lambda: self.siguiente(-1)))
        self.e_reemplazar.bind("<Return>", lambda e: self._brk(self.reemplazar_uno))
        self.e_linea.bind("<Return>", lambda e: self._brk(self._ir))
        for entrada in (self.e_buscar, self.e_reemplazar, self.e_linea):
            entrada.bind("<Control-f>", lambda e: self._brk(self.ed.mostrar_buscar))
            entrada.bind("<Control-h>", lambda e: self._brk(self.ed.mostrar_reemplazar))
            entrada.bind("<Control-g>", lambda e: self._brk(self.ed.ir_a_linea))
            entrada.bind("<F3>", lambda e: self._brk(lambda: self.siguiente(1)))
            entrada.bind("<Shift-F3>", lambda e: self._brk(lambda: self.siguiente(-1)))
            entrada.bind("<Escape>", lambda e: self._brk(self.cerrar))

    # ---------- Abrir y cerrar ----------
    def abrir(self, modo):
        self.modo = modo
        if not self.visible:
            self.pack(fill="x", padx=10, pady=(0, 6), before=self.ed.cuerpo)
            self.visible = True
        self.f_buscar.pack_forget()
        self.f_reemplazar.pack_forget()
        self.f_linea.pack_forget()

        if modo == "linea":
            self.actualizar()  # quita los resaltados de búsqueda
            self.f_linea.pack(fill="x", padx=8, pady=6)
            self.v_linea.set("")
            self.lbl_info.configure(text=f"1 – {self._total()}", text_color=TEXTO_SUAVE)
            self._enfocar(self.e_linea)
            return

        self.f_buscar.pack(fill="x", padx=8, pady=(6, 3 if modo == "reemplazar" else 6))
        if modo == "reemplazar":
            self.f_reemplazar.pack(fill="x", padx=8, pady=(0, 6))
        try:
            seleccion = self.t.get("sel.first", "sel.last")
        except tk.TclError:
            seleccion = ""
        if seleccion and "\n" not in seleccion:
            self.v_buscar.set(seleccion)
        self.actualizar(True)
        self._enfocar(self.e_buscar)

    def cerrar(self):
        self.pack_forget()
        self.visible = False
        self.t.tag_remove("buscar", "1.0", "end")
        self.t.tag_remove("buscar_actual", "1.0", "end")
        self.coin = []
        self.actual = -1
        self.ed.foco()

    def _enfocar(self, entrada):
        def accion():
            entrada.focus_force()
            entrada.select_range(0, "end")
        self.after(30, accion)

    @staticmethod
    def _brk(accion):
        accion()
        return "break"

    # ---------- Utilidades ----------
    def _total(self):
        return int(self.t.index("end-1c").split(".")[0])

    def _texto_e_inicios(self):
        texto = self.t.get("1.0", "end-1c")
        inicios = [0]
        for linea in texto.split("\n")[:-1]:
            inicios.append(inicios[-1] + len(linea) + 1)
        return texto, inicios

    @staticmethod
    def _indice(inicios, pos):
        i = bisect_right(inicios, pos) - 1
        return f"{i + 1}.{pos - inicios[i]}"

    def _contador(self, texto, error=False):
        self.lbl_cont.configure(text=texto, text_color=ROJO if error else TEXTO_SUAVE)

    def _alternar(self, var, boton):
        var.set(not var.get())
        activo = var.get()
        boton.configure(fg_color=ACTIVO if activo else INACTIVO,
                        text_color="white" if activo else TEXTO)
        self.actualizar(True)

    def _compilar(self):
        patron = self.v_buscar.get()
        if not patron:
            return None
        if not self.regex.get():
            patron = re.escape(patron)
        flags = re.MULTILINE | (0 if self.caso.get() else re.IGNORECASE)
        try:
            return re.compile(patron, flags)
        except re.error:
            self._mala = True
            return None

    # ---------- Buscar ----------
    def actualizar(self, mover=False):
        t = self.t
        t.tag_remove("buscar", "1.0", "end")
        t.tag_remove("buscar_actual", "1.0", "end")
        self.coin = []
        self.actual = -1
        if not self.visible or self.modo == "linea":
            return

        self._mala = False
        rx = self._compilar()
        if rx is None:
            if self._mala:
                self._contador("Regex inválida", error=True)
            else:
                self._contador("")
            return

        texto, inicios = self._texto_e_inicios()
        self._inicios = inicios
        self.coin = [m for m in rx.finditer(texto) if m.end() > m.start()]
        if not self.coin:
            self._contador("Sin resultados", error=True)
            return

        rangos = []
        for m in self.coin:
            rangos.append(self._indice(inicios, m.start()))
            rangos.append(self._indice(inicios, m.end()))
        t.tag_add("buscar", *rangos)

        cursor = len(t.get("1.0", "insert"))
        self.actual = next((i for i, m in enumerate(self.coin) if m.start() >= cursor), 0)
        self._mostrar_actual(mover)

    def _mostrar_actual(self, mover):
        t = self.t
        m = self.coin[self.actual]
        a = self._indice(self._inicios, m.start())
        b = self._indice(self._inicios, m.end())
        t.tag_remove("buscar_actual", "1.0", "end")
        t.tag_add("buscar_actual", a, b)
        if mover:
            t.mark_set("insert", a)
            t.see(a)
        self._contador(f"{self.actual + 1} de {len(self.coin)}")

    def siguiente(self, paso=1):
        if not self.visible or self.modo == "linea":
            self.abrir("buscar")
            return
        if not self.coin:
            return
        self.actual = (self.actual + paso) % len(self.coin)
        self._mostrar_actual(True)

    def _al_editar(self, _=None):
        if self.visible and self.modo != "linea" and self._job is None:
            self._job = self.after(150, self._refrescar)

    def _refrescar(self):
        self._job = None
        if self.visible:
            self.actualizar(False)

    # ---------- Reemplazar ----------
    def _reemplazo(self, m):
        texto = self.v_reemplazar.get()
        if not self.regex.get():
            return texto
        try:
            return m.expand(texto)
        except (re.error, IndexError):
            self._contador("Reemplazo inválido", error=True)
            return None

    def reemplazar_uno(self):
        if self.actual < 0 or not self.coin:
            return
        t = self.t
        m = self.coin[self.actual]
        a = self._indice(self._inicios, m.start())
        b = self._indice(self._inicios, m.end())
        if t.get(a, b) != m.group():   # el texto cambió: recalcular y salir
            self.actualizar(False)
            return
        nuevo = self._reemplazo(m)
        if nuevo is None:
            return
        t.edit_separator()
        t.delete(a, b)
        t.insert(a, nuevo)
        t.edit_separator()
        t.mark_set("insert", f"{a}+{len(nuevo)}c")
        self.actualizar(True)

    def reemplazar_todo(self):
        self.actualizar(False)
        if not self.coin:
            return
        cambios = []
        for m in self.coin:
            nuevo = self._reemplazo(m)
            if nuevo is None:
                return
            cambios.append((m, nuevo))

        t = self.t
        inicios = self._inicios
        t.configure(autoseparators=False)   # todo cuenta como UN solo paso de deshacer
        t.edit_separator()
        try:
            for m, nuevo in reversed(cambios):   # de atrás hacia adelante
                a = self._indice(inicios, m.start())
                b = self._indice(inicios, m.end())
                t.delete(a, b)
                t.insert(a, nuevo)
        finally:
            t.edit_separator()
            t.configure(autoseparators=True)

        self.actualizar(False)
        self._contador(f"{len(cambios)} reemplazo(s)")

    # ---------- Ir a línea ----------
    def _ir(self):
        try:
            n = int(self.v_linea.get().strip())
        except ValueError:
            self.lbl_info.configure(text="Escribe un número", text_color=ROJO)
            return
        total = self._total()
        if not 1 <= n <= total:
            self.lbl_info.configure(text=f"Rango válido: 1 – {total}", text_color=ROJO)
            return
        self.t.mark_set("insert", f"{n}.0")
        self.t.see(f"{n}.0")
        self.cerrar()