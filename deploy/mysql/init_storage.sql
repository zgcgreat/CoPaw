CREATE DATABASE IF NOT EXISTS swe
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE swe;

CREATE TABLE IF NOT EXISTS chat_specs (
  tenant_id VARCHAR(64) NOT NULL,
  agent_id VARCHAR(128) NOT NULL,
  chat_id VARCHAR(191) NOT NULL,
  name VARCHAR(255) NOT NULL,
  session_id VARCHAR(191) NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  channel VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  meta JSON NOT NULL,
  status VARCHAR(64) NOT NULL,
  PRIMARY KEY (tenant_id, agent_id, chat_id),
  UNIQUE KEY uq_chat_specs_scope_session (
    tenant_id,
    agent_id,
    session_id,
    user_id,
    channel
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_runs (
  tenant_id VARCHAR(64) NOT NULL,
  agent_id VARCHAR(128) NOT NULL,
  run_id VARCHAR(191) NOT NULL,
  chat_id VARCHAR(191) NOT NULL,
  status VARCHAR(64) NOT NULL,
  session_id VARCHAR(191) NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  channel VARCHAR(64) NOT NULL,
  started_at DATETIME NOT NULL,
  finished_at DATETIME NULL,
  error TEXT NULL,
  PRIMARY KEY (tenant_id, agent_id, run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS session_checkpoints (
  tenant_id VARCHAR(64) NOT NULL,
  agent_id VARCHAR(128) NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  session_id VARCHAR(191) NOT NULL,
  version INT NOT NULL,
  blob_path TEXT NOT NULL,
  payload_sha256 VARCHAR(64) NOT NULL,
  PRIMARY KEY (tenant_id, agent_id, user_id, session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cron_job_definitions (
  tenant_id VARCHAR(191) NOT NULL,
  agent_id VARCHAR(191) NOT NULL,
  job_id VARCHAR(191) NOT NULL,
  definition_json LONGTEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, agent_id, job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cron_heartbeat_definitions (
  tenant_id VARCHAR(191) NOT NULL,
  agent_id VARCHAR(191) NOT NULL,
  definition_json LONGTEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, agent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
