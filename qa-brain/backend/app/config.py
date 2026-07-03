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
    mock_mode: bool = False
    # Independent of mock_mode: AutomationQAAgent's two Qwen-routed tools
    # (generate_script_from_spec, explore_and_generate) check this instead, so Claude
    # (no real key yet) can stay mocked via mock_mode while Qwen (has a real key) runs
    # for real, or vice versa — a single global flag can't represent that combination.
    mock_qwen: bool = False
    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    qwen_api_key: str = ""
    qwen_model: str = "qwen3.7-max"

    class Config:
        env_file = ".env"


settings = Settings()
