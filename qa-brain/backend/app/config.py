from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    github_token: str = ""
    figma_access_token: str = ""
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8
    environment: str = "development"
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
