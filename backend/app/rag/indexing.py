import httpx

from sqlalchemy.exc import SQLAlchemyError


def is_retryable_index_error(exc: Exception) -> bool:
    """判断索引异常是否属于可恢复故障。"""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 425, 429} or exc.response.status_code >= 500
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
