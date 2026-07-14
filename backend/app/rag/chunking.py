import re


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
            chunks.extend(paragraph[index:index + chunk_size] for index in range(0, len(paragraph), step))
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
