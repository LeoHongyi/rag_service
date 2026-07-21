from backend.app.rag.service.index_profile_service import build_index_profile_payload


def test_index_profile_contains_reproducibility_contract() -> None:
    payload = build_index_profile_payload()
    assert {
        'parser_name',
        'chunker_name',
        'embedding_model',
        'embedding_dimensions',
        'tokenizer_version',
    } <= payload.keys()
