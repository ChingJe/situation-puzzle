from functools import lru_cache
from pathlib import Path
import tomllib

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT_DIR / "config.toml"


class LlmConfig(BaseSettings):
    request_timeout_seconds: int = 120
    request_max_retries: int = 2
    structured_output_max_retries: int = 2
    generation_temperature: float = 0.8
    answer_temperature: float = 0.1
    judge_temperature: float = 0.1


class PuzzleConfig(BaseSettings):
    surface_story_max_chars: int = 150
    truth_min_chars: int = 300
    truth_max_chars: int = 800
    key_facts_min: int = 4
    key_facts_max: int = 8
    language: str = "zh-TW"
    content_style: str = "懸疑、適合一般玩家、避免露骨血腥描寫"


class PuzzleGenerationConfig(BaseSettings):
    reviewer_enabled: bool = True
    deterministic_gate_enabled: bool = True
    max_revision_rounds: int = 2
    strict_surface_story_max_chars: int = 120
    strict_truth_min_chars: int = 160
    strict_truth_max_chars: int = 280


class StorageConfig(BaseSettings):
    data_dir: str = "data"
    games_dir: str = "data/games"


class ApiConfig(BaseSettings):
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class LoggingConfig(BaseSettings):
    level: str = "INFO"
    format: str = "json"
    log_dir: str = "logs"
    file_enabled: bool = True
    console_enabled: bool = True
    max_file_mb: int = 10
    backup_count: int = 5
    log_prompt_preview: bool = False
    prompt_preview_chars: int = 160
    log_llm_output_preview: bool = False
    llm_output_preview_chars: int = 160
    raw_message_mode: str = "full"
    raw_message_log_file: str = "logs/messages.log"
    raw_message_max_chars: int = 20000
    raw_message_include_player_messages: bool = True
    raw_message_include_llm_prompts: bool = True
    raw_message_include_llm_responses: bool = True
    raw_message_include_parsed_outputs: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"
    log_level: str | None = None
    llm: LlmConfig = Field(default_factory=LlmConfig)
    puzzle: PuzzleConfig = Field(default_factory=PuzzleConfig)
    puzzle_generation: PuzzleGenerationConfig = Field(
        default_factory=PuzzleGenerationConfig
    )
    storage: StorageConfig = Field(default_factory=StorageConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @property
    def effective_log_level(self) -> str:
        return self.log_level or self.logging.level


def _load_config_file() -> dict[str, object]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as config_file:
        return tomllib.load(config_file)


@lru_cache
def get_settings() -> Settings:
    config = _load_config_file()
    return Settings(**config)
