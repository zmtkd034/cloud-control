"""FastAPI 앱: B단계 조회 API.

실행: uvicorn backend.main:app --host 127.0.0.1 --port 8001
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from backend import aws_service
from backend.aws_service import AwsServiceError
from backend.config import FRONTEND_DIR, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 설정을 검증한다. 누락 시 변수 이름만 담긴 ConfigError로 시작이 중단된다.
    get_settings()
    yield


app = FastAPI(title="Cloud Control", lifespan=lifespan)


def _run(fn):
    try:
        return fn(get_settings())
    except AwsServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


def _listing(items: list) -> dict:
    return {"items": items, "count": len(items)}


@app.get("/api/context")
def get_context():
    return _run(aws_service.get_context)


@app.get("/api/ec2")
def get_ec2():
    return _listing(_run(aws_service.list_ec2_instances))


@app.get("/api/s3")
def get_s3():
    return _listing(_run(aws_service.list_s3_buckets))


@app.get("/api/security-groups")
def get_security_groups():
    return _listing(_run(aws_service.list_security_groups))


# API 경로를 먼저 등록한 뒤 frontend 폴더만 정적 파일로 공개한다.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
