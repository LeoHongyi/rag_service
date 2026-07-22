import re

from dataclasses import dataclass


def clean_text(text: str) -> str:
    """清理不可见控制字符和多余空白"""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return re.sub(r'\n{3,}', '\n\n', text.replace('\r\n', '\n').replace('\r', '\n')).strip()


def split_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    """按段落优先切分文本"""
    content = clean_text(text)
    if not content:
        return []
    paragraphs = [item.strip() for item in re.split(r'\n{2,}', content) if item.strip()]
    chunks: list[str] = []
    current = ''
    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ''
            step = max(chunk_size - overlap, 1)
            chunks.extend(paragraph[index : index + chunk_size] for index in range(0, len(paragraph), step))
            continue
        candidate = f'{current}\n\n{paragraph}'.strip()
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current)
            current = f'{current[-overlap:]}\n\n{paragraph}'.strip() if overlap else paragraph
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]


def contextualize_chunk(*, filename: str, heading_path: list[str], content: str) -> str:
    """使用确定性元数据构造检索上下文"""
    heading = ' > '.join(heading_path) if heading_path else '未分节'
    return f'文件：{filename}\n章节：{heading}\n\n{content}'


@dataclass(frozen=True)
class ParentChildChunks:
    """一个父章节及其可召回子切片。"""

    heading_path: list[str]
    parent_content: str
    children: list[str]


def split_parent_child_text(*, text: str, chunk_size: int, overlap: int) -> list[ParentChildChunks]:
    """按 Markdown 标题或 PDF 页标记划分父节，再生成用于召回的小切片。"""
    content = clean_text(text)
    if not content:
        return []
    sections: list[tuple[list[str], list[str]]] = []
    heading_path: list[str] = []
    section_lines: list[str] = []
    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$')
    page_pattern = re.compile(r'^第\s*(\d+)\s*页$')
    for line in content.splitlines():
        heading_match = heading_pattern.match(line)
        page_match = page_pattern.match(line)
        if heading_match or page_match:
            if section_lines:
                sections.append((heading_path.copy(), section_lines))
            section_lines = [line]
            if page_match:
                heading_path = [f'第 {page_match.group(1)} 页']
            else:
                assert heading_match is not None
                level = len(heading_match.group(1))
                heading_path = [*heading_path[: level - 1], heading_match.group(2).strip()]
        else:
            section_lines.append(line)
    if section_lines:
        sections.append((heading_path.copy(), section_lines))
    return [
        ParentChildChunks(path, parent, split_text(parent, chunk_size=chunk_size, overlap=overlap))
        for path, lines in sections
        if (parent := clean_text('\n'.join(lines)))
    ]
