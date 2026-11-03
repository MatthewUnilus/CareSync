"""The one place that names the harness's versioned result artefact.

Both the harness (the producer) and the Accuracy Evaluation Report (the
consumer) import these constants, so the version in the file name and the
version recorded inside the document can never drift apart.

The repository also keeps a *legacy* per-case manifest path for live,
assessment-derived runs. The harness never writes it; it exists so an
environment that scores stored Assessments directly keeps working.
"""

from __future__ import annotations

from pathlib import Path

#: Bumped only when the artefact's shape changes in a breaking way. The
#: consumer refuses any other value rather than guessing.
SCHEMA_VERSION = 1

#: A single source for the harness version and the matching file name.
ARTEFACT_VERSION = "1.0.0"
HARNESS_VERSION = f"evaluation-harness-v{ARTEFACT_VERSION}"

RESULTS_DIR = Path(__file__).resolve().parent / "results"

#: ``accuracy-evaluation-<version>.json``. The consumer's default path is this,
#: so a new harness version only has to be bumped here.
RESULT_FILENAME = f"accuracy-evaluation-v{ARTEFACT_VERSION}.json"
RESULTS_PATH = RESULTS_DIR / RESULT_FILENAME

#: The old, per-case manifest form. When this file exists, live
#: assessment-derived runs take precedence over the offline artefact.
LEGACY_MANIFEST_PATH = RESULTS_DIR / "accuracy-evaluation.json"

__all__ = [
    "ARTEFACT_VERSION",
    "HARNESS_VERSION",
    "LEGACY_MANIFEST_PATH",
    "RESULTS_DIR",
    "RESULTS_PATH",
    "RESULT_FILENAME",
    "SCHEMA_VERSION",
]
