"""Marcas de error en el editor: pinta las líneas con errores y avisos del compilador."""
import customtkinter as ctk


class Marcas:
    def __init__(self, texto):
        self.t = texto
        oscuro = ctk.get_appearance_mode() == "Dark"
        # El que se crea después tiene más prioridad: el error tapa al aviso.
        self.t.tag_configure("marca_aviso", background="#4d3b00" if oscuro else "#fff3bf")
        self.t.tag_configure("marca_error", background="#5a1d1d" if oscuro else "#ffd6d6")
        self.t.tag_raise("sel")           # la selección siempre se ve encima
        self._activas = False
        self.t.bind("<<Edicion>>", self._al_editar, add="+")

    def marcar(self, diagnosticos):
        self.limpiar()
        for d in diagnosticos:
            if d.linea <= 0:
                continue
            etiqueta = "marca_error" if d.gravedad == "error" else "marca_aviso"
            self.t.tag_add(etiqueta, f"{d.linea}.0", f"{d.linea}.0 lineend+1c")
        self._activas = True

    def limpiar(self):
        self.t.tag_remove("marca_error", "1.0", "end")
        self.t.tag_remove("marca_aviso", "1.0", "end")
        self._activas = False

    def _al_editar(self, _=None):
        # al editar, los números de línea de los errores ya no son confiables
        if self._activas:
            self.limpiar()

    def ir_a(self, linea, col=0):
        indice = f"{linea}.{max(col - 1, 0)}"
        self.t.mark_set("insert", indice)
        self.t.see(indice)
        self.t.focus_force()
