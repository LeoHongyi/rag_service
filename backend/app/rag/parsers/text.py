from io import BytesIO

from docx import Document as DocxDocument
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from backend.core.conf import settings

SUPPORTED_DOCUMENT_SUFFIXES = frozenset({'txt', 'md', 'docx', 'pdf'})


def _parse_pdf(*, data: bytes) -> str:
    """提取文本型 PDF，拒绝加密、超限和无法提取正文的文件。"""
    if not data.lstrip().startswith(b'%PDF-'):
        raise ValueError('PDF 文件签名无效')
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('不支持加密 PDF')
        if len(reader.pages) > settings.RAG_PDF_MAX_PAGES:
            raise ValueError(f'PDF 页数不能超过 {settings.RAG_PDF_MAX_PAGES} 页')
        pages: list[str] = []
        text_count = 0
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text().strip()
            if not text:
                continue
            text_count += len(text)
            if text_count > settings.RAG_PDF_MAX_TEXT_CHARS:
                raise ValueError(f'PDF 正文不能超过 {settings.RAG_PDF_MAX_TEXT_CHARS} 个字符')
            pages.append(f'第 {page_number} 页\n{text}')
    except PdfReadError as exc:
        raise ValueError('PDF 文件损坏或格式无效') from exc
    if not pages:
        raise ValueError('PDF 未包含可提取文本，暂不支持扫描件或 OCR')
    return '\n\n'.join(pages)


def parse_document(*, filename: str, data: bytes) -> str:
    """解析支持的文本文件"""
    suffix = filename.rsplit('.', 1)[-1].lower()
    if suffix in {'txt', 'md'}:
        return data.decode('utf-8', errors='replace')
    if suffix == 'docx':
        document = DocxDocument(BytesIO(data))
        return '\n\n'.join(item.text for item in document.paragraphs if item.text.strip())
    if suffix == 'pdf':
        return _parse_pdf(data=data)
    raise ValueError('不支持的文件类型')
