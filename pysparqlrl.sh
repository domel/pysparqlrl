#!/usr/bin/env bash
# Run the checkout's command-line interface without changing the caller's directory.
set -euo pipefail

pysparqlrl_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
pysparqlrl_python="${PYSPARQLRL_PYTHON:-}"

if [[ -z "$pysparqlrl_python" && -x "$pysparqlrl_root/.venv/bin/python" ]]; then
    pysparqlrl_python="$pysparqlrl_root/.venv/bin/python"
fi

if [[ -z "$pysparqlrl_python" ]]; then
    for pysparqlrl_candidate in python python3 python3.13 python3.12 python3.11; do
        if command -v "$pysparqlrl_candidate" >/dev/null 2>&1 &&
            "$pysparqlrl_candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
            pysparqlrl_python="$pysparqlrl_candidate"
            break
        fi
    done
fi

if [[ -z "$pysparqlrl_python" ]]; then
    echo 'Python >= 3.11 is required. Create .venv or set PYSPARQLRL_PYTHON.' >&2
    exit 2
fi

export PYTHONPATH="$pysparqlrl_root/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$pysparqlrl_python" -m sparql_rl "$@"
