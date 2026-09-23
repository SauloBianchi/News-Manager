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
    ultimo_login TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS categorias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS autores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(120) NOT NULL,
    email VARCHAR(150)
);

CREATE TABLE IF NOT EXISTS noticias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    conteudo TEXT,
    categoria_id INT NOT NULL,
    autor_id INT NOT NULL,
    data_publicacao DATE NOT NULL,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id),
    FOREIGN KEY (autor_id) REFERENCES autores(id)
);

-- Dados iniciais de exemplo
-- Não há mais um usuário "admin" pré-cadastrado com senha em texto puro:
-- como as senhas agora usam hash bcrypt (gerado em Python), crie o primeiro
-- usuário pela própria tela de "Criar conta" do aplicativo.

INSERT INTO categorias (nome) VALUES ('Política'), ('Esportes'), ('Tecnologia'), ('Economia')
  ON DUPLICATE KEY UPDATE nome = nome;

INSERT INTO autores (nome, email) VALUES ('Ernesto', 'ernesto@example.com'),
                                         ('Gabriel S', 'gabriel@example.com'),
                                         ('Saulo', 'saulo@example.com')
  ON DUPLICATE KEY UPDATE nome = nome;
