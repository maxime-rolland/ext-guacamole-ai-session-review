-- Migration 001 — Tables pour l'extension ext-guacamole-ai-session-review.
--
-- Cohabitent dans la base `guacamoledb` à côté des tables `guacamole_*`
-- de l'auth-jdbc Guacamole.
--
-- Pivot : history_uuid = nom du dossier dans /var/lib/guacamole/recordings/.
-- Pas de FK vers guacamole_connection_history (pas de colonne UUID côté
-- Guacamole en 1.6 — la dérivation history_id → UUID dossier n'est pas
-- triviale, à enrichir dans une migration ultérieure).

CREATE TABLE IF NOT EXISTS session_ai_summary (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    history_uuid    CHAR(36)     NOT NULL UNIQUE,
    username        VARCHAR(255) DEFAULT NULL,
    connection_name VARCHAR(255) DEFAULT NULL,
    started_at      DATETIME     DEFAULT NULL,
    ended_at        DATETIME     DEFAULT NULL,
    status          VARCHAR(50)  NOT NULL,   -- analyzing | done | failed
    summary         TEXT,
    risk_level      VARCHAR(20),
    error           TEXT,                    -- renseigné si status = 'failed'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status     (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS suspicious_event (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    history_uuid        CHAR(36)    NOT NULL,
    event_time_seconds  INT         DEFAULT NULL,
    severity            VARCHAR(20) DEFAULT NULL,
    category            VARCHAR(100) DEFAULT NULL,
    description         TEXT,
    evidence            TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_history_uuid (history_uuid),
    CONSTRAINT fk_suspicious_event_summary
        FOREIGN KEY (history_uuid)
        REFERENCES session_ai_summary (history_uuid)
        ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
