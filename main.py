import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.database import engine, Base, SessionLocal
from app.models import User, RetentionPolicy
from app.auth import get_password_hash
from app.routers import auth, users, policies, files, extensions, audit_logs
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                full_name="系统管理员",
                email="admin@example.com",
                role="admin",
                is_active=True,
                must_change_password=True
            )
            db.add(admin)

        manager = db.query(User).filter(User.username == "manager").first()
        if not manager:
            manager = User(
                username="manager",
                hashed_password=get_password_hash("manager123"),
                full_name="部门经理",
                email="manager@example.com",
                role="manager",
                is_active=True,
                must_change_password=True
            )
            db.add(manager)

        operator = db.query(User).filter(User.username == "operator").first()
        if not operator:
            operator = User(
                username="operator",
                hashed_password=get_password_hash("operator123"),
                full_name="普通操作员",
                email="operator@example.com",
                role="operator",
                is_active=True,
                must_change_password=True
            )
            db.add(operator)

        default_policies = [
            {
                "business_category": "财务文件",
                "description": "财务相关凭证、报表等文件，保留7年",
                "retention_days": 2555,
                "action_on_expiry": "archive"
            },
            {
                "business_category": "合同文件",
                "description": "各类合同文件，保留10年",
                "retention_days": 3650,
                "action_on_expiry": "archive"
            },
            {
                "business_category": "人事档案",
                "description": "员工人事档案，保留至离职后3年",
                "retention_days": 1095,
                "action_on_expiry": "archive"
            },
            {
                "business_category": "临时文档",
                "description": "临时文件，保留30天",
                "retention_days": 30,
                "action_on_expiry": "delete"
            },
            {
                "business_category": "项目文档",
                "description": "项目相关文档，保留5年",
                "retention_days": 1825,
                "action_on_expiry": "archive"
            }
        ]

        for p in default_policies:
            existing = db.query(RetentionPolicy).filter(
                RetentionPolicy.business_category == p["business_category"]
            ).first()
            if not existing:
                policy = RetentionPolicy(
                    **p,
                    created_by=1
                )
                db.add(policy)

        db.commit()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="文件保留策略API",
    description="文件保留策略管理系统API，支持按业务类别设置保留期限、到期自动归档/删除、人工延期审批、操作日志记录等功能",
    version="1.1.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = FastAPI(
    title="文件保留策略API - v1",
    version="1.1.0"
)
api_router.state.limiter = limiter
api_router.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(policies.router)
api_router.include_router(files.router)
api_router.include_router(extensions.router)
api_router.include_router(audit_logs.router)

app.mount("/api/v1", api_router)


@app.get("/")
def root():
    return {
        "name": "文件保留策略API",
        "version": "1.1.0",
        "docs": "/docs",
        "api_prefix": "/api/v1",
        "rate_limit": "60 requests/minute per IP"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
