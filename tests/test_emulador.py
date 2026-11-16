import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from assembler.compilador import compilar
from core.emulador import Emulador, ErrorEmulador
from core.plantillas import CALCULADORA, HOLA_MUNDO


def correr(src, teclas=""):
    r = compilar(src)
    assert r.exito, list(r.diagnosticos)
    e, ts = Emulador(r.codigo), list(teclas)
    while not e.terminado and e.pasos < 100000:
        e.paso()
        if e.esperando:
            e.dar_tecla(ts.pop(0))
    return "".join(e.salida), e


class Emu(unittest.TestCase):
    def test_hola(self):
        self.assertIn("Hola, mundo!", correr(HOLA_MUNDO)[0])

    def test_calculadora(self):
        casos = {"7+5": "= 12", "9-3": "= 6", "6*7": "= 42", "9/2": "= 4 (resto 1)",
                 "5/0": "division entre cero", "2-8": "= -6", "3x+2": "= 5"}
        for teclas, esperado in casos.items():
            self.assertIn(esperado, correr(CALCULADORA, teclas)[0], teclas)

    def test_aritmetica(self):
        _, e = correr("org 100h\nmov ax, 0FFFFh\nadd ax, 1\nmov bx, 300\nmov cl, 7\n"
                      "mov al, 200\nmul cl\nmov dx, 0\nmov cx, 7\nmov ax, 100\ndiv cx\n"
                      "mov ah, 4Ch\nint 21h\n")
        self.assertEqual(e.r["dx"], 2)       # 100 % 7

    def test_correr_con_teclas(self):
        """Igual que la interfaz: correr() por tandas y teclas que llegan después."""
        r = compilar(CALCULADORA)
        e = Emulador(r.codigo)
        for tecla in "7+5":
            e.correr(1000)
            self.assertTrue(e.esperando)
            e.dar_tecla(tecla)
        e.correr(100000)
        self.assertIn("= 12", "".join(e.salida))

    def test_tamanos_8_y_16_bits(self):
        """Regresión: las máscaras de 8 y 16 bits estaban al revés."""
        _, e = correr("org 100h\nmov si, 2E7Ch\nadd si, 2\n"
                      "mov al, 250\nadd al, 10\nmov bx, 0FFFFh\ninc bx\n"
                      "mov cx, 0\ndec cx\nmov dl, 0\ndec dl\nmov ah, 4Ch\nint 21h\n")
        self.assertEqual(e.r["si"], 0x2E7E)
        self.assertEqual(e.reg(0, 1), 4)          # AL: 250+10 = 260 -> 4 (CF=1 al final de ADD)
        self.assertEqual(e.r["bx"], 0)
        self.assertEqual(e.r["cx"], 0xFFFF)
        self.assertEqual(e.reg(2, 1), 0xFF)

    def test_graficos_y_teclado(self):
        _, e = correr("org 100h\nmov ax, 13h\nint 10h\nmov ah, 0Ch\nmov al, 4\nmov cx, 10\n"
                      "mov dx, 20\nint 10h\nmov ah, 0Dh\nint 10h\nmov bl, al\n"
                      "mov ah, 1\nint 16h\njz sin\nmov bl, 99\nsin: mov ah, 4Ch\nint 21h\n")
        self.assertTrue(e.modo_grafico)
        self.assertEqual(e.pantalla[20 * 320 + 10], 4)
        self.assertEqual(e.reg(3, 1), 4)         # BL = píxel leído; sin tecla no se pisó

    def test_flags_cmp(self):
        _, e = correr("org 100h\nmov al, 5\ncmp al, 5\nmov ah, 4Ch\nint 21h\n")
        self.assertEqual((e.zf, e.cf), (1, 0))

    def test_division_cero(self):
        with self.assertRaises(ErrorEmulador):
            correr("org 100h\nmov bl, 0\nmov ax, 5\ndiv bl\n")


if __name__ == "__main__":
    unittest.main()
