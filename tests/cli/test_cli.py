import json
import subprocess
import sys

import pytest

from sparql_rl import infer, parse_rules, prepare_rules, query
from sparql_rl.cli import main
from sparql_rl.rdf.io import parse_data
from sparql_rl.rdf.parser import IRI

RULES = "RULE {?s <urn:q> ?o} WHERE {?s <urn:p> ?o}"
DATA = "<urn:a> <urn:p> <urn:b> ."


@pytest.mark.parametrize("args", [["parse"], ["check", "--level", "syntax"]])
def test_syntax_only_accepts_symmetric_data(args, capsys):
    assert main([*args, "-R", "DATA { 1 <urn:p> 2 }"]) == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize("rules_file", [False, True])
@pytest.mark.parametrize("data_file", [False, True])
def test_input_matrix(tmp_path, capsys, rules_file, data_file):
    r, d = tmp_path / "rules.srl", tmp_path / "data.ttl"
    r.write_text(RULES)
    d.write_text(DATA)
    args = [
        "infer",
        *(["-r", str(r)] if rules_file else ["-R", RULES]),
        *(["-d", str(d)] if data_file else ["-D", DATA]),
    ]
    assert main(args) == 0
    result = parse_data(capsys.readouterr().out)
    assert set(result) == {(IRI("urn:a"), IRI("urn:q"), IRI("urn:b"))}


def test_library_api_does_not_mutate_base():
    base = parse_data(DATA)
    rules = prepare_rules(parse_rules(RULES))
    assert len(infer(rules, base)) == 1
    assert len(base) == 1
    assert len(infer(rules, base, include_base=True)) == 2
    result = query(rules, base, "{?s <urn:q> ?o}")
    assert result.boolean
    assert len(result.bindings) == 1


@pytest.mark.parametrize(
    "command,extra",
    [
        ("parse", ["--json"]),
        ("check", []),
        ("check", ["--level", "syntax"]),
        ("check", ["--level", "wellformed"]),
        ("explain", ["--format", "json"]),
        ("explain", ["--format", "dot"]),
        ("explain", []),
    ],
)
def test_diagnostics(capsys, command, extra):
    assert main([command, "-R", RULES, *extra]) == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize("format", ["json", "table", "boolean"])
def test_query(capsys, format):
    assert (
        main(
            [
                "query",
                "-R",
                RULES,
                "-D",
                DATA,
                "--goal",
                "{?s <urn:q> ?o}",
                "--format",
                format,
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    if format == "json":
        assert len(json.loads(output)["results"]["bindings"]) == 1
    else:
        assert output
    assert main(["query", "-R", RULES, "--goal", "{?s <urn:q> ?o}"]) == 1


def test_scope_isolation(capsys):
    assert (
        main(
            ["parse", "-R", "PREFIX : <urn:example:> DATA {}", "-R", "DATA {:a :p :b}"]
        )
        == 3
    )
    assert "undeclared prefix" in capsys.readouterr().err


def test_stdin_and_output(tmp_path, monkeypatch):
    from io import StringIO

    monkeypatch.setattr(sys, "stdin", StringIO(DATA))
    output = tmp_path / "result.nt"
    assert main(["infer", "-R", RULES, "-d", "-", "-o", str(output)]) == 0
    assert len(parse_data(output.read_text())) == 1
    with pytest.raises(SystemExit) as error:
        main(["infer", "-r", "-", "-d", "-"])
    assert error.value.code == 2


@pytest.mark.parametrize(
    "rules,code",
    [
        ("INVALID", 3),
        ("RULE {?x <urn:p> ?y} WHERE {}", 4),
        ("RULE {?x <urn:p> ?y} WHERE {?x <urn:p> ?y SET(?z := 1)}", 5),
        ("IMPORTS <https://example.org/rules.srl>", 6),
    ],
)
def test_errors(capsys, rules, code):
    assert main(["check", "-R", rules]) == code
    assert capsys.readouterr().err


def test_module_and_executable():
    for command in (
        [sys.executable, "-m", "sparql_rl"],
        [str(__import__("pathlib").Path(sys.executable).parent / "sparql-rl")],
    ):
        process = subprocess.run(
            [*command, "--version"], capture_output=True, text=True, check=True
        )
        assert "2026-09-02" in process.stdout


def test_additional_formats_stats_and_aliases(capsys):
    assert main(["infer", "-R", RULES, "-D", DATA, "-f", "rdfxml", "--stats"]) == 0
    output = capsys.readouterr()
    assert "<rdf:RDF" in output.out
    assert json.loads(output.err)["exit_code"] == 0
    assert (
        main(
            [
                "query",
                "-R",
                RULES,
                "-D",
                DATA,
                "--goal",
                "{?s <urn:q> ?o}",
                "--result-format",
                "tsv",
            ]
        )
        == 0
    )


def test_dataset_policy_and_rdf_error(capsys):
    data = "<urn:g> {<urn:a> <urn:p> <urn:b>}"
    assert main(["infer", "-R", RULES, "-D", data, "--data-string-format", "trig"]) == 7
    assert (
        main(
            [
                "infer",
                "-R",
                RULES,
                "-D",
                data,
                "--data-string-format",
                "trig",
                "--dataset-policy",
                "union",
            ]
        )
        == 0
    )


def test_explicit_rule_file_is_not_reimported(tmp_path, capsys):
    source = tmp_path / "root.srl"
    source.write_text("IMPORTS <root.srl> DATA {[] <urn:p> 1}")
    assert main(["infer", "-r", str(source)]) == 0
    assert len(parse_data(capsys.readouterr().out)) == 1


def test_bash_launcher_from_another_directory(tmp_path):
    from pathlib import Path

    launcher = Path(__file__).resolve().parents[2] / "pysparqlrl.sh"
    process = subprocess.run(
        [str(launcher), "infer", "-R", RULES, "-D", DATA],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(parse_data(process.stdout)) == 1
    process = subprocess.run(
        [
            str(launcher),
            "query",
            "-R",
            RULES,
            "--goal",
            "{?s <urn:q> ?o}",
            "--result-format",
            "boolean",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 1
    assert process.stdout.strip() == "false"


def test_rules_base_does_not_change_import_identity(tmp_path, capsys):
    source = tmp_path / "self.srl"
    source.write_text(f"IMPORTS <{source.as_uri()}> DATA {{ [] <urn:p> 1 }}")
    assert (
        main(["infer", "-r", str(source), "--rules-base", "http://example/base/"]) == 0
    )
    assert len(parse_data(capsys.readouterr().out)) == 1


def test_malformed_rdfxml_has_rdf_input_exit_code():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sparql_rl",
            "infer",
            "-R",
            "DATA {}",
            "-D",
            "<broken",
            "--data-string-format",
            "rdfxml",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 7
    assert "RDF input error" in result.stderr
    assert "Traceback" not in result.stderr
    assert not result.stdout


@pytest.mark.parametrize("active_name", ["python", "python3"])
def test_bash_launcher_prefers_active_path_python(tmp_path, active_name):
    import os
    import shlex
    import shutil
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copy2(root / "pysparqlrl.sh", checkout / "pysparqlrl.sh")
    (checkout / "src").symlink_to(root / "src", target_is_directory=True)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    active = binaries / active_name
    active.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    active.chmod(0o755)
    newer = binaries / "python3.13"
    newer.write_text('#!/bin/sh\n[ "$1" = "-c" ] && exit 0\nexit 73\n')
    newer.chmod(0o755)
    for command in ("bash", "dirname"):
        executable = shutil.which(command)
        assert executable is not None
        (binaries / command).symlink_to(executable)
    env = dict(os.environ, PATH=str(binaries))
    env.pop("PYSPARQLRL_PYTHON", None)
    result = subprocess.run(
        [str(checkout / "pysparqlrl.sh"), "infer", "-R", RULES, "-D", DATA],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(parse_data(result.stdout)) == 1
