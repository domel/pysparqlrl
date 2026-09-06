"""W3C section 4.2: sequential variable-flow validation."""

from sparql_rl.errors import WellFormednessError
from sparql_rl.model import (
    AssignmentElement,
    NegationElement,
    RuleElement,
    RuleSet,
    TriplePatternElement,
    Variable,
    variables,
)


def validate_body(
    body: tuple[RuleElement, ...], defined: set[Variable]
) -> set[Variable]:
    defined = defined.copy()
    for element in body:
        if isinstance(element, TriplePatternElement):
            defined.update(variables(element.pattern))
        elif isinstance(element, NegationElement):
            validate_body(element.body, defined)
        else:
            missing = variables(element.expression) - defined
            if missing:
                raise WellFormednessError(
                    "variables used before definition: "
                    + ", ".join(sorted(v.value for v in missing))
                )
            if isinstance(element, AssignmentElement):
                if element.variable in defined:
                    raise WellFormednessError(
                        f"SET overwrites ?{element.variable.value}"
                    )
                defined.add(element.variable)
    return defined


def validate_rules(rule_set: RuleSet) -> None:
    for index, rule in enumerate(rule_set.rules):
        try:
            defined = validate_body(rule.body, set())
            if variables(rule.head) - defined:
                raise WellFormednessError(
                    "head contains variables not defined by the body"
                )
        except WellFormednessError as error:
            raise WellFormednessError(
                f"{rule.source or '<rules>'}: rule {rule.identifier or index + 1}: {error}"
            ) from error
