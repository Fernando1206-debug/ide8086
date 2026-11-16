"""Diagnósticos (errores y avisos) que producen las etapas del compilador.

Cada etapa (léxico, sintáctico, semántico, generación de código) reporta sus
problemas con el mismo formato, así la interfaz puede mostrarlos todos juntos.
"""
from dataclasses import dataclass

# Nombres de las etapas (se muestran al usuario)
LEXICO = "léxico"
SINTACTICO = "sintáctico"
SEMANTICO = "semántico"
CODEGEN = "generación de código"

ORDEN_FASES = [LEXICO, SINTACTICO, SEMANTICO, CODEGEN]

ERROR = "error"
AVISO = "aviso"


@dataclass
class Diagnostico:
    fase: str
    gravedad: str          # "error" o "aviso"
    mensaje: str
    linea: int = 0         # 1 = primera línea; 0 = no está ligado a una línea
    col: int = 0

    def __str__(self):
        if self.linea:
            donde = f"línea {self.linea}" + (f":{self.col}" if self.col else "")
        else:
            donde = "programa"
        return f"[{self.fase}] {self.gravedad} en {donde}: {self.mensaje}"


class Diagnosticos(list):
    """Lista de diagnósticos con atajos para agregar errores y avisos."""

    def error(self, fase, mensaje, linea=0, col=0):
        self.append(Diagnostico(fase, ERROR, mensaje, linea, col))

    def aviso(self, fase, mensaje, linea=0, col=0):
        self.append(Diagnostico(fase, AVISO, mensaje, linea, col))

    @property
    def hay_errores(self):
        return any(d.gravedad == ERROR for d in self)

    @property
    def n_errores(self):
        return sum(1 for d in self if d.gravedad == ERROR)

    @property
    def n_avisos(self):
        return sum(1 for d in self if d.gravedad == AVISO)

    def de_fase(self, fase):
        return [d for d in self if d.fase == fase]

    def primera_fase_con_errores(self):
        for fase in ORDEN_FASES:
            if any(d.fase == fase and d.gravedad == ERROR for d in self):
                return fase
        return ""
