import json
from os import (
    environ,
    getcwd,
)
from os.path import (
    abspath,
    exists,
    join,
)
import subprocess
import sys
import tempfile
from typing import (
    Any,
    List,
    Optional,
    Tuple,
)

DEBUG: bool = "MAKES_DEBUG" in environ
FROM: str = environ.get("MAKES_FROM", f"file://{getcwd()}")
VERSION: str = environ["_MAKES_VERSION"]


class Error(Exception):
    pass


def _log(*args: str) -> None:
    print(*args, file=sys.stderr)


def _if(condition: Any, *value: Any) -> List[Any]:
    return list(value) if condition else []


def _nix_build(head: str, attr: str, out: str = "") -> List[str]:
    return [
        environ["_NIX_BUILD"],
        *["--arg", "head", head],
        *["--argstr", "makesVersion", VERSION],
        *["--attr", attr],
        *["--option", "narinfo-cache-negative-ttl", "1"],
        *["--option", "narinfo-cache-positive-ttl", "1"],
        *["--option", "restrict-eval", "false"],
        *["--option", "sandbox", "false"],
        *_if(out, "--out-link", out),
        *_if(not out, "--no-out-link"),
        *_if(DEBUG, "--show-trace"),
        environ["_EVALUATOR"],
    ]


def _get_head_from_file() -> str:
    return abspath(FROM[7:])


def _get_head() -> str:
    if FROM.startswith("file://"):
        return _get_head_from_file()

    raise Error(f"Unable to load Makes project from: {FROM}")


def _get_attrs(head: str) -> List[str]:
    out: str = tempfile.mktemp()
    code, _, _, = _run(
        args=_nix_build(head, "config.attrs", out),
    )
    if code == 0:
        with open(out) as file:
            return json.load(file)

    raise Error(f"Unable to list project outputs from: {FROM}")


def _run(
    args: List[str],
    stdout: bool = False,
    stderr: bool = False,
) -> Tuple[int, bytes, bytes]:
    with subprocess.Popen(
        args=args,
        stdout=subprocess.PIPE if stdout else None,
        stderr=subprocess.PIPE if stderr else None,
    ) as process:
        process.wait()
        out: Any = process.stdout if process.stdout else bytes()
        err: Any = process.stderr if process.stderr else bytes()

        return process.returncode, out, err


def _help_and_exit(attrs: Optional[List[str]] = None) -> None:
    _log(f"Makes v{VERSION}")
    _log()
    _log("Usage: m [OUTPUT] [ARGS]...")
    if attrs is not None:
        _log()
        _log(f"Outputs list for project: {FROM}")
        for attr in attrs:
            _log(f"  {attr}")
    sys.exit(1)


def cli(args: List[str]) -> None:
    if not args[1:]:
        try:
            head: str = _get_head()
            attrs: List[str] = _get_attrs(head)
        except Error:
            _help_and_exit()
        else:
            _help_and_exit(attrs)

    attr: str = args[1]
    args = args[2:]
    head = _get_head()
    attrs = _get_attrs(head)
    if attr not in attrs:
        _help_and_exit(attrs)

    cwd: str = getcwd()
    out: str = join(cwd, f"result{attr.replace('/', '-')}")
    actions_path: str = join(out, "makes-actions.json")

    code, _, _ = _run(
        args=_nix_build(head, f'config.outputs."{attr}"', out),
    )

    if code == 0:
        if exists(actions_path):
            with open(actions_path) as actions_file:
                for action in json.load(actions_file):
                    if action["type"] == "exec":
                        action_target: str = join(out, action["location"][1:])
                        code, _, _ = _run(args=[action_target, *args])
                        sys.exit(code)


def main() -> None:
    try:
        cli(sys.argv)
    except Error as err:
        _log(f"[ERROR] {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()