from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    CONTRACT = "合同初审"
    PROCUREMENT = "采购申请"
    REIMBURSEMENT = "费用报销"
    PROJECT = "项目立项"
    UNKNOWN = "未知类型"


class RiskLevel(str, Enum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"


@dataclass
class Material:
    title: str
    content: str
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Material":
        return cls(
            title=data["title"],
            content=data["content"],
            attachments=list(data.get("attachments", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ExtractedFields:
    amount: float | None = None
    supplier: str | None = None
    budget_subject: str | None = None
    payment_ratio: float | None = None
    acceptance_terms: str | None = None
    invoice_type: str | None = None
    attachments: list[str] = field(default_factory=list)
    raw_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PolicySnippet:
    id: str
    title: str
    task_types: list[TaskType]
    keywords: list[str]
    text: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicySnippet":
        return cls(
            id=data["id"],
            title=data["title"],
            task_types=[TaskType(item) for item in data["task_types"]],
            keywords=list(data["keywords"]),
            text=data["text"],
        )


@dataclass
class RuleFinding:
    severity: RiskLevel
    issue: str
    suggestion: str
    policy_id: str | None = None


@dataclass
class TokenEstimate:
    task_identification: str
    field_extraction: str
    policy_retrieval: str
    rule_checking: str
    report_generation: str
    total: str


@dataclass
class PrecheckReport:
    conclusion: str
    risk_level: RiskLevel
    task_type: TaskType
    key_fields: ExtractedFields
    policy_basis: list[PolicySnippet]
    findings: list[RuleFinding]
    missing_materials: list[str]
    suggestions: list[str]
    token_estimate: TokenEstimate

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if hasattr(value, "__dataclass_fields__"):
                return {key: convert(item) for key, item in asdict(value).items()}
            if isinstance(value, list):
                return [convert(item) for item in value]
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            return value

        return convert(self)
