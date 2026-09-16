from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "dev"
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite:///./luvre.db"
    MEDIA_DIR: str = "./media"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    ORDER_TTL_HOURS: int = 48

    PAYPAL_ENV: str = "sandbox"
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_WEBHOOK_ID: str = ""

    CRYPTO_PROVIDER: str = "coinbase"
    COINBASE_API_KEY: str = ""
    COINBASE_WEBHOOK_SECRET: str = ""
    BTPAY_URL: str = ""
    BTPAY_API_KEY: str = ""
    BTPAY_STORE_ID: str = ""
    BTPAY_WEBHOOK_SECRET: str = ""

    INTERAC_TRANSFER_EMAIL: str = ""

    JWT_EXPIRY_MINUTES: int = 60 * 12

    @field_validator("PUBLIC_BASE_URL", mode="before")
    @classmethod
    def _with_scheme(cls, v: str) -> str:
        v = str(v or "").strip()
        return v if "://" in v else f"https://{v}"


settings = Settings()
