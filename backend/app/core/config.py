from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "CAN Backend"
    ENV: str = "dev"
    DATABASE_URL: str = "postgresql+psycopg://can:can@db:5432/can"

    # OIDC (Keycloak)
    OIDC_ISSUER: str = "http://keycloak:8080/realms/can"
    OIDC_AUDIENCE: str = "can-api"

    # CAN-issued DID session JWT
    CAN_JWT_SECRET: str = "change-me"
    CAN_JWT_ALG: str = "HS256"
    CAN_DID_SESSION_TTL_SECONDS: int = 900

    # Mode: oidc | did | hybrid
    AUTH_MODE: str = "hybrid"

settings = Settings()
