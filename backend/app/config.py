from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str = Field(validation_alias="DATABASE_URL")
    fast_model: str = Field(validation_alias="MODEL_FAST")
    strong_model: str = Field(validation_alias="MODEL_STRONG")
    embed_model: str = Field(validation_alias="MODEL_EMBED")
    embed_dim: int = Field(validation_alias="EMBED_DIM")
    eval_max_usd: float = Field(validation_alias="EVAL_MAX_USD")
