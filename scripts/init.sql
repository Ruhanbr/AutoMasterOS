-- Script de inicialização do banco de dados AutoMaster
-- Executado automaticamente pelo docker-entrypoint

-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- para buscas text eficientes
CREATE EXTENSION IF NOT EXISTS "unaccent";  -- para buscas sem acentos

-- Configuração de locale para PT-BR
SET lc_messages = 'pt_BR.UTF-8';
