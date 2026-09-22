from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

WEAK_SECRETS = {"", "change-me", "dev-secret-change-me", "secret", "changeme"}
DEV_ENVS = {"dev", "test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "CAN Backend"
    ENV: str = "dev"
    DATABASE_URL: str = "postgresql+psycopg://can:can@db:5432/can"

    # OIDC (Keycloak)
    OIDC_ISSUER: str = "http://keycloak:8080/realms/can"
    OIDC_AUDIENCE: str = "can-api"
    OIDC_JWKS_TTL_SECONDS: int = 3600

    # CAN-issued DID session JWT
    CAN_JWT_SECRET: str = "change-me"
    CAN_JWT_ALG: str = "HS256"
    CAN_DID_SESSION_TTL_SECONDS: int = 900

    # Mode: oidc | did | hybrid
    AUTH_MODE: str = "hybrid"

    # Secret mixed into hashed external identifiers (e.g. imported connections)
    EXTERNAL_ID_PEPPER: str = "change-me"

    # Directory holding contribution.yaml, reliability.yaml, care.yaml and scoring.yaml.
    # Repo layout: <repo>/ledgers. Docker: mounted at /ledgers.
    LEDGER_CONFIG_DIR: str = str(Path(__file__).resolve().parents[3] / "ledgers")


settings = Settings()


def validate_settings(s: Settings = settings) -> None:
    """Refuse to run outside dev/test with default or weak secrets."""
    if s.ENV.lower() in DEV_ENVS:
        return
    problems = []
    if s.CAN_JWT_SECRET in WEAK_SECRETS or len(s.CAN_JWT_SECRET) < 32:
        problems.append("CAN_JWT_SECRET must be a random value of at least 32 characters")
    if s.EXTERNAL_ID_PEPPER in WEAK_SECRETS or len(s.EXTERNAL_ID_PEPPER) < 32:
        problems.append("EXTERNAL_ID_PEPPER must be a random value of at least 32 characters")
    if s.CAN_JWT_ALG not in {"HS256", "HS384", "HS512"}:
        problems.append("CAN_JWT_ALG must be an HMAC algorithm (HS256/HS384/HS512)")
    if problems:
        raise RuntimeError("Insecure configuration: " + "; ".join(problems))
