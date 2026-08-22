"""Pytest output distiller extracting exact failure blocks and assertion frames."""

from src.rush.token_economy.distillers.base import BaseDistiller, DistilledResult


class PytestDistiller(BaseDistiller):
    """Distills noisy pytest output into concise failure summaries (85-95% compression)."""

    def can_distill(self, command: list[str]) -> bool:
        cmd_str = " ".join(command).lower()
        return "pytest" in cmd_str

    def distill(
        self, raw_stdout: str, raw_stderr: str, exit_code: int
    ) -> DistilledResult:
        combined = (raw_stdout + "\n" + raw_stderr).strip()
        raw_lines = combined.splitlines()
        total_raw = len(raw_lines)

        if exit_code == 0:
            summary = "pytest: All tests passed successfully."
            return DistilledResult(
                summary=summary,
                failure_count=0,
                passed_count=1,
                failures=[],
                raw_lines=total_raw,
                distilled_lines=1,
                savings_pct=round(max(0.0, 1.0 - (1 / max(1, total_raw))) * 100, 1),
                distilled_text=summary,
            )

        failures: list[dict[str, str]] = []
        distilled_lines: list[str] = []
        capture = False
        current_failure_header = ""
        current_failure_lines: list[str] = []

        for line in raw_lines:
            if line.startswith("___") and line.endswith("___"):
                if current_failure_header:
                    failures.append(
                        {
                            "test": current_failure_header,
                            "trace": "\n".join(current_failure_lines),
                        }
                    )
                    current_failure_lines = []
                current_failure_header = line.replace("_", " ").strip()
                capture = True
                distilled_lines.append(line)
            elif capture:
                if line.startswith(("===", "FAILED ")):
                    capture = False
                    if current_failure_header:
                        failures.append(
                            {
                                "test": current_failure_header,
                                "trace": "\n".join(current_failure_lines),
                            }
                        )
                        current_failure_lines = []
                elif (
                    line.startswith("E   ")
                    or "assert" in line
                    or "AssertionError" in line
                ):
                    distilled_lines.append(line)
                    current_failure_lines.append(line)
            elif line.startswith("FAILED "):
                distilled_lines.append(line)

        if current_failure_header and current_failure_lines:
            failures.append(
                {
                    "test": current_failure_header,
                    "trace": "\n".join(current_failure_lines),
                }
            )

        if not distilled_lines:
            distilled_lines = raw_lines[-20:]

        distilled_text = "\n".join(distilled_lines)
        num_distilled = len(distilled_lines)
        savings = round(max(0.0, 1.0 - (num_distilled / max(1, total_raw))) * 100, 1)

        return DistilledResult(
            summary=f"pytest: {len(failures)} failed tests isolated.",
            failure_count=len(failures),
            passed_count=0,
            failures=failures,
            raw_lines=total_raw,
            distilled_lines=num_distilled,
            savings_pct=savings,
            distilled_text=distilled_text,
        )
