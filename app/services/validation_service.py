from operator import eq as _eq, ne as _neq, gt as _gt, ge as _ge, lt as _lt, le as _le

from app.models.flight_plan import FlightPlan
from app.models.validation_criterion import CriterionOperator, CriterionResult, ValidationCriterion
from app.schemas.validation import ValidationCriterionResultItem, ValidationRunResponse

_OPERATOR_MAP = {
    CriterionOperator.EQ: _eq,
    CriterionOperator.NEQ: _neq,
    CriterionOperator.GT: _gt,
    CriterionOperator.GTE: _ge,
    CriterionOperator.LT: _lt,
    CriterionOperator.LTE: _le,
}

_RESULT_PRIORITY = {CriterionResult.REJECT: 3, CriterionResult.WARN: 2, CriterionResult.APPROVE: 1}


class ValidationService:
    @staticmethod
    def _field_value(plan: FlightPlan, field_path: str) -> str | int | bool | None:
        value = getattr(plan, field_path, None)
        if value is None:
            return None
        if hasattr(value, "value"):
            return value.value
        return value

    @staticmethod
    def _normalize_for_compare(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _evaluate_one(plan: FlightPlan, criterion: ValidationCriterion) -> ValidationCriterionResultItem:
        actual = ValidationService._field_value(plan, criterion.field_path)

        if criterion.operator == CriterionOperator.IS_PRESENT:
            passed = actual is not None and actual != ""
        elif criterion.operator == CriterionOperator.IS_ABSENT:
            passed = actual is None or actual == ""
        elif criterion.operator in {CriterionOperator.CONTAINS, CriterionOperator.NOT_CONTAINS}:
            actual_str = ValidationService._normalize_for_compare(actual) or ""
            expected_str = criterion.expected_value or ""
            passed = expected_str.upper() in actual_str.upper()
            if criterion.operator == CriterionOperator.NOT_CONTAINS:
                passed = not passed
        elif criterion.operator in _OPERATOR_MAP:
            actual_norm = ValidationService._normalize_for_compare(actual)
            expected_norm = criterion.expected_value

            try:
                actual_num = float(actual_norm) if actual_norm is not None else None
                expected_num = float(expected_norm) if expected_norm is not None else None
                if actual_num is not None and expected_num is not None:
                    passed = _OPERATOR_MAP[criterion.operator](actual_num, expected_num)
                else:
                    passed = _OPERATOR_MAP[criterion.operator](actual_norm or "", expected_norm or "")
            except (ValueError, TypeError):
                passed = _OPERATOR_MAP[criterion.operator](actual_norm or "", expected_norm or "")
        else:
            passed = False

        result_applied = criterion.result_on_pass if passed else criterion.result_on_fail
        message = criterion.pass_message if passed else criterion.fail_message

        return ValidationCriterionResultItem(
            criterion_id=criterion.id,
            criterion_name=criterion.name,
            field_path=criterion.field_path,
            operator=criterion.operator,
            expected_value=criterion.expected_value,
            actual_value=ValidationService._normalize_for_compare(actual),
            passed=passed,
            result_applied=result_applied,
            message=message,
        )

    @staticmethod
    def evaluate(
        plan: FlightPlan,
        criteria: list[ValidationCriterion],
    ) -> ValidationRunResponse:
        results = [ValidationService._evaluate_one(plan, c) for c in criteria]

        max_priority = max(_RESULT_PRIORITY[r.result_applied] for r in results) if results else 1
        overall = {v: k for k, v in _RESULT_PRIORITY.items()}[max_priority]

        return ValidationRunResponse(overall=overall, results=results)
