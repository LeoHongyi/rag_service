import httpx

from sqlalchemy.exc import SQLAlchemyError


def is_retryable_index_error(exc: Exception) -> bool:
    """判断索引异常是否属于可恢复故障。

    401 与 403 视为可恢复：它们几乎总是密钥过期、轮换或配额策略调整导致的
    环境问题，对所有文档同时生效且由运维修复，而不是某一份文档本身有问题。
    若判为永久失败，故障窗口内的每份文档都会落到 FAILED 并需要逐个手工重试。
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code in {401, 403, 408, 425, 429} or status_code >= 500
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, SQLAlchemyError)):
        return True
    return isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError)


def index_retry_countdown(*, retries: int, max_seconds: int) -> int:
    """计算从一秒开始且有上限的指数退避时间。"""
    if retries < 0:
        raise ValueError('重试次数不能小于 0')
    if max_seconds < 1:
        raise ValueError('重试退避上限必须大于 0')
    return min(2**retries, max_seconds)


def sanitize_index_error(exc: Exception) -> str:
    """生成不包含供应商响应体和请求内容的失败摘要。"""
    if isinstance(exc, httpx.HTTPStatusError):
        return f'模型服务请求失败（HTTP {exc.response.status_code}）'
    if isinstance(exc, httpx.TimeoutException):
        return '模型服务请求超时'
    if isinstance(exc, httpx.TransportError):
        return '模型服务连接失败'
    if isinstance(exc, FileNotFoundError):
        return '原始文档不存在'
    if isinstance(exc, ValueError):
        message = str(exc)
        safe_prefixes = (
            'PDF ',
            '不支持加密 PDF',
            '不支持的文件类型',
            '文档没有可索引正文',
            'Embedding 返回向量数量或维度不匹配',
        )
        return message[:512] if message.startswith(safe_prefixes) else '文档内容无法索引'
    if isinstance(exc, SQLAlchemyError):
        return '索引数据库操作失败'
    if isinstance(exc, OSError):
        return '对象存储访问失败'
    return f'文档索引失败（{type(exc).__name__}）'


def sanitize_dispatch_error(exc: Exception) -> str:
    """生成不含 Broker 连接串的 Outbox 投递失败摘要。

    Broker URL 内嵌凭据（`amqp://user:password@host`、`redis://:password@host`），
    而 kombu/redis 的连接异常文本常常直接包含该 URL。因此这里与文档索引路径
    采用同样的策略：只保留异常类别，绝不写入 `str(exc)`。
    """
    if isinstance(exc, (ConnectionError, OSError)):
        return '任务投递失败：消息中间件连接异常'
    if isinstance(exc, ValueError):
        return '任务投递失败：事件类型或载荷不受支持'
    return f'任务投递失败（{type(exc).__name__}）'
