#!/usr/bin/env python3
"""
Run ALL builds at once (in parallel) and generate per-host configs.

Targets (always executed):
  - interfaces -> templates/interfaces.j2 -> ./interface_config/<host>_config.txt
  - intfix     -> templates/intfix.j2     -> ./intfix/<host>_config.txt
  - int_move   -> templates/int_move.j2   -> ./int_move/<host>_config.txt
  - allen_fix  -> templates/allen_fix.j2  -> ./allen_fix/<host>_config.txt

Usage:
  python build_all.py
  python build_all.py --hosts cox-ms edge-01
  python build_all.py --workers 20
  python build_all.py --config ./config.yaml --templates-dir ./templates
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir_utils.plugins.functions import print_result
from nornir_jinja2.plugins.tasks import template_file


@dataclass(frozen=True)
class Target:
    name: str
    template: str
    output_dir: Path


# All four fixed targets
TARGETS: Dict[str, Target] = {
    "interfaces": Target(
        name="interfaces",
        template="interfaces.j2",
        output_dir=Path("./interface_config"),
    ),
    "intfix": Target(
        name="intfix",
        template="intfix.j2",
        output_dir=Path("./intfix"),
    ),
    "int_move": Target(
        name="int_move",
        template="int_move.j2",
        output_dir=Path("./int_move"),
    ),
    "allen_fix": Target(
        name="allen_fix",
        template="allen_fix.j2",
        output_dir=Path("./allen_fix"),
    ),
}


def ensure_template_exists(templates_dir: Path, template_name: str) -> Path:
    p = (templates_dir / template_name).resolve()
    if not p.is_file():
        raise FileNotFoundError(
            f"Template not found: {p} (templates_dir={templates_dir.resolve()}, template={template_name})"
        )
    return p


def make_render_task(template_name: str, templates_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    def _task(task: Task) -> Result:
        rendered = task.run(
            task=template_file,
            template=template_name,
            path=str(templates_dir),
        )
        filename = output_dir / f"{task.host.name}_config.txt"
        with open(filename, "w") as fh:
            fh.write(rendered.result)
        return Result(host=task.host, result=f"Configuration saved to {filename}")

    return _task


def run_one_target(
    target: Target,
    config_path: Path,
    templates_dir: Path,
    hosts: Optional[List[str]],
    workers: Optional[int],
) -> Tuple[str, object, float, int, int, Optional[Exception], str]:
    """
    Run a single target with its own Nornir instance (safe for parallel execution).
    Returns:
      (target_name, result_or_empty_dict, duration, ok_count, fail_count, error, debug_info)
    """
    start = time.perf_counter()
    ok = fail = 0
    result = {}
    error: Optional[Exception] = None
    debug_info_lines: List[str] = []

    try:
        # Resolve and report paths (makes path issues obvious)
        config_abs = config_path.resolve()
        templates_abs = templates_dir.resolve()
        debug_info_lines.append(f"config.yaml: {config_abs}")
        debug_info_lines.append(f"templates dir: {templates_abs}")

        # Validate template file
        tpl_path = ensure_template_exists(templates_dir, target.template)
        debug_info_lines.append(f"template: {tpl_path}")

        # Init Nornir (optional override for workers)
        init_kwargs = {"config_file": str(config_abs)}
        if workers:
            init_kwargs["runner"] = {
                "plugin": "threaded",
                "options": {"num_workers": workers},
            }

        nr = InitNornir(**init_kwargs)
        try:
            runner = nr.filter(name__in=hosts) if hosts else nr

            # Inventory visibility
            hostnames = sorted(list(runner.inventory.hosts.keys()))
            debug_info_lines.append(f"hosts matched: {len(hostnames)} -> {hostnames[:8]}{'...' if len(hostnames) > 8 else ''}")
            if len(hostnames) == 0:
                debug_info_lines.append("WARNING: No hosts matched inventory/filter. Skipping task execution.")
                result = {}
            else:
                task_func = make_render_task(target.template, templates_dir, target.output_dir)

                print(f"\n=== Starting: {target.name} (template={target.template}) ===")
                r = runner.run(task=task_func, name=f"render:{target.name}")

                # Guard against unexpected None
                result = r if r is not None else {}
                if r is None:
                    debug_info_lines.append(
                        "WARNING: runner.run(...) returned None. This may indicate a Nornir/plugin issue or an empty execution."
                    )

                # Summarize safely
                if hasattr(result, "items"):
                    for _, multi_result in result.items():
                        if getattr(multi_result, "failed", False):
                            fail += 1
                        else:
                            ok += 1
                else:
                    # Empty or non-iterable result
                    ok = 0
                    fail = 0
        finally:
            # Release resources (connections), if supported
            try:
                nr.close()
            except Exception:
                pass

    except Exception as e:
        error = e

    duration = time.perf_counter() - start
    debug_info = "\n".join(debug_info_lines)
    return (target.name, result, duration, ok, fail, error, debug_info)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run ALL builds (4 targets) in parallel.")
    p.add_argument(
        "--config",
        default="config.yaml",
        help="Path to Nornir config.yaml (default: config.yaml)",
    )
    p.add_argument(
        "--templates-dir",
        default="./templates",
        help="Directory containing Jinja2 templates (default: ./templates)",
    )
    p.add_argument(
        "--hosts",
        nargs="+",
        help="Limit execution to specific hostnames in the inventory (optional).",
    )
    p.add_argument(
        "--workers",
        type=int,
        help="Override Nornir num_workers per target (e.g., 10, 20).",
    )
    p.add_argument(
        "--sequential",
        action="store_true",
        help="Run targets sequentially (useful for troubleshooting).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    templates_dir = Path(args.templates_dir)

    overall_start = time.perf_counter()
    any_failures = False
    completed = []

    # Run in parallel by default, or sequential if --sequential is given
    targets = list(TARGETS.values())
    if args.sequential:
        for t in targets:
            completed.append(run_one_target(t, config_path, templates_dir, args.hosts, args.workers))
    else:
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            futures = [
                pool.submit(run_one_target, t, config_path, templates_dir, args.hosts, args.workers)
                for t in targets
            ]
            for fut in as_completed(futures):
                completed.append(fut.result())

    # Print detailed results in stable order by target name
    by_name = {r[0]: r for r in completed}
    for name in sorted(TARGETS.keys()):
        target_name, result, elapsed, ok, fail, error, debug_info = by_name.get(name, (name, {}, 0.0, 0, 0, Exception("Missing results"), ""))

        print(f"\n=== Results: {target_name} ===")
        # Always print debug info to help pinpoint issues quickly
        if debug_info:
            print(debug_info)

        if error:
            print(f"[ERROR] {target_name} failed to execute: {error}")
            any_failures = True
            continue

        # Print per-host details if we have a proper Nornir result
        try:
            if hasattr(result, "items") and len(list(result.items())) > 0:
                print_result(result)
            else:
                print("No host results to display (empty result set).")
        except Exception as e:
            print(f"[WARN] Could not pretty-print results for {target_name}: {e}")

        print(f"Completed {target_name} in {elapsed:.2f}s → OK: {ok}, Failed: {fail}")
        if fail > 0:
            any_failures = True

    total = time.perf_counter() - overall_start
    print(f"\nAll builds finished in {total:.2f}s.")
    sys.exit(1 if any_failures else 0)


if __name__ == "__main__":
    main()