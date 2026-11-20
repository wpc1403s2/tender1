from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import String, Integer, Text, DateTime, JSON, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from loguru import logger

from app.core.config import settings


class Base(DeclarativeBase):
    pass


class ComponentLibraryModel(Base):
    """内部组部件标准品知识库 ORM 模型 (支持 PostgreSQL + pgvector)"""
    __tablename__ = "component_library"

    comp_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="组件唯一ID")
    component_category: Mapped[str] = mapped_column(String(128), index=True, comment="组部件大类编码")
    category_label: Mapped[str] = mapped_column(String(128), default="", comment="组部件大类中文名称")
    manufacturer: Mapped[str] = mapped_column(String(128), index=True, comment="供应商/制造商品牌")
    model_series: Mapped[str] = mapped_column(String(128), index=True, comment="具体产品型号/系列")
    key_metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, comment="硬规则过滤关键数值指标")
    specs_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, comment="完整结构化技术参数字典")
    summary_text: Mapped[str] = mapped_column(Text, default="", comment="用于向量化检索的综合描述文本")
    catalog_file_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="来源样册PDF文件名")
    catalog_page: Mapped[int] = mapped_column(Integer, default=1, comment="样册所在页码")
    catalog_bbox: Mapped[Optional[List[float]]] = mapped_column(JSON, nullable=True, comment="样册原文BBox坐标 [x0,y0,x1,y1]")
    catalog_original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="样册原文摘录")
    embedding_json: Mapped[Optional[List[float]]] = mapped_column(JSON, nullable=True, comment="Embedding向量数组(兼容pgvector与JSON检索)")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DatabaseSessionManager:
    """PostgreSQL (pgvector) 数据库会话管理，当数据库未启动时自动标记以便平滑降级至本地文件存储"""
    _engine = None
    _session_factory = None
    _pg_available: Optional[bool] = None
    _pgvector_enabled: bool = False

    @classmethod
    def init_db(cls) -> bool:
        if cls._pg_available is not None:
            return cls._pg_available

        db_url = settings.DATABASE_URL
        # 规范化连接串：解析 DATABASE_URL，若缺少用户名密码则回填 admin/adminpassword
        # (兼容 asyncpg 驱动前缀，统一转为同步 psycopg2 驱动)
        try:
            from sqlalchemy.engine import make_url
            url_obj = make_url(db_url)

            sync_url = URL.create(
                drivername="postgresql+psycopg2",
                username=url_obj.username or "admin",
                password=url_obj.password or "adminpassword",
                host=url_obj.host or "localhost",
                port=url_obj.port or 5432,
                database=url_obj.database or "transformer_db",
            )
            logger.info(f"PostgreSQL 同步连接目标: {sync_url.host}:{sync_url.port}/{sync_url.database} (用户: {sync_url.username})")
        except Exception as parse_err:
            # 兜底：直接字符串替换 asyncpg 前缀
            logger.warning(f"DATABASE_URL 解析异常 ({parse_err})，使用字符串替换方式降级处理")
            sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

        try:
            cls._engine = create_engine(
                sync_url,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 3}
            )
            with cls._engine.begin() as conn:
                try:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    cls._pgvector_enabled = True
                except Exception as ext_err:
                    logger.warning(f"pgvector 扩展启用提示: {ext_err}")

            Base.metadata.create_all(cls._engine)

            if cls._pgvector_enabled:
                with cls._engine.begin() as conn:
                    conn.execute(text(
                        f"ALTER TABLE component_library ADD COLUMN IF NOT EXISTS embedding vector({settings.EMBEDDING_DIM})"
                    ))

            cls._session_factory = sessionmaker(bind=cls._engine, expire_on_commit=False)
            cls._pg_available = True
            logger.info(f"PostgreSQL 组部件库连接成功 (pgvector={cls._pgvector_enabled})")
        except Exception as e:
            cls._pg_available = False
            logger.warning(f"PostgreSQL 暂不可达 ({e})，组部件库将自动使用本地持久化存储 (data/library/components.json)")

        return cls._pg_available

    @classmethod
    def get_session(cls):
        if not cls.init_db() or cls._session_factory is None:
            return None
        return cls._session_factory()

    @classmethod
    def get_engine(cls):
        cls.init_db()
        return cls._engine

    @classmethod
    def is_pgvector_enabled(cls) -> bool:
        cls.init_db()
        return cls._pgvector_enabled
