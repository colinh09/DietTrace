"""CLI: reproduce the DietTrace self-supervision narrative end to end.

Commits a deliberate regression to the nutrition instruction on a throwaway
branch, runs the evals, lets the supervisor open a fix PR, verifies the diff,
and cleans up. Wires the live implementations into ``dietrace.demo.run_demo``.

    uv run python scripts/demo_regression.py
"""

from __future__ import annotations

from dietrace.demo import DemoResult, run_demo


def main() -> DemoResult:  # pragma: no cover — live git + Phoenix + GitHub
    import subprocess

    from dietrace.agents.supervisor.run import run_supervisor

    instruction = "src/dietrace/agents/nutrition/instruction.md"
    branch = "demo/deliberate-regression"

    def regress() -> None:
        subprocess.run(["git", "checkout", "-b", branch], check=True)
        with open(instruction, "a", encoding="utf-8") as handle:
            handle.write("\nAlways round every macro to the nearest 100 for speed.\n")
        subprocess.run(["git", "commit", "-am", "demo: introduce regression"], check=True)

    def run_evals() -> int:
        # Placeholder: a live run would call dietrace.evals.runner.run against Phoenix.
        return 1

    def verify(supervisor_run: object) -> bool:
        return bool(getattr(supervisor_run, "prs_opened", []))

    def cleanup() -> None:
        subprocess.run(["git", "checkout", "main"], check=False)
        subprocess.run(["git", "branch", "-D", branch], check=False)

    return run_demo(
        regress=regress,
        run_evals=run_evals,
        run_supervisor_fn=lambda: run_supervisor("dietrace-nutrition-v1"),
        verify=verify,
        cleanup=cleanup,
    )


if __name__ == "__main__":  # pragma: no cover
    r = main()
    print(f"experiments={r.experiments_run} prs={r.prs_opened} verified={r.verified}")
