"""Port brAIn's Home Assistant MCP server into HubNEX: hubnex/mcp_server/brain_server.py.

    python dev/vendor_brain_mcp.py <brain/ha-mcp-server/ha_mcp_server.py> <brain/scripts/brain_exposed.py> <commit sha>

brAIn (BRUH Automation, MIT licence, see hubnex/mcp_server/LICENSE-brain) runs this server as
its own stdio process. HubNEX runs it inside the add-on instead (mcp_server/bridge.py). This
script makes that possible without editing the logic by hand, so a newer upstream can be
taken in by running it again:

  * only the tools in mcp_server/catalog.py stay: the TOOLS entries and TOOL_IMPLEMENTATIONS of
    the others go, and so does every function nothing kept can reach any more;
  * the stdio protocol loop (main, send_response, send_error) goes: bridge.py is the protocol;
  * what brAIn read from its process environment is read per call (mcp_server/context.py):
    os.environ.get -> _env, EXPOSED_ONLY / DENIED_SERVICES / PROTECTED_ENTITIES -> per-call values.

Home Assistant itself is reached through HubNEX's own connections: bridge.py replaces
ha_api_request, ha_api_request_raw and _ws_command (and the panel calls) at load time.
"""

from __future__ import annotations

import ast
import builtins
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hubnex.mcp_server.catalog import ALL_TOOLS  # noqa: E402

OUT = ROOT / "hubnex" / "mcp_server" / "brain_server.py"
OUT_EXPOSED = ROOT / "hubnex" / "mcp_server" / "brain_exposed.py"
# brAIn imports its exposure helper from the sibling scripts/ folder; here it is a module.
SIBLING_IMPORT = re.compile(
    r"sys\.path\.insert\(0, os\.path\.join\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\),\s*"
    r'"\.\.", "scripts"\)\)\n(\s*)import brain_exposed[^\n]*')
DROP_DEFS = {"main", "send_response", "send_error"}
CONTEXT_IMPORT = (
    "from hubnex.mcp_server.context import (  # per call in HubNEX, see context.py\n"
    "    CtxFlag as _CtxFlag, CtxList as _CtxList, env as _env, env_has as _env_has,\n"
    ")\n"
)


def top_names(node) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def span(node, lines) -> tuple[int, int]:
    """0-based [start, end) of a top-level node with its decorators and the comment block right
    above it."""
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]) - 1
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    return start, node.end_lineno


def main(src_path: str, sha: str) -> None:
    src = Path(src_path).read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    keep_tools = set(ALL_TOOLS)

    defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    impl_node = tools_node = None
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            if n.targets[0].id == "TOOL_IMPLEMENTATIONS":
                impl_node = n
            elif n.targets[0].id == "TOOLS":
                tools_node = n
    impl = {k.value: v.value for k, v in zip(impl_node.value.keys, impl_node.value.values)}
    missing = keep_tools - set(impl)
    if missing:
        raise SystemExit(f"upstream has no implementation for: {sorted(missing)}")

    # What must stay: the kept tools' functions, the dispatcher and the response builder, and
    # whatever module-level code (other than the tool tables and the protocol) refers to.
    roots = {impl[t] for t in keep_tools} | {"handle_tool_call", "build_tool_response"}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) or n in (impl_node, tools_node):
            continue
        if isinstance(n, ast.If) and "__name__" in top_names(n.test):
            continue
        roots |= top_names(n) & set(defs)
    keep_defs: set[str] = set()
    todo = [r for r in roots if r in defs]
    while todo:
        name = todo.pop()
        if name in keep_defs or name in DROP_DEFS:
            continue
        keep_defs.add(name)
        todo.extend(top_names(defs[name]) & set(defs))

    cut: list[tuple[int, int]] = []
    for name, node in defs.items():
        if name not in keep_defs:
            cut.append(span(node, lines))
    for n in tree.body:
        if isinstance(n, ast.If) and "__name__" in top_names(n.test):
            cut.append((n.lineno - 1, n.end_lineno))
    for el in tools_node.value.elts:
        name = next((v.value for k, v in zip(el.keys, el.values) if getattr(k, "value", None) == "name"), None)
        if name not in keep_tools:
            cut.append((el.lineno - 1, el.end_lineno))
    for k, v in zip(impl_node.value.keys, impl_node.value.values):
        if k.value not in keep_tools:
            cut.append((k.lineno - 1, v.end_lineno))

    drop = set()
    for a, b in cut:
        drop.update(range(a, b))
    out = [ln for i, ln in enumerate(lines) if i not in drop]
    text = "".join(out)
    # a removed list element can leave its trailing comma alone on a line
    text = re.sub(r"\n[ \t]*,[ \t]*\n", "\n", text)

    # --- the process environment, per call ------------------------------------
    def replace_statement(text: str, name: str, new: str) -> str:
        t = ast.parse(text)
        for n in t.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and getattr(n.targets[0], "id", None) == name:
                ls = text.splitlines(keepends=True)
                return "".join(ls[: n.lineno - 1]) + new + "\n" + "".join(ls[n.end_lineno:])
        raise SystemExit(f"{name} not found")

    text = replace_statement(text, "EXPOSED_ONLY", 'EXPOSED_ONLY = _CtxFlag("exposed_only")')
    text = replace_statement(text, "DENIED_SERVICES", 'DENIED_SERVICES = _CtxList("denied_services")')
    text = replace_statement(text, "PROTECTED_ENTITIES", 'PROTECTED_ENTITIES = _CtxList("protected_entities")')
    text = SIBLING_IMPORT.sub("from hubnex.mcp_server import brain_exposed  # vendored beside this file", text)
    text = re.sub(r"^(\s*)import brain_exposed[^\n]*", r"\1from hubnex.mcp_server import brain_exposed",
                  text, flags=re.M)
    text = re.sub(r'"(\w+)" in os\.environ', r'_env_has("\1")', text)
    text = text.replace("os.environ.get(", "_env(")
    if "os.environ" in text:
        bad = [ln.strip() for ln in text.splitlines() if "os.environ" in ln]
        raise SystemExit(f"os.environ still read: {bad[:5]}")
    # the import goes after the last top-level import of the header
    t = ast.parse(text)
    last_import = max(n.end_lineno for n in t.body[:40] if isinstance(n, (ast.Import, ast.ImportFrom)))
    ls = text.splitlines(keepends=True)
    text = "".join(ls[:last_import]) + CONTEXT_IMPORT + "".join(ls[last_import:])

    text = header("brain/ha-mcp-server/ha_mcp_server.py", sha) + text
    compile(text, str(OUT), "exec")
    check_names(text)
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(text.splitlines())} lines (from {len(lines)}), "
          f"{len(keep_tools)} tools, {len(keep_defs)} functions kept")


def header(path: str, sha: str) -> str:
    return (
        f"# Ported from brAIn by BRUH Automation (MIT licence, see LICENSE-brain):\n"
        f"# {path} at commit {sha}.\n"
        f"# Generated by dev/vendor_brain_mcp.py — do not edit by hand: change that script, catalog.py\n"
        f"# or bridge.py, then run it again. HubNEX runs it in-process (bridge.py), not over stdio.\n"
    )


def vendor_exposed(src_path: str, sha: str) -> None:
    """brAIn's exposure helper, with its environment read through context.py."""
    text = Path(src_path).read_text(encoding="utf-8").replace("os.environ.get(", "_env(")
    if "os.environ" in text:
        raise SystemExit("brain_exposed still reads os.environ")
    t = ast.parse(text)
    last_import = max(n.end_lineno for n in t.body[:20] if isinstance(n, (ast.Import, ast.ImportFrom)))
    ls = text.splitlines(keepends=True)
    text = "".join(ls[:last_import]) + "from hubnex.mcp_server.context import env as _env\n" + "".join(ls[last_import:])
    text = header("brain/scripts/brain_exposed.py", sha) + text
    compile(text, str(OUT_EXPOSED), "exec")
    OUT_EXPOSED.write_text(text, encoding="utf-8")
    print(f"{OUT_EXPOSED.relative_to(ROOT)}: {len(text.splitlines())} lines")


def check_names(text: str) -> None:
    """Every global name a kept function reads must still be defined somewhere."""
    tree = ast.parse(text)
    defined = set(dir(builtins)) | {"__file__", "__name__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            defined.add(n.name)
            if not isinstance(n, ast.ClassDef):
                a = n.args
                defined.update(x.arg for x in a.args + a.kwonlyargs + a.posonlyargs)
                if a.vararg:
                    defined.add(a.vararg.arg)
                if a.kwarg:
                    defined.add(a.kwarg.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            defined.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            defined.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            defined.add(n.name)
        elif isinstance(n, ast.arg):
            defined.add(n.arg)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    undefined = sorted(used - defined)
    if undefined:
        raise SystemExit(f"undefined after pruning: {undefined}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[3])
    vendor_exposed(sys.argv[2], sys.argv[3])
