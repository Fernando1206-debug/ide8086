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


MASM = """.model small
.stack 64
.data
    num dw 1234h, ?
    tabla db 1, 2, 3
    buf db 4 dup (0)
.code
main proc far
    mov ax, @data
    mov ds, ax
    mov bx, num
    mov al, tabla[2]
    mov cx, offset tabla
    call sub1
    mov ax, 4C00h
    int 21h
main endp
sub1 proc
    ret
endp sub1
"""


class DialectoMasm(unittest.TestCase):
    def test_compila_y_el_codigo_va_antes_que_los_datos(self):
        r = compilar(MASM)
        self.assertTrue(r.exito, list(r.diagnosticos))
        self.assertEqual(r.codigo[:5], bytes([0xB8, 0, 0, 0x8E, 0xD8]))   # empieza en main
        n = r.tabla.valor_seguro(r.tabla.buscar("num"))
        self.assertEqual(r.codigo[n - 0x100:n - 0x100 + 2], bytes([0x34, 0x12]))

    def test_variable_es_memoria_y_offset_es_direccion(self):
        r = compilar(MASM)
        listado = r.codegen.listado
        self.assertIn("8B 1E", listado)      # mov bx, [num]  (leer memoria)
        self.assertIn("B9", listado)         # mov cx, imm16  (offset tabla)

    def test_sin_distinguir_mayusculas(self):
        r = compilar(".model small\n.code\nInicio: jmp INICIO\n")
        self.assertTrue(r.exito, list(r.diagnosticos))


@unittest.skipUnless(NASM, "NASM no encontrado")
class ContraNasm(unittest.TestCase):
    def test_plantillas(self):
        for fuente in (HOLA_MUNDO, CALCULADORA):
            r = compilar(fuente)
            self.assertTrue(r.exito, list(r.diagnosticos))
            self.assertEqual(r.codigo, nasm(fuente))


if __name__ == "__main__":
    unittest.main()
