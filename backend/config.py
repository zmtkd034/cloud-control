"""앱 런타임 설정.

서버 코드가 실행될 때만 프로젝트 루트의 .env를 읽는다.
오류 메시지에는 변수 이름만 넣고 값은 절대 출력하지 않는다.
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# backend/config.py 기준 프로젝트 루트
ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"
FRONTEND_DIR = ROOT_DIR / "frontend"

REQUIRED_VARS = ("AWS_PROFILE", "AWS_REGION", "EXPECTED_ACCOUNT_ID")
ALLOWED_REGION = "ap-northeast-2"


class ConfigError(RuntimeError):
    """설정 누락·형식 오류. 메시지에 설정값을 포함하지 않는다."""


@dataclass(frozen=True)
class Settings:
    aws_profile: str
    aws_region: str
    expected_account_id: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(ENV_FILE)

    values = {name: os.getenv(name, "").strip() for name in REQUIRED_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(
            f"필수 설정이 없습니다: {', '.join(missing)} "
            f"(프로젝트 루트 .env를 .env.example 형식으로 작성하세요)"
        )

    if values["AWS_REGION"] != ALLOWED_REGION:
        raise ConfigError(f"AWS_REGION은 {ALLOWED_REGION}만 허용합니다.")

    if not re.fullmatch(r"\d{12}", values["EXPECTED_ACCOUNT_ID"]):
        raise ConfigError("EXPECTED_ACCOUNT_ID는 12자리 숫자여야 합니다.")

    return Settings(
        aws_profile=values["AWS_PROFILE"],
        aws_region=values["AWS_REGION"],
        expected_account_id=values["EXPECTED_ACCOUNT_ID"],
    )
