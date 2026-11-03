"""Read and write the versioned, rubric-labelled evaluation corpus.

The corpus is a single JSON document. Ground-truth labels live only under the
``ground_truth`` key of each Encounter; there is no engine output field, so a
Machine Recommendation can never overwrite or be mistaken for a label.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from evaluation.generator import (
    DEFAULT_SEED,
    GENERATOR_VERSION,
    LabelledEncounter,
    generate,
)
from evaluation.rubric import CITATION, RUBRIC_VERSION

CORPUS_SCHEMA_VERSION = 1
CORPUS_PATH = (
    Path(__file__).resolve().parent / "corpus" / f"{RUBRIC_VERSION}.json"
)
RUBRIC_DOCUMENT = "evaluation/RUBRIC.md"


@dataclass(frozen=True)
class Corpus:
    schema_version: int
    rubric_version: str
    seed: int
    encounter_count: int
    encounters: tuple[LabelledEncounter, ...]
    metadata: dict[str, object]


def build_corpus(seed: int = DEFAULT_SEED) -> dict[str, object]:
    """Build the serialisable corpus document from the seeded generator."""
    encounters = generate(seed)
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "rubric_citation": CITATION,
        "rubric_document": RUBRIC_DOCUMENT,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "encounter_count": len(encounters),
        "ground_truth_namespace": "ground_truth",
        "encounters": [encounter.to_dict() for encounter in encounters],
    }


def write_corpus(
    path: Path = CORPUS_PATH, seed: int = DEFAULT_SEED
) -> Path:
    """Write the corpus to ``path`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_corpus(seed), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_corpus(path: Path = CORPUS_PATH) -> Corpus:
    """Load a previously generated corpus without regenerating it."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_encounters = data["encounters"]
    if not isinstance(raw_encounters, list):
        raise ValueError("encounters must be a list")
    encounters = tuple(
        LabelledEncounter.from_dict(item) for item in raw_encounters
    )
    return Corpus(
        schema_version=int(data["schema_version"]),
        rubric_version=str(data["rubric_version"]),
        seed=int(data["seed"]),
        encounter_count=int(data["encounter_count"]),
        encounters=encounters,
        metadata=data,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the rubric-labelled evaluation corpus."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=CORPUS_PATH)
    args = parser.parse_args()
    path = write_corpus(args.out, args.seed)
    corpus = load_corpus(path)
    print(
        f"wrote {corpus.encounter_count} encounters "
        f"({RUBRIC_VERSION}, seed {corpus.seed}) to {path}"
    )


if __name__ == "__main__":
    main()
