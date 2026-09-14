import json
import time
from pathlib import Path

from rich.console import Console

console = Console()


class EscalationSession:
    """
    Pause automation, hand control to a human, resume.

    Why same session (not a fresh browser)?
      A new session loses form state, cookies, and partial progress.
      The human must operate the SAME tab the automation was using.

    Production version: sends Slack/webhook + VNC link, resumes via API.
    This version: writes a file, keeps browser open, polls for resume file.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.evidence_dir = Path(f"evidence/{run_id}")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.request_file = self.evidence_dir / "escalation_request.json"
        self.resume_file  = self.evidence_dir / "escalation_resume.json"

    def raise_intervention(
        self,
        goal: str,
        step_id: str,
        reason: str,
        screenshot_path: str,
    ) -> None:
        """Pause automation. Write intervention request. Browser stays open."""
        request = {
            "session_id":    self.run_id,
            "status":        "waiting_for_human",
            "goal":          goal,
            "stuck_at_step": step_id,
            "reason":        reason,
            "screenshot":    screenshot_path,
            "resume_file":   str(self.resume_file),
            "resume_format": {
                "session_id":    self.run_id,
                "status":        "resumed",
                "actions_taken": "describe what you did manually",
            },
        }
        self.request_file.write_text(json.dumps(request, indent=2))

        console.print("\n" + "=" * 60, style="bold yellow")
        console.print("[bold yellow]ESCALATION - Human intervention needed[/bold yellow]")
        console.print(f"  Goal:      {goal}")
        console.print(f"  Stuck at:  {step_id}")
        console.print(f"  Reason:    {reason}")
        console.print(f"  Request:   {self.request_file}")
        console.print(f"\n  Browser window is OPEN - take control now.")
        console.print(f"  When done, create this file: {self.resume_file}")
        console.print("=" * 60 + "\n", style="bold yellow")

    def wait_for_resume(self, timeout_seconds: int = 300) -> dict:
        """Block until human creates the resume signal file."""
        console.print(f"[yellow]Waiting for human to resume (timeout: {timeout_seconds}s)...[/yellow]")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.resume_file.exists():
                data = json.loads(self.resume_file.read_text())
                console.print(
                    f"[green]Resumed. Human actions: {data.get('actions_taken', 'not recorded')}[/green]"
                )
                return data
            time.sleep(2)

        raise TimeoutError(
            f"Human did not resume within {timeout_seconds}s. "
            f"Create {self.resume_file} to resume."
        )