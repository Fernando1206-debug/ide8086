"""Pruebas del compilador (unittest). Si hay NASM, compara byte por byte."""
import os, shutil, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from assembler.compilador import compilar
from core.plantillas import CALCULADORA, HOLA_MUNDO

NASM = shutil.which("nasm") or (os.path.join("tools", "nasm.exe") if os.path.exists(os.path.join("tools", "nasm.exe")) else None)


def nasm(fuente):
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.asm"), os.path.join(d, "a.com")
        open(a, "w").write("cpu 8086\nbits 16\n" + fuente)
        subprocess.run([NASM, "-f", "bin", a, "-o", b], check=True, capture_output=True)
        return open(b, "rb").read()


class Etapas(unittest.TestCase):
    def test_lexico(self):
        r = compilar("mov ax, 5 #\n")
        self.assertEqual(r.fase_fallida, "léxico")

    def test_sintactico(self):
        r = compilar("mov ax,\n")
        self.assertEqual(r.fase_fallida, "sintáctico")

    def test_semantico(self):
        r = compilar("mov ax, bl\n")
        self.assertEqual(r.fase_fallida, "semántico")

    def test_ok(self):
        r = compilar("org 100h\nmov ax, 4C00h\nint 21h\n")
        self.assertTrue(r.exito)
        self.assertEqual(r.codigo, bytes([0xB8, 0x00, 0x4C, 0xCD, 0x21]))

    def test_plegado_y_saltos(self):
        r = compilar("org 100h\nK equ 2+3\nmov al, K*2\ninicio: jmp inicio\n")
        self.assertTrue(r.exito)
        self.assertEqual(r.codigo[:2], bytes([0xB0, 10]))
        self.assertEqual(r.codigo[2:], bytes([0xEB, 0xFE]))


@unittest.skipUnless(NASM, "NASM no encontrado")
class ContraNasm(unittest.TestCase):
    def test_plantillas(self):
        for fuente in (HOLA_MUNDO, CALCULADORA):
            r = compilar(fuente)
            self.assertTrue(r.exito, list(r.diagnosticos))
            self.assertEqual(r.codigo, nasm(fuente))


if __name__ == "__main__":
    unittest.main()
