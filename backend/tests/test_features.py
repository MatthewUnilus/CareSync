"""The classifier's feature vector is structured, never text.

The vector is the contract between the Training step and Seam B: both build it
with the same function, from recognised Symptom Groups, pain level, illness
duration, age and the four vitals. These tests assert the vector's shape and
that the free-text complaint never reaches it.
"""

from dataclasses import replace

import pytest

from app.features import FEATURE_NAMES, build_feature_vector
from app.prioritisation import PrioritisationInputs
from app.symptom_groups import vocabulary

BASE_INPUTS = PrioritisationInputs(
    presenting_complaint="Mild headache for a day",
    age=36,
    pain_level=2,
    illness_duration_hours=24.0,
    temperature_c=36.8,
    heart_rate_bpm=78,
    respiratory_rate_bpm=16,
    systolic_bp=120,
    diastolic_bp=80,
    oxygen_saturation_percent=98,
    recognised_symptom_groups=(),
)


def as_mapping(inputs: PrioritisationInputs) -> dict[str, float]:
    vector = build_feature_vector(inputs)
    return dict(zip(FEATURE_NAMES, vector, strict=True))


def test_the_vector_names_are_unique() -> None:
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))


def test_the_vector_has_one_dimension_per_vocabulary_group_plus_the_scalars() -> None:
    group_features = [
        name for name in FEATURE_NAMES if name.startswith("symptom_group:")
    ]

    assert group_features == [
        f"symptom_group:{group}" for group in vocabulary().groups
    ]
    # 49 Symptom Groups, pain, illness duration, age and five vital numbers.
    assert len(FEATURE_NAMES) == len(vocabulary().groups) + 8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pain_level", 7),
        ("illness_duration_hours", 3.5),
        ("age", 71),
        ("temperature_c", 38.4),
        ("heart_rate_bpm", 112),
        ("systolic_bp", 148),
        ("diastolic_bp", 92),
        ("oxygen_saturation_percent", 91),
    ],
)
def test_each_captured_scalar_reaches_its_named_dimension(
    field: str, value: object
) -> None:
    inputs = replace(BASE_INPUTS, **{field: value})

    assert as_mapping(inputs)[field] == pytest.approx(float(value))  # type: ignore[arg-type]


def test_recognised_groups_become_a_multi_hot_over_the_vocabulary() -> None:
    inputs = replace(
        BASE_INPUTS,
        recognised_symptom_groups=("chest pain", "fever"),
    )

    features = as_mapping(inputs)

    assert features["symptom_group:chest pain"] == 1.0
    assert features["symptom_group:fever"] == 1.0
    assert sum(
        value for name, value in features.items() if name.startswith("symptom_group:")
    ) == 2.0


def test_the_order_groups_were_recognised_in_does_not_matter() -> None:
    first = build_feature_vector(
        replace(BASE_INPUTS, recognised_symptom_groups=("chest pain", "fever"))
    )
    second = build_feature_vector(
        replace(BASE_INPUTS, recognised_symptom_groups=("fever", "chest pain"))
    )

    assert first == second


def test_a_group_outside_the_current_vocabulary_is_ignored_not_fatal() -> None:
    features = as_mapping(
        replace(BASE_INPUTS, recognised_symptom_groups=("not a real group",))
    )

    assert all(
        value == 0.0 for name, value in features.items() if name.startswith("symptom_group:")
    )


def test_the_complaint_text_never_reaches_the_vector() -> None:
    quiet = build_feature_vector(
        replace(BASE_INPUTS, presenting_complaint="Mild headache for a day")
    )
    alarming = build_feature_vector(
        replace(
            BASE_INPUTS,
            presenting_complaint="Crushing chest pain, cannot breathe",
        )
    )

    assert quiet == alarming
    assert "presenting_complaint" not in FEATURE_NAMES
    assert all(isinstance(value, float) for value in quiet)


def test_the_same_inputs_always_build_the_same_vector() -> None:
    inputs = replace(BASE_INPUTS, recognised_symptom_groups=("fever",), pain_level=6)

    assert build_feature_vector(inputs) == build_feature_vector(inputs)
