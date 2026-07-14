from io import BytesIO

from docx import Document as DocxDocument


def parse_document(*, filename: str, data: bytes) -> str:
    """解析支持的文本文件"""
    suffix = filename.rsplit('.', 1)[-1].lower()
    if suffix in {'txt', 'md'}:
        return data.decode('utf-8', errors='replace')
    if suffix == 'docx':
        document = DocxDocument(BytesIO(data))
        return '\n\n'.join(item.text for item in document.paragraphs if item.text.strip())
    raise ValueError('不支持的文件类型')
