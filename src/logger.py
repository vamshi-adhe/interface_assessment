"""
Structured logger.
Writes JSONL to evidence/<run_id>/run.jsonl and prints to console with Rich.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from rich.console import Console

console = Console()

class RunLogger:
    def __init__(self, run_id: str, mode: str):
        self.run_id = run_id
        self.mode = mode
        self.evidence_dir = Path(f"evidence/{run_id}")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.evidence_dir / "run.jsonl"

    def _write(self, event: str, data: dict):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "mode": self.mode,
            "event": event,
            **data,
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def info(self, event: str, **data):
        self._write(event, data)
        console.print(f"[cyan][{self.mode}][/cyan] {event}", data or "")

    def step(self, num: int, action: str, reason: str):
        self._write("step", {"step_num": num, "action": action, "reason": reason})
        console.print(f"[green]  Step {num:02d}[/green] [bold]{action}[/bold] — {reason}")

    def warn(self, event: str, **data):
        self._write(event, data)
        console.print(f"[yellow][WARN][/yellow] {event}", data or "")

    def error(self, event: str, **data):
        self._write(event, data)
        console.print(f"[red][ERROR][/red] {event}", data or "")

    def success(self, **data):
        self._write("success", data)
        console.print(f"[bold green]✅ Run complete[/bold green]", data or "")

    def screenshot_path(self, label: str) -> str:
        return str(self.evidence_dir / f"{label}.png")