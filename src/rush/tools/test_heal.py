"""Empirical flaky-test diagnosis and verified AST repair."""

from __future__ import annotations

import ast
import difflib
import hashlib
import os
import random
import sys
from pathlib import Path
from typing import Any

from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..permissions import ExecutionPermissions, check_permissions
from ..safety.redactor import sanitize_value
from .common import run_subprocess

CAUSES = {
    "random": "Unseeded Random State",
    "global": "Global State Leak",
    "async": "Async Race Condition",
}


def _plans(nodes: list[str], runs: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    result = []
    for iteration in range(runs):
        order = list(nodes)
        if iteration % 2:
            order.reverse()
        result.append(
            {
                "iteration": iteration,
                "schedule": "ready" if iteration % 2 == 0 else "delayed",
                "clock_offset_ms": rng.randint(-25, 25),
                "random_seed": seed + iteration,
                "test_order": order,
            }
        )
    return result


def _execute(root: Path, plans, intervention: str) -> list[dict[str, Any]]:
    plugin = root / "_rush_test_heal_perturb.py"
    if not plugin.exists():
        plugin.write_text(
            "import os, sys, time\n"
            "import random\n"
            "_real_time = time.time\n"
            "def pytest_configure(config):\n"
            "    sys.setswitchinterval(1e-6 if os.environ['RUSH_TEST_HEAL_SCHEDULE'] == 'ready' else 0.05)\n"
            "    random.seed(int(os.environ['RUSH_TEST_HEAL_RANDOM_SEED']))\n"
            "def pytest_runtest_setup(item):\n"
            "    offset = int(os.environ['RUSH_TEST_HEAL_CLOCK_OFFSET_MS']) / 1000\n"
            "    time.time = lambda: _real_time() + offset\n"
            "def pytest_runtest_teardown(item):\n"
            "    time.time = _real_time\n",
            encoding="utf-8",
        )
    observations = []
    for plan in plans:
        env = os.environ.copy()
        env["RUSH_TEST_HEAL_SCHEDULE"] = plan["schedule"]
        env["RUSH_TEST_HEAL_CLOCK_OFFSET_MS"] = str(plan["clock_offset_ms"])
        env["RUSH_TEST_HEAL_RANDOM_SEED"] = str(plan["random_seed"])
        proc = run_subprocess(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "_rush_test_heal_perturb",
                *plan["test_order"],
                "-q",
            ],
            cwd=root,
            timeout=120,
            env=env,
        )
        observations.append(
            {
                **plan,
                "intervention": intervention,
                "result": "passed" if proc.returncode == 0 else "failed",
                "exit_code": proc.returncode,
            }
        )
    return observations


class _RandomRepair(ast.NodeTransformer):
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.changed = False

    def _function(self, node):
        has_random_call = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and isinstance(child.func.value, ast.Name)
            and child.func.value.id == "random"
            and child.func.attr
            in {"choice", "choices", "randint", "randrange", "random", "uniform"}
            for child in ast.walk(node)
        )
        self.generic_visit(node)
        if has_random_call:
            insert_at = int(
                bool(
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                )
            )
            node.body[insert_at:insert_at] = [
                ast.ImportFrom(
                    module="random",
                    names=[ast.alias(name="Random", asname="_RushRandom")],
                    level=0,
                ),
                ast.Assign(
                    targets=[ast.Name(id="random", ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id="_RushRandom", ctx=ast.Load()),
                        args=[ast.Constant(self.seed)],
                        keywords=[],
                    ),
                ),
            ]
            self.changed = True
        return node

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function


class _AsyncRepair(ast.NodeTransformer):
    def __init__(self) -> None:
        self.changed = False

    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)
        body = []
        for statement in node.body:
            if (
                isinstance(statement, ast.Assert)
                and isinstance(statement.test, ast.Call)
                and isinstance(statement.test.func, ast.Attribute)
                and statement.test.func.attr in {"done", "is_set"}
                and isinstance(statement.test.func.value, ast.Name)
            ):
                observed = statement.test.func.value.id
                wait = (
                    ast.Name(id=observed, ctx=ast.Load())
                    if statement.test.func.attr == "done"
                    else ast.Call(
                        ast.Attribute(
                            ast.Name(observed, ast.Load()), "wait", ast.Load()
                        ),
                        [],
                        [],
                    )
                )
                body.append(ast.Expr(ast.Await(wait)))
                self.changed = True
            body.append(statement)
        node.body = body
        return node


def _global_repair(tree: ast.Module) -> bool:
    declared = {
        node.targets[0].id: type(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, (ast.List, ast.Dict, ast.Set))
    }
    mutated = {
        node.func.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in declared
        and node.func.attr
        in {
            "add",
            "append",
            "clear",
            "discard",
            "extend",
            "pop",
            "remove",
            "setdefault",
            "update",
        }
    }
    mutable = {name: declared[name] for name in mutated}
    environment_keys = {
        node.slice.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "os"
        and node.value.attr == "environ"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
        and isinstance(node.ctx, (ast.Store, ast.Del))
    }
    if not mutable and not environment_keys:
        return False
    lines = ["@pytest.fixture(autouse=True)", "def _rush_restore_owned_state():"]
    lines += [f"    _rush_before_{name} = {name}.copy()" for name in mutable]
    if environment_keys:
        lines.append("    _rush_missing = object()")
    for key in sorted(environment_keys):
        lines.append(
            f"    _rush_before_env_{len(lines)} = os.environ.get({key!r}, _rush_missing)"
        )
    lines.append("    yield")
    for name, kind in mutable.items():
        lines.append(f"    {name}.clear()")
        method = "extend" if kind is ast.List else "update"
        lines.append(f"    {name}.{method}(_rush_before_{name})")
    env_offsets = range(
        2 + len(mutable) + 1,
        2 + len(mutable) + 1 + len(environment_keys),
    )
    for key, offset in zip(sorted(environment_keys), env_offsets, strict=True):
        lines.append(f"    if _rush_before_env_{offset} is _rush_missing:")
        lines.append(f"        os.environ.pop({key!r}, None)")
        lines.append("    else:")
        lines.append(f"        os.environ[{key!r}] = _rush_before_env_{offset}")
    fixture = ast.parse("\n".join(lines)).body
    offset = 0
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        offset = 1
    while offset < len(tree.body) and isinstance(
        tree.body[offset], (ast.Import, ast.ImportFrom)
    ):
        offset += 1
    imports = [ast.Import(names=[ast.alias(name="pytest")])]
    if environment_keys and not any(
        isinstance(node, ast.Import) and any(alias.name == "os" for alias in node.names)
        for node in tree.body
    ):
        imports.append(ast.Import(names=[ast.alias(name="os")]))
    tree.body[offset:offset] = [*imports, *fixture]
    return True


def _candidate_sources(source: str, seed: int) -> dict[str, str]:
    candidates = {}
    random_tree = ast.parse(source)
    random_repair = _RandomRepair(seed)
    random_repair.visit(random_tree)
    if random_repair.changed:
        candidates["random"] = (
            ast.unparse(ast.fix_missing_locations(random_tree)) + "\n"
        )
    global_tree = ast.parse(source)
    if _global_repair(global_tree):
        candidates["global"] = (
            ast.unparse(ast.fix_missing_locations(global_tree)) + "\n"
        )
    async_tree = ast.parse(source)
    async_repair = _AsyncRepair()
    async_repair.visit(async_tree)
    if async_repair.changed:
        candidates["async"] = ast.unparse(ast.fix_missing_locations(async_tree)) + "\n"
    return {
        cause: candidate
        for cause, candidate in candidates.items()
        if _is_substantive_repair(source, candidate)
    }


def _is_substantive_repair(original: str, candidate: str) -> bool:
    try:
        old_tree = ast.parse(original)
        new_tree = ast.parse(candidate)
    except SyntaxError:
        return False
    old_asserts = [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(old_tree)
        if isinstance(node, ast.Assert)
    ]
    new_asserts = [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(new_tree)
        if isinstance(node, ast.Assert)
    ]
    return ast.dump(old_tree) != ast.dump(new_tree) and old_asserts == new_asserts


def _patch(relative: Path, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{relative.as_posix()}",
            tofile=f"b/{relative.as_posix()}",
        )
    )


class TestHealer:
    """Diagnose only causes proven by one stabilizing AST intervention."""

    __test__ = False

    def __init__(self, project_root: Path | None = None):
        self.project_root = (project_root or Path.cwd()).resolve()

    def __call__(
        self,
        test_path: str,
        *,
        runs: int = 20,
        seed: int = 0,
        dry_run: bool = True,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_build: bool = False,
    ) -> dict[str, Any]:
        return self.diagnose_and_heal(
            test_path,
            runs=runs,
            seed=seed,
            dry_run=dry_run,
            permissions=ExecutionPermissions(
                slow=allow_slow,
                artifact_write=allow_artifact_write,
                build=allow_build,
            ),
        )

    def diagnose_and_heal(
        self,
        test_path: str,
        runs: int = 20,
        *,
        seed: int = 0,
        dry_run: bool = True,
        permissions: ExecutionPermissions | None = None,
    ) -> dict[str, Any]:
        if isinstance(runs, bool) or not isinstance(runs, int) or not 1 <= runs <= 1000:
            return {
                "status": "error",
                "error": "runs must be an integer from 1 to 1000",
            }
        if isinstance(seed, bool) or not isinstance(seed, int):
            return {"status": "error", "error": "seed must be an integer"}
        allowed, missing = check_permissions(
            ExecutionPermissions(slow=True, artifact_write=True), permissions
        )
        if not allowed:
            return {
                "status": "skipped",
                "summary": f"test-heal requires {', '.join(missing)}",
                "runs": runs,
                "seed": seed,
                "dry_run": dry_run,
            }
        try:
            physical = PhysicalRoot(self.project_root)
            relative = Path(test_path)
            if relative.is_absolute():
                relative = relative.relative_to(self.project_root)
            target = physical.open_contained(relative, purpose="read")
            if not target.is_file() or target.suffix != ".py":
                raise ValueError("test target must be a contained Python file")
            original = target.read_text(encoding="utf-8")
            ast.parse(original)
        except (
            ContainmentError,
            OSError,
            UnicodeError,
            SyntaxError,
            ValueError,
        ) as exc:
            return sanitize_value(
                {"status": "error", "error": f"invalid test target: {exc}"}
            ).value
        relative = target.relative_to(self.project_root)
        from ..patch.sandbox import PatchSandboxManager

        manager = PatchSandboxManager(self.project_root)
        sandbox = None
        try:
            sandbox = manager.create_sandbox()
            collected = run_subprocess(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "--collect-only",
                    "-q",
                    relative.as_posix(),
                ],
                cwd=sandbox,
                timeout=120,
            )
            nodes = [
                line.strip()
                for line in collected.stdout.splitlines()
                if line.strip().startswith(f"{relative.as_posix()}::")
            ]
            if collected.returncode != 0 or not nodes:
                raise ValueError("test collection did not produce target test nodes")
            plans = _plans(nodes, runs, seed)
            result = self._diagnose_in_sandbox(
                sandbox,
                relative,
                original,
                plans,
                seed,
                dry_run,
                permissions,
            )
        except Exception as exc:  # noqa: BLE001
            result = sanitize_value(
                {"status": "error", "error": f"test-heal execution failed: {exc}"}
            ).value
        if sandbox is not None:
            try:
                manager.cleanup_sandbox(sandbox)
            except Exception as exc:  # noqa: BLE001
                return sanitize_value(
                    {"status": "error", "error": f"sandbox cleanup failed: {exc}"}
                ).value
        return result

    def _diagnose_in_sandbox(
        self, sandbox, relative, original, plans, seed, dry_run, permissions
    ):
        baseline = _execute(sandbox, plans, "baseline")
        runs = len(plans)
        passes = sum(item["result"] == "passed" for item in baseline)
        failures = runs - passes
        base = {
            "test_path": relative.as_posix(),
            "runs": runs,
            "seed": seed,
            "dry_run": dry_run,
            "passes": passes,
            "failures": failures,
            "is_flaky": passes > 0 and failures > 0,
            "observations": baseline,
            "interventions": [],
            "suggested_fix": "",
            "patch": "",
            "verified": False,
            "applied": False,
        }
        if failures == 0:
            return sanitize_value(
                {**base, "status": "ok", "diagnosis": "Deterministic"}
            ).value
        if any(item["exit_code"] not in (0, 1) for item in baseline):
            raise ValueError("perturbation process did not complete as a test result")
        if passes == 0:
            return sanitize_value(
                {
                    **base,
                    "status": "skipped",
                    "diagnosis": "Inconclusive",
                    "summary": "deterministic failure; no flaky-test repair proposed",
                }
            ).value
        stabilized = []
        isolated_target = sandbox / relative
        for cause, repaired in _candidate_sources(original, seed).items():
            isolated_target.write_text(repaired, encoding="utf-8")
            observations = _execute(sandbox, plans, CAUSES[cause])
            base["interventions"].append(
                {"cause": CAUSES[cause], "observations": observations}
            )
            if any(item["exit_code"] not in (0, 1) for item in observations):
                raise ValueError(
                    "controlled intervention did not complete as a test result"
                )
            if all(item["exit_code"] == 0 for item in observations):
                stabilized.append((cause, repaired))
            isolated_target.write_text(original, encoding="utf-8")
        if len(stabilized) != 1:
            return sanitize_value(
                {
                    **base,
                    "status": "skipped",
                    "diagnosis": "Inconclusive",
                    "summary": "no single supported intervention stabilized the fixture",
                }
            ).value
        cause, repaired = stabilized[0]
        if not _is_substantive_repair(original, repaired):
            return sanitize_value(
                {
                    **base,
                    "status": "skipped",
                    "diagnosis": "Inconclusive",
                    "summary": "repair made no executable AST change",
                }
            ).value
        patch = _patch(relative, original, repaired)
        return self._verify_and_promote(
            base, cause, patch, relative, dry_run, permissions, sandbox
        )

    def _verify_and_promote(
        self, base, cause, patch, relative, dry_run, permissions, sandbox
    ) -> dict[str, Any]:
        from ..patch.applier import PatchApplier
        from ..patch.contracts import PatchContract, VerifierCommandPlan
        from ..patch.promoter import PatchPromoter
        from ..patch.verifier import PatchVerifier

        try:
            applied, _ = PatchApplier.apply_patch_to_dir(sandbox, patch)
            if not applied:
                raise ValueError("repair could not be applied in sandbox")
            head = run_subprocess(["git", "rev-parse", "HEAD"], cwd=sandbox)
            tree = run_subprocess(["git", "rev-parse", "HEAD^{tree}"], cwd=sandbox)
            if head.returncode != 0 or tree.returncode != 0:
                raise ValueError("sandbox source identity unavailable")
            contract = PatchContract(
                base_commit=head.stdout.strip(),
                base_tree_digest=tree.stdout.strip(),
                patch_content_digest=hashlib.sha256(patch.encode()).hexdigest(),
                sandbox_path=sandbox,
                required_commands=(
                    VerifierCommandPlan(
                        command=(
                            sys.executable,
                            "-m",
                            "pytest",
                            relative.as_posix(),
                            "-q",
                        ),
                        timeout_seconds=120,
                    ),
                ),
                config_digest="",
            )
            verification = PatchVerifier(sandbox, contract).verify(contract)
            if verification.outcome != "completed":
                raise ValueError("repair verification failed")
            promoted = False
            if not dry_run:
                promoted, message = PatchPromoter(
                    self.project_root
                ).promote_sandbox_diff(sandbox, contract, permissions=permissions)
                if not promoted:
                    raise ValueError(message)
            return sanitize_value(
                {
                    **base,
                    "status": "ok",
                    "diagnosis": CAUSES[cause],
                    "suggested_fix": patch,
                    "patch": patch,
                    "verified": True,
                    "applied": promoted,
                }
            ).value
        except Exception as exc:  # noqa: BLE001
            return sanitize_value(
                {
                    **base,
                    "status": "error",
                    "error": f"verified repair failed: {exc}",
                    "diagnosis": CAUSES[cause],
                }
            ).value
