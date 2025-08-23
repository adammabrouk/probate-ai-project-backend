import os
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    POSTGRES_PASSWORD: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    DB_URL: str = "duckdb:///probate_ops/data/duckdb.db"
    BLOB_DIR: str = "./_blobs"

settings = Settings()
