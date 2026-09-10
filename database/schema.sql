-- Script de criação do banco de dados NewsManager
-- Sistema de Gerenciamento e Análise de Notícias

CREATE DATABASE IF NOT EXISTS newsmanager
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE newsmanager;

CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario VARCHAR(50) NOT NULL UNIQUE,
    senha VARCHAR(100) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
INSERT INTO usuarios (usuario, senha) VALUES ('admin', 'admin123')
  ON DUPLICATE KEY UPDATE usuario = usuario;

INSERT INTO categorias (nome) VALUES ('Política'), ('Esportes'), ('Tecnologia'), ('Economia')
  ON DUPLICATE KEY UPDATE nome = nome;

INSERT INTO autores (nome, email) VALUES ('Ernesto', 'ernesto@example.com'),
                                         ('Gabriel S', 'gabriel@example.com'),
                                         ('Saulo', 'saulo@example.com');
