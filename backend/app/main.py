import logging

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="울산컬처 API",
    version="0.1.0",
    description="울산 문화행사 발견 서비스의 Phase 1 API",
)
app.include_router(api_router)

