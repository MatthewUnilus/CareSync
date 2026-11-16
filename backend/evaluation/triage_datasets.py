"""Dataset-agnostic loading of published triage data for training.

Every adapter here turns one published source into the same
:class:`TrainingEncounter`: structured :class:`FeatureInputs` plus one
ground-truth Urgency Level. The training step knows nothing about which file a
row came from, so adding the credentialed primary dataset later means writing
one more adapter and adding one entry to ``datasets/provenance.json`` — not
changing the pipeline.

Nothing is committed from these sources: the fetch step downloads into
``backend/data/datasets/`` (already ignored), verifies each file's SHA-256
against ``provenance.json``, and refuses to continue on a mismatch. The licence
of each source is recorded there too.
"""

from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.features import (
    MISSING_ILLNESS_DURATION_HOURS,
    MISSING_PAIN_LEVEL,
    MISSING_RESPIRATORY_RATE_BPM,
    FeatureInputs,
)
from app.prioritisation import UrgencyLevel

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data" / "datasets"
PROVENANCE_PATH = Path("evaluation") / "datasets" / "provenance.json"
ARTEFACT_PATH = BACKEND_ROOT / "models" / "urgency-classifier-v1.1.0.json"

DATAVERSE_SOURCE_ID = "hoseini-2022-triage-levels"

# Both hosts reject the default urllib user agent.
USER_AGENT = "TriageAssist-training/1.0 (academic prototype)"

_DATAVERSE_LEVELS = {
    "1": UrgencyLevel.high,
    "2": UrgencyLevel.medium,
    "3": UrgencyLevel.low,
}


@dataclass(frozen=True)
class TrainingEncounter:
    """One labelled Encounter, in the shape the training step consumes."""

    source_id: str
    encounter_id: str
    urgency_level: UrgencyLevel
    inputs: FeatureInputs


@dataclass(frozen=True)
class DatasetIdentity:
    """Where a training source came from, recorded with the artefact."""

    source_id: str
    title: str
    citation: str
    licence: str
    doi: str | None
    file_sha256: tuple[str, ...]
    note: str = ""
    files: tuple[dict[str, object], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "citation": self.citation,
            "licence": self.licence,
            "doi": self.doi,
            "file_sha256": list(self.file_sha256),
            "note": self.note,
            "files": list(self.files),
        }


@lru_cache(maxsize=1)
def provenance() -> dict[str, object]:
    """Load the checked-in provenance record."""
    return json.loads(
        (BACKEND_ROOT / PROVENANCE_PATH).read_text(encoding="utf-8")
    )


def dataset_identities() -> tuple[DatasetIdentity, ...]:
    """Return the source identities, in the order training consumes them."""
    identities: list[DatasetIdentity] = []
    for source in provenance()["sources"]:  # type: ignore[union-attr]
        files = tuple(dict(file) for file in source["files"])
        identities.append(
            DatasetIdentity(
                source_id=str(source["source_id"]),
                title=str(source["title"]),
                citation=str(source["citation"]),
                licence=str(source["licence"]),
                doi=source.get("doi"),
                file_sha256=tuple(str(file["sha256"]) for file in files),
                note=str(source.get("note", "")),
                files=files,
            )
        )
    return tuple(identities)


def source_files(source_id: str) -> tuple[dict[str, object], ...]:
    for source in provenance()["sources"]:  # type: ignore[union-attr]
        if source["source_id"] == source_id:
            return tuple(dict(file) for file in source["files"])
    raise KeyError(source_id)


def cached_files_exist(data_dir: Path = DATA_DIR) -> bool:
    """True when every declared source file is already on disk."""
    return all(
        (data_dir / str(file["name"])).exists()
        for source in provenance()["sources"]  # type: ignore[union-attr]
        for file in source["files"]
    )


def fetch(data_dir: Path = DATA_DIR, force: bool = False) -> tuple[Path, ...]:
    """Download every declared file and verify its checksum."""
    data_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source in provenance()["sources"]:  # type: ignore[union-attr]
        for file in source["files"]:
            destination = data_dir / str(file["name"])
            if force or not destination.exists():
                request = urllib.request.Request(
                    str(file["url"]),
                    headers={"User-Agent": USER_AGENT},
                )
                with urllib.request.urlopen(request, timeout=120) as response:
                    payload = response.read()
                destination.write_bytes(payload)
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            if digest != file["sha256"]:
                raise ValueError(
                    f"{destination} does not match the checksum in provenance.json "
                    f"(expected {file['sha256']}, got {digest})"
                )
            written.append(destination)
    return tuple(written)


def load_dataverse(path: Path) -> tuple[TrainingEncounter, ...]:
    """Parse the three-level triage table into training Encounters.

    Rows the source does not record completely enough to featurise are dropped,
    and so are rows whose triage level is outside the three-level scale. The
    fields this source does not record are marked with the sentinel from
    :mod:`app.features` rather than a plausible-looking value.
    """
    encounters: list[TrainingEncounter] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            level = _DATAVERSE_LEVELS.get(str(row.get("Triage_Level", "")).strip())
            age = _number(row.get("Age"))
            temperature = _number(row.get("Temp"))
            heart_rate = _number(row.get("pulse"))
            systolic = _number(row.get("SBP"))
            diastolic = _number(row.get("DBP"))
            ratio = _number(row.get("spo2_fio2"))
            fio2 = _number(row.get("Fio2"))
            if level is None or ratio is None or fio2 is None:
                continue
            if None in (age, temperature, heart_rate, systolic, diastolic):
                continue
            encounters.append(
                TrainingEncounter(
                    source_id=DATAVERSE_SOURCE_ID,
                    encounter_id=str(row.get("ID", "")).strip(),
                    urgency_level=level,
                    inputs=FeatureInputs(
                        recognised_symptom_groups=(),
                        pain_level=MISSING_PAIN_LEVEL,
                        illness_duration_hours=MISSING_ILLNESS_DURATION_HOURS,
                        age=age,
                        temperature_c=temperature,
                        heart_rate_bpm=heart_rate,
                        systolic_bp=systolic,
                        diastolic_bp=diastolic,
                        oxygen_saturation_percent=ratio * fio2 / 100.0,
                        respiratory_rate_bpm=MISSING_RESPIRATORY_RATE_BPM,
                    ),
                )
            )
    return tuple(encounters)


def load_training_records(data_dir: Path = DATA_DIR) -> tuple[TrainingEncounter, ...]:
    """Load every source, in a fixed order, from the cached files."""
    if not cached_files_exist(data_dir):
        raise FileNotFoundError(
            f"training data is not cached in {data_dir}; "
            "run `uv run python -m evaluation.train_classifier --fetch-only`"
        )
    return load_dataverse(data_dir / "ed-triage-levels.tab")


def _number(raw: object) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


__all__ = [
    "ARTEFACT_PATH",
    "DATA_DIR",
    "DATAVERSE_SOURCE_ID",
    "PROVENANCE_PATH",
    "DatasetIdentity",
    "TrainingEncounter",
    "cached_files_exist",
    "dataset_identities",
    "fetch",
    "load_dataverse",
    "load_training_records",
    "provenance",
    "source_files",
]
