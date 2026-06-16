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


class StorageConfig(BaseSettings):
    data_dir: str = "data"
    games_dir: str = "data/games"


class ApiConfig(BaseSettings):
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:12b"
    llm: LlmConfig = Field(default_factory=LlmConfig)
    puzzle: PuzzleConfig = Field(default_factory=PuzzleConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)


def _load_config_file() -> dict[str, object]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as config_file:
        return tomllib.load(config_file)


@lru_cache
def get_settings() -> Settings:
    config = _load_config_file()
    return Settings(**config)

