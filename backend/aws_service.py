"""Boto3 조회 함수와 AWS 오류 분류.

모든 함수는 동기 함수이며 FastAPI의 일반 def 경로 함수에서 호출한다.
실패를 빈 목록으로 바꾸지 않고 AwsServiceError로 올린다.
"""

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionError as BotoConnectionError,
    CredentialRetrievalError,
    HTTPClientError,
    LoginError,
    NoCredentialsError,
    PartialCredentialsError,
    ProfileNotFound,
    RefreshWithMFAUnsupportedError,
    SSOError,
    TokenRetrievalError,
)

from backend.config import Settings

BOTO_CONFIG = Config(
    connect_timeout=3,
    read_timeout=10,
    retries={"max_attempts": 2, "mode": "standard"},
)

ACCESS_DENIED_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "UnauthorizedOperation",
    "AuthorizationError",
    "AllAccessDisabled",
}
LOGIN_REQUIRED_CODES = {
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "RequestExpired",
    "TokenRefreshRequired",
    "AuthFailure",
}
LOGIN_ERRORS = (
    NoCredentialsError,
    PartialCredentialsError,
    ProfileNotFound,
    CredentialRetrievalError,
    TokenRetrievalError,
    RefreshWithMFAUnsupportedError,
    LoginError,
    SSOError,
)
CONNECTION_ERRORS = (BotoConnectionError, HTTPClientError)

LOGIN_MESSAGE = "AWS 로그인이 만료되었거나 갱신할 수 없습니다. WSL에서 aws login --profile <프로필>을 다시 실행하세요."


class AwsServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _translate(exc: Exception) -> AwsServiceError:
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ACCESS_DENIED_CODES:
            return AwsServiceError(403, "AWS_ACCESS_DENIED", "이 작업에 필요한 AWS 권한이 없습니다.")
        if code in LOGIN_REQUIRED_CODES:
            return AwsServiceError(503, "AWS_LOGIN_REQUIRED", LOGIN_MESSAGE)
        return AwsServiceError(502, "AWS_REQUEST_FAILED", f"AWS 요청이 실패했습니다. (오류 코드: {code or '알 수 없음'})")
    if isinstance(exc, LOGIN_ERRORS):
        return AwsServiceError(503, "AWS_LOGIN_REQUIRED", LOGIN_MESSAGE)
    if isinstance(exc, CONNECTION_ERRORS):
        return AwsServiceError(503, "AWS_CONNECTION_ERROR", "AWS와 통신하지 못했습니다. 네트워크 상태를 확인한 뒤 다시 시도하세요.")
    return AwsServiceError(502, "AWS_REQUEST_FAILED", "AWS 요청 처리 중 알 수 없는 오류가 발생했습니다.")


def _call(fn):
    try:
        return fn()
    except (ClientError, BotoCoreError) as exc:
        raise _translate(exc) from exc


def _session(settings: Settings) -> boto3.Session:
    return _call(lambda: boto3.Session(
        profile_name=settings.aws_profile,
        region_name=settings.aws_region,
    ))


def _verified_session(settings: Settings) -> tuple[boto3.Session, dict]:
    """STS로 현재 계정을 확인하고, 기대 계정이 아니면 403으로 차단한다."""
    session = _session(settings)
    identity = _call(lambda: session.client("sts", config=BOTO_CONFIG).get_caller_identity())
    if identity["Account"] != settings.expected_account_id:
        raise AwsServiceError(
            403,
            "AWS_ACCOUNT_MISMATCH",
            "로그인한 AWS 계정이 EXPECTED_ACCOUNT_ID와 다릅니다. 프로필과 .env 설정을 확인하세요.",
        )
    return session, identity


def get_context(settings: Settings) -> dict:
    _, identity = _verified_session(settings)
    return {
        "account_id": identity["Account"],
        "caller_arn": identity["Arn"],
        "region": settings.aws_region,
    }


def list_ec2_instances(settings: Settings) -> list[dict]:
    session, _ = _verified_session(settings)

    def fetch():
        ec2 = session.client("ec2", config=BOTO_CONFIG)
        items = []
        for page in ec2.get_paginator("describe_instances").paginate():
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                    items.append({
                        "instance_id": inst["InstanceId"],
                        "name": tags.get("Name") or inst["InstanceId"],
                        "state": inst.get("State", {}).get("Name"),
                        "instance_type": inst.get("InstanceType"),
                        "private_ip": inst.get("PrivateIpAddress"),
                        "public_ip": inst.get("PublicIpAddress"),
                    })
        return items

    return _call(fetch)


def list_s3_buckets(settings: Settings) -> list[dict]:
    session, _ = _verified_session(settings)

    def fetch():
        s3 = session.client("s3", config=BOTO_CONFIG)
        items = []
        for page in s3.get_paginator("list_buckets").paginate():
            items.extend({"name": b["Name"]} for b in page.get("Buckets", []))
        return items

    return _call(fetch)


def list_security_groups(settings: Settings) -> list[dict]:
    session, _ = _verified_session(settings)

    def fetch():
        ec2 = session.client("ec2", config=BOTO_CONFIG)
        items = []
        for page in ec2.get_paginator("describe_security_groups").paginate():
            for sg in page.get("SecurityGroups", []):
                items.append({
                    "GroupId": sg["GroupId"],
                    "GroupName": sg.get("GroupName"),
                    "IpPermissions": sg.get("IpPermissions", []),
                })
        return items

    return _call(fetch)
