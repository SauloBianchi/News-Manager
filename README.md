# NewsManager

Sistema de Gerenciamento e Análise de Notícias — aplicação desktop em Python
com Tkinter e banco de dados MySQL (ou MariaDB, como o do XAMPP).

**Equipe:** Ernesto, Gabriel S e Saulo.

## Índice
1. [Guia rápido para um PC novo](#1-guia-rápido-para-um-pc-novo-windows--xampp)
2. [Requisitos](#2-requisitos)
3. [Instalação passo a passo](#3-instalação-passo-a-passo)
4. [Levar o projeto (e os dados) para outro computador](#4-levar-o-projeto-e-os-dados-para-outro-computador)
5. [Solução de problemas](#5-solução-de-problemas)
6. [Funcionalidades](#6-funcionalidades)
7. [Estrutura do projeto](#7-estrutura-do-projeto)
8. [Como funcionam o 2FA, o "esqueci minha senha" e os e-mails](#8-como-funcionam-o-2fa-o-esqueci-minha-senha-e-os-e-mails)
9. [Dados de teste e roteiro de testes](#9-dados-de-teste-e-roteiro-de-testes)
10. [Migrações de bancos antigos](#10-migrações-de-bancos-antigos)
11. [Previsão do tempo e Clipping: internet, atribuição, configuração](#11-previsão-do-tempo-e-clipping)
12. [Testes automatizados](#12-testes-automatizados)

---

## 1. Guia rápido para um PC novo (Windows + XAMPP)

Se você só quer ver o sistema rodando, estes são os passos (os detalhes e as
alternativas estão na [seção 3](#3-instalação-passo-a-passo)). Use o
**PowerShell** na pasta que contém o `main.py`.

```powershell
# 1) Ambiente Python (uma vez por computador)
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # se der erro de "execução de scripts", veja a seção 5
pip install -r requirements.txt

# 2) Ligue o banco: abra o XAMPP Control Panel e clique em Start no MySQL (fica verde)

# 3) Crie o banco e as tabelas (o schema.sql já cria o banco "newsmanager")
$mysql = "C:\xampp\mysql\bin"
& "$mysql\mysql.exe" -u root --default-character-set=utf8mb4 -e "source sql/schema.sql"

# 4) Dados de teste (opcional, recomendado) e verificação automática
python seed.py

# 5) Abra o sistema e crie sua conta em "Criar conta"
python main.py
```

> O banco se chama **`newsmanager`** (sem underline) — é o nome que o
> `main.py` e o `schema.sql` usam. Não crie um banco com outro nome.
>
> O e-mail (2FA) e o login com o Google são **opcionais** para ver o sistema
> funcionando; as instruções estão nas seções 3.5 e 3.6.

---

## 2. Requisitos

| O que | Versão / observação |
|---|---|
| **Python** | 3.10 ou mais novo, **com Tkinter** (no instalador do python.org marque *tcl/tk and IDLE*). Teste com `python -m tkinter`: deve abrir uma janelinha. |
| **MySQL ou MariaDB** | MySQL 8.x ou o MariaDB do **XAMPP** (10.4 funciona). O servidor precisa estar **ligado** — o `mysql.exe` sozinho é só o cliente. |
| **Internet** | Para `pip install` e, se usados, e-mail (2FA) e login com o Google. |
| **Permissões do banco** | O usuário do banco (`root` no XAMPP) precisa poder `CREATE`/`ALTER` tabelas: o sistema cria colunas e tabelas novas sozinho na primeira conexão. |
| **Pasta gravável** | O projeto grava em `logs/`, `midia/`, `rascunhos/` e `config/`; não rode de dentro de *Program Files*. |

Bibliotecas Python (todas no `requirements.txt`): `mysql-connector-python`,
`matplotlib`, `pillow`, `bcrypt`, `google-auth-oauthlib` e `requests`.

---

## 3. Instalação passo a passo

### 3.1 Obter o projeto
Clone o repositório ou baixe o ZIP e extraia. Ao baixar o ZIP do GitHub, a
pasta costuma ficar **duplicada** (`News-Manager-main\News-Manager-main`):
todos os comandos abaixo devem ser rodados na pasta **que contém o `main.py`**.

```powershell
cd "C:\Users\SEU_USUARIO\Downloads\News-Manager-main\News-Manager-main"
dir main.py        # tem que listar o arquivo
```

Confira também se a pasta `app\` está completa (cerca de 20 arquivos `.py`).
Um erro como `No module named 'app.midia'` quer dizer que algum arquivo não
foi copiado.

### 3.2 Python e ambiente virtual
```powershell
python --version                  # 3.10 ou superior
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # o prompt passa a mostrar (.venv)
pip install -r requirements.txt
```
- Cada novo PowerShell precisa **ativar o ambiente de novo** (`.\.venv\Scripts\Activate.ps1`).
- Se o PowerShell reclamar que *a execução de scripts foi desabilitada*, rode
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` e ative de novo
  (vale só para aquela janela).
- Se `python` não for reconhecido, instale o Python (marcando *Add python.exe to PATH*)
  ou tente `py -m venv .venv`.

### 3.3 Banco de dados
O `schema.sql` **cria o banco `newsmanager`** e todas as tabelas. Você só
precisa de um servidor MySQL/MariaDB ligado e do caminho dos programas dele.

**Descubra qual servidor você tem** e guarde o caminho numa variável
(repita isso em cada PowerShell novo — uma variável vazia causa o erro
*"O termo '\mysql.exe' não é reconhecido"*):

```powershell
$mysql = "C:\xampp\mysql\bin"                                   # XAMPP
# $mysql = "C:\Program Files\MySQL\MySQL Server 8.0\bin"       # MySQL Server 8
Test-Path "$mysql\mysql.exe"                                    # tem que dar True
```

#### Passo 1 — ligar o servidor (escolha UMA opção)

**Opção A — XAMPP Control Panel (a mais simples).** Abra
`C:\xampp\xampp-control.exe` e clique em **Start** na linha do **MySQL**
até ele ficar verde. Não é preciso criar pasta de dados nem rodar
`mysqld` à mão.

**Opção B — XAMPP pela linha de comando (sem o painel).**
```powershell
& "C:\xampp\mysql\bin\mysqld.exe" --defaults-file="C:\xampp\mysql\bin\my.ini" --console
```
Essa janela **fica ocupada** mostrando o log; não feche (aparece
`ready for connections`). Use **outro** PowerShell para os próximos passos.
Para desligar: `Ctrl+C` na janela, ou `& "$mysql\mysqladmin.exe" -u root shutdown`.

**Opção C — MySQL Server instalado como serviço.**
```powershell
Get-Service *mysql*              # mostra, por exemplo, MySQL80 (Stopped ou Running)
net start MySQL80                # precisa de PowerShell como Administrador
```
Se aparecer *Acesso negado*, abra o PowerShell com **Executar como
administrador**. Em computador de laboratório sem administrador, use a opção A,
B ou D.

**Opção D — pasta de dados própria (avançado; computador sem permissão para
o serviço).** Cria um servidor separado dentro da sua pasta de usuário. **O
comando de inicialização depende do tipo de servidor** — veja qual é o seu:
```powershell
& "$mysql\mysqld.exe" --version          # mostra "MariaDB" (XAMPP) ou "MySQL"
```
```powershell
$dados = "$env:USERPROFILE\mysql-dados"
New-Item -ItemType Directory -Force -Path $dados | Out-Null     # a pasta PRECISA existir antes

# MariaDB (XAMPP) — NÃO use --initialize-insecure aqui (é só do MySQL)
& "$mysql\mysql_install_db.exe" --datadir="$dados"
# MySQL Server:
# & "$mysql\mysqld.exe" --initialize-insecure --datadir="$dados"

& "$mysql\mysqld.exe" --datadir="$dados" --console               # janela fica ocupada
```
Isso cria o usuário `root` **sem senha**, que é o que o `main.py` espera. Não
deixe dois servidores ligados ao mesmo tempo: os dois disputam a porta 3306.

#### Passo 2 — testar a conexão
```powershell
& "$mysql\mysql.exe" -u root -e "SELECT VERSION();"
```
Se mostrar a versão, o servidor está no ar. Se aparecer
`ERROR 2002/2003 ... (10061)`, o servidor **não está rodando**: volte ao
passo 1.

#### Passo 3 — criar o banco e as tabelas
Na pasta do projeto (onde está a pasta `sql\`):
```powershell
& "$mysql\mysql.exe" -u root --default-character-set=utf8mb4 -e "source sql/schema.sql"
& "$mysql\mysql.exe" -u root -e "USE newsmanager; SHOW TABLES;"
```
- `--default-character-set=utf8mb4` evita acentos quebrados ("PolÃ­tica") nos
  dados de exemplo do script.
- O PowerShell **não aceita** `mysql ... < arquivo.sql`; por isso usamos
  `-e "source ..."`.
- Se o `root` tiver senha, acrescente `-p` (ele pede a senha) — e ajuste o
  `main.py` (seção 3.4).
- **Atalho:** depois de instalar as dependências, o `python seed.py` também
  cria o banco a partir do `sql/schema.sql` se ele ainda não existir.

#### O que o sistema cria sozinho
Ao conectar, o sistema confere o banco e **adiciona as colunas e tabelas que
faltarem** (perfil do usuário, notificações, imagens, etc.). Por isso o
usuário do banco precisa de permissão de `CREATE` e `ALTER`.

### 3.4 Conectar o sistema ao banco
As credenciais ficam em `main.py`, na criação do `DatabaseManager`:
```python
db = DatabaseManager(host="localhost", user="root", password="", database="newsmanager")
```
- **XAMPP:** `root` sem senha — já é o padrão, não precisa mexer.
- **MySQL Server** instalado com senha no `root`: coloque-a em `password=""`.
  **Não faça commit** de senha real.
- A porta usada é a padrão do MySQL, **3306**. Se outro MySQL já estiver nela,
  desligue um dos dois.
- O `seed.py` aceita as mesmas informações pela linha de comando:
  `python seed.py --usuario root --senha "SUA_SENHA" --banco newsmanager`.

### 3.5 Envio de e-mail (necessário só para o 2FA e o "esqueci minha senha")
O código de verificação é enviado por SMTP. O jeito mais simples para um
trabalho de faculdade é uma conta do Gmail com **Senha de App**:

1. Na conta Google que vai enviar os e-mails, ative a **Verificação em duas
   etapas** (myaccount.google.com/security) — é pré-requisito.
2. Em myaccount.google.com/apppasswords, crie uma senha para o app
   "NewsManager" e copie o código de 16 letras.
   - Se a opção não aparecer, use uma conta pessoal comum do Gmail só para
     testes ou um serviço como Mailtrap/SendGrid (mesma configuração,
     mudando `smtp_host`/`smtp_porta`).
3. Copie `config/email_config.json.example` para `config/email_config.json`
   e preencha:
   ```json
   {
     "smtp_host": "smtp.gmail.com",
     "smtp_porta": 587,
     "smtp_usuario": "seu.email@gmail.com",
     "smtp_senha": "a-senha-de-app-de-16-letras",
     "remetente_nome": "NewsManager"
   }
   ```
4. **Nunca** faça commit do `config/email_config.json` (já está no
   `.gitignore`). Cada integrante precisa da sua cópia, combinada fora do Git.

Sem esse arquivo o sistema funciona normalmente; ele só avisa o que falta
quando você tenta usar 2FA, "esqueci minha senha" ou o e-mail de urgência.

### 3.6 Login com o Google (necessário só para o botão "Entrar com o Google")
1. No [Google Cloud Console](https://console.cloud.google.com/), crie (ou
   reaproveite) um projeto.
2. Em **APIs e Serviços → Tela de consentimento OAuth**, configure o app como
   "Externo" e adicione os escopos `openid`, `.../auth/userinfo.email` e
   `.../auth/userinfo.profile`. Enquanto estiver em modo de teste, adicione os
   e-mails da equipe em **Usuários de teste** (senão o Google bloqueia o login).
3. Em **Credenciais → Criar credenciais → ID do cliente OAuth**, escolha
   **"Aplicativo para computador"** (Desktop app).
4. Baixe o JSON, renomeie para `client_secret.json` e coloque em
   `config/client_secret.json` (use `config/client_secret.json.example` como
   referência). **Nunca** faça commit dele.

O navegador abre para o login e o sistema sobe um servidor local temporário só
para receber o retorno do Google; não há nada para publicar.

### 3.7 Primeiro acesso e dados de teste
1. Rode `python main.py` e clique em **Criar conta** — não existe usuário
   `admin` pré-cadastrado.
2. Para ter conteúdo para testar (editorias, autores, matérias, gráficos e
   despachos de exemplo), rode `python seed.py` (seção 9).

### 3.8 Rodar o sistema
Sempre a partir da raiz do projeto (é de lá que `config/`, `assets/`,
`midia/` e `logs/` são resolvidos), com o ambiente virtual ativo e o banco ligado:
```powershell
python main.py
```

---

## 4. Levar o projeto (e os dados) para outro computador

**O que vai pelo Git (código):** tudo, menos o que está no `.gitignore`.

**O que NÃO vai pelo Git e precisa ser refeito ou copiado em cada PC:**

| Item | O que fazer no PC novo |
|---|---|
| Ambiente `.venv/` | Criar de novo (`python -m venv .venv` + `pip install -r requirements.txt`) |
| Banco de dados | Criar com o `schema.sql` (seção 3.3) — ou restaurar um backup (abaixo) |
| `config/email_config.json` | Copiar de uma fonte segura ou criar (seção 3.5) |
| `config/client_secret.json` | Copiar ou baixar de novo do Google Cloud (seção 3.6) |
| `midia/` (capas, fotos, imagens no texto) | Copiar a pasta junto com o backup do banco |
| `config/graficos.json`, `rascunhos/`, `logs/` | Não precisa: são recriados (preferências dos gráficos, auto-salvamento e logs) |

### Levar os dados de um PC para outro (backup e restauração)
No PC de origem (use `--result-file`; o `>` do Windows PowerShell grava com
codificação errada):
```powershell
& "$mysql\mysqldump.exe" -u root --databases newsmanager --default-character-set=utf8mb4 --result-file=backup_newsmanager.sql
```
Copie `backup_newsmanager.sql` **e a pasta `midia\`** para o outro PC (o banco
guarda só o caminho das imagens). No PC de destino, com o servidor ligado:
```powershell
& "$mysql\mysql.exe" -u root --default-character-set=utf8mb4 -e "source backup_newsmanager.sql"
```
O backup já contém o `CREATE DATABASE`. Se você usa o sistema com um banco de
cada computador, os dados de um PC **não aparecem** no outro: é por isso que
o seed e o backup existem.

### Checklist rápido de um PC novo
- [ ] Python 3.10+ com Tkinter (`python -m tkinter` abre uma janela)
- [ ] Projeto completo, na pasta que contém o `main.py`
- [ ] `.venv` criado, ativado e `pip install -r requirements.txt` sem erros
- [ ] Servidor MySQL/MariaDB **ligado** (`mysql -u root -e "SELECT VERSION();"` responde)
- [ ] `schema.sql` executado (`SHOW TABLES;` lista as tabelas do banco `newsmanager`)
- [ ] `main.py` com o usuário/senha corretos do banco
- [ ] (Opcional) `config/email_config.json` e `config/client_secret.json`
- [ ] `python seed.py` terminou com **0 falhas**
- [ ] `python main.py` abre o login e a conta nova consegue entrar

---

## 5. Solução de problemas

### Banco de dados / servidor

| O que aparece | Causa | Solução |
|---|---|---|
| `ERROR 2002 (HY000): Can't connect to MySQL server ... (10061)` ou `ERROR 2003 ...` | O servidor **não está rodando** (o `mysql.exe` é só o cliente). | Ligue o servidor: XAMPP Control Panel → MySQL → Start, ou use as opções B, C ou D da seção 3.3. |
| `O termo 'C:\Program Files\MySQL\...\mysqld.exe' não é reconhecido` | Esse caminho não existe no seu PC (por exemplo, você usa o XAMPP). | Procure o caminho certo: `Get-ChildItem C:\xampp\mysql\bin\mysqld.exe, "C:\Program Files\MySQL" -Recurse -Filter mysqld.exe -ErrorAction SilentlyContinue` e ajuste `$mysql`. |
| `O termo '\mysql.exe' não é reconhecido` | A variável `$mysql` está vazia (ela vale só na janela em que foi criada). | Defina de novo: `$mysql = "C:\xampp\mysql\bin"`, ou use o caminho completo entre aspas. |
| `Can't change dir to '...\mysql-dados\'` / `Can't create test file ... (Errcode: 2)` | A pasta de dados escolhida ainda não existe. | `New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\mysql-dados"` e tente de novo. |
| `Table 'mysql.servers' doesn't exist`, `Can't open and lock privilege tables`, `Could not open mysql.plugin table` | Uma pasta de dados nova foi iniciada com `--initialize-insecure` num **MariaDB** (esse parâmetro é só do MySQL). | Apague a pasta de dados (`Remove-Item -Recurse -Force "$env:USERPROFILE\mysql-dados"`), recrie e use `mysql_install_db.exe --datadir=...` (opção D da seção 3.3). Ou simplesmente use o servidor do XAMPP (opção A/B). |
| `ERROR 1049 (42000): Unknown database 'newsmanager'` | O banco ainda não foi criado. | Rode o `schema.sql` (seção 3.3, passo 3) ou `python seed.py`. |
| Criei um banco `news_manager` (com underline) | Nome errado: o sistema usa **`newsmanager`**. | Rode o `schema.sql` (ele cria o `newsmanager`) e, se quiser, apague o errado: `& "$mysql\mysql.exe" -u root -e "DROP DATABASE news_manager;"` |
| `ERROR 1045 (28000): Access denied for user 'root'` | A senha do `root` não é vazia. | Informe a senha no `main.py` (`password="..."`) e use `-p` nos comandos do `mysql.exe`. |
| `ERROR 1044` / `1142 ... command denied ... ALTER / CREATE` | O usuário do banco não tem permissão para criar/alterar tabelas. | Use o `root` ou conceda `ALL PRIVILEGES` ao usuário no banco `newsmanager`. |
| `Acesso negado` ao rodar `net start MySQL80` / `sc.exe config` | O PowerShell não está como administrador (ou a conta não pode mexer em serviços). | Abra o PowerShell como administrador, ou use as opções A, B ou D. |
| O XAMPP mostra *"MySQL shutdown unexpectedly"* ou o MySQL não fica verde | Porta 3306 em uso (por exemplo, o serviço `MySQL80` ligado) ou pasta de dados com problema. | Pare o outro MySQL (`net stop MySQL80` como admin) e veja o log em `C:\xampp\mysql\data\mysql_error.log`. |
| Acentos estranhos (`Ã­`, `Ã§`) | Dados importados com a codificação errada. | Reimporte usando `--default-character-set=utf8mb4` (o banco já é `utf8mb4`). |
| `Unknown column ...` depois de atualizar o código | O banco ainda não recebeu as colunas novas. | Abra o sistema (ou rode `python seed.py --verificar`) com um usuário que possa `ALTER`: a migração é automática. |

### Python / instalação

| O que aparece | Causa | Solução |
|---|---|---|
| `ModuleNotFoundError: No module named 'app.midia'` (ou outro `app.<nome>`) | A pasta `app\` está incompleta ou você não está na raiz do projeto. | Copie a pasta `app\` inteira e rode `python main.py` a partir da pasta que contém o `main.py`. |
| `ModuleNotFoundError: No module named 'PIL'` / `'matplotlib'` / `'bcrypt'` / `'mysql'` / `'google_auth_oauthlib'` | O ambiente virtual não está ativo ou as dependências não foram instaladas. | `.\.venv\Scripts\Activate.ps1` e `pip install -r requirements.txt`. |
| `No module named '_tkinter'` / `tkinter` | Python instalado sem Tkinter. | Reinstale o Python marcando *tcl/tk and IDLE* (Windows) ou `sudo apt install python3-tk` (Linux). |
| *"a execução de scripts foi desabilitada neste sistema"* ao ativar o `.venv` | Política do PowerShell. | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` e ative de novo. |
| `python` não é reconhecido | Python fora do PATH. | Reinstale marcando *Add python.exe to PATH* ou use `py`. |
| `PermissionError` em `logs/`, `midia/` ou `config/` | Projeto em pasta sem permissão de escrita. | Mova o projeto para uma pasta sua (Documentos, Downloads, `C:\Projetos`). |

### Recursos opcionais

| O que aparece | Causa | Solução |
|---|---|---|
| Aviso de e-mail não configurado (2FA / esqueci minha senha / e-mail de urgência) | Falta o `config/email_config.json` ou ele está incompleto. | Seção 3.5. |
| Erro `access_denied` no login com o Google | App em modo de teste e seu e-mail não está na lista. | Adicione o e-mail em **Usuários de teste** (seção 3.6). |
| Falta `config/client_secret.json` | Credenciais do Google não instaladas. | Seção 3.6. |
| Capas e fotos não aparecem | Pillow não instalado, ou a pasta `midia/` deste PC não tem os arquivos. | `pip install pillow` e copie a pasta `midia\` junto com o backup (seção 4). |
| O cabeçalho mostra "Banco de dados desconectado" | O servidor MySQL parou. | Ligue o servidor de novo (seção 3.3); o aviso some sozinho em até 30 segundos. |

---

## 6. Funcionalidades
- **Login e cadastro** com layout editorial (protótipo do Stitch), usuário/e-mail
  + senha com hash **bcrypt**.
- **Verificação em duas etapas (2FA) por e-mail** (código de 6 dígitos, válido por
  10 minutos, via SMTP) e **"Esqueci minha senha"** por código.
- **Login com o Google** (OAuth 2.0), com criação automática da conta.
- **E-mails com layout próprio** (HTML no estilo editorial, com logo opcional).
- **Janela principal** com cabeçalho/masthead e navegação (Notícias, Categorias,
  Autores, Gráficos, Clipping), previsão do tempo clicável na faixa superior, envelope de notificações, acesso ao Perfil pelo nome do
  usuário e botão Sair.
- **Notícias**: editor rápido, feed em cartões com busca, filtros (seção e
  estado), ordenação e paginação, painel "Cadência da Tiragem" e leitura.
- **Editor redacional completo** (botão "+ Nova matéria"): título, linha fina,
  barra de formatação (negrito, itálico, sublinhado, intertítulos, citação,
  link, listas, imagem, filete), contadores, ficha de rotativa (colunas,
  legibilidade, tempo de leitura, embargo), capa com legenda e crédito,
  etiquetas, auto-salvamento local e Salvar rascunho / Publicar. O texto usa
  marcadores simples (`**negrito**`, `*itálico*`, `## intertítulo`, `> citação`).
- **Página de leitura**: sumário "Nesta edição", texto formatado, capa,
  bloco do autor, palavras-chave, leituras suplementares e exportação em HTML.
- **Categorias e Autores**: cartões de resumo, busca, filtros, formulários,
  paginação, fotos dos jornalistas, relatório CSV e bloqueio de exclusão de
  quem tem matérias.
- **Gráficos & Análise** (matplotlib embutido): indicadores com comparação com
  o período anterior, distribuição por editoria, evolução, produtividade por
  autor, volume por dia da semana, pipeline, leitura automática dos dados e
  meta; filtros por período (inclusive personalizado), editoria, jornalista e
  estado; exportação em **PDF** e **CSV**.
- **Notificações**: painel lateral "Despachos & Notificações" (Todas / Não
  lidas / Urgente), selo de não lidas, "lido" por usuário, atalho para o
  assunto, histórico completo, alerta sonoro e e-mail para furos de reportagem.
- **Perfil**: crachá com foto, dados biográficos, troca de senha com regras em
  tempo real, 2FA e preferências do operador (alerta sonoro, e-mail de
  urgência, revisão automática de redação e polegadas de coluna).
- **Previsão do tempo**: a faixa superior mostra `CIDADE • 21°C CÉU LIMPO` (clique para abrir
  o "Caderno de Meteorologia": agora, próximas 24 h com gráfico, 7 dias, detalhes e alertas
  da redação). Cidade por usuário (tela do tempo ou Perfil), localização por IP só com
  consentimento, cache e modo offline. Dados: Open-Meteo.com.
- **Clipping**: importa notícias do dia de jornais escolhidos a partir de feeds RSS/Atom oficiais,
  com filtros, prévia, importação como pauta (`em_pauta`, nunca publicada), importações salvas
  (inclusive automática 1×/dia), histórico, teste de fontes e feed próprio. Matérias importadas
  trazem atribuição e o selo "Conteúdo externo".
- **Imagens** (capas, fotos, imagens no texto): copiadas para `midia/`.
- Registro de eventos e erros em `logs/error.log`.

## 7. Estrutura do projeto
```
News-Manager-main/
├── main.py                        # Ponto de entrada — sempre rode a partir daqui
├── seed.py                        # Dados de teste + verificação automática
├── requirements.txt               # Dependências
├── README.md
├── ROTEIRO_DE_TESTE.md            # Roteiro do que conferir na tela
├── .gitignore
├── tests/                         # Testes automatizados (unittest) e tests/fixtures/
├── app/
│   ├── gui.py                     # Login, cadastro, 2FA e janela principal
│   ├── shell.py                   # Cabeçalho/masthead, navegação, abas e rodapé
│   ├── database.py                # Conexão MySQL e consultas
│   ├── auth.py                    # Hash de senha, 2FA por e-mail, login com Google
│   ├── cadastros.py               # Regras de categorias e autores
│   ├── noticias.py                # Regras do CRUD de notícias
│   ├── notificacoes.py            # Notificações: eventos, leitura por usuário, e-mail
│   ├── perfil.py                  # Regras do Perfil: dados, foto, senha, 2FA, preferências
│   ├── estatisticas.py            # Consultas e indicadores da tela de Gráficos
│   ├── graficos.py                # Gráficos do matplotlib e relatório em PDF
│   ├── texto_rico.py              # Formatação do texto, estatísticas, revisão, exportação HTML
│   ├── midia.py                   # Importação, redimensionamento e exibição de imagens
│   ├── telas_cadastros.py         # Telas de Categorias e Autores
│   ├── tela_noticias.py           # Tela de Notícias (editor rápido + feed)
│   ├── tela_editor.py             # Editor redacional completo
│   ├── tela_leitura.py            # Página de leitura da matéria
│   ├── tela_graficos.py           # Tela Gráficos & Análise
│   ├── tela_notificacoes.py       # Painel de notificações e histórico
│   ├── tela_perfil.py             # Tela de Perfil (inclui a cidade da previsão)
│   ├── rede.py                    # Acesso à internet (timeout, User-Agent, erros em português)
│   ├── segundo_plano.py           # Roda rede em thread e devolve à tela com after()
│   ├── tempo.py                   # Previsão do tempo: Open-Meteo, cache, alertas, cidades, IP
│   ├── graficos_tempo.py          # Gráfico de 24 h (matplotlib)
│   ├── tela_tempo.py              # Faixa/atualizador e tela "Previsão do Tempo"
│   ├── feeds.py                   # Parser seguro de RSS 2.0 / RSS 1.0 / Atom
│   ├── clipping.py                # Catálogo, coleta, filtros, importação, importações salvas
│   ├── tela_clipping.py           # Tela Clipping
│   ├── theme.py                   # Paleta e tipografia (estilo editorial)
│   └── logger.py                  # Registro de eventos/erros
├── config/
│   ├── client_secret.json.example # Modelo das credenciais OAuth do Google
│   ├── email_config.json.example  # Modelo das credenciais SMTP
│   └── fontes_noticias.json       # Catálogo de jornais/feeds do Clipping (sem segredos; VERSIONADO)
│       (os arquivos de verdade, sem ".example", ficam aqui e nunca vão para o Git)
├── sql/
│   ├── schema.sql                 # Cria o banco "newsmanager" e as tabelas (do zero)
│   ├── migration_auth.sql         # Migração da versão bem antiga (senha em texto puro)
│   └── migration_totp_para_email.sql  # Migração de quem usava 2FA por TOTP/QR Code
├── assets/logo.png                # Opcional — logo dos e-mails (crie a pasta se quiser usar)
├── design/LayoutStitch/           # Opcional — protótipo de telas (referência visual)
├── docs/  screenshots/            # Opcional — documentação e prints (se existirem no seu clone)
└── (criados em uso, fora do Git) logs/  midia/  rascunhos/  config/graficos.json
```

## 8. Como funcionam o 2FA, o "esqueci minha senha" e os e-mails

**2FA por e-mail**
- No **Cadastro**, "Ativar verificação em duas etapas por e-mail" vem marcada;
  o sistema envia um código de 6 dígitos e, ao digitá-lo, o 2FA fica ativo.
- Dá para pular e ativar depois, no **Perfil → Módulo 02 (Segurança)**, que
  também desativa o 2FA e troca a senha.
- No login tradicional, contas com 2FA recebem um código por e-mail (há
  "Reenviar código"). O código vale 10 minutos e só pode ser usado uma vez.
- Contas que entram pelo **Google** não passam pelo 2FA do NewsManager: a
  própria Conta Google autentica.

**Esqueci minha senha**
- No login, "Esqueceu a senha?" pede o usuário/e-mail, envia um código ao
  e-mail cadastrado e, na segunda etapa, pede o código e a nova senha.
- Contas criadas só pelo Google (sem senha local) recebem um aviso.
- Por simplicidade, o sistema informa quando a conta não existe; em produção
  o ideal seria uma mensagem genérica (vale citar na análise de segurança).

**Layout e logo dos e-mails**
- O layout fica em `app/auth.py` (`EmailSender._montar_html`).
- Para usar um logo, coloque `assets/logo.png` (ou ajuste `LOGO_FILE` em
  `app/auth.py`); sem o arquivo, o e-mail usa o logo em texto.

## 9. Dados de teste e roteiro de testes
```powershell
python seed.py                  # popula o banco e roda as verificações
python seed.py --verificar      # só confere, sem alterar nada
python seed.py --recriar        # apaga o que o seed criou e cria tudo de novo
python seed.py --limpar         # remove só os dados do seed (e as imagens deles)
python seed.py --volume 300     # matérias extras para os gráficos (padrão 120)
python seed.py --autosave       # cria um rascunho automático de exemplo (teste da recuperação)
python seed.py --sem-imagens    # sem capas/fotos
python seed.py --verificar-rede # testa AO VIVO os feeds do Clipping e a API do tempo (OK/FALHA por fonte)
python seed.py --verificar-rede --com-ip   # idem, e testa também a localização por IP
```
O seed cria editorias, autores (com e sem foto), 18 matérias em todos os
estados, matérias extras espalhadas pelos últimos 120 dias, despachos de
exemplo e roda dezenas de verificações automáticas — inclusive as de Previsão do tempo e Clipping, feitas
**offline** com os arquivos de `tests/fixtures/` (os dados temporários que elas criam são removidos
no fim). `--verificar-rede` não usa o banco e precisa de internet. Ele nunca mexe no que
**você** cadastrou. Se algum item aparecer como `FALHA`, copie a saída do
terminal. O `ROTEIRO_DE_TESTE.md` lista, tela por tela, o que conferir na
janela real.

## 10. Migrações de bancos antigos
Só são necessárias para bancos criados por versões muito antigas do projeto.
Para um banco novo, o `schema.sql` basta.

- **Versão bem antiga** (tabela `usuarios` com `usuario`/`senha` em texto puro):
  ```powershell
  & "$mysql\mysql.exe" -u root --default-character-set=utf8mb4 newsmanager -e "source sql/migration_auth.sql"
  ```
- **Versão intermediária com 2FA por TOTP/QR Code** (colunas `totp_secret`/`totp_ativo`):
  ```powershell
  & "$mysql\mysql.exe" -u root --default-character-set=utf8mb4 newsmanager -e "source sql/migration_totp_para_email.sql"
  ```

Leia os comentários dentro de cada script. Como as senhas usam bcrypt
(calculado em Python), depois de migrar da versão mais antiga o jeito mais
simples é recriar os usuários pela tela **Criar conta**.

## Ideias futuras
- Fontes de notícias por API (GNews, NewsData.io...) como complemento opcional, com chave em `config/`.
- Resumo do clipping por e-mail.

## 11. Previsão do tempo e Clipping
**Nada novo para instalar:** só `requests` e `matplotlib`, que já estão no `requirements.txt`. As tabelas
novas e as colunas `fonte_*` de `noticias` são criadas **sozinhas** ao abrir o programa (e estão no
`sql/schema.sql` para instalações novas). Sem internet o programa continua funcionando: o tempo mostra o
último dado guardado (ou `SEM PREVISÃO`) e o Clipping permite ver os itens já coletados.

### Previsão do tempo
- **Fonte:** [Open-Meteo.com](https://open-meteo.com/), sem chave. Termos conferidos em 28/10/2026: uso
  gratuito apenas **não comercial**, abaixo de 10.000 chamadas/dia (5.000/hora, 600/minuto); dados sob
  **CC BY 4.0** com atribuição visível ("Dados meteorológicos: Open-Meteo.com (CC BY 4.0)", no rodapé da tela).
  O programa consulta uma vez a cada ~25 min e reaproveita o cache por 20 min.
- **Cidade** (ordem): cidade salva do usuário → (perguntado **uma vez**) localização aproximada pelo IP →
  busca por nome → cidade padrão **Santa Maria, RS** (constante `CIDADE_PADRAO` em `app/tempo.py`; troque lá).
  A cidade se muda na tela do tempo ou no **Perfil** (mesma preferência, por usuário).
- **IP:** só com o seu "sim". O IP vai ao serviço de terceiros **ipapi.co** (gratuito, HTTPS, sem chave,
  cerca de 1.000 consultas/dia). Recusou? Fica registrado e não perguntamos de novo.
- **Alertas da redação:** limites em `LIMITES_ALERTA` (`app/tempo.py`): chuva ≥ 70%, vento ≥ 40 km/h,
  UV ≥ 8, calor ≥ 35 °C, frio ≤ 5 °C, mais aviso de tempestade.

### Clipping
- **Fontes:** feeds RSS/Atom listados em `config/fontes_noticias.json` (sem segredos, versionado). Não há
  raspagem de páginas. Cada feed tem `verificacao`: `indireta` = endereço visto em diretório de terceiros em
  28/10/2026 (não aberto ao vivo na página oficial do jornal); `nao_verificada` = endereço conhecido, mas não
  confirmado (a fonte vem **desativada**). Estadão, UOL, Correio do Povo e GZH estão **sem feed**: cole o
  endereço oficial em *Fontes → Adicionar feed próprio*. Use **Testar fontes** (ou `python seed.py
  --verificar-rede`) para conferir tudo na sua rede.
- **O que é importado:** título, resumo curto do feed, data, link e nome do jornal. Não republicamos o
  texto completo e **não baixamos imagens**. A matéria leva `Fonte: [Jornal](link)` no texto, os campos
  `fonte_nome/fonte_url/fonte_guid` e o selo **Conteúdo externo** no cartão e na leitura. Entra como
  **Em Pauta** (ou Rascunho/Revisão); **publicar sozinho é recusado**. O autor é "Clipping — <jornal>".
- **Boas maneiras com os servidores:** User-Agent identificável, no máximo **1 coleta por feed a cada
  15 minutos** (dentro disso a prévia usa o que já foi coletado), 4 conexões no total e 2 por servidor,
  timeout de 10 s, 2 tentativas, ETag/Last-Modified. Aviso fixo na tela: *conteúdo de terceiros — confira
  os termos de uso de cada jornal*.
- **Filtros:** jornais e seções, palavras que devem aparecer (basta uma; `econom*` = curinga) e que não
  devem, período, máximo por jornal, só com imagem, ocultar já importados, ordem. Itens repetidos (mesmo
  guid ou mesmo link) aparecem uma vez, e o que já foi importado nunca é importado de novo.
- **Importações salvas:** guardam um conjunto de filtros com nome; *Rodar agora*, editar, excluir; a opção
  **automática** roda 1 vez por dia, em segundo plano, ao abrir o programa, e deixa um aviso-resumo.
- **Editoria:** sugerida pela seção do feed e por palavras do título/resumo (política, esportes,
  tecnologia, economia, mundo, cultura, saúde) e ajustável; só usa editorias que **já existem**.
- **Segurança do XML:** documentos com `<!ENTITY>` ou DOCTYPE com subconjunto interno são rejeitados
  (por isso não precisamos do `defusedxml`); só links http/https; resumos têm as tags removidas.

### Solução de problemas de rede
| Sintoma | O que fazer |
|---|---|
| "Sem conexão com a internet ou servidor inacessível" | Teste o navegador; em rede de faculdade/empresa configure o proxy: `$env:HTTPS_PROXY="http://proxy.suaescola.br:3128"` e `$env:HTTP_PROXY=...` no PowerShell **antes** de rodar `python main.py`. |
| "Falha de certificado/SSL" | A rede intercepta conexões seguras. Peça o certificado ao suporte e use `$env:REQUESTS_CA_BUNDLE="C:\caminho\certificado.pem"`. |
| Um feed dá 404 | O jornal mudou/descontinuou o feed. Desative-o na aba Fontes ou cole o endereço novo em "Adicionar feed próprio". |
| "O endereço devolveu uma página HTML" | O link não é de um feed RSS/Atom (procure o ícone/página "RSS" do jornal). |
| Muitas requisições (429) | Aguarde; o programa já espaça as coletas. |
| `SEM PREVISÃO` na faixa | Sem internet e sem cache. Abra a tela do tempo e use **Atualizar** quando voltar a conexão. |

## 12. Testes automatizados
O repositório agora tem `tests/` (biblioteca padrão `unittest`, **sem pytest, sem internet, sem MySQL e sem
janela real**). Na pasta do projeto:
```powershell
python -m unittest discover -s tests -t . -v
```
- `test_tempo.py`: códigos WMO, regras de alerta, leitura da fixture JSON do Open-Meteo, cache/TTL, falhas
  de rede, busca de cidades, localização por IP, cidade por usuário e o atualizador (sem Tk).
- `test_feeds.py`: parser RSS/Atom (acentos, Latin-1, HTML, datas, segurança do XML).
- `test_clipping.py`: filtros (incluir/excluir/período/limite), deduplicação, mapeamento seção→editoria,
  coleta com falhas parciais, intervalo de 15 min, GET condicional, criação das matérias com atribuição,
  importações salvas e automática.
- `test_telas.py`: monta e exercita as telas novas com um **Tk de mentira** (`tests/_tkfalso.py`); é uma
  simulação que acha erros de lógica, **não** valida aparência nem eventos reais.
- Os serviços rodam num **SQLite em memória** (`tests/_ambiente.py`): a lógica é testada, mas o SQL específico
  de MySQL/MariaDB (ex.: `INSERT IGNORE`, `AUTO_INCREMENT`) **não** — confira com `python seed.py --verificar`.
- As fixtures de RSS/Atom em `tests/fixtures/` seguem a estrutura real desses formatos, mas o conteúdo é
  **fictício** (feito à mão, com acentos, HTML, CDATA e casos de erro).
