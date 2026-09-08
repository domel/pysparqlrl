"""RDF 1.2 lexical and Turtle parsing primitives. See LICENSE.rdf-parser."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import NoReturn
from urllib.parse import urlsplit, urlunsplit

__version__ = "0.3.0"

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"

RDF_TYPE_IRI = f"{RDF_NS}type"
RDF_FIRST_IRI = f"{RDF_NS}first"
RDF_REST_IRI = f"{RDF_NS}rest"
RDF_NIL_IRI = f"{RDF_NS}nil"
RDF_REIFIES_IRI = f"{RDF_NS}reifies"

XSD_BOOLEAN_IRI = f"{XSD_NS}boolean"
XSD_INTEGER_IRI = f"{XSD_NS}integer"
XSD_DECIMAL_IRI = f"{XSD_NS}decimal"
XSD_DOUBLE_IRI = f"{XSD_NS}double"

RDF_LANG_STRING_IRI = f"{RDF_NS}langString"
RDF_DIR_LANG_STRING_IRI = f"{RDF_NS}dirLangString"

NAME_PUNCTUATION = "_-"


class ParseError(ValueError):
    """Raised on deterministic syntax/semantic parse errors."""

    def __init__(self, source: str, line: int, column: int, message: str):
        """Initialize a parse error with source location details."""
        super().__init__(f"{source}:{line}:{column}: {message}")
        self.source = source
        self.line = line
        self.column = column
        self.message = message


@dataclass(frozen=True)
class IRI:
    """IRI node value used by the parser and serializers."""

    value: str


@dataclass(frozen=True)
class BNode:
    """Blank node identifier used in parsed RDF triples."""

    label: str


@dataclass(frozen=True)
class Literal:
    """RDF literal value with optional language, direction, or datatype."""

    value: str
    lang: str | None = None
    direction: str | None = None
    datatype: str | None = None

    def __post_init__(self) -> None:
        if self.lang is not None:
            object.__setattr__(self, "lang", self.lang.lower())
        if self.datatype == XSD_NS + "string":
            object.__setattr__(self, "datatype", None)


@dataclass(frozen=True)
class TripleTerm:
    """Quoted triple term used as an RDF-star style node value."""

    subject: Node
    predicate: IRI
    object: IRI | BNode | Literal | TripleTerm


Node = IRI | BNode | Literal | TripleTerm
Triple = tuple[Node, IRI, Node]
GraphLabel = IRI | BNode
Quad = tuple[IRI | BNode, IRI, Node, GraphLabel | None]


@dataclass
class AnnotationData:
    """Stores parsed annotation/reification information for a statement."""

    reifiers: list[IRI | BNode] = field(default_factory=list)
    blocks: list[list[tuple[IRI, list[tuple[Node, AnnotationData]]]]] = field(
        default_factory=list
    )
    events: list[tuple[str, object]] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        """Return whether any annotation payload was collected."""
        return bool(self.events or self.reifiers or self.blocks)


class Scanner:
    """Stateful character scanner with line and column tracking."""

    def __init__(self, text: str, source: str):
        """Initialize scanner state for the provided source text."""
        self.text = text
        self.source = source
        self.i = 0
        self.line = 1
        self.col = 1

    def eof(self) -> bool:
        """Return `True` when the scanner reached the end of input."""
        return self.i >= len(self.text)

    def peek(self, offset: int = 0) -> str:
        """Return the character at the current position plus an optional offset."""
        idx = self.i + offset
        if idx >= len(self.text):
            return ""
        return self.text[idx]

    def startswith(self, token: str) -> bool:
        """Return `True` if the remaining input starts with `token`."""
        return self.text.startswith(token, self.i)

    def advance(self) -> str:
        """Consume and return one character while updating line/column counters."""
        if self.eof():
            self.error("unexpected end of input")
        ch = self.text[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def consume(self, token: str) -> bool:
        """Consume `token` if present and return whether it matched."""
        if not self.startswith(token):
            return False
        for _ in token:
            self.advance()
        return True

    def expect(self, token: str, message: str | None = None) -> None:
        """Consume `token` or raise a parse error with a helpful message."""
        if not self.consume(token):
            self.error(message or f"expected '{token}'")

    def mark(self) -> tuple[int, int, int]:
        """Capture the current scanner position for backtracking."""
        return self.i, self.line, self.col

    def reset(self, mark: tuple[int, int, int]) -> None:
        """Restore a position previously returned by `mark()`."""
        self.i, self.line, self.col = mark

    def error(self, message: str) -> NoReturn:
        """Raise `ParseError` at the current scanner position."""
        raise ParseError(self.source, self.line, self.col, message)


def is_space(ch: str) -> bool:
    """Return whether a character is RDF whitespace."""
    return ch in " \t\r\n"


def skip_ws_comments(scanner: Scanner) -> None:
    """Skip whitespace and `#` comments in the current scanner."""
    while not scanner.eof():
        ch = scanner.peek()
        if is_space(ch):
            scanner.advance()
            continue
        if ch == "#":
            while not scanner.eof() and scanner.peek() not in "\r\n":
                scanner.advance()
            continue
        break


def _in_ranges(cp: int, ranges: Iterable[tuple[int, int]]) -> bool:
    """Internal helper for in ranges."""
    for lo, hi in ranges:
        if lo <= cp <= hi:
            return True
    return False


PN_BASE_RANGES = (
    (0x00C0, 0x00D6),
    (0x00D8, 0x00F6),
    (0x00F8, 0x02FF),
    (0x0370, 0x037D),
    (0x037F, 0x1FFF),
    (0x200C, 0x200D),
    (0x2070, 0x218F),
    (0x2C00, 0x2FEF),
    (0x3001, 0xD7FF),
    (0xF900, 0xFDCF),
    (0xFDF0, 0xFFFD),
    (0x10000, 0xEFFFF),
)


def is_pn_chars_base(ch: str) -> bool:
    """Return whether a character is a valid `PN_CHARS_BASE` code point."""
    if len(ch) != 1:
        return False
    if "A" <= ch <= "Z" or "a" <= ch <= "z":
        return True
    cp = ord(ch)
    return _in_ranges(cp, PN_BASE_RANGES)


def is_pn_chars_u(ch: str) -> bool:
    """Return whether a character is a valid `PN_CHARS_U` code point."""
    return ch == "_" or is_pn_chars_base(ch)


def is_pn_chars(ch: str) -> bool:
    """Return whether a character is a valid `PN_CHARS` code point."""
    if len(ch) != 1:
        return False
    if is_pn_chars_u(ch) or ch in "-0123456789":
        return True
    cp = ord(ch)
    return cp == 0x00B7 or 0x0300 <= cp <= 0x036F or 0x203F <= cp <= 0x2040


def is_hex(ch: str) -> bool:
    """Return whether a character is a hexadecimal digit."""
    return ch.isdigit() or ("A" <= ch <= "F") or ("a" <= ch <= "f")


def decode_uchar(scanner: Scanner) -> str:
    """Decode Unicode escapes."""

    def read_hex4() -> int:
        """Read four hexadecimal digits and return their integer value."""
        digits = []
        for _ in range(4):
            ch = scanner.peek()
            if not is_hex(ch):
                scanner.error("invalid \\u escape")
            digits.append(scanner.advance())
        return int("".join(digits), 16)

    if scanner.consume("\\u"):
        codepoint = read_hex4()
        if 0xD800 <= codepoint <= 0xDFFF:
            scanner.error("surrogate code points are not allowed")
        return chr(codepoint)
    if scanner.consume("\\U"):
        digits = []
        for _ in range(8):
            ch = scanner.peek()
            if not is_hex(ch):
                scanner.error("invalid \\U escape")
            digits.append(scanner.advance())
        codepoint = int("".join(digits), 16)
        if codepoint > 0x10FFFF:
            scanner.error("code point out of range")
        if 0xD800 <= codepoint <= 0xDFFF:
            scanner.error("surrogate code points are not allowed")
        return chr(codepoint)
    scanner.error("expected unicode escape")


def decode_echar(scanner: Scanner, allow_single_quote: bool) -> str:
    """Decode ECHAR escapes."""
    scanner.expect("\\", "expected escape")
    ch = scanner.peek()
    mapping = {
        "t": "\t",
        "b": "\b",
        "n": "\n",
        "r": "\r",
        "f": "\f",
        '"': '"',
        "\\": "\\",
    }
    if allow_single_quote:
        mapping["'"] = "'"
    if ch not in mapping:
        scanner.error("invalid escape sequence")
    scanner.advance()
    return mapping[ch]


def parse_iri_ref(scanner: Scanner, require_absolute: bool, allow_empty: bool) -> str:
    """Parse IRI reference from the current input and return the result."""
    scanner.expect("<")
    chars: list[str] = []
    while True:
        if scanner.eof():
            scanner.error("unterminated IRI")
        ch = scanner.peek()
        if ch == ">":
            scanner.advance()
            iri = "".join(chars)
            validate_iri(
                iri, require_absolute=require_absolute, allow_empty=allow_empty
            )
            return iri
        if ch == "\\":
            uch = decode_uchar(scanner)
            if uch in '<>"{}|^`\\' or ord(uch) <= 0x20:
                scanner.error("invalid escaped character in IRI")
            chars.append(uch)
            continue
        if ch in '<>"{}|^`':
            scanner.error("invalid character in IRI")
        if ord(ch) <= 0x20:
            scanner.error("invalid whitespace/control in IRI")
        chars.append(scanner.advance())


def validate_iri(value: str, require_absolute: bool, allow_empty: bool) -> None:
    """Validate IRI."""
    if not value and not allow_empty:
        raise ValueError("IRI must not be empty")
    if any(ord(ch) <= 0x20 for ch in value):
        raise ValueError("IRI contains whitespace/control")
    parts = urlsplit(value)
    if require_absolute and not parts.scheme:
        raise ValueError("IRI must be absolute")


def encode_iri_ref(value: str) -> str:
    """Encode IRI reference."""
    out: list[str] = ["<"]
    for ch in value:
        cp = ord(ch)
        if ch in '<>"{}|^`\\' or cp <= 0x20:
            if cp <= 0xFFFF:
                out.append(f"\\u{cp:04X}")
            else:
                out.append(f"\\U{cp:08X}")
        else:
            out.append(ch)
    out.append(">")
    return "".join(out)


def _remove_dot_segments(path: str) -> str:
    """Normalize a path by removing `.` and `..` dot segments."""
    input_buffer = path
    output_buffer = ""

    def remove_last_segment(buf: str) -> str:
        """Drop the final path segment while preserving leading slash semantics."""
        idx = buf.rfind("/")
        if idx < 0:
            return ""
        return buf[:idx]

    while input_buffer:
        if input_buffer.startswith("../"):
            input_buffer = input_buffer[3:]
            continue
        if input_buffer.startswith("./"):
            input_buffer = input_buffer[2:]
            continue
        if input_buffer.startswith("/./"):
            input_buffer = "/" + input_buffer[3:]
            continue
        if input_buffer == "/.":
            input_buffer = "/"
            continue
        if input_buffer.startswith("/../"):
            input_buffer = "/" + input_buffer[4:]
            output_buffer = remove_last_segment(output_buffer)
            continue
        if input_buffer == "/..":
            input_buffer = "/"
            output_buffer = remove_last_segment(output_buffer)
            continue
        if input_buffer == "." or input_buffer == "..":
            input_buffer = ""
            continue

        if input_buffer.startswith("/"):
            next_slash = input_buffer.find("/", 1)
        else:
            next_slash = input_buffer.find("/")
        if next_slash < 0:
            segment = input_buffer
            input_buffer = ""
        else:
            segment = input_buffer[:next_slash]
            input_buffer = input_buffer[next_slash:]
        output_buffer += segment

    return output_buffer


def _merge_reference_path(
    base_path: str, base_has_authority: bool, ref_path: str
) -> str:
    """Merge an RFC 3986 reference path against the base path."""
    if base_has_authority and base_path == "":
        return "/" + ref_path
    slash = base_path.rfind("/")
    if slash < 0:
        return ref_path
    return base_path[: slash + 1] + ref_path


def resolve_iri_reference(base_iri: str, ref_iri: str) -> str:
    """Resolve a relative IRI reference against a base without collapsing // path segments."""

    ref_parts = urlsplit(ref_iri)
    if ref_parts.scheme:
        resolved = urlunsplit(
            (
                ref_parts.scheme,
                ref_parts.netloc,
                _remove_dot_segments(ref_parts.path),
                ref_parts.query,
                ref_parts.fragment,
            )
        )
    else:
        base_parts = urlsplit(base_iri)
        if ref_parts.netloc:
            path = _remove_dot_segments(ref_parts.path)
            resolved = urlunsplit(
                (
                    base_parts.scheme,
                    ref_parts.netloc,
                    path,
                    ref_parts.query,
                    ref_parts.fragment,
                )
            )
        else:
            if ref_parts.path == "":
                path = base_parts.path
                query = (
                    ref_parts.query
                    if "?" in ref_iri.split("#", 1)[0]
                    else base_parts.query
                )
            elif ref_parts.path.startswith("/"):
                path = _remove_dot_segments(ref_parts.path)
                query = ref_parts.query
            else:
                merged = _merge_reference_path(
                    base_parts.path,
                    base_has_authority=bool(base_parts.netloc),
                    ref_path=ref_parts.path,
                )
                path = _remove_dot_segments(merged)
                query = ref_parts.query
            resolved = urlunsplit(
                (base_parts.scheme, base_parts.netloc, path, query, ref_parts.fragment)
            )

    # Preserve explicit empty query/fragment markers (urlunsplit drops them).
    ref_no_fragment, _, _ = ref_iri.partition("#")
    has_query_marker = "?" in ref_no_fragment
    has_fragment_marker = "#" in ref_iri
    if has_query_marker and ref_parts.query == "":
        head, sep, tail = resolved.partition("#")
        if "?" not in head:
            resolved = f"{head}?{sep}{tail}" if sep else f"{head}?"
    if has_fragment_marker and ref_parts.fragment == "" and "#" not in resolved:
        resolved += "#"
    return resolved


def parse_short_string(
    scanner: Scanner, quote: str, allow_single_quote_escape: bool
) -> str:
    """Parse short string from the current input and return the result."""
    scanner.expect(quote)
    out: list[str] = []
    while True:
        if scanner.eof():
            scanner.error("unterminated string")
        ch = scanner.peek()
        if ch == quote:
            scanner.advance()
            return "".join(out)
        if ch in "\n\r":
            scanner.error("newline in short string literal")
        if ch == "\\":
            mark = scanner.mark()
            scanner.advance()
            esc = scanner.peek()
            scanner.reset(mark)
            if esc in "uU":
                out.append(decode_uchar(scanner))
            else:
                out.append(
                    decode_echar(scanner, allow_single_quote=allow_single_quote_escape)
                )
            continue
        out.append(scanner.advance())


def parse_long_string(
    scanner: Scanner, quote: str, allow_single_quote_escape: bool
) -> str:
    """Parse long string from the current input and return the result."""
    delim = quote * 3
    scanner.expect(delim)
    out: list[str] = []
    while True:
        if scanner.eof():
            scanner.error("unterminated long string")
        if scanner.startswith(delim):
            scanner.consume(delim)
            return "".join(out)
        ch = scanner.peek()
        if ch == "\\":
            mark = scanner.mark()
            scanner.advance()
            esc = scanner.peek()
            scanner.reset(mark)
            if esc in "uU":
                out.append(decode_uchar(scanner))
            else:
                out.append(
                    decode_echar(scanner, allow_single_quote=allow_single_quote_escape)
                )
            continue
        out.append(scanner.advance())


def parse_lang_dir(scanner: Scanner) -> tuple[str, str | None]:
    """Parse language and direction suffix from the current input and return the result."""
    scanner.expect("@")
    primary = []
    while scanner.peek().isalpha():
        primary.append(scanner.advance())
    if not primary:
        scanner.error("invalid language tag")
    if len(primary) > 8:
        scanner.error("language subtag too long")
    subtags: list[str] = []
    while scanner.peek() == "-" and scanner.peek(1) != "-":
        scanner.advance()
        segment = []
        while scanner.peek().isalnum():
            segment.append(scanner.advance())
        if not segment:
            scanner.error("empty language subtag")
        if len(segment) > 8:
            scanner.error("language subtag too long")
        subtags.append("".join(segment))
    lang = "".join(primary).lower()
    if subtags:
        lang += "-" + "-".join(segment.lower() for segment in subtags)
    direction = None
    if scanner.consume("--"):
        letters = []
        while scanner.peek().isalpha():
            letters.append(scanner.advance())
        if not letters:
            scanner.error("missing text direction")
        direction = "".join(letters)
        if direction not in ("ltr", "rtl"):
            scanner.error("text direction must be 'ltr' or 'rtl'")
    return lang, direction


def escape_string_value(value: str) -> str:
    """Escape string value."""
    out: list[str] = []
    for ch in value:
        cp = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\f":
            out.append("\\f")
        elif cp < 0x20 or cp in (0x7F, 0xFFFE, 0xFFFF):
            out.append(f"\\u{cp:04X}")
        else:
            out.append(ch)
    return "".join(out)


def is_name_boundary(ch: str) -> bool:
    """Return whether a character terminates a Turtle/N-Triples keyword token."""
    if not ch:
        return True
    return is_space(ch) or ch in ";,.()[]{}<>\"'|#"


def is_keyword(scanner: Scanner, kw: str) -> bool:
    """Return whether the scanner is positioned at the exact keyword."""
    if not scanner.startswith(kw):
        return False
    nxt = scanner.peek(len(kw))
    return is_name_boundary(nxt)


def is_keyword_ci(scanner: Scanner, kw: str) -> bool:
    """Return whether the scanner matches a keyword case-insensitively."""
    end = scanner.i + len(kw)
    if end > len(scanner.text):
        return False
    if scanner.text[scanner.i : end].lower() != kw.lower():
        return False
    nxt = scanner.peek(len(kw))
    return is_name_boundary(nxt)


def is_keyword_with_extra_boundary(scanner: Scanner, kw: str, extra: str) -> bool:
    """Return whether keyword matches and is followed by a standard or extra boundary."""
    if not scanner.startswith(kw):
        return False
    nxt = scanner.peek(len(kw))
    return is_name_boundary(nxt) or nxt in extra


def is_keyword_ci_with_extra_boundary(scanner: Scanner, kw: str, extra: str) -> bool:
    """Case-insensitive keyword match allowing additional boundary characters."""
    end = scanner.i + len(kw)
    if end > len(scanner.text):
        return False
    if scanner.text[scanner.i : end].lower() != kw.lower():
        return False
    nxt = scanner.peek(len(kw))
    return is_name_boundary(nxt) or nxt in extra


class BaseParser:
    """Shared parser utilities used by the N-Triples and Turtle parsers."""

    def __init__(self, text: str, source: str):
        """Initialize the `BaseParser` instance."""
        self.scanner = Scanner(text, source)
        self.triples: list[Triple] = []
        self._generated_bnode = 0
        self._reserved_labels: set[str] = set(re.findall(r"_:([\w.-]+)", text))

    def new_bnode(self) -> BNode:
        """Create a fresh generated blank node label that avoids collisions."""
        while True:
            label = f"genid{self._generated_bnode}"
            self._generated_bnode += 1
            if label not in self._reserved_labels:
                self._reserved_labels.add(label)
                return BNode(label)

    def emit(self, subject: Node, predicate: IRI, obj: Node) -> None:
        """Append one triple to the parser output buffer."""
        self.triples.append((subject, predicate, obj))

    def emit_annotation(
        self,
        subject: Node,
        predicate: IRI,
        obj: Node,
        annotation: AnnotationData,
    ) -> None:
        """Emit triples representing parsed statement annotations/reification."""
        if not annotation.has_data:
            return
        triple_term = TripleTerm(subject, predicate, obj)
        if annotation.events:
            current_subject: Node | None = None
            for kind, payload in annotation.events:
                if kind == "reifier":
                    current_subject = payload  # type: ignore[assignment]
                    assert current_subject is not None
                    self.emit(current_subject, IRI(RDF_REIFIES_IRI), triple_term)
                    continue
                if kind == "block":
                    if current_subject is None:
                        current_subject = self.new_bnode()
                        self.emit(current_subject, IRI(RDF_REIFIES_IRI), triple_term)
                    self.emit_pairs_from_structure(
                        current_subject,
                        payload,  # type: ignore[arg-type]
                    )
                    # A block applies to a single reifier occurrence in sequence.
                    current_subject = None
                    continue
                raise TypeError(f"unsupported annotation event kind: {kind!r}")
            return
        ann_subject: Node
        if annotation.reifiers:
            ann_subject = annotation.reifiers[0]
            for extra in annotation.reifiers[1:]:
                self.emit(extra, IRI(RDF_REIFIES_IRI), triple_term)
        else:
            ann_subject = self.new_bnode()
        self.emit(ann_subject, IRI(RDF_REIFIES_IRI), triple_term)
        for block in annotation.blocks:
            self.emit_pairs_from_structure(ann_subject, block)

    def emit_pairs_from_structure(
        self,
        subject: Node,
        pairs: list[tuple[IRI, list[tuple[Node, AnnotationData]]]],
    ) -> None:
        """Emit predicate-object pairs from a parsed block/list structure."""
        for predicate, objects in pairs:
            for obj, annotation in objects:
                self.emit(subject, predicate, obj)
                self.emit_annotation(subject, predicate, obj, annotation)


class NTriplesParser(BaseParser):
    """Parser for the repository's RDF 1.2 N-Triples grammar."""

    def parse(self) -> list[Triple]:
        """Parse the current document and return parsed triples."""
        while True:
            skip_ws_comments(self.scanner)
            if self.scanner.eof():
                return self.triples
            if is_keyword(self.scanner, "VERSION"):
                self.parse_version_directive()
                continue
            self.parse_statement()

    def parse_version_directive(self) -> None:
        """Parse version directive from the current input and return the result."""
        self.scanner.expect("VERSION")
        skip_ws_comments(self.scanner)
        # Grammar allows string literal only.
        _ = parse_short_string(self.scanner, '"', allow_single_quote_escape=False)

    def parse_statement(self) -> None:
        """Parse statement from the current input and return the result."""
        subject = self.parse_subject()
        skip_ws_comments(self.scanner)
        predicate = self.parse_predicate()
        skip_ws_comments(self.scanner)
        obj = self.parse_object()

        annotation = self.parse_annotation_data()
        if annotation.has_data and isinstance(subject, BNode):
            self.scanner.error(
                "annotated N-Triples statements cannot have blank node subjects"
            )
        if annotation.has_data and isinstance(obj, BNode):
            self.scanner.error(
                "annotated N-Triples statements cannot have blank node objects"
            )

        skip_ws_comments(self.scanner)
        self.scanner.expect(".", "expected '.' to end N-Triples statement")

        self.emit(subject, predicate, obj)
        self.emit_annotation(subject, predicate, obj, annotation)

    def parse_annotation_data(self) -> AnnotationData:
        """Parse annotation data from the current input and return the result."""
        annotation = AnnotationData()
        while True:
            skip_ws_comments(self.scanner)
            if not self.scanner.startswith("{|"):
                break
            block = self.parse_annotation_block_structure()
            annotation.blocks.append(block)
            annotation.events.append(("block", block))
        return annotation

    def parse_annotation_block_structure(
        self,
    ) -> list[tuple[IRI, list[tuple[Node, AnnotationData]]]]:
        """Parse annotation block structure from the current input and return the result."""
        self.scanner.expect("{|")
        skip_ws_comments(self.scanner)
        pairs = self.parse_pairs_structure(terminator="|}", allow_a_verb=False)
        skip_ws_comments(self.scanner)
        self.scanner.expect("|}", "expected '|}' to close annotation block")
        return pairs

    def parse_pairs_structure(
        self,
        terminator: str,
        allow_a_verb: bool,
    ) -> list[tuple[IRI, list[tuple[Node, AnnotationData]]]]:
        """Parse pairs structure from the current input and return the result."""
        pairs: list[tuple[IRI, list[tuple[Node, AnnotationData]]]] = []
        while True:
            if self.scanner.startswith(terminator):
                break
            pred = self.parse_verb(allow_a=allow_a_verb)
            skip_ws_comments(self.scanner)
            objs = self.parse_object_list_structure()
            pairs.append((pred, objs))
            skip_ws_comments(self.scanner)
            if not self.scanner.consume(";"):
                break
            skip_ws_comments(self.scanner)
            while self.scanner.consume(";"):
                skip_ws_comments(self.scanner)
            if self.scanner.startswith(terminator):
                break
        return pairs

    def parse_object_list_structure(self) -> list[tuple[Node, AnnotationData]]:
        """Parse object list structure from the current input and return the result."""
        objects: list[tuple[Node, AnnotationData]] = []
        while True:
            obj = self.parse_object()
            annotation = self.parse_annotation_data()
            objects.append((obj, annotation))
            skip_ws_comments(self.scanner)
            if not self.scanner.consume(","):
                break
            skip_ws_comments(self.scanner)
        return objects

    def parse_subject(self) -> Node:
        """Parse subject from the current input and return the result."""
        ch = self.scanner.peek()
        if ch == "<":
            return IRI(self.parse_iri(require_absolute=True))
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        self.scanner.error("N-Triples subject must be IRI or blank node")

    def parse_predicate(self) -> IRI:
        """Parse predicate from the current input and return the result."""
        if self.scanner.peek() != "<":
            self.scanner.error("N-Triples predicate must be IRI")
        return IRI(self.parse_iri(require_absolute=True))

    def parse_verb(self, allow_a: bool) -> IRI:
        """Parse verb from the current input and return the result."""
        if allow_a and is_keyword(self.scanner, "a"):
            self.scanner.expect("a")
            return IRI(RDF_TYPE_IRI)
        return self.parse_predicate()

    def parse_object(self) -> Node:
        """Parse object from the current input and return the result."""
        if self.scanner.startswith("<<("):
            return self.parse_triple_term()
        if self.scanner.startswith("<<"):
            self.scanner.error("invalid RDF-star syntax, expected '<<( ... )>>'")
        ch = self.scanner.peek()
        if ch == "<":
            return IRI(self.parse_iri(require_absolute=True))
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        if ch == '"':
            return self.parse_literal()
        self.scanner.error("invalid N-Triples object")

    def parse_literal(self) -> Literal:
        """Parse literal from the current input and return the result."""
        value = parse_short_string(self.scanner, '"', allow_single_quote_escape=False)
        lang = None
        direction = None
        datatype = None
        while is_space(self.scanner.peek()):
            self.scanner.advance()
        if self.scanner.consume("^^"):
            while is_space(self.scanner.peek()):
                self.scanner.advance()
            datatype = self.parse_iri(require_absolute=True)
            if datatype in (RDF_LANG_STRING_IRI, RDF_DIR_LANG_STRING_IRI):
                self.scanner.error(
                    "rdf:langString and rdf:dirLangString datatypes are not allowed"
                )
        elif self.scanner.peek() == "@":
            lang, direction = parse_lang_dir(self.scanner)
        return Literal(value=value, lang=lang, direction=direction, datatype=datatype)

    def parse_blank_node_label(self) -> BNode:
        """Parse blank node label from the current input and return the result."""
        self.scanner.expect("_:")
        if not (is_pn_chars_u(self.scanner.peek()) or self.scanner.peek().isdigit()):
            self.scanner.error("invalid blank node label")
        chars = [self.scanner.advance()]
        while True:
            ch = self.scanner.peek()
            if not ch:
                break
            if is_pn_chars(ch):
                chars.append(self.scanner.advance())
                continue
            if ch == ".":
                nxt = self.scanner.peek(1)
                if nxt and (nxt == "." or is_pn_chars(nxt)):
                    chars.append(self.scanner.advance())
                    continue
                break
            break
        label = "".join(chars)
        self._reserved_labels.add(label)
        return BNode(label)

    def parse_iri(self, require_absolute: bool) -> str:
        """Parse IRI from the current input and return the result."""
        try:
            return parse_iri_ref(
                self.scanner, require_absolute=require_absolute, allow_empty=False
            )
        except ValueError as exc:
            self.scanner.error(str(exc))
        raise AssertionError("unreachable")

    def parse_triple_term(self) -> TripleTerm:
        """Parse triple-term node from the current input and return the result."""
        self.scanner.expect("<<(")
        skip_ws_comments(self.scanner)
        subject = self.parse_tt_subject()
        skip_ws_comments(self.scanner)
        predicate = self.parse_predicate()
        skip_ws_comments(self.scanner)
        obj = self.parse_tt_object()
        skip_ws_comments(self.scanner)
        self.scanner.expect(")>>", "expected ')>>' to close triple term")
        return TripleTerm(subject=subject, predicate=predicate, object=obj)

    def parse_tt_subject(self) -> Node:
        """Parse triple-term subject from the current input and return the result."""
        ch = self.scanner.peek()
        if ch == "<":
            return IRI(self.parse_iri(require_absolute=True))
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        self.scanner.error("triple term subject must be IRI or blank node")

    def parse_tt_object(self) -> Node:
        """Parse triple-term object from the current input and return the result."""
        if self.scanner.startswith("<<("):
            return self.parse_triple_term()
        ch = self.scanner.peek()
        if ch == "<":
            return IRI(self.parse_iri(require_absolute=True))
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        if ch == '"':
            return self.parse_literal()
        self.scanner.error("invalid triple term object")


class TurtleParser(BaseParser):
    """Parser for the repository's RDF 1.2 Turtle grammar."""

    def __init__(self, text: str, source: str, base_iri: str | None):
        """Initialize the `TurtleParser` instance."""
        super().__init__(text, source)
        self.base_iri = base_iri
        self.prefixes: dict[str, str] = {}

    def parse(self) -> list[Triple]:
        """Parse the current document and return parsed triples."""
        while True:
            skip_ws_comments(self.scanner)
            if self.scanner.eof():
                return self.triples
            if self.parse_directive_if_present():
                continue
            self.parse_triples_statement()
            skip_ws_comments(self.scanner)
            self.scanner.expect(".", "expected '.' to end Turtle triple statement")

    def parse_directive_if_present(self) -> bool:
        """Parse directive if present from the current input and return the result."""
        if is_keyword_with_extra_boundary(self.scanner, "@prefix", ":"):
            self.scanner.expect("@prefix")
            skip_ws_comments(self.scanner)
            prefix = self.parse_pname_ns()
            skip_ws_comments(self.scanner)
            iri = self.parse_iri_ref_turtle()
            skip_ws_comments(self.scanner)
            self.scanner.expect(".", "expected '.' after @prefix")
            self.prefixes[prefix] = iri
            return True
        if is_keyword_with_extra_boundary(self.scanner, "@base", "<"):
            self.scanner.expect("@base")
            skip_ws_comments(self.scanner)
            self.base_iri = self.parse_iri_ref_turtle()
            skip_ws_comments(self.scanner)
            self.scanner.expect(".", "expected '.' after @base")
            return True
        if is_keyword_with_extra_boundary(self.scanner, "@version", "\"'"):
            self.scanner.expect("@version")
            skip_ws_comments(self.scanner)
            self.parse_version_specifier()
            skip_ws_comments(self.scanner)
            self.scanner.expect(".", "expected '.' after @version")
            return True
        if is_keyword_ci_with_extra_boundary(self.scanner, "PREFIX", ":"):
            for _ in "PREFIX":
                self.scanner.advance()
            skip_ws_comments(self.scanner)
            prefix = self.parse_pname_ns()
            skip_ws_comments(self.scanner)
            iri = self.parse_iri_ref_turtle()
            self.prefixes[prefix] = iri
            return True
        if is_keyword_ci_with_extra_boundary(self.scanner, "BASE", "<"):
            for _ in "BASE":
                self.scanner.advance()
            skip_ws_comments(self.scanner)
            self.base_iri = self.parse_iri_ref_turtle()
            return True
        if is_keyword_ci_with_extra_boundary(self.scanner, "VERSION", "\"'"):
            for _ in "VERSION":
                self.scanner.advance()
            skip_ws_comments(self.scanner)
            self.parse_version_specifier()
            return True
        return False

    def parse_version_specifier(self) -> str:
        """Parse version specifier from the current input and return the result."""
        if self.scanner.peek() == '"':
            return parse_short_string(self.scanner, '"', allow_single_quote_escape=True)
        if self.scanner.peek() == "'":
            return parse_short_string(self.scanner, "'", allow_single_quote_escape=True)
        self.scanner.error("expected version specifier string")

    def parse_triples_statement(self) -> None:
        """Parse triples statement from the current input and return the result."""
        skip_ws_comments(self.scanner)
        if self.scanner.startswith("<<") and not self.scanner.startswith("<<("):
            subject, _ = self.parse_reified_triple(needs_subject_reference=True)
            skip_ws_comments(self.scanner)
            if self.can_start_verb():
                pairs = self.parse_pairs_structure(
                    terminators=(".",), allow_a_verb=True
                )
                self.emit_pairs_from_structure(subject, pairs)
            return

        if self.scanner.peek() == "[":
            subject = self.parse_blank_node_property_list()
            skip_ws_comments(self.scanner)
            if self.can_start_verb():
                pairs = self.parse_pairs_structure(
                    terminators=(".",), allow_a_verb=True
                )
                self.emit_pairs_from_structure(subject, pairs)
            return

        ordinary_subject = self.parse_subject()
        skip_ws_comments(self.scanner)
        pairs = self.parse_pairs_structure(terminators=(".",), allow_a_verb=True)
        self.emit_pairs_from_structure(ordinary_subject, pairs)

    def parse_pairs_structure(
        self,
        terminators: tuple[str, ...],
        allow_a_verb: bool,
    ) -> list[tuple[IRI, list[tuple[Node, AnnotationData]]]]:
        """Parse pairs structure from the current input and return the result."""
        pairs: list[tuple[IRI, list[tuple[Node, AnnotationData]]]] = []
        predicate = self.parse_verb(allow_a=allow_a_verb)
        skip_ws_comments(self.scanner)
        objects = self.parse_object_list_structure()
        pairs.append((predicate, objects))

        while True:
            skip_ws_comments(self.scanner)
            if any(self.scanner.startswith(tok) for tok in terminators):
                break
            if not self.scanner.consume(";"):
                break
            skip_ws_comments(self.scanner)
            while self.scanner.consume(";"):
                skip_ws_comments(self.scanner)
            if any(self.scanner.startswith(tok) for tok in terminators):
                break
            if not self.can_start_verb():
                self.scanner.error("expected predicate after ';'")
            predicate = self.parse_verb(allow_a=allow_a_verb)
            skip_ws_comments(self.scanner)
            objects = self.parse_object_list_structure()
            pairs.append((predicate, objects))
        return pairs

    def parse_object_list_structure(self) -> list[tuple[Node, AnnotationData]]:
        """Parse object list structure from the current input and return the result."""
        out: list[tuple[Node, AnnotationData]] = []
        while True:
            obj = self.parse_object()
            annotation = self.parse_annotation_data()
            out.append((obj, annotation))
            skip_ws_comments(self.scanner)
            if not self.scanner.consume(","):
                break
            skip_ws_comments(self.scanner)
        return out

    def parse_annotation_data(self) -> AnnotationData:
        """Parse annotation data from the current input and return the result."""
        annotation = AnnotationData()
        while True:
            skip_ws_comments(self.scanner)
            if self.scanner.consume("~"):
                skip_ws_comments(self.scanner)
                if self.can_start_iri_or_blanknode():
                    reifier = self.parse_iri_or_blanknode()
                else:
                    reifier = self.new_bnode()
                annotation.reifiers.append(reifier)
                annotation.events.append(("reifier", reifier))
                continue
            if self.scanner.startswith("{|"):
                block = self.parse_annotation_block_structure()
                annotation.blocks.append(block)
                annotation.events.append(("block", block))
                continue
            break
        return annotation

    def parse_annotation_block_structure(
        self,
    ) -> list[tuple[IRI, list[tuple[Node, AnnotationData]]]]:
        """Parse annotation block structure from the current input and return the result."""
        self.scanner.expect("{|")
        skip_ws_comments(self.scanner)
        pairs = self.parse_pairs_structure(terminators=("|}",), allow_a_verb=True)
        skip_ws_comments(self.scanner)
        self.scanner.expect("|}", "expected '|}' to close annotation block")
        return pairs

    def parse_subject(self) -> Node:
        """Parse subject from the current input and return the result."""
        if self.scanner.peek() == "(":
            return self.parse_collection_subject()
        if self.scanner.peek() == "[":
            return self.parse_blank_node_property_list()
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        return self.parse_iri()

    def parse_verb(self, allow_a: bool) -> IRI:
        """Parse verb from the current input and return the result."""
        if allow_a and is_keyword(self.scanner, "a"):
            self.scanner.expect("a")
            return IRI(RDF_TYPE_IRI)
        return self.parse_predicate()

    def parse_predicate(self) -> IRI:
        """Parse predicate from the current input and return the result."""
        return self.parse_iri()

    def parse_object(self) -> Node:
        """Parse object from the current input and return the result."""
        if self.scanner.startswith("<<("):
            return self.parse_triple_term()
        if self.scanner.startswith("<<"):
            ref_subject, _ = self.parse_reified_triple(needs_subject_reference=False)
            return ref_subject
        if self.scanner.peek() == "[":
            return self.parse_blank_node_property_list()
        if self.scanner.peek() == "(":
            return self.parse_collection_subject()
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()

        ch = self.scanner.peek()
        if ch == '"':
            return self.parse_rdf_literal(double_quote=True)
        if ch == "'":
            return self.parse_rdf_literal(double_quote=False)
        if is_keyword(self.scanner, "true"):
            self.scanner.expect("true")
            return Literal(value="true", datatype=XSD_BOOLEAN_IRI)
        if is_keyword(self.scanner, "false"):
            self.scanner.expect("false")
            return Literal(value="false", datatype=XSD_BOOLEAN_IRI)
        if ch in "+-." or ch.isdigit():
            numeric = self.try_parse_numeric_literal()
            if numeric is not None:
                return numeric
        return self.parse_iri()

    def try_parse_numeric_literal(self) -> Literal | None:
        """Try to parse numeric literal from the current input."""
        tail = self.scanner.text[self.scanner.i :]
        patterns = (
            (
                re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)[eE][+-]?[0-9]+"),
                XSD_DOUBLE_IRI,
            ),
            (re.compile(r"[+-]?(?:[0-9]*\.[0-9]+)"), XSD_DECIMAL_IRI),
            (re.compile(r"[+-]?[0-9]+"), XSD_INTEGER_IRI),
        )
        for regex, datatype in patterns:
            match = regex.match(tail)
            if not match:
                continue
            token = match.group(0)
            nxt = tail[len(token) : len(token) + 1]
            if nxt and not (is_name_boundary(nxt) or nxt in ")]};,|/*+-=<>!&"):
                continue
            for _ in token:
                self.scanner.advance()
            return Literal(value=token, datatype=datatype)
        return None

    def parse_rdf_literal(self, double_quote: bool) -> Literal:
        """Parse RDF literal from the current input and return the result."""
        quote = '"' if double_quote else "'"
        if self.scanner.startswith(quote * 3):
            value = parse_long_string(
                self.scanner, quote, allow_single_quote_escape=True
            )
        else:
            value = parse_short_string(
                self.scanner, quote, allow_single_quote_escape=True
            )

        lang = None
        direction = None
        datatype = None
        if self.scanner.peek() == "@":
            lang, direction = parse_lang_dir(self.scanner)
        elif self.scanner.consume("^^"):
            datatype = self.parse_iri().value
            if datatype in (RDF_LANG_STRING_IRI, RDF_DIR_LANG_STRING_IRI):
                self.scanner.error(
                    "rdf:langString and rdf:dirLangString datatypes are not allowed"
                )
        return Literal(value=value, lang=lang, direction=direction, datatype=datatype)

    def parse_collection_subject(self) -> IRI | BNode:
        """Parse collection subject from the current input and return the result."""
        self.scanner.expect("(")
        skip_ws_comments(self.scanner)
        items: list[Node] = []
        while not self.scanner.consume(")"):
            item = self.parse_object()
            items.append(item)
            skip_ws_comments(self.scanner)
            if self.scanner.eof():
                self.scanner.error("unterminated collection")
        if not items:
            return IRI(RDF_NIL_IRI)

        head = self.new_bnode()
        current = head
        for idx, item in enumerate(items):
            self.emit(current, IRI(RDF_FIRST_IRI), item)
            if idx == len(items) - 1:
                self.emit(current, IRI(RDF_REST_IRI), IRI(RDF_NIL_IRI))
            else:
                nxt = self.new_bnode()
                self.emit(current, IRI(RDF_REST_IRI), nxt)
                current = nxt
        return head

    def parse_blank_node_property_list(self) -> BNode:
        """Parse blank-node property list from the current input and return the result."""
        self.scanner.expect("[")
        skip_ws_comments(self.scanner)
        subject = self.new_bnode()
        if self.scanner.consume("]"):
            return subject
        pairs = self.parse_pairs_structure(terminators=("]",), allow_a_verb=True)
        self.emit_pairs_from_structure(subject, pairs)
        skip_ws_comments(self.scanner)
        self.scanner.expect("]", "expected ']' to close blank node property list")
        return subject

    def parse_reified_triple(
        self, needs_subject_reference: bool
    ) -> tuple[IRI | BNode, TripleTerm]:
        """Parse reified triple syntax from the current input and return the result."""
        self.scanner.expect("<<")
        skip_ws_comments(self.scanner)
        subject = self.parse_rt_subject()
        skip_ws_comments(self.scanner)
        predicate = self.parse_verb(allow_a=True)
        skip_ws_comments(self.scanner)
        obj = self.parse_rt_object()
        skip_ws_comments(self.scanner)

        reifier: IRI | BNode | None = None
        if self.scanner.consume("~"):
            skip_ws_comments(self.scanner)
            if self.can_start_iri_or_blanknode():
                reifier = self.parse_iri_or_blanknode()
            else:
                reifier = self.new_bnode()
            skip_ws_comments(self.scanner)

        self.scanner.expect(">>", "expected '>>' to close reified triple")

        term = TripleTerm(subject=subject, predicate=predicate, object=obj)
        if reifier is not None:
            ref_subject = reifier
        else:
            ref_subject = self.new_bnode()
        self.emit(ref_subject, IRI(RDF_REIFIES_IRI), term)
        return ref_subject, term

    def parse_rt_subject(self) -> Node:
        """Parse reified-triple subject from the current input and return the result."""
        if self.scanner.startswith("<<") and not self.scanner.startswith("<<("):
            reifier, _ = self.parse_reified_triple(needs_subject_reference=False)
            return reifier
        if self.scanner.peek() == "[":
            return self.parse_rt_empty_blank_node()
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        return self.parse_iri()

    def parse_rt_object(self) -> Node:
        """Parse reified-triple object from the current input and return the result."""
        if self.scanner.startswith("<<("):
            return self.parse_triple_term()
        if self.scanner.startswith("<<"):
            ref_subject, _ = self.parse_reified_triple(needs_subject_reference=False)
            return ref_subject
        if self.scanner.peek() == "[":
            return self.parse_rt_empty_blank_node()
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        ch = self.scanner.peek()
        if ch in ('"', "'"):
            return self.parse_rdf_literal(double_quote=(ch == '"'))
        if is_keyword(self.scanner, "true"):
            self.scanner.expect("true")
            return Literal(value="true", datatype=XSD_BOOLEAN_IRI)
        if is_keyword(self.scanner, "false"):
            self.scanner.expect("false")
            return Literal(value="false", datatype=XSD_BOOLEAN_IRI)
        if ch in "+-." or ch.isdigit():
            numeric = self.try_parse_numeric_literal()
            if numeric is not None:
                return numeric
        return self.parse_iri()

    def parse_triple_term(self) -> TripleTerm:
        """Parse triple-term node from the current input and return the result."""
        self.scanner.expect("<<(")
        skip_ws_comments(self.scanner)
        subject = self.parse_tt_subject()
        skip_ws_comments(self.scanner)
        predicate = self.parse_verb(allow_a=True)
        skip_ws_comments(self.scanner)
        obj = self.parse_tt_object()
        skip_ws_comments(self.scanner)
        self.scanner.expect(")>>", "expected ')>>' to close triple term")
        return TripleTerm(subject=subject, predicate=predicate, object=obj)

    def parse_tt_subject(self) -> Node:
        """Parse triple-term subject from the current input and return the result."""
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        return self.parse_iri()

    def parse_tt_object(self) -> Node:
        """Parse triple-term object from the current input and return the result."""
        if self.scanner.startswith("<<("):
            return self.parse_triple_term()
        if self.scanner.startswith("<<"):
            ref_subject, _ = self.parse_reified_triple(needs_subject_reference=False)
            return ref_subject
        if self.scanner.peek() == "[":
            return self.parse_blank_node_property_list()
        if self.scanner.peek() == "(":
            return self.parse_collection_subject()
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        ch = self.scanner.peek()
        if ch in ('"', "'"):
            return self.parse_rdf_literal(double_quote=(ch == '"'))
        if is_keyword(self.scanner, "true"):
            self.scanner.expect("true")
            return Literal(value="true", datatype=XSD_BOOLEAN_IRI)
        if is_keyword(self.scanner, "false"):
            self.scanner.expect("false")
            return Literal(value="false", datatype=XSD_BOOLEAN_IRI)
        if ch in "+-." or ch.isdigit():
            numeric = self.try_parse_numeric_literal()
            if numeric is not None:
                return numeric
        return self.parse_iri()

    def parse_iri_or_blanknode(self) -> IRI | BNode:
        """Parse IRI or blanknode from the current input and return the result."""
        if self.scanner.startswith("_:"):
            return self.parse_blank_node_label()
        return self.parse_iri()

    def can_start_iri_or_blanknode(self) -> bool:
        """Return whether the next token can start an IRI or blank node."""
        if self.scanner.startswith("_:"):
            return True
        ch = self.scanner.peek()
        return ch == "<" or ch == ":" or is_pn_chars_base(ch)

    def parse_rt_empty_blank_node(self) -> BNode:
        """Parse reified-triple empty blank node from the current input and return the result."""
        self.scanner.expect("[")
        skip_ws_comments(self.scanner)
        if not self.scanner.consume("]"):
            self.scanner.error("reified triple allows only empty blank node []")
        return self.new_bnode()

    def parse_blank_node_label(self) -> BNode:
        """Parse blank node label from the current input and return the result."""
        self.scanner.expect("_:")
        if not (is_pn_chars_u(self.scanner.peek()) or self.scanner.peek().isdigit()):
            self.scanner.error("invalid blank node label")
        chars = [self.scanner.advance()]
        while True:
            ch = self.scanner.peek()
            if not ch:
                break
            if is_pn_chars(ch):
                chars.append(self.scanner.advance())
                continue
            if ch == ".":
                nxt = self.scanner.peek(1)
                if nxt and (nxt == "." or is_pn_chars(nxt)):
                    chars.append(self.scanner.advance())
                    continue
                break
            break
        label = "".join(chars)
        self._reserved_labels.add(label)
        return BNode(label)

    def parse_iri(self) -> IRI:
        """Parse IRI from the current input and return the result."""
        if self.scanner.peek() == "<":
            return IRI(self.parse_iri_ref_turtle())
        return IRI(self.parse_prefixed_name())

    def parse_iri_ref_turtle(self) -> str:
        """Parse Turtle IRI reference from the current input and return the result."""
        try:
            iri = parse_iri_ref(self.scanner, require_absolute=False, allow_empty=True)
        except ValueError as exc:
            self.scanner.error(str(exc))
            raise AssertionError("unreachable")
        if self.base_iri is not None and not urlsplit(iri).scheme:
            return resolve_iri_reference(self.base_iri, iri)
        return iri

    def parse_prefixed_name(self) -> str:
        """Parse prefixed name from the current input and return the result."""
        prefix = self.parse_pname_ns()
        local = ""
        if not is_name_boundary(self.scanner.peek()):
            local = self.parse_pn_local()
        if prefix not in self.prefixes:
            self.scanner.error(f"undeclared prefix '{prefix}'")
        return self.prefixes[prefix] + local

    def parse_pname_ns(self) -> str:
        """Parse PName namespace prefix from the current input and return the result."""
        if self.scanner.consume(":"):
            return ""
        if not is_pn_chars_base(self.scanner.peek()):
            self.scanner.error("invalid prefix name")
        chars = [self.scanner.advance()]
        while True:
            ch = self.scanner.peek()
            if not ch:
                self.scanner.error("unterminated prefix name")
            if ch == ":":
                self.scanner.advance()
                if chars[-1] == ".":
                    self.scanner.error("prefix cannot end with '.'")
                return "".join(chars)
            if is_pn_chars(ch) or ch == ".":
                chars.append(self.scanner.advance())
                continue
            self.scanner.error("invalid character in prefix")

    def parse_pn_local(self) -> str:
        """Parse PN_LOCAL text from the current input and return the result."""
        parts: list[str] = []
        endable = False

        first = self.scanner.peek()
        if first == "%":
            parts.append(self.parse_percent())
            endable = True
        elif first == "\\":
            parts.append(self.parse_pn_local_escape())
            endable = True
        elif first == ":" or first.isdigit() or is_pn_chars_u(first):
            parts.append(self.scanner.advance())
            endable = True
        else:
            self.scanner.error("invalid local name")

        while True:
            ch = self.scanner.peek()
            if not ch:
                break
            if ch == "%":
                parts.append(self.parse_percent())
                endable = True
                continue
            if ch == "\\":
                parts.append(self.parse_pn_local_escape())
                endable = True
                continue
            if ch == ":" or is_pn_chars(ch):
                parts.append(self.scanner.advance())
                endable = True
                continue
            if ch == ".":
                nxt = self.scanner.peek(1)
                if nxt and (
                    nxt == "."
                    or nxt == "%"
                    or nxt == "\\"
                    or nxt == ":"
                    or is_pn_chars(nxt)
                ):
                    parts.append(self.scanner.advance())
                    endable = False
                    continue
                break
            break

        if not endable:
            self.scanner.error("local name cannot end with '.'")
        return "".join(parts)

    def parse_percent(self) -> str:
        """Parse percent from the current input and return the result."""
        self.scanner.expect("%")
        a = self.scanner.peek()
        if not is_hex(a):
            self.scanner.error("invalid percent escape")
        self.scanner.advance()
        b = self.scanner.peek()
        if not is_hex(b):
            self.scanner.error("invalid percent escape")
        self.scanner.advance()
        return f"%{a}{b}"

    def parse_pn_local_escape(self) -> str:
        """Parse PN_LOCAL escape sequence from the current input and return the result."""
        self.scanner.expect("\\")
        ch = self.scanner.peek()
        allowed = "_~.-!$&'()*+,;=/?#@%"
        if ch not in allowed:
            self.scanner.error("invalid PN_LOCAL escape")
        self.scanner.advance()
        return ch

    def can_start_verb(self) -> bool:
        """Return whether the next token can start a Turtle verb."""
        if is_keyword(self.scanner, "a"):
            return True
        ch = self.scanner.peek()
        if ch == "<" or ch == ":":
            return True
        return is_pn_chars_base(ch)


def format_node_nt(node: Node) -> str:
    """Format an RDF node using N-Triples syntax."""
    if isinstance(node, IRI):
        return encode_iri_ref(node.value)
    if isinstance(node, BNode):
        return f"_:{node.label}"
    if isinstance(node, Literal):
        base = f'"{escape_string_value(node.value)}"'
        if node.lang is not None:
            if node.direction is not None:
                return f"{base}@{node.lang}--{node.direction}"
            return f"{base}@{node.lang}"
        if node.datatype is not None:
            if node.datatype == f"{XSD_NS}string":
                return base
            return f"{base}^^{encode_iri_ref(node.datatype)}"
        return base
    if isinstance(node, TripleTerm):
        subject = format_node_nt(node.subject)
        predicate = format_node_nt(node.predicate)
        obj = format_node_nt(node.object)
        return f"<<( {subject} {predicate} {obj} )>>"
    raise TypeError(f"unsupported node type: {type(node)!r}")


def serialize_ntriples(triples: list[Triple]) -> str:
    """Serialize triples to deterministic N-Triples text."""
    lines: list[str] = []
    for subject, predicate, obj in triples:
        s = format_node_nt(subject)
        p = format_node_nt(predicate)
        o = format_node_nt(obj)
        lines.append(f"{s} {p} {o} .")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"
