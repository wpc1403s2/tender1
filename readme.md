transformer-agent-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用程序入口
│   ├── api/                     # API 路由层 (Controllers)
│   │   ├── dependencies.py      # 依赖注入 (如数据库会话、权限校验)
│   │   ├── v1/                  # API 版本1
│   │   │   ├── tender.py        # 标书上传与解析任务API
│   │   │   ├── component.py     # 组部件库增删改查API
│   │   │   └── export.py        # Excel导出API
│   ├── core/                    # 核心配置
│   │   ├── config.py            # 环境变量与应用配置 (Pydantic Settings)
│   │   ├── exceptions.py        # 全局异常处理
│   │   └── security.py          # 认证与安全
│   ├── models/                  # 关系型数据库模型 (SQLAlchemy ORM)
│   │   ├── project.py           # 项目与标书文档表
│   │   └── library.py           # 标准组部件库表
│   ├── schemas/                 # 数据校验与序列化 (Pydantic Models)
│   │   ├── tender_schema.py     # 标书提取数据的 JSON Schema 定义
│   │   └── api_response.py      # 标准 API 返回格式
│   ├── services/                # 核心业务逻辑层 (Services)
│   │   ├── parser_service.py    # 文档解析服务 (PyMuPDF, PaddleOCR)
│   │   ├── vector_store.py      # 向量数据库服务 (Milvus 连接与查询)
│   │   └── excel_service.py     # openpyxl 填表与导出服务
│   ├── agents/                  # LLM 与智能体编排层 (LangGraph)
│   │   ├── graph.py             # 多 Agent 工作流定义 (State Graph)
│   │   ├── nodes.py             # 商务Agent, 主参Agent, 匹配Agent 的具体执行逻辑
│   │   ├── prompts.py           # 系统与用户的 Prompt 模板管理
│   │   └── state.py             # Agent 运行时的上下文状态定义 (TypedDict)
│   ├── worker/                  # 异步任务处理 (Celery)
│   │   ├── celery_app.py        # Celery 实例配置
│   │   └── tasks.py             # 耗时的标书解析与向量化后台任务
│   └── utils/                   # 工具类
│       └── logger.py            # Loguru 日志配置
├── alembic/                     # 数据库迁移工具目录
│   └── versions/                # 迁移脚本
├── data/                        # 本地临时数据或样例文件存放
├── tests/                       # 单元测试与集成测试
│   ├── test_api/
│   └── test_agents/
├── alembic.ini                  # Alembic 配置文件
├── requirements.txt             # Python 依赖清单
├── .env                         # 环境变量配置文件 (数据库密码、API Key等)
└── docker-compose.yml           # 容器化部署编排 (Postgres, Redis, Milvus, Backend)


transformer-agent-frontend/
├── public/
│   └── favicon.ico
├── src/
│   ├── main.ts                  # Vue 应用入口，挂载实例
│   ├── App.vue                  # 根组件
│   ├── api/                     # 封装 Axios 请求
│   │   ├── request.ts           # Axios 拦截器与基础配置
│   │   ├── tender.ts            # 标书相关接口
│   │   └── library.ts           # 组部件库相关接口
│   ├── assets/                  # 静态资源
│   │   ├── styles/              # 全局 CSS/SCSS (如 element-plus 覆盖)
│   │   └── images/              # 图标与占位图
│   ├── components/              # 页面复用组件库
│   │   ├── pdf/                 
│   │   │   ├── PdfViewer.vue    # 基于 PDF.js 的预览组件 (核心)
│   │   │   └── HighlightBox.vue # 用于渲染 BBox 的高亮蒙层组件
│   │   ├── common/
│   │   │   ├── FileUpload.vue   # 拖拽上传组件
│   │   │   └── StatusBadge.vue  # 解析状态标签
│   │   └── forms/
│   │       └── JsonEditor.vue   # JSON 树状展示与编辑组件
│   ├── views/                   # 核心页面视图
│   │   ├── Dashboard/           
│   │   │   └── index.vue        # 首页/项目列表看板
│   │   ├── TenderAnalysis/      
│   │   │   ├── Upload.vue       # 标书上传与任务创建页面
│   │   │   └── Review.vue       # 【核心页面】左右分屏审阅工作台 (左侧PDF溯源，右侧提取结果)
│   │   └── ComponentLibrary/    
│   │       └── index.vue        # 内部组部件标准品管理与向量化状态页面
│   ├── store/                   # 状态管理 (Pinia)
│   │   ├── tenderStore.ts       # 存储当前解析标书的状态与 BBox 坐标数据
│   │   └── userStore.ts         # 用户登录状态
│   ├── router/                  # 路由配置 (Vue Router)
│   │   └── index.ts             # 路由表定义
│   ├── types/                   # TypeScript 类型声明接口
│   │   ├── tender.d.ts          # 对应后端 Schema 的 TS Interface
│   │   └── component.d.ts       
│   └── utils/                   # 前端工具类
│       ├── bboxUtils.ts         # PDF 坐标转换工具 (后端坐标映射到前端屏幕坐标)
│       └── format.ts            # 日期、文本格式化工具
├── .env                         # 前端环境变量 (VITE_API_BASE_URL 等)
├── index.html                   # Vite 挂载模板
├── package.json                 # Node 依赖与脚本
├── tsconfig.json                # TypeScript 编译配置
└── vite.config.ts               # Vite 打包与代理配置