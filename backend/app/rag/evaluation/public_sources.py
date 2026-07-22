import json
import re

from html.parser import HTMLParser

_PAGE_STATE_PREFIX = 'window.__ICE_PAGE_PROPS__='
_NOISE_MARKERS = ('window.pageStartTime', '__ICE_PAGE_PROPS__', '"@context"', '<script')
_BLOCK_TAGS = frozenset({'article', 'blockquote', 'div', 'main', 'p', 'section'})


class _StructuredTextParser(HTMLParser):
    """将受信正文 HTML 转换为保留章节边界的确定性文本。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.table_cell_index = 0
        self.list_item_depth = 0
        self.table_cell_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in _BLOCK_TAGS and not (tag == 'p' and (self.list_item_depth or self.table_cell_depth)):
            self.parts.append('\n\n')
        elif tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            self.parts.append(f'\n\n{"#" * int(tag[1])} ')
        elif tag == 'li':
            self.parts.append('\n- ')
            self.list_item_depth += 1
        elif tag == 'br':
            self.parts.append('\n')
        elif tag == 'tr':
            self.parts.append('\n')
            self.table_cell_index = 0
        elif tag in {'td', 'th'}:
            if self.table_cell_index:
                self.parts.append(' | ')
            self.table_cell_index += 1
            self.table_cell_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == 'li':
            self.list_item_depth = max(0, self.list_item_depth - 1)
        elif tag in {'td', 'th'}:
            self.table_cell_depth = max(0, self.table_cell_depth - 1)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _normalize_text(text: str) -> str:
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.replace('\r', '').splitlines()]
    normalized: list[str] = []
    for line in lines:
        if line:
            normalized.append(line)
        elif normalized and normalized[-1]:
            normalized.append('')
    return '\n'.join(normalized).strip()


def extract_aliyun_document(page_html: str, *, min_chars: int = 200) -> str:
    """从阿里云帮助页面的服务端状态中提取唯一正文。"""
    start = page_html.find(_PAGE_STATE_PREFIX)
    if start < 0:
        raise ValueError('公开资料页面缺少可解析的正文状态')
    payload_start = start + len(_PAGE_STATE_PREFIX)
    try:
        state, _end = json.JSONDecoder().raw_decode(page_html[payload_start:])
        data = state['docDetailData']['storeData']['data']
        title = str(data['docTitle']).strip()
        content_html = str(data['content']).strip()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError('公开资料页面正文结构无效') from exc
    if not title or not content_html:
        raise ValueError('公开资料页面正文为空')

    parser = _StructuredTextParser()
    parser.feed(content_html)
    body = _normalize_text(''.join(parser.parts))
    if len(body) < min_chars:
        raise ValueError('公开资料页面正文过短')
    text = _normalize_text(f'# {title}\n\n{body}')
    if any(marker in text for marker in _NOISE_MARKERS):
        raise ValueError('公开资料页面正文仍包含脚本或元数据噪声')
    return text
