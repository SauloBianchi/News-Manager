# NewsManager

Sistema de Gerenciamento e Análise de Notícias — aplicação desktop em Python
com Tkinter e banco de dados MySQL.

## Equipe
- Ernesto
- Gabriel S
- Saulo

## Funcionalidades
- Login e Cadastro com layout editorial (baseado no protótipo do Stitch),
  usuário/e-mail + senha com hash **bcrypt**.
- **Verificação em duas etapas (2FA) por código enviado por e-mail** —
  código de 6 dígitos, válido por 10 minutos, enviado via SMTP.
- **"Esqueci minha senha"** — redefine a senha confirmando a identidade
  por um código enviado ao e-mail cadastrado.
- **Login com o Google** (OAuth 2.0), tanto na tela de login quanto na de
  cadastro — cria a conta automaticamente no primeiro acesso.
- **E-mails com layout próprio** (HTML, no estilo editorial do app), com
  suporte a logo customizado.
- Janela Principal com cabeçalho/masthead e navegação no estilo do Stitch
  (Notícias, Categorias, Autores, Gráficos, Segurança) e botão Sair.
- **CRUD de notícias** (criar, listar com busca/filtros/paginação, editar,
  excluir, ler): editor com linha fina, seção, jornalista, data/hora, estado
  (rascunho, em pauta, revisão, publicado), manchete de capa e etiquetas.
- **Editor redacional completo** (tela própria, aberto por "+ Nova matéria"):
  título nobre, linha fina, barra de formatação (negrito, itálico, sublinhado,
  intertítulos, citação, link, listas, imagem e filete), contadores, ficha de
  rotativa (colunas, legibilidade Flesch, tempo de leitura, embargo), registro
  editorial, etiquetas, auto-salvamento local e botões Salvar rascunho /
  Publicar. O texto usa marcadores simples (`**negrito**`, `*itálico*`,
  `## intertítulo`, `> citação`).
- **Página de leitura da matéria** (tela inteira): sumário "Nesta edição",
  texto formatado, capa com legenda, bloco do autor, palavras-chave,
  leituras suplementares da mesma editoria e exportação em HTML (para
  imprimir/salvar em PDF pelo navegador).
- **Notificações** (envelope no cabeçalho): painel lateral "Despachos & Notificações" com abas
  Todas / Não lidas / Urgente, selo de não lidas, tempo relativo, atalho para o assunto, histórico
  completo, "lido" por usuário, alerta sonoro e e-mail para furos de reportagem.
- **Perfil** (clicar no nome no cabeçalho): crachá com foto, dados biográficos, troca de senha com
  regras em tempo real, 2FA e preferências do operador (alerta sonoro, e-mail de urgência, revisão
  automática de redação e polegadas de coluna no editor).
- **Gráficos & Análise** (tela inteira, gráficos do matplotlib embutidos): indicadores com
  comparação com o período anterior, distribuição por editoria, evolução no período,
  produtividade por autor, volume por dia da semana, pipeline redatorial, leitura automática
  dos dados e meta do período. Filtros por período (inclusive personalizado), editoria,
  jornalista e estado da matéria; exportação em PDF e CSV.
- **Dados de teste**: `python seed.py` cria editorias, autores e matérias em todos os
  estados (com imagens) e roda uma verificação automática; o roteiro do que
  conferir na tela está em `ROTEIRO_DE_TESTE.md`.
- **Imagens**: fotografia de capa (com legenda e crédito) nas matérias e foto
  dos jornalistas. Os arquivos são copiados para a pasta `midia/` (criada
  automaticamente, fora do Git); precisa do Pillow (`pip install pillow`).
- **Telas de Categorias e Autores** no layout do Stitch: cartões de resumo,
  busca, filtros por função, formulários de cadastro/edição, paginação,
  relatório de categorias em CSV e bloqueio de exclusão de quem tem matérias.
- Gráfico de notícias por categoria (matplotlib).
- Aba de Segurança para ativar/desativar o 2FA depois do cadastro.
- Registro de eventos e erros em `logs/error.log`.

## Estrutura do projeto
```
News-Manager-main/
├── main.py                        # Ponto de entrada — sempre rode a partir daqui
├── requirements.txt                # Dependências
├── README.md
├── .gitignore
├── app/                             # Código da aplicação
│   ├── __init__.py
│   ├── gui.py                       # Janelas Tkinter (login, cadastro, 2FA, principal)
│   ├── database.py                  # Conexão MySQL e operações CRUD
│   ├── cadastros.py                 # Regras de negócio do CRUD de categorias e autores (services)
│   ├── telas_cadastros.py           # Telas Tkinter de Categorias e Autores (layout Stitch)
│   ├── noticias.py                  # Regras de negócio do CRUD de notícias (NoticiaService)
│   ├── tela_noticias.py             # Tela de Notícias: editor, feed em cartões e leitura
│   ├── texto_rico.py                # Formatação do texto das matérias, estatísticas e exportação HTML
│   ├── tela_editor.py               # Tela Nova Matéria: editor redacional completo
│   ├── tela_leitura.py              # Tela de leitura da matéria (página inteira)
│   ├── notificacoes.py              # Notificações: eventos, leitura por usuário, e-mail de urgência
│   ├── perfil.py                    # Regras do Perfil: dados, foto, senha, 2FA e preferências
│   ├── tela_notificacoes.py         # Painel de notificações (gaveta) e histórico
│   ├── tela_perfil.py               # Tela de Perfil
│   ├── estatisticas.py              # Consultas e indicadores da tela de Gráficos (filtros, KPIs, séries)
│   ├── graficos.py                  # Gráficos do matplotlib e relatório em PDF
│   ├── tela_graficos.py             # Tela Gráficos & Análise
│   ├── midia.py                     # Importação, redimensionamento e exibição das imagens
│   ├── shell.py                     # Cabeçalho/masthead, navegação, área de abas e rodapé
│   ├── auth.py                      # Hash de senha, 2FA por e-mail e login com Google
│   ├── theme.py                     # Paleta de cores e tipografia (estilo editorial)
│   └── logger.py                    # Registro de eventos/erros
├── config/
│   ├── client_secret.json.example   # Modelo das credenciais OAuth do Google
│   └── email_config.json.example    # Modelo das credenciais SMTP (2FA por e-mail)
│       (os arquivos de verdade, sem ".example", também vão aqui — nunca commitados)
├── assets/
│   └── logo.png                     # Opcional — se existir, é usado nos e-mails (ver seção 8)
├── sql/
│   ├── schema.sql                   # Script de criação do banco e tabelas (do zero)
│   ├── migration_auth.sql           # Migração da versão bem antiga (texto puro) para a atual
│   └── migration_totp_para_email.sql  # Migração de quem já tinha a versão com TOTP/QR Code
├── design/
│   └── LayoutStitch/                 # Protótipo de telas gerado no Stitch (referência visual)
├── logs/                              # Gerado em runtime (error.log)
├── docs/                               # Documentação em PDF (diagrama de classes, etc.)
└── screenshots/                         # Prints das telas da aplicação
```

## Como executar

### 1. Instalar dependências
Na raiz do projeto:
```bash
pip install -r requirements.txt
```
(O envio de e-mail usa só bibliotecas nativas do Python — `smtplib`,
`hashlib`, `secrets` — não precisa instalar nada além disso.)

### 2. Configurar o banco de dados MySQL

**Banco novo (ainda não existe):**
```bash
mysql -u root -p < sql/schema.sql
```

**Banco criado com a versão bem antiga** (tabela `usuarios` só com
`usuario`/`senha` em texto puro):
```bash
mysql -u root -p newsmanager < sql/migration_auth.sql
```

**Banco que já tinha a versão intermediária com 2FA por TOTP/QR Code**
(colunas `totp_secret`/`totp_ativo`):
```bash
mysql -u root -p newsmanager < sql/migration_totp_para_email.sql
```

Leia os comentários dentro de cada script. Como as senhas usam hash bcrypt
(calculado em Python), o jeito mais simples de testar depois de migrar a
partir da versão bem antiga é recriar os usuários pela própria tela
**Criar conta** do aplicativo. Não existe mais um usuário `admin`/`admin123`
pré-cadastrado.

### 3. Ajustar a conexão com o MySQL
Edite as credenciais em `main.py`, na criação de `DatabaseManager`
(`host`, `user`, `password`, `database`), conforme o seu ambiente.

### 4. Configurar o envio de e-mail (necessário para o 2FA)
O código de verificação é enviado por SMTP. O jeito mais simples para um
projeto de faculdade é usar uma conta do Gmail com **Senha de App**:

1. Na Conta Google que vai enviar os e-mails, ative a **Verificação em
   duas etapas** (em myaccount.google.com/security) — é pré-requisito
   para gerar senhas de app.
2. Ainda em "Segurança", acesse **Senhas de app**
   (myaccount.google.com/apppasswords), crie uma nova senha para o app
   "NewsManager" e copie o código de 16 letras gerado.
   - Se a opção "Senhas de app" não aparecer, é porque a conta usa
     verificação em 2 etapas de outro jeito (chave de segurança, etc.) —
     nesse caso, use uma conta pessoal comum do Gmail só para testes, ou
     um serviço como o Mailtrap/SendGrid (mesma configuração, mudando
     `smtp_host`/`smtp_porta`).
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
4. **Nunca** faça commit do `config/email_config.json` de verdade — ele já
   está no `.gitignore`. Cada integrante que for rodar o projeto localmente
   precisa da sua própria cópia (ou combinar de usar a mesma, compartilhada
   fora do Git).

Se quiser usar outro provedor de e-mail (Outlook, um SMTP da faculdade,
etc.), só troca `smtp_host`/`smtp_porta`/`smtp_usuario`/`smtp_senha` —
o código não depende do Gmail especificamente.

### 5. Configurar o login com o Google (necessário para o botão "Entrar/Cadastrar com o Google")
1. Acesse o [Google Cloud Console](https://console.cloud.google.com/) e
   crie (ou reaproveite) um projeto.
2. Em **APIs e Serviços → Tela de consentimento OAuth**, configure o app
   como "Externo" (ou "Interno", se for Workspace) e adicione os escopos
   `openid`, `.../auth/userinfo.email` e `.../auth/userinfo.profile`.
   - Enquanto o app estiver em modo de teste, adicione os e-mails da
     equipe em **Usuários de teste** (senão o Google bloqueia o login).
3. Em **APIs e Serviços → Credenciais → Criar credenciais → ID do cliente
   OAuth**, escolha o tipo de aplicativo **"Aplicativo para computador"**
   (Desktop app).
4. Baixe o JSON gerado, renomeie para `client_secret.json` e coloque
   dentro da pasta **`config/`** (`config/client_secret.json`). Use
   `config/client_secret.json.example` como referência do formato esperado.
5. **Nunca** faça commit do `client_secret.json` de verdade — ele já está
   no `.gitignore`.

Ao clicar em "Entrar com o Google" ou "Cadastrar com o Google", o
NewsManager abre o navegador padrão para o login e sobe um servidor local
temporário só para capturar o retorno do Google — não é preciso nenhuma
configuração de servidor/deploy.

### 6. Como funciona o 2FA por e-mail
- Na tela de **Cadastro**, a caixa "Ativar verificação em duas etapas por
  e-mail" vem marcada por padrão. Ao criar a conta, o sistema já envia um
  código de 6 dígitos para o e-mail informado; digitando o código
  corretamente, o 2FA fica ativado.
- É possível pular a ativação e configurar depois, na aba **Segurança**
  da janela principal.
- No login tradicional (usuário/senha), se a conta tiver 2FA ativo, o
  sistema envia (de novo) um código por e-mail e pede que ele seja
  digitado antes de liberar o acesso. Tem um link "Reenviar código" caso
  o e-mail demore ou não chegue.
- O código expira em 10 minutos e só pode ser usado uma vez.
- Contas que entram via **Google** não passam pelo 2FA do NewsManager
  nesse fluxo, já que a própria Conta Google autentica o usuário.
- Se `config/email_config.json` não existir ou estiver incompleto, o
  sistema avisa exatamente o que falta configurar, em vez de travar.

### 7. Como funciona o "Esqueci minha senha"
- Na tela de **Login**, o link "Esqueceu a senha?" abre uma janela em
  duas etapas: primeiro pede o usuário/e-mail da conta; se encontrada,
  envia um código de 6 dígitos para o e-mail cadastrado.
- Na segunda etapa, a pessoa informa o código recebido, a nova senha e a
  confirmação. O código tem a mesma validade de 10 minutos do 2FA (tem
  link "Reenviar código" também).
- Contas criadas só pelo **Google** (sem senha local) mostram um aviso
  explicando que o login é feito só pelo botão do Google.
- Por simplicidade, se o usuário/e-mail informado não existir, o sistema
  avisa diretamente ("Não encontramos uma conta..."). Em um sistema de
  produção, o ideal seria mostrar sempre a mesma mensagem genérica (algo
  como "se essa conta existir, enviamos um e-mail"), para não revelar se
  um e-mail está ou não cadastrado — vale considerar isso na documentação
  do trabalho, se for pedido uma análise de segurança.

### 8. Personalizando o layout e o logo dos e-mails
Todos os e-mails de código (2FA e "esqueci minha senha") são gerados em
HTML, no mesmo estilo editorial do resto do app (cores, tipografia,
filetes), com uma versão em texto puro como reserva para clientes que não
exibem HTML.

- O **layout** fica em `app/auth.py`, no método `EmailSender._montar_html`
  — dá pra mexer nas cores, textos e na estrutura da tabela HTML ali.
- Para usar um **logo de verdade** em vez do nome "NewsManager" estilizado
  em texto, basta colocar um arquivo de imagem em `assets/logo.png` (ou
  `.jpg`, ajustando `LOGO_FILE` em `app/auth.py`) na raiz do projeto. Se o
  arquivo existir, ele é detectado e embutido automaticamente no e-mail;
  se não existir, o e-mail continua funcionando normalmente com o logo em
  texto.
- Os textos de título/introdução do e-mail podem ser personalizados por
  chamada (é o que já é feito para diferenciar o e-mail de 2FA do e-mail
  de redefinição de senha) — veja os parâmetros `titulo` e `texto_intro`
  de `EmailSender.enviar_codigo_verificacao`.

### 9. Rodar a aplicação
Sempre a partir da raiz do projeto (é daqui que os caminhos relativos de
`config/`, `assets/` e `logs/` são resolvidos):
```bash
python main.py
```

## Próximos passos sugeridos
- Adicionar validações extras nos formulários.
- Adicionar filtro por categoria/data na listagem de notícias.
- Gerar relatório em PDF a partir dos dados do sistema.
- Elaborar a documentação final (PDF) com diagrama de classes e prints.
