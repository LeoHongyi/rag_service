from backend.app.rag.chunking import clean_text, contextualize_chunk, split_text


def test_split_text_preserves_nonempty_content() -> None:
    chunks = split_text('甲' * 80 + '\n\n' + '乙' * 80, chunk_size=100, overlap=20)
    assert len(chunks) == 2
    assert chunks[0].startswith('甲')


def test_clean_text_removes_controls() -> None:
    assert clean_text('甲\x00\n\n\n乙') == '甲\n\n乙'


def test_contextualize_chunk_has_source_metadata() -> None:
    assert '文件：手册.md' in contextualize_chunk(filename='手册.md', heading_path=['安装'], content='正文')
