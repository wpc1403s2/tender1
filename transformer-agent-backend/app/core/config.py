from pydantic_settings import BaseSettings, SettingsConfigDict
import os
import dotenv
from langchain_openai import ChatOpenAI
dotenv.load_dotenv()

class Settings(BaseSettings):
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL")

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