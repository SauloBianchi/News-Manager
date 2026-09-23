-- Migração para quem já rodou a versão intermediária deste projeto que
-- usava 2FA por TOTP/QR Code (colunas totp_secret e totp_ativo) e agora
-- quer passar para a verificação em duas etapas por código enviado por
-- e-mail.
--
-- Se o seu banco NUNCA teve as colunas totp_secret/totp_ativo, ignore
-- este arquivo — ele não se aplica ao seu caso.
--
-- Uso:
--   mysql -u root -p newsmanager < sql/migration_totp_para_email.sql

USE newsmanager;

ALTER TABLE usuarios CHANGE COLUMN totp_ativo dois_fatores_ativo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN codigo_verificacao VARCHAR(255) NULL AFTER dois_fatores_ativo;
ALTER TABLE usuarios ADD COLUMN codigo_expira_em DATETIME NULL AFTER codigo_verificacao;
ALTER TABLE usuarios DROP COLUMN totp_secret;

-- Como o segredo TOTP não serve mais para nada (o método mudou para
-- e-mail), quem tinha o 2FA antigo ativado precisa reconfigurar pela aba
-- "Segurança" da janela principal — o código antigo simplesmente não é
-- mais válido, então isso já é feito automaticamente na prática (o campo
-- fica ativado, mas o próximo login vai gerar e enviar um código novo por
-- e-mail normalmente).
