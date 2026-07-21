import argparse

from pathlib import Path

from backend.app.rag.evaluation.runner import evaluate_files, write_report
from backend.app.rag.evaluation.thresholds import assert_report_meets_thresholds, load_thresholds


def main() -> None:
    """运行 RAG 离线评测。"""
    parser = argparse.ArgumentParser(description='运行 RAG 离线评测')
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-approved', action='store_true')
    parser.add_argument('--thresholds', type=Path, help='版本化质量阈值 JSON 文件')
    args = parser.parse_args()
    report = evaluate_files(
        dataset_path=args.dataset, results_path=args.results, require_approved=args.require_approved
    )
    if args.thresholds:
        assert_report_meets_thresholds(report=report, thresholds=load_thresholds(args.thresholds))
    write_report(report=report, output_path=args.output)


if __name__ == '__main__':
    main()
