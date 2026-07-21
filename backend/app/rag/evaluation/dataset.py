import json

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvaluationCase:
    """一条可版本化的 RAG 离线评测样本。"""

    case_id: str
    question: str
    category: str
    knowledge_base_ids: list[int]
    relevant_chunk_ids: list[int]
    relevance: dict[int, int]
    expected_citation_chunk_ids: list[int]
    expected_abstain: bool
    review_status: str


def load_dataset(path: Path, *, require_approved: bool = False) -> list[EvaluationCase]:
    """加载 JSONL 数据集；生产基线可要求全部人工审批。"""
    cases: list[EvaluationCase] = []
    for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        required = {
            'case_id',
            'question',
            'category',
            'knowledge_base_ids',
            'relevant_chunk_ids',
            'expected_abstain',
            'review_status',
        }
        missing = required - raw.keys()
        if missing:
            raise ValueError(f'第 {line_number} 行缺少字段: {sorted(missing)}')
        if require_approved and raw['review_status'] != 'approved':
            raise ValueError(f'样本 {raw["case_id"]} 尚未人工审批')
        relevance = {int(key): int(value) for key, value in raw.get('relevance', {}).items()}
        cases.append(
            EvaluationCase(
                case_id=raw['case_id'],
                question=raw['question'],
                category=raw['category'],
                knowledge_base_ids=[int(item) for item in raw['knowledge_base_ids']],
                relevant_chunk_ids=[int(item) for item in raw['relevant_chunk_ids']],
                relevance=relevance,
                expected_citation_chunk_ids=[
                    int(item) for item in raw.get('expected_citation_chunk_ids', raw['relevant_chunk_ids'])
                ],
                expected_abstain=bool(raw['expected_abstain']),
                review_status=raw['review_status'],
            )
        )
    if not cases:
        raise ValueError('评测数据集不能为空')
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError('评测数据集存在重复 case_id')
    return cases
