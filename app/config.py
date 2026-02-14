from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Webhook
    WEBHOOK_TOKEN: str

    # CFO DB
    CFO_HOST: str
    CFO_PORT: int = 3306
    CFO_USER: str
    CFO_PASSWORD: str
    CFO_DATABASE: str

    # BOOSTA DB
    BOOSTA_HOST: str
    BOOSTA_PORT: int = 3306
    BOOSTA_USER: str
    BOOSTA_PASSWORD: str
    BOOSTA_DATABASE: str

    # BOOSTAERP DB
    BOOSTAERP_HOST: str
    BOOSTAERP_PORT: int = 3306
    BOOSTAERP_USER: str
    BOOSTAERP_PASSWORD: str
    BOOSTAERP_DATABASE: str

    # BOOSTAADMIN DB
    BOOSTAADMIN_HOST: str
    BOOSTAADMIN_PORT: int = 3306
    BOOSTAADMIN_USER: str
    BOOSTAADMIN_PASSWORD: str
    BOOSTAADMIN_DATABASE: str

    # BOOSTAAPI DB
    BOOSTAAPI_HOST: str
    BOOSTAAPI_PORT: int = 3306
    BOOSTAAPI_USER: str
    BOOSTAAPI_PASSWORD: str
    BOOSTAAPI_DATABASE: str

    # SCM DB
    SCM_HOST: str
    SCM_PORT: int = 3306
    SCM_USER: str
    SCM_PASSWORD: str
    SCM_DATABASE: str

    # MART DB
    MART_HOST: str
    MART_PORT: int = 3306
    MART_USER: str
    MART_PASSWORD: str
    MART_DATABASE: str

    # Google
    GOOGLE_KEY_PATH: str = "/google_keys/google_boosters_finance_key.json"

    # Slack
    BOOSTA_BOT_TOKEN: str
    META_BOT_TOKEN: str

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
