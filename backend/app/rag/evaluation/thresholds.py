"""版本化质量阈值的加载与确定性比较。"""

import json

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Comparator = Literal['min', 'max']


@dataclass(frozen=True)
class MetricThreshold:
    """单个质量或性能指标的发布约束。"""

    metric: str
    comparator: Comparator
    value: float


@dataclass(frozen=True)
class EvaluationThresholds:
    """与数据集和索引配置绑定的阈值集合。"""

    dataset_version: str
    index_profile_hash: str
    thresholds: list[MetricThreshold]


def load_thresholds(path: Path) -> EvaluationThresholds:
    """加载版本化阈值文件并校验最小契约。"""
    raw = json.loads(path.read_text(encoding='utf-8'))
    required = {'dataset_version', 'index_profile_hash', 'thresholds'}
    missing = required - raw.keys()
    if missing:
        raise ValueError(f'阈值文件缺少字段: {sorted(missing)}')
    thresholds = [
        MetricThreshold(metric=item['metric'], comparator=item['comparator'], value=float(item['value']))
        for item in raw['thresholds']
    ]
    if not thresholds:
        raise ValueError('阈值文件不能为空')
    if any(item.comparator not in {'min', 'max'} for item in thresholds):
        raise ValueError('阈值比较器只能是 min 或 max')
    return EvaluationThresholds(
        dataset_version=str(raw['dataset_version']),
        index_profile_hash=str(raw['index_profile_hash']),
        thresholds=thresholds,
    )


def assert_report_meets_thresholds(*, report: dict[str, float | int], thresholds: EvaluationThresholds) -> None:
    """不满足任一冻结阈值时拒绝产生发布基线。"""
    failures: list[str] = []
    for threshold in thresholds.thresholds:
        actual = report.get(threshold.metric)
        if actual is None:
            failures.append(f'{threshold.metric} 缺失')
            continue
        if threshold.comparator == 'min' and float(actual) < threshold.value:
            failures.append(f'{threshold.metric}={actual} 低于最小值 {threshold.value}')
        if threshold.comparator == 'max' and float(actual) > threshold.value:
            failures.append(f'{threshold.metric}={actual} 高于最大值 {threshold.value}')
    if failures:
        raise ValueError('质量阈值未通过: ' + '; '.join(failures))
