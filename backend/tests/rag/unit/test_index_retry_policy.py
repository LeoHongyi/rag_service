import httpx

from backend.app.rag.indexing import index_retry_countdown, is_retryable_index_error, sanitize_index_error


def _http_status_error(status_code: int, *, body: str = 'sensitive response body') -> httpx.HTTPStatusError:
    request = httpx.Request('POST', 'https://model.example/v1/embeddings?api_key=secret')
    response = httpx.Response(status_code, request=request, text=body)
    return httpx.HTTPStatusError('provider request failed', request=request, response=response)


def test_index_error_classification_distinguishes_temporary_and_permanent_failures() -> None:
    assert is_retryable_index_error(httpx.ReadTimeout('timeout'))
    assert is_retryable_index_error(httpx.ConnectError('connection failed'))
    assert is_retryable_index_error(_http_status_error(429))
    assert is_retryable_index_error(_http_status_error(503))
    assert not is_retryable_index_error(_http_status_error(400))
    assert not is_retryable_index_error(FileNotFoundError('missing object'))
    assert not is_retryable_index_error(ValueError('PDF 文件损坏'))


def test_index_retry_countdown_is_exponential_and_capped() -> None:
    assert [index_retry_countdown(retries=value, max_seconds=10) for value in range(6)] == [1, 2, 4, 8, 10, 10]


def test_index_error_summary_does_not_expose_provider_response_or_url() -> None:
    error = _http_status_error(400, body='document text and secret-token')

    summary = sanitize_index_error(error)

    assert summary == '模型服务请求失败（HTTP 400）'
    assert 'document text' not in summary
    assert 'secret-token' not in summary
    assert 'model.example' not in summary


def test_unknown_value_error_does_not_expose_original_input() -> None:
    summary = sanitize_index_error(ValueError('private document body: secret-token'))

    assert summary == '文档内容无法索引'
    assert 'secret-token' not in summary
