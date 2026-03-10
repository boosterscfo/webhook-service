from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Webhook
    WEBHOOK_TOKEN: str
    WEBHOOK_SECRET: str = ""

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
    SLACK_CHANNEL_ID_TEST: str = ""

    # Amazon Researcher
    BROWSE_AI_API_KEY: str = ""
    AMZ_GEMINI_API_KEY: str = ""
    AMZ_BOT_TOKEN: str = ""
    AMZ_SEARCH_ROBOT_ID: str = ""
    AMZ_DETAIL_ROBOT_ID: str = ""
    AMZ_ADMIN_SLACK_ID: str = ""

    # Bright Data
    BRIGHT_DATA_API_TOKEN: str = ""
    BRIGHT_DATA_DATASET_ID: str = "gd_l7q7dkf244hwjntr0"
    WEBHOOK_BASE_URL: str = ""  # e.g. https://hooks.example.com

    # Keyword Search
    AMZ_KEYWORD_CACHE_DAYS: int = 7

    # Report Serving
    REPORT_DIR: str = "data/reports"
    REPORT_TTL_DAYS: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
