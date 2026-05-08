from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import CompliancePrecheckPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a compliance precheck workflow.")
    parser.add_argument("case_file", type=Path, help="Path to a JSON approval material file.")
    parser.add_argument("--policy", type=Path, default=Path("policies/company_policy.json"))
    args = parser.parse_args()

    pipeline = CompliancePrecheckPipeline.from_policy_file(args.policy)
    report = pipeline.run_file(args.case_file)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
