"""生产环境模型回退策略的配置级回归测试。

适配器只负责执行策略；策略本身由 `Settings.check_env` 决定。若这里失守，
适配器的 fail-closed 判断会全部失效，因此必须在配置层独立锁定。
"""

from backend.core.conf import Settings


def test_prod_environment_forces_local_model_fallback_off() -> None:
    values = Settings.check_env({'ENVIRONMENT': 'prod', 'RAG_ALLOW_LOCAL_MODEL_FALLBACK': True})

    assert values['RAG_ALLOW_LOCAL_MODEL_FALLBACK'] is False


def test_dev_environment_leaves_local_model_fallback_untouched() -> None:
    values = Settings.check_env({'ENVIRONMENT': 'dev', 'RAG_ALLOW_LOCAL_MODEL_FALLBACK': True})

    assert values['RAG_ALLOW_LOCAL_MODEL_FALLBACK'] is True


def test_dev_environment_can_opt_into_fail_closed() -> None:
    """生产主机沿用 dev 配置时，必须能显式关闭回退。"""
    values = Settings.check_env({'ENVIRONMENT': 'dev', 'RAG_ALLOW_LOCAL_MODEL_FALLBACK': False})

    assert values['RAG_ALLOW_LOCAL_MODEL_FALLBACK'] is False
