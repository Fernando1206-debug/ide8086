import tkinter as tk
import tkinter.font as tkfont
import customtkinter as ctk

from ui.panels import FUENTE_TITULO, FONDO_CODIGO, TEXTO_SUAVE
from ui.syntax import Resaltador, COLORES_SINTAXIS
from ui.findbar import BarraBuscar

PALETAS = {
    "Dark": {
        "fondo": "#1e1e1e", "texto": "#d4d4d4", "cursor": "#ffffff",
        "seleccion": "#264f78", "linea_actual": "#2a2d2e",
        "num": "#6e7681", "num_actual": "#d4d4d4",
        "coincidencia": "#4a4000", "coincidencia_actual": "#8a6500",
    },
    "Light": {
        "fondo": "#ffffff", "texto": "#1c1c1c", "cursor": "#000000",
        "seleccion": "#add6ff", "linea_actual": "#f3f3f3",
        "num": "#9a9a9a", "num_actual": "#1c1c1c",
        "coincidencia": "#fff1b8", "coincidencia_actual": "#ffb347",
    },
}

PLANTILLA = """; Programa de ejemplo (8086, formato .COM)
org 100h

inicio:
    mov ah, 09h         ; imprimir cadena
    mov dx, mensaje
    int 21h

    mov al, 5
    add al, 3           ; AL = 8
    mov bl, 1010b
    cmp al, 8
    je  fin

fin:
    mov ah, 4Ch         ; terminar programa
    int 21h

mensaje db "Hola 8086$"
numero  dw 1234h
"""


class TextoObservable(tk.Text):
    """tk.Text que avisa con eventos virtuales:
    <<Cambio>>  -> cambió el texto o se movió el cursor
    <<Edicion>> -> cambió el texto (insertar, borrar, deshacer, rehacer)
    """

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._orig = self._w + "_orig"
        self.tk.call("rename", self._w, self._orig)
        self.tk.createcommand(self._w, self._proxy)

    def _proxy(self, *args):
        try:
            resultado = self.tk.call((self._orig,) + args)
        except tk.TclError:
            return ""
        edicion = (
            args[0] in ("insert", "delete", "replace")
            or (args[0] == "edit" and len(args) > 1 and args[1] in ("undo", "redo"))
        )
        movimiento = (
            args[0] == "mark" and len(args) > 2
            and args[1] == "set" and args[2] == "insert"
        )
        try:
            if edicion or movimiento:
                self.event_generate("<<Cambio>>", when="tail")
            if edicion:
                self.event_generate("<<Edicion>>", when="tail")
        except tk.TclError:
            pass
        return resultado


class NumerosLinea(tk.Canvas):
    def __init__(self, master, texto, fuente, paleta):
        super().__init__(master, width=52, highlightthickness=0, bd=0,
                         bg=paleta["fondo"])
        self.texto = texto
        self.fuente = fuente
        self.paleta = paleta
        self._pendiente = False

    def programar(self):
        if not self._pendiente:
            self._pendiente = True
            self.after_idle(self._redibujar)

    def _redibujar(self):
        self._pendiente = False
        try:
            self.delete("all")
            ultimo = int(self.texto.index("end-1c").split(".")[0])
            ancho = self.fuente.measure("0") * max(3, len(str(ultimo))) + 22
            if int(self.cget("width")) != ancho:
                self.configure(width=ancho)
            actual = int(self.texto.index("insert").split(".")[0])
            primero = int(self.texto.index("@0,0").split(".")[0])
            for num in range(primero, ultimo + 1):
                info = self.texto.dlineinfo(f"{num}.0")
                if info is None:
                    break
                color = self.paleta["num_actual"] if num == actual else self.paleta["num"]
                self.create_text(ancho - 10, info[1] + info[3] / 2, text=str(num),
                                 anchor="e", font=self.fuente, fill=color)
        except tk.TclError:
            pass


class EditorPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, corner_radius=10, fg_color=FONDO_CODIGO)
        clave = "Dark" if ctk.get_appearance_mode() == "Dark" else "Light"
        self.p = PALETAS[clave]
        self.colores = COLORES_SINTAXIS[clave]
        self.fuente = tkfont.Font(family="Consolas", size=13)
        self._nombre = "sin_titulo.asm"
        self._cambiado = False
        self._construir()
        self.poner_texto(PLANTILLA)

    # ---------- Construcción ----------
    def _construir(self):
        p = self.p

        cab = ctk.CTkFrame(self, height=32, fg_color="transparent")
        cab.pack(fill="x", padx=4, pady=(6, 0))
        cab.pack_propagate(False)
        self.titulo = ctk.CTkLabel(cab, text=self._nombre, font=FUENTE_TITULO)
        self.titulo.pack(side="left", padx=10)
        self.pos = ctk.CTkLabel(cab, text="Ln 1, Col 1", font=("Segoe UI", 12),
                                text_color=TEXTO_SUAVE)
        self.pos.pack(side="right", padx=10)

        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        self.cuerpo.grid_rowconfigure(0, weight=1)
        self.cuerpo.grid_columnconfigure(1, weight=1)

        self.texto = TextoObservable(
            self.cuerpo, wrap="none", undo=True, autoseparators=True, maxundo=-1,
            font=self.fuente, bg=p["fondo"], fg=p["texto"],
            insertbackground=p["cursor"], insertwidth=2,
            selectbackground=p["seleccion"], selectforeground=p["texto"],
            inactiveselectbackground=p["seleccion"],
            relief="flat", bd=0, highlightthickness=0, padx=8, pady=4,
            tabs=(self.fuente.measure(" " * 4),),
        )
        self.resaltador = Resaltador(self.texto, self.colores)

        self.numeros = NumerosLinea(self.cuerpo, self.texto, self.fuente, p)
        self.vscroll = ctk.CTkScrollbar(self.cuerpo, command=self.texto.yview)
        self.hscroll = ctk.CTkScrollbar(self.cuerpo, orientation="horizontal",
                                        command=self.texto.xview)
        self.texto.configure(yscrollcommand=self._al_desplazar,
                             xscrollcommand=self.hscroll.set)

        self.numeros.grid(row=0, column=0, sticky="ns")
        self.texto.grid(row=0, column=1, sticky="nsew")
        self.vscroll.grid(row=0, column=2, sticky="ns")
        self.hscroll.grid(row=1, column=1, sticky="ew")

        # Orden de creación = prioridad: la selección queda por encima de todo
        self.texto.tag_configure("linea_actual", background=p["linea_actual"])
        self.texto.tag_configure("buscar", background=p["coincidencia"])
        self.texto.tag_configure("buscar_actual", background=p["coincidencia_actual"])
        self.texto.tag_raise("sel")

        self.barra = BarraBuscar(self)

        t = self.texto
        t.bind("<<Cambio>>", self._al_cambiar)
        t.bind("<<Modified>>", self._al_modificar)
        t.bind("<Configure>", self._al_redimensionar)
        t.bind("<Button-1>", lambda e: t.focus_force(), add="+")
        t.bind("<Control-z>", lambda e: self._atajo(self.deshacer))
        t.bind("<Control-y>", lambda e: self._atajo(self.rehacer))
        t.bind("<Control-Shift-Z>", lambda e: self._atajo(self.rehacer))
        t.bind("<Control-a>", lambda e: self._atajo(self.seleccionar_todo))
        t.bind("<Control-f>", lambda e: self._atajo(self.mostrar_buscar))
        t.bind("<Control-h>", lambda e: self._atajo(self.mostrar_reemplazar))
        t.bind("<Control-g>", lambda e: self._atajo(self.ir_a_linea))
        t.bind("<F3>", lambda e: self._atajo(self.buscar_siguiente))
        t.bind("<Shift-F3>", lambda e: self._atajo(self.buscar_anterior))
        t.bind("<Escape>", self._escape)
        t.bind("<Tab>", self._tabulador)
        t.bind("<Return>", self._salto_linea)

    # ---------- Eventos ----------
    def _al_desplazar(self, a, b):
        self.vscroll.set(a, b)
        self.numeros.programar()
        self.resaltador.programar()

    def _al_redimensionar(self, _=None):
        self.numeros.programar()
        self.resaltador.programar()

    def _al_cambiar(self, _=None):
        t = self.texto
        try:
            linea, col = t.index("insert").split(".")
            self.pos.configure(text=f"Ln {linea}, Col {int(col) + 1}")
            t.tag_remove("linea_actual", "1.0", "end")
            if not t.tag_ranges("sel"):
                t.tag_add("linea_actual", f"{linea}.0", f"{linea}.0 lineend+1c")
        except tk.TclError:
            return
        self.numeros.programar()

    def _al_modificar(self, _=None):
        if self.texto.edit_modified():
            self.texto.edit_modified(False)
            self._cambiado = True
            self._refrescar_titulo()

    def _refrescar_titulo(self):
        self.titulo.configure(text=("● " if self._cambiado else "") + self._nombre)

    def _atajo(self, accion):
        accion()
        return "break"

    def _escape(self, _):
        if self.barra.visible:
            self.barra.cerrar()
            return "break"

    def _tabulador(self, _):
        if self.texto.tag_ranges("sel"):
            self.texto.delete("sel.first", "sel.last")
        self.texto.insert("insert", "    ")
        return "break"

    def _salto_linea(self, _):
        t = self.texto
        if t.tag_ranges("sel"):
            t.delete("sel.first", "sel.last")
        antes = t.get("insert linestart", "insert")
        sangria = antes[: len(antes) - len(antes.lstrip(" \t"))]
        t.insert("insert", "\n" + sangria)
        t.see("insert")
        return "break"

    # ---------- Acciones (las usa el menú Editar) ----------
    def deshacer(self):
        try:
            self.texto.edit_undo()
        except tk.TclError:
            pass
        self.foco()

    def rehacer(self):
        try:
            self.texto.edit_redo()
        except tk.TclError:
            pass
        self.foco()

    def cortar(self):
        self.texto.event_generate("<<Cut>>")
        self.foco()

    def copiar(self):
        self.texto.event_generate("<<Copy>>")
        self.foco()

    def pegar(self):
        self.texto.event_generate("<<Paste>>")
        self.foco()

    def seleccionar_todo(self):
        self.texto.tag_add("sel", "1.0", "end-1c")
        self.foco()

    def mostrar_buscar(self):
        self.barra.abrir("buscar")

    def mostrar_reemplazar(self):
        self.barra.abrir("reemplazar")

    def ir_a_linea(self):
        self.barra.abrir("linea")

    def buscar_siguiente(self):
        self.barra.siguiente(1)

    def buscar_anterior(self):
        self.barra.siguiente(-1)

    def foco(self):
        self.texto.focus_force()

    # ---------- Para archivos (Fase 4) ----------
    def obtener_texto(self):
        return self.texto.get("1.0", "end-1c")

    def poner_texto(self, contenido, nombre=None):
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", contenido)
        self.texto.edit_reset()
        self.texto.edit_modified(False)
        self.texto.mark_set("insert", "1.0")
        self._cambiado = False
        if nombre:
            self._nombre = nombre
        self._refrescar_titulo()
        self._al_cambiar()
        self.resaltador.programar()

    def marcar_guardado(self, nombre=None):
        if nombre:
            self._nombre = nombre
        self._cambiado = False
        self._refrescar_titulo()

    @property
    def modificado(self):
        return self._cambiado