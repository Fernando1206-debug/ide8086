import json
import os
import tempfile

PLANTILLA_NUEVO = """; Nuevo programa (8086, formato .COM)
org 100h

    mov ah, 4Ch         ; terminar programa
    int 21h
"""

MAX_RECIENTES = 8
MAX_BYTES = 5 * 1024 * 1024  # 5 MB


# ---------- Configuración (archivos recientes) ----------
def _ruta_config():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    carpeta = os.path.join(base, "IDE8086")
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, "config.json")


def cargar_config():
    try:
        with open(_ruta_config(), "r", encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_config(datos):
    try:
        with open(_ruta_config(), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # la configuración es opcional: nunca debe romper la app


def recientes():
    lista = cargar_config().get("recientes", [])
    return [r for r in lista if isinstance(r, str) and os.path.isfile(r)]


def agregar_reciente(ruta):
    ruta = os.path.abspath(ruta)
    datos = cargar_config()
    lista = [r for r in datos.get("recientes", [])
             if os.path.normcase(r) != os.path.normcase(ruta)]
    lista.insert(0, ruta)
    datos["recientes"] = lista[:MAX_RECIENTES]
    guardar_config(datos)


def limpiar_recientes():
    datos = cargar_config()
    datos["recientes"] = []
    guardar_config(datos)


# ---------- Leer y escribir archivos ----------
def leer_archivo(ruta):
    """Devuelve (texto, codificación). Prueba UTF-8 y, si falla, Latin-1."""
    if os.path.getsize(ruta) > MAX_BYTES:
        raise ValueError("El archivo es demasiado grande para el editor (máx. 5 MB).")
    with open(ruta, "rb") as f:
        datos = f.read()
    if b"\x00" in datos[:4096]:
        raise ValueError("Parece un archivo binario, no un archivo de texto.")
    try:
        texto, codificacion = datos.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        texto, codificacion = datos.decode("latin-1"), "latin-1"
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    return texto, codificacion


def escribir_archivo(ruta, texto, codificacion="utf-8"):
    """Guarda de forma segura (archivo temporal + reemplazo).
    Devuelve la codificación realmente usada."""
    try:
        datos = texto.encode(codificacion)
    except UnicodeEncodeError:
        codificacion = "utf-8"
        datos = texto.encode(codificacion)
    datos = datos.replace(b"\n", b"\r\n") 

    carpeta = os.path.dirname(os.path.abspath(ruta))
    fd, temporal = tempfile.mkstemp(dir=carpeta, prefix=".ide8086_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(datos)
        os.replace(temporal, ruta)
    except BaseException:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise
    return codificacion