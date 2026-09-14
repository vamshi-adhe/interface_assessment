"""
CLI entry point.

Commands:
  discover  - LLM agent discovers a goal, saves a capability artifact
  replay    - Replay a saved artifact deterministically (no LLM)
  list      - List all saved artifacts

Usage:
  python cli.py discover --goal "look up member 12345" --params-file params.json
  python cli.py replay   --artifact artifacts/xxx.json --params-file params.json
  python cli.py list
"""

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from src.agent.loop import run_discovery
from src.artifact.store import list_artifacts, load_artifact, save_artifact
from src.replay.executor import replay_artifact

app     = typer.Typer(help="Computer-Use Automation System", add_completion=False)
console = Console()


def load_params(params: str, params_file: str) -> dict:
    """
    Load params from either a JSON string or a file.
    File takes priority if both are given.
    """
    if params_file:
        try:
            return json.loads(Path(params_file).read_text())
        except Exception as e:
            console.print(f"[red]Could not read params file '{params_file}': {e}[/red]")
            raise typer.Exit(1)
    try:
        return json.loads(params)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON in --params: {e}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

@app.command()
def discover(
    goal: str = typer.Option(
        ..., "--goal", "-g",
        help='Natural language goal e.g. "look up member 12345"',
    ),
    url: str = typer.Option(
        "http://localhost:5000", "--url", "-u",
        help="Target application URL",
    ),
    params: str = typer.Option(
        "{}", "--params", "-p",
        help="JSON params string (use --params-file on Windows)",
    ),
    params_file: str = typer.Option(
        None, "--params-file", "-f",
        help="Path to a JSON file containing params e.g. params.json",
    ),
):
    """LLM-driven discovery - saves a capability artifact."""
    p = load_params(params, params_file)

    console.print(f"\n[bold cyan]Starting discovery[/bold cyan]")
    console.print(f"  Goal:   {goal}")
    console.print(f"  URL:    {url}")
    console.print(f"  Params: {p}\n")

    try:
        artifact = asyncio.run(run_discovery(goal, url, p))
    except Exception as exc:
        console.print(f"[red]Discovery failed: {exc}[/red]")
        raise typer.Exit(1)

    path = save_artifact(artifact)

    console.print(f"\n[bold green]Artifact saved:[/bold green] {path}")
    console.print(f"   ID:     {artifact.artifact_id}")
    console.print(f"   Steps:  {len(artifact.steps)}")
    console.print(f"   Status: {artifact.status}")
    console.print(f"\nTo replay:")
    console.print(f"  python cli.py replay --artifact {path} --params-file params.json")


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

@app.command()
def replay(
    artifact_path: str = typer.Option(
        ..., "--artifact", "-a",
        help="Path to the capability artifact JSON file",
    ),
    params: str = typer.Option(
        "{}", "--params", "-p",
        help="JSON params string (use --params-file on Windows)",
    ),
    params_file: str = typer.Option(
        None, "--params-file", "-f",
        help="Path to a JSON file containing params e.g. params.json",
    ),
):
    """Deterministic replay - no LLM involved."""
    try:
        artifact = load_artifact(artifact_path)
    except Exception as exc:
        console.print(f"[red]Could not load artifact: {exc}[/red]")
        raise typer.Exit(1)

    p = load_params(params, params_file)

    console.print(f"\n[bold cyan]Starting replay[/bold cyan]")
    console.print(f"  Artifact: {artifact.name}")
    console.print(f"  Params:   {p}\n")

    try:
        result = asyncio.run(replay_artifact(artifact, p))
    except Exception as exc:
        console.print(f"[red]Replay crashed: {exc}[/red]")
        raise typer.Exit(1)

    console.print()

    if result.status == "success":
        console.print("[bold green]Success[/bold green]")
        if result.outputs:
            console.print(f"  Outputs: {result.outputs}")

    elif result.status == "business_outcome":
        console.print(f"[bold yellow]Business outcome: {result.business_outcome}[/bold yellow]")
        console.print("  (This is a valid answer - not a crash)")

    else:
        console.print("[bold red]Hard failure[/bold red]")
        console.print(f"  Failed step: {result.failed_step_id}")
        console.print(f"  Detail:      {result.error_detail}")
        if result.screenshot_path:
            console.print(f"  Screenshot:  {result.screenshot_path}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command(name="list")
def list_cmd():
    """List all saved capability artifacts."""
    paths = list_artifacts()

    if not paths:
        console.print("[yellow]No artifacts found in artifacts/[/yellow]")
        return

    table = Table(title="Saved Capability Artifacts")
    table.add_column("File",    style="cyan")
    table.add_column("Name",    style="white")
    table.add_column("Status",  style="yellow")
    table.add_column("Steps",   style="green")
    table.add_column("Created", style="dim")

    for path in paths:
        try:
            a = load_artifact(str(path))
            table.add_row(
                path.name,
                a.name[:40],
                a.status,
                str(len(a.steps)),
                a.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        except Exception as exc:
            table.add_row(path.name, f"[red]Error: {exc}[/red]", "", "", "")

    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()