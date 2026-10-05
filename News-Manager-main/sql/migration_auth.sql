-- Migração da tabela `usuarios` da versão bem antiga (usuario + senha em
-- texto puro) direto para a versão atual: cadastro completo, hash bcrypt,
-- login com Google e verificação em duas etapas por código enviado por
-- e-mail.
--
-- Se você já rodou uma versão intermediária deste projeto que usava 2FA
-- por TOTP/QR Code (colunas totp_secret/totp_ativo), use em vez deste o
-- arquivo `sql/migration_totp_para_email.sql`.
--
-- Rode este script UMA VEZ, apenas se o banco já foi criado com o
-- schema bem antigo. Se o banco ainda não existe, ignore este arquivo e
-- rode direto o sql/schema.sql atual.
--
-- Uso:
--   mysql -u root -p newsmanager < sql/migration_auth.sql

USE newsmanager;

ALTER TABLE usuarios ADD COLUMN nome VARCHAR(150) NOT NULL DEFAULT '' AFTER id;
ALTER TABLE usuarios ADD COLUMN email VARCHAR(150) NULL AFTER usuario;
ALTER TABLE usuarios ADD COLUMN senha_hash VARCHAR(255) NULL AFTER senha;
ALTER TABLE usuarios ADD COLUMN google_id VARCHAR(255) NULL;
ALTER TABLE usuarios ADD COLUMN dois_fatores_ativo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN codigo_verificacao VARCHAR(255) NULL;
ALTER TABLE usuarios ADD COLUMN codigo_expira_em DATETIME NULL;
ALTER TABLE usuarios ADD COLUMN ultimo_login TIMESTAMP NULL;

-- E-mail e google_id precisam ser únicos, mas só depois que todo mundo
-- tiver um e-mail preenchido (senão a constraint falha com múltiplos NULL
-- tratados de forma inconsistente entre versões do MySQL). Preencha os
-- e-mails que faltarem antes de rodar as duas linhas abaixo, por exemplo:
--   UPDATE usuarios SET email = CONCAT(usuario, '@exemplo.com') WHERE email IS NULL;
ALTER TABLE usuarios ADD UNIQUE KEY uk_usuarios_email (email);
ALTER TABLE usuarios ADD UNIQUE KEY uk_usuarios_google_id (google_id);

-- IMPORTANTE sobre a senha antiga:
-- A coluna `senha` antiga guardava texto puro e o novo login usa apenas
-- `senha_hash` (bcrypt), gerado em Python. Não há como converter uma senha
-- em texto puro para hash bcrypt dentro do próprio MySQL. O caminho mais
-- simples para um projeto de faculdade é recriar os usuários de teste pela
-- tela "Criar conta" do aplicativo depois de rodar esta migração.
--
-- Depois de recriar os usuários, se quiser, remova a coluna antiga:
-- ALTER TABLE usuarios DROP COLUMN senha;
