CREATE TABLE IF NOT EXISTS custom_column_labels (
    id SERIAL PRIMARY KEY,
    column_name VARCHAR(100) NOT NULL UNIQUE,
    label TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_col_name ON custom_column_labels(column_name);
