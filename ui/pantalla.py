"""Ventana de la pantalla gráfica (modo 13h: 320x200, 256 colores).

El emulador va marcando el rectángulo de píxeles que cambió; aquí solo se
repinta esa parte (así el juego no se vuelve lento). Las teclas que se pulsan
en esta ventana van al programa (INT 16h).
"""
import tkinter as tk

from core.emulador import PALETA, ANCHO, ALTO

ZOOM = 2
_HEX = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in PALETA]


class VentanaPantalla(tk.Toplevel):
    def __init__(self, master, alcerrar, alteclar):
        super().__init__(master)
        self.title("Pantalla gráfica 320x200")
        self.configure(bg="#111111")
        self.resizable(False, False)
        self._alcerrar = alcerrar
        self._alteclar = alteclar
        self.imagen = tk.PhotoImage(width=ANCHO * ZOOM, height=ALTO * ZOOM)
        self.imagen.put("#000000", to=(0, 0, ANCHO * ZOOM, ALTO * ZOOM))
        self.lienzo = tk.Label(self, image=self.imagen, bd=0, highlightthickness=0)
        self.lienzo.pack(padx=8, pady=8)
        self.pie = tk.Label(self, text="Teclas del programa: escribe aquí  ·  cerrar = detener",
                            bg="#111111", fg="#8b949e", font=("Segoe UI", 9))
        self.pie.pack(pady=(0, 6))
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.bind("<Key>", self._tecla)
        self.after(50, self.enfocar)

    def enfocar(self):
        try:
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def _cerrar(self):
        self._alcerrar()

    def _tecla(self, e):
        c = {"Return": "\r", "BackSpace": "\b", "space": " "}.get(e.keysym, e.char)
        if c:
            self._alteclar(c)
        return "break"

    def terminado(self):
        self.pie.configure(text="Programa terminado  ·  cierra esta ventana cuando quieras")

    def actualizar(self, cpu):
        """Repinta el rectángulo modificado desde la última vez."""
        if cpu.pantalla_borrada:
            cpu.pantalla_borrada = False
            self.imagen.put("#000000", to=(0, 0, ANCHO * ZOOM, ALTO * ZOOM))
        s = cpu.tomar_sucio()
        if s is None:
            return
        x0, y0, x1, y1 = s
        pant = cpu.pantalla
        filas = []
        for y in range(y0, y1 + 1):
            base = y * ANCHO
            fila = "{" + " ".join(_HEX[c] for c in pant[base + x0: base + x1 + 1]
                                  for _ in range(ZOOM)) + "}"
            filas.extend([fila] * ZOOM)
        self.imagen.put(" ".join(filas), to=(x0 * ZOOM, y0 * ZOOM))
