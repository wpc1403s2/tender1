from pydantic_settings import BaseSettings, SettingsConfigDict
import os
import dotenv
from langchain_openai import ChatOpenAI
dotenv.load_dotenv()

class Settings(BaseSettings):
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://admin:adminpassword@localhost:5432/transformer_db"
    )
    EMBEDDING_MODEL_NAME: str = os.getenv(
        "EMBEDDING_MODEL_NAME",
        "BAAI/bge-small-zh-v1.5"
    )
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "512"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

if __name__ == '__main__':
    llm = ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,  # 请替换为你的真实 Key
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.7,
    )

    # 发送测试消息
    response = llm.invoke("你好，请简单介绍一下你自己。")
    print(response.content)