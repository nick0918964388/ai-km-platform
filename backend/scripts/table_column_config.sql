CREATE TABLE IF NOT EXISTS table_column_config (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    column_name VARCHAR(100) NOT NULL,
    display_order INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(table_name, column_name)
);
CREATE INDEX IF NOT EXISTS idx_tcc_table ON table_column_config(table_name);
