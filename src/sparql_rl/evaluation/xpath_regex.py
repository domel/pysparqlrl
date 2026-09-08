"""XPath regular-expression syntax and replacement rules with bounded matching."""

import re

import regex
from elementpath.regex import RegexError, translate_pattern

from sparql_rl.errors import ExpressionError

TIMEOUT = 0.1


def strip_pattern_whitespace(pattern: str) -> str:
    result = []
    depth = 0
    escaped = False
    for char in pattern:
        if depth == 0 and char in " \t\r\n":
            continue
        result.append(char)
        if not escaped:
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
        escaped = not escaped and char == "\\"
    return "".join(result)


def compile_pattern(pattern: str, flags_text: str) -> regex.Pattern[str]:
    if set(flags_text) - set("smixq"):
        raise ExpressionError("invalid XPath regular-expression flags")
    flags = sum(
        {"s": re.DOTALL, "m": re.MULTILINE, "i": re.IGNORECASE}[f]
        for f in set(flags_text) & set("smi")
    )
    try:
        if "q" in flags_text:
            translated = re.escape(pattern)
        else:
            if "x" in flags_text:
                pattern = strip_pattern_whitespace(pattern)
            translated = translate_pattern(pattern, flags=flags, xsd_version="1.1")
        return regex.compile(translated, flags)
    except (RegexError, regex.error) as error:
        raise ExpressionError(f"invalid XPath regular expression: {error}") from error


def replacement_parts(replacement: str, groups: int) -> list[str | int]:
    parts: list[str | int] = []
    index = 0
    while index < len(replacement):
        char = replacement[index]
        if char == "\\":
            index += 1
            if index == len(replacement) or replacement[index] not in ("\\", "$"):
                raise ExpressionError("invalid XPath replacement escape")
            parts.append(replacement[index])
        elif char == "$":
            index += 1
            start = index
            while index < len(replacement) and replacement[index] in "0123456789":
                index += 1
            if index == start:
                raise ExpressionError("replacement dollar sign requires a group number")
            digits = replacement[start:index]
            suffix = ""
            while int(digits) > groups and int(digits) > 9:
                suffix = digits[-1] + suffix
                digits = digits[:-1]
            number = int(digits)
            parts.append(number if number <= groups else "")
            parts.append(suffix)
            continue
        else:
            parts.append(char)
        index += 1
    return parts


def matches(text: str, pattern: str, flags: str = "") -> bool:
    return compile_pattern(pattern, flags).search(text, timeout=TIMEOUT) is not None


def replace(text: str, pattern: str, replacement: str, flags: str = "") -> str:
    compiled = compile_pattern(pattern, flags)
    if compiled.search("", timeout=TIMEOUT) is not None:
        raise ExpressionError("replacement pattern matches an empty string")
    parts = (
        [replacement]
        if "q" in flags
        else replacement_parts(replacement, compiled.groups)
    )

    def substitute(match: regex.Match[str]) -> str:
        return "".join(
            (match.group(part) or "") if isinstance(part, int) else part
            for part in parts
        )

    return compiled.sub(substitute, text, timeout=TIMEOUT)
