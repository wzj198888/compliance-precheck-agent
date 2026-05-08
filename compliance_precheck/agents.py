from __future__ import annotations

import re
from collections import Counter

from .models import (
    ExtractedFields,
    Material,
    PolicySnippet,
    RiskLevel,
    RuleFinding,
    TaskType,
    TokenEstimate,
)


class TaskIdentificationAgent:
    KEYWORDS = {
        TaskType.CONTRACT: ["合同", "付款比例", "违约", "验收条款", "甲方", "乙方"],
        TaskType.PROCUREMENT: ["采购", "供应商", "比价", "询价", "采购申请"],
        TaskType.REIMBURSEMENT: ["报销", "发票", "差旅", "费用", " reimburse"],
        TaskType.PROJECT: ["立项", "项目周期", "项目预算", "里程碑", "验收目标"],
    }

    def run(self, material: Material) -> TaskType:
        text = f"{material.title}\n{material.content}"
        scores = {
            task_type: sum(1 for keyword in keywords if keyword.lower() in text.lower())
            for task_type, keywords in self.KEYWORDS.items()
        }
        task_type, score = max(scores.items(), key=lambda item: item[1])
        return task_type if score > 0 else TaskType.UNKNOWN


class FieldExtractionAgent:
    AMOUNT_PATTERN = re.compile(r"(?:金额|预算|合同金额|报销金额|采购金额)[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*(万)?元")
    RATIO_PATTERN = re.compile(r"(?:付款比例|预付款比例|首付款比例)[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%")

    def run(self, material: Material) -> ExtractedFields:
        text = f"{material.title}\n{material.content}"
        amount = self._extract_amount(text)
        payment_ratio = self._extract_ratio(text)
        raw = {
            "title": material.title,
            "metadata": material.metadata,
        }
        return ExtractedFields(
            amount=amount,
            supplier=self._extract_after_label(text, ["供应商", "乙方", "收款单位"]),
            budget_subject=self._extract_after_label(text, ["预算科目", "费用科目"]),
            payment_ratio=payment_ratio,
            acceptance_terms=self._extract_after_label(text, ["验收条件", "验收条款"]),
            invoice_type=self._extract_after_label(text, ["发票类型", "票据类型"]),
            attachments=material.attachments,
            raw_fields=raw,
        )

    def _extract_amount(self, text: str) -> float | None:
        match = self.AMOUNT_PATTERN.search(text)
        if not match:
            return None
        value = float(match.group(1))
        if match.group(2) == "万":
            value *= 10000
        return value

    def _extract_ratio(self, text: str) -> float | None:
        match = self.RATIO_PATTERN.search(text)
        return float(match.group(1)) if match else None

    def _extract_after_label(self, text: str, labels: list[str]) -> str | None:
        for label in labels:
            pattern = re.compile(rf"{label}[:：]\s*([^\n，。；;]+)")
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return None


class PolicyRetrievalAgent:
    def __init__(self, snippets: list[PolicySnippet]) -> None:
        self.snippets = snippets

    def run(self, task_type: TaskType, fields: ExtractedFields, top_k: int = 5) -> list[PolicySnippet]:
        query_terms = [task_type.value]
        query_terms.extend(str(value) for value in fields.to_dict().values() if value)
        query = " ".join(query_terms)

        scored: list[tuple[int, PolicySnippet]] = []
        for snippet in self.snippets:
            score = 0
            if task_type in snippet.task_types:
                score += 5
            score += sum(1 for keyword in snippet.keywords if keyword in query or keyword in snippet.text)
            scored.append((score, snippet))

        return [snippet for score, snippet in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0][:top_k]


class RuleCheckingAgent:
    def run(self, task_type: TaskType, fields: ExtractedFields, policies: list[PolicySnippet]) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        policy_lookup = {policy.id: policy for policy in policies}

        if fields.amount is None:
            findings.append(
                RuleFinding(
                    severity=RiskLevel.HIGH,
                    issue="未识别到明确金额，无法判断审批权限和预算占用。",
                    policy_id=None,
                    suggestion="补充合同金额、采购金额、报销金额或项目预算。",
                )
            )
        elif fields.amount >= 50000 and task_type in {TaskType.PROCUREMENT, TaskType.CONTRACT}:
            findings.append(
                RuleFinding(
                    severity=RiskLevel.MEDIUM,
                    issue="金额达到 5 万元及以上，应检查是否满足比价、审批权限和合同审批要求。",
                    policy_id=self._find_policy(policy_lookup, "采购金额"),
                    suggestion="补充至少 3 家供应商比价材料或说明单一来源理由。",
                )
            )

        if task_type == TaskType.PROCUREMENT and not self._has_attachment(fields, ["比价", "询价", "报价"]):
            findings.append(
                RuleFinding(
                    severity=RiskLevel.HIGH,
                    issue="采购申请缺少比价或询价材料。",
                    policy_id=self._find_policy(policy_lookup, "比价"),
                    suggestion="上传比价表、供应商报价单或单一来源审批说明。",
                )
            )

        if task_type == TaskType.CONTRACT:
            if fields.payment_ratio is not None and fields.payment_ratio > 30:
                findings.append(
                    RuleFinding(
                        severity=RiskLevel.MEDIUM,
                        issue="预付款比例高于 30%，存在付款风险。",
                        policy_id=self._find_policy(policy_lookup, "付款比例"),
                        suggestion="降低预付款比例，或补充担保、阶段验收和付款条件说明。",
                    )
                )
            if not fields.acceptance_terms:
                findings.append(
                    RuleFinding(
                        severity=RiskLevel.HIGH,
                        issue="合同未识别到明确验收条件。",
                        policy_id=self._find_policy(policy_lookup, "验收"),
                        suggestion="补充验收标准、验收时间、验收责任人和不合格处理方式。",
                    )
                )

        if task_type == TaskType.REIMBURSEMENT:
            if not fields.invoice_type:
                findings.append(
                    RuleFinding(
                        severity=RiskLevel.MEDIUM,
                        issue="费用报销未识别到发票类型。",
                        policy_id=self._find_policy(policy_lookup, "发票"),
                        suggestion="补充增值税专用发票、普通发票或其他合规票据类型。",
                    )
                )
            if not self._has_attachment(fields, ["发票"]):
                findings.append(
                    RuleFinding(
                        severity=RiskLevel.HIGH,
                        issue="费用报销缺少发票附件。",
                        policy_id=self._find_policy(policy_lookup, "发票"),
                        suggestion="上传发票影像、费用明细和审批单据。",
                    )
                )

        if not fields.budget_subject:
            findings.append(
                RuleFinding(
                    severity=RiskLevel.MEDIUM,
                    issue="未识别到预算科目或费用科目。",
                    policy_id=self._find_policy(policy_lookup, "预算"),
                    suggestion="补充预算科目，便于财务核查预算占用和归口部门。",
                )
            )

        return findings

    def _has_attachment(self, fields: ExtractedFields, keywords: list[str]) -> bool:
        attachment_text = " ".join(fields.attachments)
        return any(keyword in attachment_text for keyword in keywords)

    def _find_policy(self, policies: dict[str, PolicySnippet], keyword: str) -> str | None:
        for policy in policies.values():
            if keyword in "".join(policy.keywords):
                return policy.id
        for policy in policies.values():
            if keyword in policy.text:
                return policy.id
        return None


class ReportGenerationAgent:
    def run(
        self,
        task_type: TaskType,
        fields: ExtractedFields,
        policies: list[PolicySnippet],
        findings: list[RuleFinding],
    ) -> tuple[str, RiskLevel, list[str], list[str], TokenEstimate]:
        if any(f.severity == RiskLevel.HIGH for f in findings):
            risk_level = RiskLevel.HIGH
            conclusion = "建议退回补充材料后再进入正式审批。"
        elif any(f.severity == RiskLevel.MEDIUM for f in findings):
            risk_level = RiskLevel.MEDIUM
            conclusion = "可进入审批，但建议先按风险提示补充说明或修改材料。"
        else:
            risk_level = RiskLevel.LOW
            conclusion = "未发现明显合规缺口，可进入后续审批。"

        missing_materials = self._missing_materials(findings)
        suggestions = [finding.suggestion for finding in findings]
        estimate = self._estimate_tokens(task_type)
        return conclusion, risk_level, missing_materials, suggestions, estimate

    def _missing_materials(self, findings: list[RuleFinding]) -> list[str]:
        counter = Counter()
        for finding in findings:
            text = finding.suggestion
            if "上传" in text or "补充" in text:
                counter[text] += 1
        return list(counter.keys())

    def _estimate_tokens(self, task_type: TaskType) -> TokenEstimate:
        ranges = {
            TaskType.REIMBURSEMENT: ("1600-2500", "2000-3300", "2800-5400", "3800-7700", "3200-6300", "13000-21000"),
            TaskType.PROCUREMENT: ("1600-2500", "3200-5000", "2800-5400", "3800-7700", "3200-6300", "16000-25000"),
            TaskType.CONTRACT: ("1600-2500", "6000-10500", "2800-5400", "3800-7700", "3200-6300", "20000-34000"),
            TaskType.PROJECT: ("1600-2500", "6000-10500", "2800-5400", "3800-7700", "3200-6300", "23000-37000"),
            TaskType.UNKNOWN: ("1600-2500", "2000-5000", "2800-5400", "3800-7700", "3200-6300", "13000-25000"),
        }
        values = ranges[task_type]
        return TokenEstimate(
            task_identification=values[0],
            field_extraction=values[1],
            policy_retrieval=values[2],
            rule_checking=values[3],
            report_generation=values[4],
            total=values[5],
        )
