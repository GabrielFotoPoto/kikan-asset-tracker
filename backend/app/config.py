from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Kikan"
    # Surchargee par la variable d'environnement DATABASE_URL en conteneur.
    database_url: str = "postgresql+psycopg2://kikan:kikan@db:5432/kikan"


settings = Settings()
