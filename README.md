# IDE 8086

Un editor para escribir programas en ensamblador 8086, compilarlos y ejecutarlos, todo en la misma ventana. Hecho en Python con customtkinter, para Windows.

Lo más importante del proyecto: **el compilador está hecho desde cero**, sin usar NASM ni ningún otro programa externo. Es el proyecto de la clase de compiladores, así que cada etapa del compilador vive en su propio archivo y se puede ver funcionando desde el programa.

## Qué puedes hacer con él

- Escribir código 8086 con colores (las instrucciones como `mov` se ven distintas a los registros y a los números).
- Deshacer, rehacer, buscar y reemplazar, ir a una línea.
- Compilar con **F7**. Si hay errores, la línea se marca en rojo y puedes hacer clic en el mensaje para ir a ella.
- Compilar y ejecutar con **F5**. El programa corre dentro de un emulador y su resultado sale en la terminal.
- Ver, pestaña por pestaña, lo que hizo cada etapa del compilador.
- Ver los registros, las banderas y las variables cuando el programa termina.
- Cargar un programa de ejemplo desde el menú Compiladores: una calculadora y un "hola mundo".

## Cómo abrirlo

Necesitas Python 3.11 o más nuevo y customtkinter (`pip install customtkinter`). Desde la carpeta del proyecto:

```
python main.py
```

## Probar la calculadora

1. Menú **Compiladores → Plantilla: calculadora**.
2. Pulsa **F5**.
3. Haz clic en el cuadro de abajo (debajo de la terminal) y escribe un número, un operador y otro número. Por ejemplo `7`, `+`, `5`. No hace falta pulsar Enter.
4. En la terminal aparece `Resultado = 12`.

La calculadora suma, resta, multiplica y divide números de un dígito. Si divides entre cero, avisa en vez de fallar.

## Cómo funciona el compilador

Tomar texto escrito por una persona y convertirlo en los números que entiende el procesador se hace en cuatro pasos. Cada uno recibe el resultado del anterior:

```
 Texto del programa
        │
        ▼
 1. Lexer     →  lista de tokens
        │
        ▼
 2. Parser    →  árbol (AST)
        │
        ▼
 3. Semantic  →  tabla de símbolos + tipos y tamaños revisados
        │
        ▼
 4. CodeGen   →  bytes reales del programa (.COM)
```

Si una etapa encuentra un error, el compilador se detiene ahí y te dice en cuál fue. No tiene sentido generar código de algo que ni siquiera está bien escrito.

Para explicar cada paso usamos este programa de tres líneas:

```
org 100h
inicio:
    mov ax, 5
    add ax, bx
    jmp inicio
```

### 1. Lexer (`assembler/lexer.py`)

Lee el texto letra por letra y lo corta en piezas con significado, llamadas *tokens*. Es como separar una oración en palabras y decidir si cada una es un verbo, un nombre o un número.

| Texto | Tipo de token |
|-------|---------------|
| `mov`, `add`, `jmp` | instrucción |
| `ax`, `bx` | registro |
| `5`, `100h` | número (también entiende `0x1F` y `1010b`) |
| `inicio` | nombre (identificador) |
| `,` `:` | símbolos |

Aquí se detectan errores como un carácter que no existe en el lenguaje (`#`), un número mal escrito (`0xZZ`) o una cadena que no se cerró.

### 2. Parser (`assembler/parser.py`)

Revisa que los tokens estén en un orden válido y los organiza en un **árbol** que muestra la estructura del programa. Por ejemplo, `mov ax, 5` es una instrucción `MOV` con dos hijos: el registro `AX` y el número `5`.

Las reglas de la gramática son más o menos así:

```
programa     = { línea }
línea        = [ etiqueta ":" ] [ instrucción | directiva ] fin_de_línea
instrucción  = [ prefijo ] nombre [ operando { "," operando } ]
operando     = registro | expresión | "[" dirección "]"
```

Es un parser de *descenso recursivo*: hay una función por cada regla, y cada función llama a las de las reglas que contiene. Si algo está mal escrito, por ejemplo `mov ax,` sin nada después de la coma, el parser avisa y sigue con la línea siguiente para poder mostrarte varios errores a la vez. Cuando te equivocas en el nombre de una instrucción, sugiere el más parecido.

### 3. Semantic (`assembler/semantic.py`)

Aquí se revisa que el programa **tenga sentido**, aunque esté bien escrito. Hace dos cosas:

- **Tabla de símbolos.** Es una lista con todos los nombres que definiste (etiquetas, variables, constantes), su tipo, su tamaño y su dirección. En el ejemplo, `inicio` es una etiqueta en la dirección `0100h` y se usa una vez.
- **Revisión de tipos y tamaños.** Comprueba cosas como que no mezcles un registro de 8 bits con uno de 16 (`mov ax, bl` es un error), que un número quepa en el registro y que no uses una etiqueta que no existe.

El resultado de esta etapa es el árbol del paso 2, pero con anotaciones: cada instrucción ya sabe de cuántos bits es.

### 4. CodeGen (`assembler/codegen.py`)

Es la etapa que produce el resultado final. Tiene cuatro partes:

- **4.1 Código intermedio.** Para cada instrucción se elige la forma exacta de codificarla. Por ejemplo, `mov ax, 5` usa la forma "mover un número a un registro de 16 bits".
- **4.2 Optimización.** Hace dos mejoras: resuelve las constantes (si escribes `2+3`, guarda `5`) y elige el tamaño más corto para cada salto.
- **4.3 Opcodes.** Convierte cada instrucción en sus bytes reales.
- **4.4 Volcado hexadecimal.** Muestra el archivo final.

Para el ejemplo, el resultado es:

```
Línea  Dir.   Bytes     Fuente
    3  0100   B8 05 00  mov ax, 5
    4  0103   01 D8     add ax, bx
    5  0105   EB F9     jmp inicio
```

Esos 7 bytes (`B8 05 00 01 D8 EB F9`) son el programa. Se guardan en un archivo `.COM`, que es el formato más simple de programa que existe para DOS.

## Cómo se ejecuta

El programa compilado no corre directamente en Windows, porque es código de 16 bits para un procesador de 1978. Por eso el proyecto incluye un **emulador del 8086** (`core/emulador.py`) que imita al procesador: tiene sus registros, sus banderas y 64 KB de memoria, y ejecuta los bytes uno por uno.

Para imprimir y leer teclas, los programas llaman a la interrupción `INT 21h` del antiguo DOS. El emulador entiende las funciones que se necesitan: leer una tecla (01 y 08), imprimir un carácter (02), imprimir una cadena (09), leer una línea (0A) y terminar (4C).

## Programas estilo MASM / emu8086 (y juegos gráficos)

Además del estilo NASM (el de la calculadora), el compilador entiende el estilo de MASM y emu8086. Se activa solo cuando el programa empieza con `.model`. Soporta:

- `.model`, `.stack`, `.data`, `.code` y `end`.
- Procedimientos: `nombre proc [far|near]` ... `nombre endp` (también `proc nombre` y `endp nombre`).
- Datos sin valor inicial (`dw ?, ?`) y repeticiones (`db 10 dup (0)`).
- Posiciones de una tabla: `tabla[2]`, `tabla[bx]`.
- `offset variable` y `word ptr [bx]`.
- Los nombres no distinguen mayúsculas de minúsculas, como en MASM.

Dos reglas de MASM que cambian el significado del código:

1. **Escribir el nombre de una variable lee su contenido.** `mov bx, puntos` carga el valor de `puntos`. Para obtener su dirección hay que escribir `mov bx, offset puntos`. (En el estilo NASM pasa al revés.)
2. **Todo vive en un solo segmento de 64 KB**, como un `.COM`. El compilador pone el código primero y los datos después, aunque `.data` vaya antes en el texto. `mov ax, @data` y `mov ds, ax` se aceptan pero no hacen nada importante.

### Pantalla gráfica y teclado

El emulador entiende lo que usan los juegos de DOS:

- `INT 10h`: modo gráfico 13h (320x200, 256 colores), escribir y leer un píxel (funciones 0Ch y 0Dh).
- `INT 16h`: leer teclas sin esperar.
- `INT 1Ah` y `INT 21h/2Ch`: reloj.

Cuando un programa pasa a modo gráfico, se abre la ventana **Pantalla gráfica**. Las teclas se escriben dentro de esa ventana, y al cerrarla el programa se detiene. Como los juegos esperan con bucles larguísimos (que en una PC real duran milisegundos), el emulador acorta esos bucles 4 veces para que el juego no se sienta lento.

Se probó con un Tetris de unas 3400 líneas: compila, dibuja el tablero, las piezas y el panel de siguientes piezas, las piezas caen, se mueven y se apilan.

## Mapa de archivos

```
main.py                 arranca el programa
assembler/              el compilador
    lexer.py              etapa 1
    parser.py             etapa 2
    semantic.py           etapa 3
    codegen.py            etapa 4
    formas.py             tabla de cómo se codifica cada instrucción
    tablas.py             registros e instrucciones que existen
    nodos.py              las piezas del árbol
    errores.py            manejo de errores y avisos
    reportes.py           los textos de las pestañas 1 a 4
    compilador.py         junta las cuatro etapas
core/
    emulador.py           el emulador 8086
    plantillas.py         programas de ejemplo
    archivos.py           abrir, guardar y archivos recientes
ui/                     la ventana
    app.py                ventana principal y menús
    editor.py             el editor con colores
    fases.py              terminal y pestañas de las etapas
    pantalla.py           ventana de la pantalla gráfica (modo 13h)
    marcas.py             marca las líneas con error
tests/                  pruebas automáticas
```

## Pruebas

```
python -m unittest discover tests
```

Las pruebas revisan cada etapa y ejecutan la calculadora de punta a punta. Si NASM está instalado en tu computadora, también se compara byte por byte lo que genera este compilador con lo que genera NASM; si no está, esas pruebas se saltan solas.

## Limitaciones

- Solo genera programas `.COM` (un solo segmento de 64 KB). No hay `segment` ni `.EXE`.
- `times` solo funciona con `db` y `dw`.
- El emulador no soporta las instrucciones decimales (`daa`, `aaa`…) ni `in`/`out`, ni sonido, ni el ratón.
- En el estilo MASM solo hay un segmento: no se pueden usar varios segmentos ni programas `.EXE` reales.
- Es más estricto que NASM con los tamaños: `mov dx, [tabla+1]` sobre una tabla de bytes da error, y hay que escribir `word [tabla+1]` para indicar el tamaño.
- Un salto a un número escrito directamente (por ejemplo `jne 256`) se codifica corto, mientras que NASM usaría la forma larga. Ambos funcionan.
