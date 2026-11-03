"""Offline, dependency-light ground truth for TriageAssist evaluation.

This package is deliberately separate from the API, database and Prioritization
Engine. It provides the written ESI v4 rubric, the labeller that applies it, the
seeded synthetic Encounter generator, and the versioned corpus artefact.

Typical use::

    from evaluation.corpus import load_corpus
    from evaluation.labeller import label
"""
