from pathlib import Path
from src.artifact.schema import CapabilityArtifact

ARTIFACTS_DIR = Path("artifacts")

def save_artifact(artifact: CapabilityArtifact) -> str:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    path = ARTIFACTS_DIR / f"{artifact.artifact_id}.json"
    path.write_text(artifact.model_dump_json(indent=2))
    return str(path)

def load_artifact(path: str) -> CapabilityArtifact:
    return CapabilityArtifact.model_validate_json(Path(path).read_text())

def list_artifacts() -> list[Path]:
    return sorted(ARTIFACTS_DIR.glob("*.json"))