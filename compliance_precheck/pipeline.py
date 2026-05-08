from __future__ import annotations

import json
from pathlib import Path

from .agents import (
    FieldExtractionAgent,
    PolicyRetrievalAgent,
    ReportGenerationAgent,
    RuleCheckingAgent,
    TaskIdentificationAgent,
)
from .models import Material, PolicySnippet, PrecheckReport


class CompliancePrecheckPipeline:
    def __init__(self, policies: list[PolicySnippet]) -> None:
        self.task_agent = TaskIdentificationAgent()
        self.field_agent = FieldExtractionAgent()
        self.policy_agent = PolicyRetrievalAgent(policies)
        self.rule_agent = RuleCheckingAgent()
        self.report_agent = ReportGenerationAgent()

    @classmethod
    def from_policy_file(cls, path: Path) -> "CompliancePrecheckPipeline":
        data = json.loads(path.read_text(encoding="utf-8"))
        policies = [PolicySnippet.from_dict(item) for item in data["policies"]]
        return cls(policies)

    def run_file(self, path: Path) -> PrecheckReport:
        material = Material.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return self.run(material)

    def run(self, material: Material) -> PrecheckReport:
        task_type = self.task_agent.run(material)
        fields = self.field_agent.run(material)
        policies = self.policy_agent.run(task_type, fields)
        findings = self.rule_agent.run(task_type, fields, policies)
        conclusion, risk_level, missing_materials, suggestions, token_estimate = self.report_agent.run(
            task_type=task_type,
            fields=fields,
            policies=policies,
            findings=findings,
        )

        return PrecheckReport(
            conclusion=conclusion,
            risk_level=risk_level,
            task_type=task_type,
            key_fields=fields,
            policy_basis=policies,
            findings=findings,
            missing_materials=missing_materials,
            suggestions=suggestions,
            token_estimate=token_estimate,
        )
