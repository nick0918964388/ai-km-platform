CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Seed default settings
INSERT INTO system_settings (key, value) VALUES
    ('site_name', 'AI 知識管理平台'),
    ('primary_color', '#0f62fe'),
    ('ollama_chat_url', 'http://ollama.webtw.xyz:11434/v1'),
    ('ollama_chat_api_key', 'ollama'),
    ('ollama_chat_model', 'qwen3.5:397b-cloud'),
    ('ollama_light_model', 'qwen3.5:397b-cloud'),
    ('intent_llm_url', 'http://ollama.webtw.xyz:11434/v1'),
    ('intent_llm_model', 'llama3.2:3b'),
    ('max_tokens', '4096')
ON CONFLICT (key) DO NOTHING;
