"""Symptom Group recognition: spaCy entity extraction onto a fixed vocabulary.

A Symptom Group is the canonical clinical concept that the free-text presenting
complaint is mapped onto (``CONTEXT.md``). The vocabulary is a concrete, finite,
versioned list shipped as data in ``app/symptom_groups.json``; this module
loads it and recognises it in complaint text.

Recognition is deliberately literal. A spaCy pipeline adds an ``EntityRuler``
seeded with every vocabulary term, and the recognised groups are exactly the
terms whose phrase occurs in the complaint. There is no synonym table, no
lemmatisation, no stemming, no embedding similarity and no inference: "heart
attack" is not "chest pain", and a term inside a longer vocabulary term resolves
to the longer term. Case is folded, because that is spelling rather than meaning.
Negation is not interpreted either — "no chest pain" still reports *chest pain*,
which is why the recognised groups are shown to the Clinical user: a misreading
of the text must be visible before it affects care.

The vocabulary is versioned in the data file (``Vocabulary.version``). Changing
the list means publishing a new version there; stored Triage Assessments keep
the group names they were written with, so earlier records are not reinterpreted
by a later vocabulary.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import spacy
from spacy.language import Language

VOCABULARY_PATH = Path(__file__).with_name("symptom_groups.json")
SPACY_PIPELINE = "en_core_web_sm"
ENTITY_LABEL = "SYMPTOM_GROUP"

_VALID_BASIS = {"esi_red_flag", "common_presentation"}


@dataclass(frozen=True)
class Vocabulary:
    """The versioned Symptom Group list, in authored order."""

    version: str
    groups: tuple[str, ...]


@lru_cache(maxsize=1)
def vocabulary() -> Vocabulary:
    """Load and validate the vocabulary data file once per process."""
    data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Symptom Group vocabulary needs a version")

    groups: list[str] = []
    for entry in data.get("groups", []):
        name = entry.get("name")
        basis = entry.get("basis")
        if not isinstance(name, str) or name != name.strip().lower():
            raise ValueError(f"Symptom Group name is not canonical: {name!r}")
        if basis not in _VALID_BASIS:
            raise ValueError(f"Symptom Group {name!r} has no valid basis")
        if name in groups:
            raise ValueError(f"Duplicate Symptom Group: {name!r}")
        groups.append(name)

    if not groups:
        raise ValueError("Symptom Group vocabulary is empty")
    return Vocabulary(version=version, groups=tuple(groups))


@lru_cache(maxsize=1)
def _pipeline() -> Language:
    """The spaCy pipeline, with the vocabulary installed as an entity ruler."""
    try:
        nlp = spacy.load(SPACY_PIPELINE)
    except OSError as error:
        raise RuntimeError(
            f"spaCy pipeline {SPACY_PIPELINE!r} is not installed. "
            "Run `uv sync` in backend/ to install it."
        ) from error

    ruler = nlp.add_pipe(
        "entity_ruler",
        after="ner",
        config={"phrase_matcher_attr": "LOWER"},
    )
    ruler.add_patterns(
        [
            {"label": ENTITY_LABEL, "pattern": group}
            for group in vocabulary().groups
        ]
    )
    return nlp


def recognise(complaint: str) -> tuple[str, ...]:
    """Return the Symptom Groups whose exact phrase occurs in the complaint.

    The result is in vocabulary order, so the same complaint always produces the
    same tuple, and an empty tuple means none were recognised.
    """
    doc = _pipeline()(complaint)
    matched = {
        entity.text.lower()
        for entity in doc.ents
        if entity.label_ == ENTITY_LABEL
    }
    return tuple(group for group in vocabulary().groups if group in matched)
