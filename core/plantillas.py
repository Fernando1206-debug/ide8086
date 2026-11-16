"""Programas de ejemplo (plantillas) para el editor."""

HOLA_MUNDO = """; Hola mundo (8086, formato .COM)
org 100h

    mov ah, 09h             ; función 09h de DOS: imprimir cadena terminada en '$'
    mov dx, mensaje
    int 21h

    mov ax, 4C00h           ; función 4Ch: terminar el programa
    int 21h

mensaje db "Hola, mundo!", 13, 10, "$"
"""

CALCULADORA = """; ===========================================================
;  Calculadora simple (8086, formato .COM)
;  Pide dos numeros de 1 digito y un operador: + - * /
; ===========================================================
org 100h

inicio:
    mov dx, msg_num1
    call imprimir
    call leer_digito
    mov [num1], al

pedir_operador:
    mov dx, msg_op
    call imprimir
    mov ah, 01h             ; leer un caracter (con eco)
    int 21h
    cmp al, '+'
    je operador_ok
    cmp al, '-'
    je operador_ok
    cmp al, '*'
    je operador_ok
    cmp al, '/'
    je operador_ok
    mov dx, msg_err_op
    call imprimir
    jmp pedir_operador

operador_ok:
    mov [operador], al

    mov dx, msg_num2
    call imprimir
    call leer_digito
    mov [num2], al

    mov dx, msg_res
    call imprimir

    mov al, [num1]
    mov bl, [num2]
    xor ah, ah              ; AX = num1
    mov cl, [operador]
    cmp cl, '+'
    je sumar
    cmp cl, '-'
    je restar
    cmp cl, '*'
    je multiplicar
    jmp dividir

sumar:
    add al, bl
    xor ah, ah
    call imprimir_numero
    jmp fin

restar:
    cmp al, bl
    jae resta_positiva
    push ax                 ; el resultado sera negativo:
    mov dl, '-'             ; imprimir el signo '-'
    mov ah, 02h
    int 21h
    pop ax
    xchg al, bl             ; y restar al reves (el mayor menos el menor)
resta_positiva:
    sub al, bl
    xor ah, ah
    call imprimir_numero
    jmp fin

multiplicar:
    mul bl                  ; AX = AL * BL
    call imprimir_numero
    jmp fin

dividir:
    test bl, bl
    jz division_por_cero
    xor ah, ah
    div bl                  ; AL = cociente, AH = residuo
    mov [residuo], ah
    xor ah, ah
    call imprimir_numero
    cmp byte [residuo], 0
    je fin
    mov dx, msg_resto
    call imprimir
    mov al, [residuo]
    xor ah, ah
    call imprimir_numero
    mov dl, ')'
    mov ah, 02h
    int 21h
    jmp fin

division_por_cero:
    mov dx, msg_cero
    call imprimir

fin:
    mov dx, msg_nl
    call imprimir
    mov ax, 4C00h           ; terminar el programa
    int 21h

; ---------- subrutinas ----------
imprimir:                   ; DX = direccion del mensaje (termina en '$')
    mov ah, 09h
    int 21h
    ret

leer_digito:                ; lee una tecla '0'-'9' y deja su valor en AL
    mov ah, 01h
    int 21h
    cmp al, '0'
    jb .invalido
    cmp al, '9'
    ja .invalido
    sub al, '0'
    ret
.invalido:
    mov dx, msg_err_dig
    call imprimir
    jmp leer_digito

imprimir_numero:            ; AX = numero (0-65535): lo imprime en decimal
    mov bx, 10
    xor cx, cx
.dividir:
    xor dx, dx
    div bx                  ; AX = AX / 10, DX = ultimo digito
    push dx
    inc cx
    test ax, ax
    jnz .dividir
.sacar:
    pop dx
    add dl, '0'
    mov ah, 02h
    int 21h
    loop .sacar
    ret

; ---------- datos ----------
msg_num1    db 13, 10, "Primer numero (0-9): $"
msg_op      db 13, 10, "Operador (+ - * /): $"
msg_num2    db 13, 10, "Segundo numero (0-9): $"
msg_res     db 13, 10, "Resultado = $"
msg_resto   db " (resto $"
msg_cero    db "Error: division entre cero$"
msg_err_op  db 13, 10, "Operador no valido. Intenta de nuevo.$"
msg_err_dig db 13, 10, "Digito no valido. Intenta de nuevo (0-9): $"
msg_nl      db 13, 10, "$"
num1        db 0
num2        db 0
operador    db 0
residuo     db 0
"""
