# NewsManager

Sistema de Gerenciamento e Análise de Notícias — aplicação desktop em Python
com Tkinter e banco de dados MySQL.

## Equipe
- Ernesto
- Gabriel S
- Saulo

## Funcionalidades
- Janela de Login e Janela Principal.
- CRUD completo de notícias (criar, listar, editar, excluir).
- Cadastro de categorias e autores.
- Gráfico de notícias por categoria (matplotlib).
- Registro de erros em `error.log`.
- Código orientado a objetos, dividido em módulos (`main.py`, `database.py`,
  `gui.py`, `logger.py`).

## Estrutura do projeto
```
newsmanager/
├── main.py            # Inicia a aplicação
├── database.py        # Conexão MySQL e operações CRUD
├── gui.py              # Janelas Tkinter (login, principal, gráfico)
├── logger.py           # Registro de erros
├── requirements.txt    # Dependências
├── error.log            # Arquivo de logs (gerado em runtime)
├── database/
│   └── schema.sql       # Script de criação do banco e tabelas
├── docs/                 # Documentação em PDF (diagrama de classes, etc.)
└── screenshots/           # Prints das telas da aplicação
```

## Como executar

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Configurar o banco de dados MySQL
Crie o banco e as tabelas executando o script:
```bash
mysql -u root -p < database/schema.sql
```

Um usuário de teste já é criado:
- **usuário:** `admin`
- **senha:** `admin123`

### 3. Ajustar a conexão
Edite as credenciais em `main.py`, na criação de `DatabaseManager`
(`host`, `user`, `password`, `database`), conforme o seu ambiente.

### 4. Rodar a aplicação
```bash
python main.py
```

## Próximos passos sugeridos
- Adicionar validações extras nos formulários.
- Adicionar filtro por categoria/data na listagem de notícias.
- Gerar relatório em PDF a partir dos dados do sistema.
- Elaborar a documentação final (PDF) com diagrama de classes e prints.
