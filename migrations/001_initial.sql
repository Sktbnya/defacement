-- Создание основных таблиц

-- Таблица настроек
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание индексов
CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key);

-- Вставка базовых настроек
INSERT OR IGNORE INTO settings (key, value) VALUES
('app.title', 'WDM V12'),
('app.version', '12.0.0'),
('app.language', 'ru'),
('app.theme', 'system'),
('database.backup_on_start', 'true'),
('database.backup_on_exit', 'true'),
('database.auto_vacuum', 'true'),
('monitoring.enabled', 'true'),
('monitoring.check_interval', '3600'),
('monitoring.parallel_checks', '5'),
('monitoring.retry_count', '3'),
('monitoring.retry_delay', '60'),
('logging.level', 'INFO'),
('logging.max_file_size', '10485760'),
('logging.max_files', '5'),
('logging.log_to_console', 'true');

-- Создание схемы валидации настроек
INSERT OR IGNORE INTO settings (key, value) VALUES ('validation_schema', '{
    "app.title": {
        "type": "str",
        "min_length": 1,
        "max_length": 100
    },
    "app.version": {
        "type": "str",
        "pattern": "^\\d+\\.\\d+\\.\\d+$"
    },
    "app.language": {
        "type": "str",
        "pattern": "^[a-z]{2}$"
    },
    "monitoring.check_interval": {
        "type": "int",
        "min": 60,
        "max": 86400
    },
    "monitoring.parallel_checks": {
        "type": "int",
        "min": 1,
        "max": 20
    },
    "logging.max_file_size": {
        "type": "int",
        "min": 1048576,
        "max": 104857600
    }
}'); 