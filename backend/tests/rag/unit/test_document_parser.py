from io import BytesIO

import pytest

from pypdf import PdfWriter

from backend.app.rag.parsers import text


def test_pdf_parser_returns_page_delimited_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class Page:
        def extract_text(self) -> str:
            return 'PDF 正文'

    class Reader:
        is_encrypted = False
        pages = [Page()]

    monkeypatch.setattr(text, 'PdfReader', lambda _stream: Reader())

    assert text.parse_document(filename='简历.pdf', data=b'%PDF-1.7') == '第 1 页\nPDF 正文'


def test_pdf_parser_rejects_encrypted_file() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt('secret')
    data = BytesIO()
    writer.write(data)

    with pytest.raises(ValueError, match='不支持加密 PDF'):
        text.parse_document(filename='encrypted.pdf', data=data.getvalue())


def test_pdf_parser_rejects_textless_pdf() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    data = BytesIO()
    writer.write(data)

    with pytest.raises(ValueError, match='未包含可提取文本'):
        text.parse_document(filename='blank.pdf', data=data.getvalue())


def test_pdf_is_an_allowed_document_suffix() -> None:
    assert 'pdf' in text.SUPPORTED_DOCUMENT_SUFFIXES


def test_pdf_parser_rejects_invalid_signature() -> None:
    with pytest.raises(ValueError, match='文件签名无效'):
        text.parse_document(filename='invalid.pdf', data=b'not a PDF')
