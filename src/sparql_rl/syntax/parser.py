"""SPARQL-RL recursive descent grammar and ordered abstract syntax."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from sparql_rl.model import (
    AssignmentElement,
    Expression,
    FilterElement,
    NegationElement,
    Rule,
    RuleElement,
    RuleSet,
    TriplePatternElement,
    Variable,
)
from sparql_rl.rdf.parser import (
    IRI,
    Node,
    Triple,
    TurtleParser,
    is_keyword_ci_with_extra_boundary,
    skip_ws_comments,
)

BUILTINS = {
    "STR",
    "LANG",
    "LANGMATCHES",
    "LANGDIR",
    "DATATYPE",
    "IRI",
    "URI",
    "STRLANG",
    "STRLANGDIR",
    "STRDT",
    "BNODE",
    "UUID",
    "STRUUID",
    "ABS",
    "CEIL",
    "FLOOR",
    "ROUND",
    "CONCAT",
    "SUBSTR",
    "STRLEN",
    "REPLACE",
    "UCASE",
    "LCASE",
    "ENCODE_FOR_URI",
    "CONTAINS",
    "STRSTARTS",
    "STRENDS",
    "STRBEFORE",
    "STRAFTER",
    "REGEX",
    "YEAR",
    "MONTH",
    "DAY",
    "HOURS",
    "MINUTES",
    "SECONDS",
    "TIMEZONE",
    "TZ",
    "NOW",
    "IF",
    "SAMETERM",
    "ISIRI",
    "ISURI",
    "ISBLANK",
    "ISLITERAL",
    "ISNUMERIC",
    "HASLANG",
    "HASLANGDIR",
    "ISTRIPLE",
    "TRIPLE",
    "SUBJECT",
    "PREDICATE",
    "OBJECT",
}


@dataclass(frozen=True)
class Path(IRI):
    steps: tuple[tuple[IRI, bool], ...] = ()


class RuleParser(TurtleParser):
    def __init__(self, text: str, source: str = "<rules>", base_iri: str | None = None):
        super().__init__(text, source, base_iri)
        self.document_iri = base_iri
        self.context = "data"
        self.counter = 0
        if any(0xD800 <= ord(c) <= 0xDFFF for c in text):
            self.scanner.error("Unicode surrogate is not permitted")

    def ws(self) -> None:
        skip_ws_comments(self.scanner)

    def keyword(self, word: str) -> bool:
        self.ws()
        if not is_keyword_ci_with_extra_boundary(self.scanner, word, "{}()<>?\"'"):
            return False
        for _ in word:
            self.scanner.advance()
        self.ws()
        return True

    def expect(self, token: str) -> None:
        self.ws()
        self.scanner.expect(token)
        self.ws()

    def fresh(self) -> Variable:
        self.counter += 1
        return Variable(f"@path{self.counter}")

    def parse_iri_ref_turtle(self) -> str:
        iri = super().parse_iri_ref_turtle()
        if not urlsplit(iri).scheme:
            self.scanner.error("relative IRI requires a base IRI")
        return iri

    def parse_iri(self) -> IRI:
        if self.scanner.peek() in ("?", "$"):
            if self.context == "data":
                self.scanner.error("variables are not allowed in DATA")
            self.scanner.advance()
            match = re.match(
                r"(?:[^\W\d]|\d)[\w\u00b7\u0300-\u036f\u203f-\u2040]*",
                self.scanner.text[self.scanner.i :],
            )
            if match is None:
                self.scanner.error("expected variable name")
            name = match.group()
            for _ in name:
                self.scanner.advance()
            return Variable(name)
        return super().parse_iri()

    def parse_subject(self) -> Node:
        return self.parse_object()

    def can_start_iri_or_blanknode(self) -> bool:
        return self.scanner.peek() in ("?", "$") or super().can_start_iri_or_blanknode()

    def can_start_verb(self) -> bool:
        return self.scanner.peek() in ("?", "$", "^", "(") or super().can_start_verb()

    def parse_pairs_structure(self, terminators: tuple[str, ...], allow_a_verb: bool):
        return super().parse_pairs_structure(terminators + ("}",), allow_a_verb)

    def parse_verb(self, allow_a: bool) -> IRI:
        # W3C [29]-[33]: finite inverse and sequence paths.
        if self.context not in ("body", "negation"):
            return super().parse_verb(allow_a)
        steps: list[tuple[IRI, bool]] = []
        while True:
            self.ws()
            reverse = self.scanner.consume("^")
            self.ws()
            if self.scanner.consume("("):
                nested = self.parse_verb(allow_a)
                self.expect(")")
                part = (
                    list(nested.steps)
                    if isinstance(nested, Path)
                    else [(nested, False)]
                )
            else:
                part = [(super().parse_verb(allow_a), False)]
            if reverse:
                part = [(p, not inv) for p, inv in reversed(part)]
            steps.extend(part)
            self.ws()
            if not self.scanner.consume("/"):
                break
        if len(steps) == 1 and not steps[0][1]:
            return steps[0][0]
        return Path("@path", tuple(steps))

    def emit(self, subject: Node, predicate: IRI, obj: Node) -> None:
        if not isinstance(predicate, Path):
            super().emit(subject, predicate, obj)
            return
        current = subject
        for index, (p, inverse) in enumerate(predicate.steps):
            end = obj if index == len(predicate.steps) - 1 else self.fresh()
            if inverse:
                super().emit(end, p, current)
            else:
                super().emit(current, p, end)
            current = end

    def document(self) -> RuleSet:
        # W3C [1] RuleSet, [2]-[10] prologue, [11] Rule.
        rules = []
        data: list[Triple] = []
        imports = []
        self.ws()
        while not self.scanner.eof():
            if self.scanner.peek() == "@":
                self.scanner.error("Turtle directives are not rule-set directives")
            if self.keyword("VERSION"):
                if self.parse_version_specifier() != "1.2":
                    self.scanner.error("unsupported VERSION")
            elif self.parse_directive_if_present():
                pass
            elif self.keyword("IMPORTS"):
                imports.append(self.parse_iri().value)
            elif self.keyword("DATA"):
                elements = self.block("data")
                data.extend(
                    e.pattern for e in elements if isinstance(e, TriplePatternElement)
                )
            elif self.keyword("RULE"):
                self.context = "head"
                identifier = None if self.scanner.peek() == "{" else self.parse_iri()
                head = self.block("head")
                if not self.keyword("WHERE"):
                    self.scanner.error("expected WHERE")
                data_only = self.keyword("DATA")
                body = self.block("body")
                rules.append(
                    Rule(
                        tuple(
                            e.pattern
                            for e in head
                            if isinstance(e, TriplePatternElement)
                        ),
                        body,
                        data_only,
                        identifier,
                        self.scanner.source,
                    )
                )
            else:
                self.scanner.error("expected prologue, RULE or DATA")
            self.ws()
        return RuleSet(tuple(rules), tuple(data), tuple(imports), self.document_iri)

    def block(self, context: str) -> tuple[RuleElement, ...]:
        previous = self.context
        self.context = context
        self.expect("{")
        elements: list[RuleElement] = []
        while not self.scanner.consume("}"):
            self.ws()
            if context in ("body", "negation") and self.keyword("FILTER"):
                elements.append(FilterElement(self.expression()))
            elif context == "body" and self.keyword("NOT"):
                data_only = self.keyword("DATA")
                elements.append(NegationElement(self.block("negation"), data_only))
            elif context == "body" and self.keyword("SET"):
                self.expect("(")
                variable = self.parse_iri()
                if not isinstance(variable, Variable):
                    self.scanner.error("SET target must be a variable")
                self.expect(":=")
                expression = self.expression()
                self.expect(")")
                elements.append(AssignmentElement(variable, expression))
            else:
                start = len(self.triples)
                self.parse_triples_statement()
                elements.extend(TriplePatternElement(t) for t in self.triples[start:])
                del self.triples[start:]
                self.ws()
                if (
                    self.scanner.peek() != "}"
                    and not self.scanner.consume(".")
                    and not any(
                        is_keyword_ci_with_extra_boundary(self.scanner, word, "(")
                        for word in ("FILTER", "SET", "NOT")
                    )
                ):
                    self.scanner.error("expected '.' between triple patterns")
            self.ws()
            self.ws()
        self.context = previous
        self.ws()
        return tuple(elements)

    def expression(self, minimum: int = 0) -> Expression | Node:
        self.ws()
        if self.scanner.peek() in ("!", "+", "-"):
            unary_op = self.scanner.advance()
            left: Expression | Node = Expression(
                "unary" + unary_op, (self.expression(6),)
            )
        elif self.scanner.consume("("):
            left = self.expression()
            self.expect(")")
        else:
            match = re.match(
                r"[A-Za-z_][A-Za-z_0-9]*(?=\s*\()", self.scanner.text[self.scanner.i :]
            )
            if match:
                name = match.group().upper()
                if name not in BUILTINS:
                    self.scanner.error(f"unsupported built-in {name}")
                for _ in match.group():
                    self.scanner.advance()
                arguments = self.arguments()
                count = len(arguments)
                allowed = {
                    "NOW": {0},
                    "UUID": {0},
                    "STRUUID": {0},
                    "BNODE": {0, 1},
                    "SUBSTR": {2, 3},
                    "REPLACE": {3, 4},
                    "REGEX": {2, 3},
                    "IF": {3},
                    "STRLANGDIR": {3},
                    "TRIPLE": {3},
                }
                binary = {
                    "LANGMATCHES",
                    "CONTAINS",
                    "STRSTARTS",
                    "STRENDS",
                    "STRBEFORE",
                    "STRAFTER",
                    "STRLANG",
                    "STRDT",
                    "SAMETERM",
                }
                if name != "CONCAT" and count not in allowed.get(
                    name, {2} if name in binary else {1}
                ):
                    self.scanner.error(f"invalid argument count for {name}")
                left = Expression(name, arguments)
            else:
                left = self.parse_object()
                self.ws()
                if (
                    isinstance(left, IRI)
                    and not isinstance(left, Variable)
                    and self.scanner.peek() == "("
                ):
                    left = Expression(left.value, self.arguments())
        precedence = {
            "||": 1,
            "&&": 2,
            "=": 3,
            "!=": 3,
            "<": 3,
            ">": 3,
            "<=": 3,
            ">=": 3,
            "+": 4,
            "-": 4,
            "*": 5,
            "/": 5,
        }
        while True:
            self.ws()
            mark = self.scanner.mark()
            if minimum <= 3 and (self.keyword("IN") or self.keyword("NOT")):
                word = self.scanner.text[mark[0] : self.scanner.i].strip().upper()
                if word == "NOT" and not self.keyword("IN"):
                    self.scanner.error("expected IN")
                left = Expression(
                    "NOT IN" if word == "NOT" else "IN", (left, *self.arguments())
                )
                continue
            self.scanner.reset(mark)
            op = next(
                (
                    x
                    for x in (
                        "||",
                        "&&",
                        "!=",
                        "<=",
                        ">=",
                        "=",
                        "<",
                        ">",
                        "+",
                        "-",
                        "*",
                        "/",
                    )
                    if self.scanner.startswith(x)
                ),
                None,
            )
            if op is None or precedence[op] < minimum:
                break
            self.scanner.consume(op)
            left = Expression(op, (left, self.expression(precedence[op] + 1)))
        return left

    def arguments(self) -> tuple[Expression | Node, ...]:
        self.expect("(")
        args = []
        if self.scanner.consume(")"):
            return ()
        while True:
            args.append(self.expression())
            self.ws()
            if self.scanner.consume(")"):
                return tuple(args)
            self.expect(",")


def parse_rules(
    text: str, *, base_iri: str | None = None, source_name: str | None = None
) -> RuleSet:
    return RuleParser(text, source_name or "<rules>", base_iri).document()
