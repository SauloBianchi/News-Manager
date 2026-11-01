-- Script de criação do banco de dados NewsManager
-- Sistema de Gerenciamento e Análise de Notícias
--
-- ATENÇÃO: se o banco já existia com a versão antiga da tabela `usuarios`
-- (colunas `usuario` + `senha` em texto puro), rode em vez deste script o
-- arquivo `sql/migration_auth.sql`, que faz a migração sem perder os dados
-- de notícias/categorias/autores já cadastrados.

CREATE DATABASE IF NOT EXISTS newsmanager
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE newsmanager;

-- Usuários do sistema (login tradicional e/ou login com Google, com
-- verificação em duas etapas por código enviado por e-mail).
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    usuario VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(150) NOT NULL UNIQUE,
    senha_hash VARCHAR(255) NULL,          -- hash bcrypt; NULL para contas só-Google
    google_id VARCHAR(255) NULL UNIQUE,    -- "sub" retornado pelo Google OAuth
    dois_fatores_ativo BOOLEAN NOT NULL DEFAULT FALSE,
    codigo_verificacao VARCHAR(255) NULL,  -- hash SHA-256 do código de 6 dígitos (nunca texto puro)
    codigo_expira_em DATETIME NULL,        -- validade do código acima (10 min)
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultimo_login TIMESTAMP NULL,
    -- perfil do usuário (tela Perfil)
    byline VARCHAR(150) NULL,
    telefone VARCHAR(60) NULL,
    atribuicao TEXT NULL,
    cargo VARCHAR(120) NULL,
    matricula VARCHAR(40) NULL,
    registro VARCHAR(40) NULL,
    conselho VARCHAR(120) NULL,
    mesa VARCHAR(120) NULL,
    nota_biografica TEXT NULL,
    foto VARCHAR(255) NULL,
    atualizado_em DATETIME NULL,
    atualizado_por VARCHAR(150) NULL
);

CREATE TABLE IF NOT EXISTS categorias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(80) NOT NULL UNIQUE,
    descricao VARCHAR(255) NULL,                       -- "resumo editorial da seção"
    cor VARCHAR(20) NOT NULL DEFAULT 'rubro',          -- rubro | azul | sepia | carvao
    status VARCHAR(20) NOT NULL DEFAULT 'ativa'        -- ativa | em_revisao
);

CREATE TABLE IF NOT EXISTS autores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(120) NOT NULL,
    email VARCHAR(150),
    bio TEXT NULL,
    funcao VARCHAR(30) NOT NULL DEFAULT 'reporter',    -- reporter | colunista | editor_setorial | correspondente
    cargo VARCHAR(120) NULL,                           -- ex.: Editora de Política • Brasília
    registro VARCHAR(40) NULL,                         -- MTB / cédula profissional
    status VARCHAR(30) NOT NULL DEFAULT 'ativo',       -- ativo | em_pauta_externa
    foto VARCHAR(255) NULL                             -- caminho dentro de midia/
);

CREATE TABLE IF NOT EXISTS noticias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    subtitulo VARCHAR(300) NULL,                       -- linha fina / lead editorial
    conteudo TEXT,
    categoria_id INT NOT NULL,
    autor_id INT NOT NULL,
    data_publicacao DATETIME NOT NULL,                 -- data e hora de emissão
    status VARCHAR(20) NOT NULL DEFAULT 'publicado',   -- rascunho | em_pauta | revisao | publicado
    destaque TINYINT(1) NOT NULL DEFAULT 0,            -- manchete de capa
    etiquetas VARCHAR(255) NULL,                       -- separadas por vírgula, sem o '#'
    leituras INT NOT NULL DEFAULT 0,
    imagem VARCHAR(255) NULL,                          -- fotografia de capa (caminho dentro de midia/)
    imagem_legenda VARCHAR(255) NULL,
    imagem_credito VARCHAR(120) NULL,
    fonte_nome VARCHAR(120) NULL,                      -- só nas matérias importadas por clipping (conteúdo externo)
    fonte_url VARCHAR(1000) NULL,
    fonte_guid VARCHAR(255) NULL,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id),
    FOREIGN KEY (autor_id) REFERENCES autores(id)
);

-- Dados iniciais de exemplo
-- Não há mais um usuário "admin" pré-cadastrado com senha em texto puro:
-- como as senhas agora usam hash bcrypt (gerado em Python), crie o primeiro
-- usuário pela própria tela de "Criar conta" do aplicativo.

INSERT INTO categorias (nome, descricao, cor) VALUES
  ('Política', 'Cobertura de plenário, ministérios, políticas públicas e relações institucionais de governo.', 'rubro'),
  ('Esportes', 'Campeonatos nacionais, olimpismo, automobilismo e análise tática esportiva.', 'carvao'),
  ('Tecnologia', 'Avanços computacionais, inteligência artificial, espaço e pesquisas acadêmicas de vanguarda.', 'sepia'),
  ('Economia', 'Indicadores macroeconômicos, mercados financeiros, balanços corporativos e tributação.', 'azul')
  ON DUPLICATE KEY UPDATE nome = nome;

INSERT INTO autores (nome, email, funcao) VALUES ('Ernesto', 'ernesto@example.com', 'reporter'),
                                                 ('Gabriel S', 'gabriel@example.com', 'reporter'),
                                                 ('Saulo', 'saulo@example.com', 'reporter')
  ON DUPLICATE KEY UPDATE nome = nome;

-- Despachos & notificações (painel do sino) e preferências por usuário
CREATE TABLE IF NOT EXISTS notificacoes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tipo VARCHAR(30) NOT NULL,                         -- furo | publicacao | revisao | pauta | estrutura | arquivo | seguranca
    titulo VARCHAR(200) NOT NULL,
    mensagem VARCHAR(600) NULL,
    etiqueta VARCHAR(80) NULL,
    rodape VARCHAR(160) NULL,
    urgente TINYINT(1) NOT NULL DEFAULT 0,
    alvo_tipo VARCHAR(20) NULL,                        -- noticia | categoria | autor | perfil
    alvo_id INT NULL,
    usuario_destino INT NULL,                          -- NULL = todos; senão, só esse usuário
    ator VARCHAR(150) NULL,
    criado_em DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS notificacoes_lidas (
    usuario_id INT NOT NULL,
    notificacao_id INT NOT NULL,
    lida_em DATETIME NOT NULL,
    PRIMARY KEY (usuario_id, notificacao_id)
);

CREATE TABLE IF NOT EXISTS preferencias_usuario (
    usuario_id INT NOT NULL,
    chave VARCHAR(60) NOT NULL,
    valor VARCHAR(255) NOT NULL,
    PRIMARY KEY (usuario_id, chave)
);

-- ---------------------------------------------------------------------------
-- Previsão do tempo (cache da última resposta, para abrir na hora e funcionar offline)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tempo_cache (
    chave VARCHAR(40) NOT NULL PRIMARY KEY,            -- "latitude,longitude" com 2 casas
    atualizado_em DATETIME NOT NULL,
    payload MEDIUMTEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Clipping (notícias de jornais via RSS/Atom)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clipping_itens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fonte_chave VARCHAR(60) NOT NULL,
    secao VARCHAR(80) NULL,
    guid VARCHAR(255) NOT NULL,
    url VARCHAR(1000) NOT NULL,
    titulo VARCHAR(500) NOT NULL,
    resumo TEXT NULL,
    autor_fonte VARCHAR(200) NULL,
    publicado_em DATETIME NULL,
    imagem_url VARCHAR(1000) NULL,
    coletado_em DATETIME NOT NULL,
    importado_noticia_id INT NULL,                     -- nulo até importar
    UNIQUE KEY uq_clipping_fonte_guid (fonte_chave, guid)
);

CREATE TABLE IF NOT EXISTS importacoes_salvas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    nome VARCHAR(120) NOT NULL,
    fontes TEXT NOT NULL,                              -- JSON: chaves dos jornais
    secoes TEXT NULL,                                  -- JSON: feeds escolhidos (vazio = todos)
    palavras_incluir VARCHAR(500) NULL,
    palavras_excluir VARCHAR(500) NULL,
    periodo_horas INT NOT NULL DEFAULT 24,
    limite_por_fonte INT NOT NULL DEFAULT 10,
    so_com_imagem TINYINT(1) NOT NULL DEFAULT 0,
    ordem VARCHAR(20) NOT NULL DEFAULT 'recentes',
    categoria_id INT NULL,                             -- NULL = editoria sugerida automaticamente
    autor_id INT NULL,                                 -- NULL = "Clipping — <jornal>"
    status_destino VARCHAR(20) NOT NULL DEFAULT 'em_pauta',
    automatica TINYINT(1) NOT NULL DEFAULT 0,
    ultima_execucao DATETIME NULL
);

CREATE TABLE IF NOT EXISTS clipping_historico (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NULL,
    quando DATETIME NOT NULL,
    origem VARCHAR(20) NOT NULL,                       -- manual | salva | auto
    nome VARCHAR(120) NULL,
    importadas INT NOT NULL DEFAULT 0,
    existentes INT NOT NULL DEFAULT 0,
    falhas INT NOT NULL DEFAULT 0,
    fontes VARCHAR(500) NULL
);

CREATE TABLE IF NOT EXISTS clipping_feeds_estado (     -- ETag/Last-Modified e hora da última coleta (15 min entre coletas)
    chave CHAR(40) NOT NULL PRIMARY KEY,               -- SHA-1 da URL
    url VARCHAR(1000) NOT NULL,
    etag VARCHAR(255) NULL,
    last_modified VARCHAR(100) NULL,
    ultima_coleta DATETIME NULL,
    ultimo_status VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS clipping_feeds_proprios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    nome VARCHAR(100) NOT NULL,
    url VARCHAR(500) NOT NULL,
    secao VARCHAR(80) NULL,
    criado_em DATETIME NOT NULL
);
