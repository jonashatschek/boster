"""Print what the extractor finds in one or more annual report PDFs. Useful when tuning extraction.

Usage: python -m scripts.inspect_report path/to/report.pdf [...]
"""

import sys
from collections import defaultdict
from pathlib import Path

from app.documents.annual_report import extract_annual_report


def main(paths: list[str]) -> None:
    for path in paths:
        extraction = extract_annual_report(Path(path).read_bytes())
        print(f"\n######## {Path(path).name}")
        print(f"type={extraction.document_type} org={extraction.organisation_number} name={extraction.cooperative_name!r}")
        print(f"fiscal year={extraction.fiscal_year} period={extraction.fiscal_period_start}..{extraction.fiscal_period_end}")
        print(f"pages={extraction.page_count} text pages={extraction.text_page_count} land={extraction.land_tenure}")
        by_metric = defaultdict(list)
        for figure in extraction.figures:
            by_metric[(figure.method.value, figure.metric_key)].append(figure)
        for (method, metric), figures in sorted(by_metric.items()):
            values = ", ".join(f"{f.fiscal_year}: {f.value:,.1f}" for f in sorted(figures, key=lambda f: -f.fiscal_year))
            print(f"  [{method[:14]}] {metric:34} p{figures[0].page_number:<3} {values}   <- {figures[0].printed_label[:60]!r}")
        for warning in extraction.warnings:
            print(f"  WARNING: {warning}")
        topics = defaultdict(int)
        for finding in extraction.findings:
            topics[finding.topic] += 1
        print(f"  findings: {dict(topics)}")


if __name__ == "__main__":
    main(sys.argv[1:])
