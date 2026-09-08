import pytest

from sparql_rl.errors import ExpressionError
from sparql_rl.evaluation.xpath_regex import matches, replace


@pytest.mark.parametrize(
    "text,pattern,flags,expected",
    [
        ("a.b", "a.b", "q", True),
        ("axb", "a.b", "q", False),
        ("A.B", "a.b", "qi", True),
        ("a b", "a b", "qx", True),
        ("a#b", "a # b", "x", True),
        ("a b", "[ ]", "x", True),
        ("b", "[a-z-[aeiou]]", "", True),
        ("a", "[a-z-[aeiou]]", "", False),
        ("é", r"\p{L}", "", True),
        ("x:name", r"\i\c*", "", True),
        ("a\n", "^a$", "", False),
        ("a\n", "^a$", "m", True),
    ],
)
def test_xpath_patterns(text, pattern, flags, expected):
    assert matches(text, pattern, flags) is expected


@pytest.mark.parametrize(
    "pattern,flags", [("(?=a)", ""), ("[", ""), (r"\b", ""), ("a", "z")]
)
def test_invalid_xpath_patterns(pattern, flags):
    with pytest.raises(ExpressionError):
        matches("abc", pattern, flags)


@pytest.mark.parametrize("pattern", ["", "a*", "(a)?", ".*?"])
def test_replace_rejects_empty_matching_pattern(pattern):
    with pytest.raises(ExpressionError):
        replace("abc", pattern, "X")


@pytest.mark.parametrize(
    "text,pattern,replacement,flags,expected",
    [
        ("abcd", "(ab)|(a)", "[1=$1][2=$2]", "", "[1=ab][2=]cd"),
        ("ab", "(a)(b)", "$23/$0/$9", "", "b3/ab/"),
        ("a", "a", "$23", "", "3"),
        ("a", "(a)", "$01", "", "a"),
        ("a", "(a)", r"\$1\\", "", "$1\\"),
        ("a.b", ".", "$1\\", "q", "a$1\\b"),
        ("abc", "a", "", "", "bc"),
        ("abc", "(z)", "$0", "", "abc"),
    ],
)
def test_xpath_replacements(text, pattern, replacement, flags, expected):
    assert replace(text, pattern, replacement, flags) == expected


@pytest.mark.parametrize("replacement", ["$", "$x", "\\", r"\n"])
def test_invalid_replacement_is_error_even_without_a_match(replacement):
    with pytest.raises(ExpressionError):
        replace("abc", "z", replacement)
