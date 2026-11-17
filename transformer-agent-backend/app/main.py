from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# 导入步骤一编写的标书预处理路由
from app.api.v1.tender import router as tender_router

# 必须实例化名为 app 的 FastAPI 对象，Uvicorn 才能识别 app.main:app
app = FastAPI(
    title="变压器标书智能解析与组部件匹配系统 API",
    description="支持 PDF/Word/Excel 多源标书解析、BBox空间坐标锚定、LangGraph提取与混合RAG匹配",
    version="1.0.0"
)

# 配置 CORS 跨域中间件，允许本地 Vue 前端 (5173端口) 直接调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(tender_router)

@app.get("/", tags=["Health Check"])
async def root():
    return {
        "code": 200,
        "status": "online",
        "message": "Transformer Tender Agent Backend is running!"
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("正在启动后端服务...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)