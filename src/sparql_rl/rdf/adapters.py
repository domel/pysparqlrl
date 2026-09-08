"""RDFLib parser adapters that retain the source literal lexical forms.

Adapters use per-parser hooks; RDFLib globals and datatype registries are untouched.
"""

import json
from io import StringIO
from typing import cast
from xml.sax.handler import ContentHandler

import rdflib
from rdflib.parser import create_input_source
from rdflib.plugins.parsers.jsonld import Parser as JSONLDParser
from rdflib.plugins.parsers.notation3 import RDFSink
from rdflib.plugins.parsers.nquads import NQuadsParser
from rdflib.plugins.parsers.ntriples import r_literal, unquote
from rdflib.plugins.parsers.rdfxml import RDFXMLHandler, create_parser
from rdflib.plugins.parsers.trig import TrigSinkParser
from rdflib.plugins.shared.jsonld.context import Context


class LexicalXMLHandler(RDFXMLHandler):
    def property_element_end(self, name, qname):
        current = self.current
        if current.data is not None and current.object is None:
            current.object = rdflib.Literal(
                current.data,
                lang=None if current.datatype else current.language,
                datatype=current.datatype,
                normalize=False,
            )
            current.data = None
        super().property_element_end(name, qname)


class LexicalJSONLDParser(JSONLDParser):
    def _to_object(self, dataset, graph, context, term, node, inlist=False):
        result = super()._to_object(dataset, graph, context, term, node, inlist)
        if isinstance(result, rdflib.Literal):
            if (term and term.type == "@json") or (
                isinstance(node, dict) and context.get_type(node) == "@json"
            ):
                return result
            value = context.get_value(node) if isinstance(node, dict) else node
            if isinstance(value, tuple):
                value = value[0]
            if isinstance(value, str):
                return rdflib.Literal(
                    value,
                    lang=result.language,
                    datatype=result.datatype,
                    normalize=False,
                )
        return result


class LexicalSink(RDFSink):
    def newLiteral(self, s, dt, lang):
        return rdflib.Literal(
            s, lang=None if dt else lang, datatype=dt, normalize=False
        )


class LexicalNQuadsParser(NQuadsParser):
    def literal(self):
        original = self.line
        result = super().literal()
        if isinstance(result, rdflib.Literal):
            assert original is not None
            match = r_literal.match(original)
            assert match is not None
            return rdflib.Literal(
                unquote(match.group(1)),
                lang=result.language,
                datatype=result.datatype,
                normalize=False,
            )
        return result


def parse_rdflib(text: str, format: str, base_iri: str | None) -> rdflib.Graph:
    if format == "json-ld":
        graph = rdflib.Graph()
        LexicalJSONLDParser().parse(json.loads(text), Context(base=base_iri), graph)
        return graph
    if format == "trig":
        dataset = rdflib.Dataset()
        sink = LexicalSink(dataset)
        parser = TrigSinkParser(
            sink, baseURI=base_iri or dataset.absolutize(""), turtle=True
        )
        parser.loadStream(StringIO(text))
        for prefix, namespace in parser._bindings.items():
            dataset.bind(prefix, namespace)
        return dataset
    source = create_input_source(data=text, publicID=base_iri)
    try:
        if format == "nquads":
            dataset = rdflib.Dataset()
            LexicalNQuadsParser().parse(source, dataset)
            return dataset
        graph = rdflib.Graph()
        parser_xml = create_parser(source, graph)
        parser_xml.setContentHandler(cast(ContentHandler, LexicalXMLHandler(graph)))
        parser_xml.parse(source)
        return graph
    finally:
        source.close()
