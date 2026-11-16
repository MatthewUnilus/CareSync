"""The dataset loader is dataset-agnostic and honest about what it reads.

Each source is parsed by its own small adapter, but every adapter produces the
same `TrainingEncounter`: structured feature inputs plus one ground-truth
Urgency Level. Swapping in the credentialed primary dataset later is a new
adapter, not a rewrite of the training pipeline.
"""

import json
from pathlib import Path

import pytest

from app.features import (
    MISSING_ILLNESS_DURATION_HOURS,
    MISSING_PAIN_LEVEL,
    MISSING_RESPIRATORY_RATE_BPM,
)
from app.prioritisation import UrgencyLevel
from evaluation import triage_datasets as datasets

DATAVERSE_HEADER = [
    "ID",
    "Age",
    "Temp",
    "pulse",
    "SBP",
    "DBP",
    "Fio2",
    "spo2_fio2",
    "Triage_Level",
]

DATAVERSE_ROWS = [
    # triage 1 is the most urgent, and everything needed is recorded.
    ["1", "71", "37.4", "112", "128", "76", "21", "457.14", "1"],
    # triage 3 is the least urgent.
    ["2", "24", "36.8", "76", "118", "74", "21", "471.43", "3"],
    ["3", "55", "37.0", "90", "130", "82", "21", "461.90", "2"],
    # A blank vital means the row cannot be featurised, so it is dropped.
    ["4", "40", "37.0", "", "130", "82", "21", "461.90", "1"],
    # A level outside the three-level scale cannot be mapped, so it is dropped.
    ["5", "40", "37.0", "90", "130", "82", "21", "461.90", "9"],
    # No SpO2/FiO2 ratio means no oxygen saturation, so the row is dropped.
    ["6", "40", "37.0", "90", "130", "82", "", "", "2"],
]


def write_dataverse(path: Path) -> Path:
    lines = ["\t".join(DATAVERSE_HEADER)]
    lines.extend("\t".join(row) for row in DATAVERSE_ROWS)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_source_maps_its_three_levels_one_to_one(tmp_path: Path) -> None:
    records = datasets.load_dataverse(write_dataverse(tmp_path / "ed.tab"))

    assert [record.urgency_level for record in records] == [
        UrgencyLevel.high,
        UrgencyLevel.low,
        UrgencyLevel.medium,
    ]


def test_the_source_derives_oxygen_saturation_from_the_ratio_and_fio2(
    tmp_path: Path,
) -> None:
    records = datasets.load_dataverse(write_dataverse(tmp_path / "ed.tab"))

    first = records[0].inputs
    assert first.age == 71
    assert first.temperature_c == 37.4
    assert first.heart_rate_bpm == 112
    assert first.systolic_bp == 128
    assert first.diastolic_bp == 76
    # SpO2/FiO2 ratio 457.14 at FiO2 21% is an oxygen saturation of ~96%.
    assert first.oxygen_saturation_percent == pytest.approx(96.0, abs=0.01)


def test_fields_the_source_does_not_record_are_marked_not_guessed(
    tmp_path: Path,
) -> None:
    records = datasets.load_dataverse(write_dataverse(tmp_path / "ed.tab"))

    for record in records:
        assert record.inputs.pain_level == MISSING_PAIN_LEVEL
        assert (
            record.inputs.illness_duration_hours == MISSING_ILLNESS_DURATION_HOURS
        )
        # The source records no respiratory rate, so it too is marked rather
        # than given a plausible-looking value.
        assert (
            record.inputs.respiratory_rate_bpm == MISSING_RESPIRATORY_RATE_BPM
        )
        assert record.inputs.recognised_symptom_groups == ()


def test_rows_that_cannot_be_featurised_or_labelled_are_dropped(
    tmp_path: Path,
) -> None:
    records = datasets.load_dataverse(write_dataverse(tmp_path / "ed.tab"))

    assert [record.encounter_id for record in records] == ["1", "2", "3"]


def test_every_training_encounter_carries_the_source_it_came_from(
    tmp_path: Path,
) -> None:
    records = datasets.load_dataverse(write_dataverse(tmp_path / "ed.tab"))

    assert {record.source_id for record in records} == {
        datasets.DATAVERSE_SOURCE_ID
    }


def test_the_shipped_provenance_matches_the_shipped_artefact() -> None:
    provenance = json.loads(
        (Path(__file__).resolve().parents[1] / datasets.PROVENANCE_PATH).read_text(
            encoding="utf-8"
        )
    )
    artefact = json.loads(datasets.ARTEFACT_PATH.read_text(encoding="utf-8"))

    shipped = {source["source_id"] for source in provenance["sources"]}
    recorded = {source["source_id"] for source in artefact["training"]["datasets"]}
    assert shipped == recorded


def test_the_provenance_records_the_datasets_that_were_rejected() -> None:
    considered = datasets.provenance()["considered_but_not_used"]

    assert considered
    for entry in considered:
        assert entry["title"]
        assert entry["reason"]


def test_the_declared_fetch_urls_and_checksums_cover_every_source_file() -> None:
    for source in datasets.provenance()["sources"]:
        assert source["licence"]
        assert source["citation"]
        assert source["files"], source["source_id"]
        for file in source["files"]:
            assert file["url"].startswith("https://")
            assert len(file["sha256"]) == 64
