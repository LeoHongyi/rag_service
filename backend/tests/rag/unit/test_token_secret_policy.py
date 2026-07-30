"""生产环境 TOKEN_SECRET_KEY 防误配的配置级回归测试。

`.env.example` 中的示例密钥已经随仓库公开；一旦被直接复制到生产 `.env`，
JWT 即可被伪造。`Settings.check_env` 必须在 ENVIRONMENT=prod 时拒绝启动，
而不是让服务带着可预测的签名密钥正常运行。

注意：本文件刻意不出现任何已泄露的密钥明文，只使用其 SHA-256 摘要，
以免密钥扫描器把回归测试本身判定为一次新的泄露。
"""

import hashlib

import pytest

from backend.core.conf import _INSECURE_TOKEN_SECRET_KEY_DIGESTS, Settings

# 历史上随 backend/.env.example 提交的真实可用密钥的摘要
_LEAKED_HISTORICAL_KEY_DIGEST = 'a8ed8bd0486cef6e19c1f5ca484060bf9e79e440480651b79742ce7a10fc3b65'
# 当前 backend/.env.example 中的占位符；它本身不是密钥，可安全写出明文
_CURRENT_PLACEHOLDER = 'REPLACE_WITH_YOUR_OWN_SECRET_KEY_DO_NOT_USE_THIS_VALUE'


def test_historical_leaked_key_is_still_blocklisted() -> None:
    """旧克隆可能仍缓存着历史密钥，其摘要必须留在黑名单中。"""
    assert _LEAKED_HISTORICAL_KEY_DIGEST in _INSECURE_TOKEN_SECRET_KEY_DIGESTS


def test_current_placeholder_is_blocklisted() -> None:
    digest = hashlib.sha256(_CURRENT_PLACEHOLDER.encode()).hexdigest()

    assert digest in _INSECURE_TOKEN_SECRET_KEY_DIGESTS


def test_prod_rejects_the_example_token_secret_key() -> None:
    with pytest.raises(ValueError, match='TOKEN_SECRET_KEY'):
        Settings.check_env({'ENVIRONMENT': 'prod', 'TOKEN_SECRET_KEY': _CURRENT_PLACEHOLDER})


def test_prod_accepts_a_real_secret_key() -> None:
    values = Settings.check_env({
        'ENVIRONMENT': 'prod',
        'TOKEN_SECRET_KEY': 'a-genuinely-random-operator-generated-value',
    })

    assert values['TOKEN_SECRET_KEY'] == 'a-genuinely-random-operator-generated-value'


def test_prod_tolerates_a_missing_token_secret_key() -> None:
    """缺失时应交由 pydantic 的必填校验报错，本检查不得先抛出误导性的异常。"""
    values = Settings.check_env({'ENVIRONMENT': 'prod'})

    assert 'TOKEN_SECRET_KEY' not in values


def test_dev_environment_allows_the_example_token_secret_key() -> None:
    """本地开发允许直接使用示例密钥，不能阻断既有的 `cp .env.example .env` 流程。"""
    values = Settings.check_env({'ENVIRONMENT': 'dev', 'TOKEN_SECRET_KEY': _CURRENT_PLACEHOLDER})

    assert values['TOKEN_SECRET_KEY'] == _CURRENT_PLACEHOLDER
