import ctypes
import os
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.archivos import (PLANTILLA_NUEVO, leer_archivo, escribir_archivo,
                           recientes, agregar_reciente, limpiar_recientes)
from ui.menubar import MenuBar, SEPARADOR
from ui.editor import EditorPanel
from ui.panels import VariablesPanel
from ui.fases import FasesPanel, TERMINAL, LEXER, PARSER, SEMANTIC, CODEGEN
from ui.marcas import Marcas
from ui.pantalla import VentanaPantalla
from assembler.compilador import compilar as compilar_fuente
from assembler.tablas import todas_las_instrucciones
from core.plantillas import CALCULADORA, HOLA_MUNDO
from core.emulador import Emulador, ErrorEmulador

MIN_W, MIN_H = 800, 500
NOMBRE_APP = "IDE 8086"
TIPOS_ARCHIVO = [("Ensamblador", "*.asm *.s *.inc"), ("Todos los archivos", "*.*")]


class TitleBar(ctk.CTkFrame):
    def __init__(self, master, title):
        super().__init__(master, height=38, corner_radius=0,
                         fg_color=("#e6e6e6", "#323232"))
        self.pack_propagate(False)

        botones = [
            ("#ff5f57", "#ff3b30", master.cerrar),
            ("#febc2e", "#f5a700", master.minimizar),
            ("#28c840", "#1fa832", master.maximizar),
        ]
        for i, (color, hover, cmd) in enumerate(botones):
            ctk.CTkButton(
                self, text="", width=13, height=13, corner_radius=7,
                fg_color=color, hover_color=hover, border_width=0, command=cmd,
            ).pack(side="left", padx=(14 if i == 0 else 8, 0))

        self.titulo = ctk.CTkLabel(self, text=title, font=("Segoe UI", 13, "bold"))
        self.titulo.place(relx=0.5, rely=0.5, anchor="center")

        for w in (self, self.titulo):
            w.bind("<ButtonPress-1>", master.iniciar_arrastre)
            w.bind("<B1-Motion>", master.arrastrar)
            w.bind("<Double-Button-1>", lambda e: master.maximizar())

    def poner_titulo(self, texto):
        self.titulo.configure(text=texto)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(NOMBRE_APP)
        self.geometry("1100x720+150+100")
        self.minsize(MIN_W, MIN_H)

        self._maximizada = False
        self._minimizada = False
        self._geo_normal = ""
        self._dx = self._dy = 0

        # Archivo actual
        self.ruta = None
        self.nombre_sin_ruta = "sin_titulo.asm"
        self.codificacion = "utf-8"

        self.overrideredirect(True)  # quita la barra nativa de Windows
        self.bind("<Map>", self._al_restaurar)
        self.protocol("WM_DELETE_WINDOW", self.cerrar)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Fila 0: barra de título
        self.barra_titulo = TitleBar(self, NOMBRE_APP)
        self.barra_titulo.grid(row=0, column=0, sticky="ew")

        # Fila 1: barra de menús
        self.menubar = MenuBar(self, self._menus())
        self.menubar.grid(row=1, column=0, sticky="ew")

        # Fila 2: zona de trabajo (editor + terminal | variables)
        self.zona = ctk.CTkFrame(self, fg_color="transparent")
        self.zona.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.zona.grid_columnconfigure(0, weight=1)
        self.zona.grid_rowconfigure(0, weight=3, uniform="alto")
        self.zona.grid_rowconfigure(1, weight=2, uniform="alto")

        self.editor = EditorPanel(self.zona)
        self.editor.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))

        # Panel inferior: terminal + una pestaña por etapa del compilador
        self.fases = FasesPanel(self.zona)
        self.fases.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self.terminal = self.fases.terminal
        self.marcas = Marcas(self.editor.texto)

        # Cuadro de entrada del programa (las teclas se envían al programa al instante)
        self.entrada = ctk.CTkEntry(
            self.zona, height=30, corner_radius=8,
            placeholder_text="Entrada del programa: cuando se ejecute, haz clic aquí y escribe "
                             "(Enter = tecla Enter)")
        self.entrada.grid(row=2, column=0, sticky="ew", padx=(0, 10), pady=(8, 0))
        self.entrada._entry.bind("<Key>", self._tecla_entrada)

        self.variables = VariablesPanel(self.zona)
        self.variables.grid(row=0, column=1, rowspan=2, sticky="ns")

        # Fila 3: barra de estado + esquina para redimensionar
        self.barra = ctk.CTkFrame(self, height=28, corner_radius=0,
                                  fg_color=("#e6e6e6", "#2b2b2b"))
        self.barra.grid(row=3, column=0, sticky="ew")
        self.barra.grid_columnconfigure(0, weight=1)
        self.estado = ctk.CTkLabel(self.barra, text="Listo", anchor="w")
        self.estado.grid(row=0, column=0, sticky="ew", padx=14)
        self.grip = ctk.CTkLabel(self.barra, text="◢", width=24,
                                 cursor="size_nw_se")
        self.grip.grid(row=0, column=1, sticky="e")
        self.grip.bind("<B1-Motion>", self.redimensionar)

        self.pantalla = None       # ventana gráfica (modo 13h)
        self.cpu = None            # emulador en ejecución
        self.ultimo = None         # último resultado de compilación
        self._job = None
        self._atajos_archivo()
        self._atajos_compilador()
        self._teclado_terminal()
        self._actualizar_titulo()
        self.after(50, self._ajustes_windows)
        self.after(400, self.editor.foco)

    # ---------- Ajustes de Windows ----------
    def _ajustes_windows(self):
        """Muestra la ventana en la barra de tareas y redondea esquinas (Win 11)."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            estilo = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            estilo = (estilo & ~0x00000080) | 0x00040000  # APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, estilo)
            redondeo = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(redondeo), ctypes.sizeof(redondeo))
        except Exception:
            pass
        self.withdraw()
        self.after(10, self.deiconify)

    # ---------- Botones de ventana ----------
    def cerrar(self):
        if self.confirmar_descartar():
            self.destroy()

    def minimizar(self):
        self._minimizada = True
        self.overrideredirect(False)
        self.iconify()

    def _al_restaurar(self, event):
        if event.widget is self and self._minimizada and self.state() == "normal":
            self._minimizada = False
            self.overrideredirect(True)
            self.after(20, self._ajustes_windows)

    def maximizar(self):
        if self._maximizada:
            self.geometry(self._geo_normal)
        else:
            self._geo_normal = self.geometry()
            ancho = self.winfo_screenwidth()
            alto = self.winfo_screenheight() - 48  # deja libre la barra de tareas
            self.geometry(f"{ancho}x{alto}+0+0")
        self._maximizada = not self._maximizada

    # ---------- Mover y redimensionar ----------
    def iniciar_arrastre(self, e):
        self._dx = e.x_root - self.winfo_x()
        self._dy = e.y_root - self.winfo_y()

    def arrastrar(self, e):
        if not self._maximizada:
            self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def redimensionar(self, e):
        ancho = max(MIN_W, e.x_root - self.winfo_x())
        alto = max(MIN_H, e.y_root - self.winfo_y())
        self.geometry(f"{ancho}x{alto}")

    # ---------- Archivos ----------
    def _atajos_archivo(self):
        acciones = {
            "<Control-n>": self.nuevo,
            "<Control-o>": self.abrir,
            "<Control-s>": self.guardar,
            "<Control-Shift-S>": self.guardar_como,
            "<Control-Shift-s>": self.guardar_como,
        }
        for secuencia, accion in acciones.items():
            # En el editor, "break" evita los atajos propios de Tk (Ctrl+O abre línea)
            self.editor.texto.bind(secuencia, lambda e, a=accion: (a(), "break")[1])
            self.bind_all(secuencia, lambda e, a=accion: a())

    def _atajos_compilador(self):
        for secuencia, accion in (("<F7>", self.compilar_programa),
                                  ("<F5>", lambda: self.compilar_programa(True)),
                                  ("<F8>", self.ejecutar),
                                  ("<Shift-F5>", self.detener)):
            self.bind_all(secuencia, lambda e, a=accion: a())

    def _nombre_actual(self):
        return os.path.basename(self.ruta) if self.ruta else self.nombre_sin_ruta

    def _carpeta_inicial(self):
        if self.ruta:
            return os.path.dirname(self.ruta)
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        return docs if os.path.isdir(docs) else os.path.expanduser("~")

    def _actualizar_titulo(self):
        texto = f"{self._nombre_actual()} — {NOMBRE_APP}"
        self.title(texto)
        self.barra_titulo.poner_titulo(texto)

    def confirmar_descartar(self):
        """True si se puede continuar: sin cambios, ya guardados o descartados."""
        if not self.editor.modificado:
            return True
        respuesta = messagebox.askyesnocancel(
            NOMBRE_APP,
            f"¿Quieres guardar los cambios en «{self._nombre_actual()}»?\n"
            "Si no los guardas, se perderán.",
            icon="warning", parent=self)
        if respuesta is None:      # Cancelar
            return False
        if respuesta:              # Sí: guardar (si cancela el guardado, no continuar)
            return self.guardar()
        return True                # No: descartar

    def nuevo(self):
        if not self.confirmar_descartar():
            return
        self.ruta = None
        self.nombre_sin_ruta = "sin_titulo.asm"
        self.codificacion = "utf-8"
        self.editor.poner_texto(PLANTILLA_NUEVO, "sin_titulo.asm")
        self._actualizar_titulo()
        self.estado.configure(text="Documento nuevo")
        self.editor.foco()

    def abrir(self):
        if not self.confirmar_descartar():
            return
        ruta = filedialog.askopenfilename(
            parent=self, title="Abrir archivo",
            initialdir=self._carpeta_inicial(), filetypes=TIPOS_ARCHIVO)
        if ruta:
            self._cargar(ruta)
        else:
            self.editor.foco()

    def abrir_reciente(self, ruta):
        if not self.confirmar_descartar():
            return
        if not os.path.isfile(ruta):
            messagebox.showerror(NOMBRE_APP, f"El archivo ya no existe:\n{ruta}",
                                 parent=self)
            return
        self._cargar(ruta)

    def _cargar(self, ruta):
        try:
            texto, codificacion = leer_archivo(ruta)
        except (OSError, ValueError) as e:
            messagebox.showerror(NOMBRE_APP, f"No se pudo abrir el archivo:\n{e}",
                                 parent=self)
            return False
        self.ruta = os.path.abspath(ruta)
        self.codificacion = codificacion
        self.editor.poner_texto(texto, os.path.basename(self.ruta))
        agregar_reciente(self.ruta)
        self._actualizar_titulo()
        self.estado.configure(text=f"Abierto: {self.ruta}")
        self.editor.foco()
        return True

    def guardar(self):
        if self.ruta is None:
            return self.guardar_como()
        return self._escribir(self.ruta)

    def guardar_como(self):
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Guardar como", defaultextension=".asm",
            initialdir=self._carpeta_inicial(), initialfile=self._nombre_actual(),
            filetypes=[("Ensamblador", "*.asm"), ("Todos los archivos", "*.*")])
        if not ruta:
            self.editor.foco()
            return False
        return self._escribir(ruta)

    def _escribir(self, ruta):
        try:
            self.codificacion = escribir_archivo(
                ruta, self.editor.obtener_texto(), self.codificacion)
        except OSError as e:
            messagebox.showerror(NOMBRE_APP, f"No se pudo guardar el archivo:\n{e}",
                                 parent=self)
            return False
        self.ruta = os.path.abspath(ruta)
        self.editor.marcar_guardado(os.path.basename(self.ruta))
        agregar_reciente(self.ruta)
        self._actualizar_titulo()
        self.estado.configure(text=f"Guardado: {self.ruta}")
        self.editor.foco()
        return True

    # ---------- Compilador ----------
    def _carpeta_salida(self):
        if self.ruta:
            return os.path.dirname(self.ruta)
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        carpeta = os.path.join(base, "IDE8086", "build")
        os.makedirs(carpeta, exist_ok=True)
        return carpeta

    def compilar_programa(self, ejecutar=False):
        """Corre las 4 etapas (Lexer, Parser, Semantic, CodeGen) y muestra todo."""
        t = self.terminal
        t.limpiar()
        nombre = self._nombre_actual()
        t.escribir(f"> compilando {nombre}\n", "suave")
        res = compilar_fuente(self.editor.obtener_texto())
        self.fases.mostrar(res)
        self.marcas.marcar(res.diagnosticos)

        for d in res.diagnosticos:
            etiqueta = "error" if d.gravedad == "error" else "aviso"
            t.escribir(f"{d.gravedad} [{d.fase}] ", etiqueta)
            if d.linea > 0:
                t.escribir_enlace(f"línea {d.linea}:{d.col}",
                                  lambda l=d.linea, c=d.col: (self.marcas.ir_a(l, c)))
                t.escribir(": ")
            t.escribir(f"{d.mensaje}\n")

        # Resumen de etapas: ✓ ok, ✗ falló, – no se ejecutó
        orden = [("Lexer", res.tokens), ("Parser", res.programa),
                 ("Semantic", res.tabla), ("CodeGen", res.codigo)]
        falla = False
        partes = []
        for etapa, dato in orden:
            if falla:
                partes.append(f"{etapa} –")
            elif dato is None:
                partes.append(f"{etapa} ✗")
                falla = True
            else:
                partes.append(f"{etapa} ✓")
        t.escribir("\n" + "  ".join(partes) + "\n", "suave")

        if not res.exito:
            t.escribir(f"Compilación fallida: {res.diagnosticos.n_errores} error(es), "
                       f"{res.diagnosticos.n_avisos} aviso(s)\n", "error")
            self.fases.seleccionar(TERMINAL)
            self.estado.configure(text="Compilación fallida")
            return None

        base = os.path.splitext(nombre)[0]
        carpeta = self._carpeta_salida()
        com = os.path.join(carpeta, base + ".com")
        try:
            with open(com, "wb") as f:
                f.write(res.codigo)
            with open(os.path.join(carpeta, base + ".lst"), "w", encoding="utf-8") as f:
                f.write(res.codegen.listado)
        except OSError as e:
            t.escribir(f"No se pudo escribir la salida: {e}\n", "error")
            return None
        t.escribir(f"OK: {len(res.codigo)} bytes → {com}\n", "ok")
        if res.diagnosticos.n_avisos:
            t.escribir(f"({res.diagnosticos.n_avisos} aviso(s))\n", "aviso")
        self.ultimo = res
        self.estado.configure(text=f"Compilado: {len(res.codigo)} bytes")
        if ejecutar:
            self.ejecutar()
        return res

    # ---------- Ejecución (emulador 8086) ----------
    def _teclado_terminal(self):
        """Las teclas que se escriben en la terminal van al programa en ejecución."""
        tb = self.terminal.texto._textbox
        tb.bind("<Key>", self._tecla_terminal)
        # Con la ventana sin borde de Windows hay que forzar el foco; y un Text
        # deshabilitado no lo toma solo al hacer clic.
        tb.bind("<Button-1>", lambda e: (tb.focus_force(), "break")[1])
        tb.bind("<Key>", self._tecla_terminal)
        self.bind_all("<Key>", self._tecla_global, add="+")

    def _tecla_entrada(self, e):
        """Cada tecla pulsada en el cuadro de entrada va directo al programa."""
        if e.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                        "Caps_Lock", "Tab") or (e.state & 0x4):
            return None                       # Ctrl+C, etc. funcionan normal
        if self.cpu is not None and not self.cpu.terminado:
            self._tecla_terminal(e)
        return "break"                        # el cuadro nunca guarda texto

    def _tecla_global(self, e):
        """Respaldo: si hay un programa esperando y el foco no está en un cuadro de
        texto (editor, buscar…), la tecla va al programa."""
        if self.cpu is None or self.cpu.terminado:
            return
        w = self.focus_get()
        clase = w.winfo_class() if w is not None else ""
        if clase in ("Text", "Entry", "TEntry"):
            return
        self._tecla_terminal(e)

    def _tecla_terminal(self, e):
        if self.cpu is not None and not self.cpu.terminado:
            c = {"Return": "\r", "BackSpace": "\b"}.get(e.keysym, e.char)
            if c and (c in ("\r", "\b") or c.isprintable()):
                self.cpu.dar_tecla(c)
        return "break"

    def ejecutar(self):
        if self.ultimo is None or not self.ultimo.exito:
            self.compilar_programa(False)
            if self.ultimo is None or not self.ultimo.exito:
                return
        self.detener(silencioso=True)
        self._cerrar_pantalla()
        self.terminal.escribir("\n--- ejecución (escribe en el cuadro de entrada de abajo) ---\n", "suave")
        self.fases.seleccionar(TERMINAL)
        self.cpu = Emulador(self.ultimo.codigo, self.ultimo.origen)
        self._volcado = 0
        self.entrada._entry.focus_force()
        self.after(150, self.entrada._entry.focus_force)
        self.estado.configure(text="Ejecutando…")
        self._job = self.after(1, self._ciclo)

    def _ciclo(self):
        cpu = self.cpu
        if cpu is None:
            return
        try:
            cpu.correr(15000 if cpu.modo_grafico else 3000)
        except ErrorEmulador as e:
            self._sacar_salida()
            self.terminal.escribir(f"\nError en ejecución: {e}\n", "error")
            self._fin("Error en ejecución")
            return
        self._sacar_salida()
        if cpu.modo_grafico:
            self._pintar_pantalla(cpu)
        if cpu.terminado:
            self.terminal.escribir(f"\n--- programa terminado (código {cpu.codigo_salida}, "
                                   f"{cpu.pasos} instrucciones) ---\n", "ok")
            self._fin("Programa terminado")
        elif not cpu.modo_grafico and cpu.pasos > 30_000_000:   # los juegos no tienen límite
            self.terminal.escribir("\nSe detuvo: demasiadas instrucciones (¿bucle infinito?)\n",
                                   "aviso")
            self._fin("Detenido")
        else:
            self._job = self.after(30 if cpu.esperando else 1, self._ciclo)

    # ---------- pantalla gráfica ----------
    def _pintar_pantalla(self, cpu):
        if self.pantalla is None:
            self.pantalla = VentanaPantalla(self, self.detener_y_cerrar,
                                            lambda c: cpu_dar(self, c))
            cpu.turbo = 4            # los juegos esperan con bucles enormes: se acortan
        self.pantalla.actualizar(cpu)

    def _cerrar_pantalla(self):
        if self.pantalla is not None:
            try:
                self.pantalla.destroy()
            except Exception:
                pass
            self.pantalla = None

    def detener_y_cerrar(self):
        self.detener(silencioso=True)
        self._cerrar_pantalla()
        self.terminal.escribir("\n--- detenido (se cerró la pantalla) ---\n", "aviso")

    def _sacar_salida(self):
        cpu = self.cpu
        if not cpu.salida:
            return
        texto = "".join(cpu.salida).replace("\r\n", "\n").replace("\r", "")
        cpu.salida.clear()
        tb = self.terminal.texto._textbox
        trozos = texto.split("\b \b")
        for k, trozo in enumerate(trozos):
            if k > 0:                       # borrar el último carácter escrito
                tb.configure(state="normal")
                tb.delete("end-2c")
                tb.configure(state="disabled")
            if trozo:
                self.terminal.escribir(trozo)

    def _fin(self, mensaje):
        cpu = self.cpu
        if cpu is not None and self.pantalla is not None:
            self._pintar_pantalla(cpu)
            self.pantalla.terminado()
        self.cpu = None
        self._job = None
        if cpu is not None:
            self.variables.actualizar_registros({n.upper(): v for n, v in cpu.r.items()})
            self.variables.actualizar_banderas(
                {"ZF": cpu.zf, "CF": cpu.cf, "SF": cpu.sf, "OF": cpu.of})
            datos = {}
            for e in self.ultimo.tabla:
                if e.tipo == "dato":
                    datos[e.nombre] = (cpu.rd(e.valor, e.tam or 1), e.tam or 1)
            self.variables.actualizar_variables(
                {k: f"{v} ({v:0{2 * t}X}h)" for k, (v, t) in datos.items()} or {"(sin variables)": ""})
        self.estado.configure(text=mensaje)

    def detener(self, silencioso=False):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        if self.cpu is not None:
            if not silencioso:
                self.terminal.escribir("\n--- detenido por el usuario ---\n", "aviso")
            self._fin("Detenido")

    def ver_etapa(self, nombre):
        self.fases.seleccionar(nombre)

    def cargar_plantilla(self, texto, nombre):
        if not self.confirmar_descartar():
            return
        self.ruta = None
        self.nombre_sin_ruta = nombre
        self.codificacion = "utf-8"
        self.editor.poner_texto(texto, nombre)
        self._actualizar_titulo()
        self.estado.configure(text=f"Plantilla: {nombre}")
        self.editor.foco()

    def mostrar_instrucciones(self):
        t = self.terminal
        self.fases.seleccionar(TERMINAL)
        t.escribir("Instrucciones 8086 soportadas:\n", "ok")
        lista = sorted(todas_las_instrucciones())
        for i in range(0, len(lista), 10):
            t.escribir("  " + " ".join(f"{m:<7}" for m in lista[i:i + 10]) + "\n")

    def mostrar_atajos(self):
        self.fases.seleccionar(TERMINAL)
        self.terminal.escribir(
            "Atajos: Ctrl+N/O/S nuevo/abrir/guardar · Ctrl+Z/Y deshacer/rehacer · "
            "Ctrl+F buscar · Ctrl+H reemplazar · Ctrl+G ir a línea · "
            "F7 compilar · F5 compilar y ejecutar\n")

    def acerca_de(self):
        messagebox.showinfo(
            NOMBRE_APP,
            "IDE 8086\nEditor y compilador propio de ensamblador 8086\n"
            "Etapas: Lexer → Parser → Semantic → CodeGen", parent=self)

    # ---------- Menús ----------
    def pendiente(self, nombre):
        self.estado.configure(text=f"{nombre}: aún no implementado")
        self.terminal.escribir(f"[pendiente] {nombre}\n")

    def _p(self, nombre):
        return lambda: self.pendiente(nombre)

    def _ed(self, metodo):
        """Devuelve una función que llama a un método del editor al hacer clic."""
        return lambda: getattr(self.editor, metodo)()

    def limpiar_variables(self):
        self.variables.limpiar()
        self.estado.configure(text="Valores limpiados")

    def _menu_archivo(self):
        items = [
            ("Nuevo", "Ctrl+N", self.nuevo),
            ("Abrir…", "Ctrl+O", self.abrir),
            SEPARADOR,
        ]
        lista = recientes()[:5]
        if lista:
            for i, ruta in enumerate(lista, 1):
                carpeta = os.path.basename(os.path.dirname(ruta))
                items.append((f"{i}  {os.path.basename(ruta)}", carpeta,
                              lambda r=ruta: self.abrir_reciente(r)))
            items.append(("Borrar recientes", "", limpiar_recientes))
            items.append(SEPARADOR)
        items += [
            ("Guardar", "Ctrl+S", self.guardar),
            ("Guardar como…", "Ctrl+Shift+S", self.guardar_como),
            SEPARADOR,
            ("Salir", "Alt+F4", self.cerrar),
        ]
        return items

    def _menus(self):
        p = self._p
        ed = self._ed
        return {
            "Archivo": self._menu_archivo,   # función: se actualiza al abrir el menú
            "Editar": [
                ("Deshacer", "Ctrl+Z", ed("deshacer")),
                ("Rehacer", "Ctrl+Y", ed("rehacer")),
                SEPARADOR,
                ("Cortar", "Ctrl+X", ed("cortar")),
                ("Copiar", "Ctrl+C", ed("copiar")),
                ("Pegar", "Ctrl+V", ed("pegar")),
                ("Seleccionar todo", "Ctrl+A", ed("seleccionar_todo")),
                SEPARADOR,
                ("Buscar", "Ctrl+F", ed("mostrar_buscar")),
                ("Reemplazar", "Ctrl+H", ed("mostrar_reemplazar")),
                ("Buscar siguiente", "F3", ed("buscar_siguiente")),
                ("Buscar anterior", "Shift+F3", ed("buscar_anterior")),
                ("Ir a línea…", "Ctrl+G", ed("ir_a_linea")),
            ],
            "Ejecutar": [
                ("Compilar y ejecutar", "F5", lambda: self.compilar_programa(True)),
                ("Compilar", "F7", self.compilar_programa),
                ("Ejecutar", "F8", self.ejecutar),
                SEPARADOR,
                ("Detener", "Shift+F5", self.detener),
            ],
            "Compiladores": [
                ("Ver etapa 1 · Lexer", "", lambda: self.ver_etapa(LEXER)),
                ("Ver etapa 2 · Parser", "", lambda: self.ver_etapa(PARSER)),
                ("Ver etapa 3 · Semantic", "", lambda: self.ver_etapa(SEMANTIC)),
                ("Ver etapa 4 · CodeGen", "", lambda: self.ver_etapa(CODEGEN)),
                SEPARADOR,
                ("Plantilla: calculadora", "",
                 lambda: self.cargar_plantilla(CALCULADORA, "calculadora.asm")),
                ("Plantilla: hola mundo", "",
                 lambda: self.cargar_plantilla(HOLA_MUNDO, "hola.asm")),
            ],
            "Ayuda": [
                ("Instrucciones 8086", "", self.mostrar_instrucciones),
                ("Atajos de teclado", "", self.mostrar_atajos),
                SEPARADOR,
                ("Acerca de IDE 8086", "", self.acerca_de),
            ],
            "Variables": [
                ("Ver registros", "", p("Variables > Registros")),
                ("Ver variables del programa", "", p("Variables > Variables")),
                SEPARADOR,
                ("Limpiar valores", "", self.limpiar_variables),
            ],
        }


def cpu_dar(app, tecla):
    """Teclas de la ventana gráfica -> programa en ejecución."""
    if app.cpu is not None and not app.cpu.terminado:
        app.cpu.dar_tecla(tecla)