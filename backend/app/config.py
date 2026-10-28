from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://askdb_app:askdb_app@db:5432/askdb"
    llm_provider: str = "openai"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-haiku-latest"
    max_rows: int = 100
    statement_timeout_ms: int = 5000
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
