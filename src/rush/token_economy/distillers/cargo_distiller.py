"""Cargo test output distiller isolating panic locations and compilation errors."""

from src.rush.token_economy.distillers.base import BaseDistiller, DistilledResult


class CargoDistiller(BaseDistiller):
    """Distills cargo test and cargo build output."""

    def can_distill(self, command: list[str]) -> bool:
        cmd_str = " ".join(command).lower()
        return "cargo" in cmd_str

    def distill(
        self, raw_stdout: str, raw_stderr: str, exit_code: int
    ) -> DistilledResult:
        combined = (raw_stdout + "\n" + raw_stderr).strip()
        raw_lines = combined.splitlines()
        total_raw = len(raw_lines)

        if exit_code == 0:
            summary = "cargo: Tests passed successfully."
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

        distilled: list[str] = []
        for line in raw_lines:
            if "error[E" in line or "panicked at" in line or "FAILED" in line:
                distilled.append(line)

        if not distilled:
            distilled = raw_lines[-15:]

        num_distilled = len(distilled)
        savings = round(max(0.0, 1.0 - (num_distilled / max(1, total_raw))) * 100, 1)

        return DistilledResult(
            summary=f"cargo: {len(distilled)} error frames isolated.",
            failure_count=max(1, len(distilled)),
            passed_count=0,
            failures=[{"log": "\n".join(distilled)}],
            raw_lines=total_raw,
            distilled_lines=num_distilled,
            savings_pct=savings,
            distilled_text="\n".join(distilled),
        )
