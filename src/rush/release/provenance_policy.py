"""SLSA Provenance v1 / in-toto Statement v1 policy enforcement and schema types."""

from __future__ import annotations

import dataclasses
import json
import unicodedata
from pathlib import Path  # noqa: F401 - standard library as required by spec
from typing import Any

from rush.release.provenance import ProvenanceError


class SchemaMismatchError(ProvenanceError):
    """Raised when a provenance statement fails in-toto / SLSA schema validation."""


class DuplicateKeyError(ProvenanceError):
    """Raised when JSON input contains duplicate keys at any nesting level."""

    def __init__(self, key: str, path: str = "$", message: str | None = None) -> None:
        self.key = key
        self.path = path
        super().__init__(
            message
            or f"Duplicate key detected in provenance JSON: '{key}' at path '{path}'"
        )


class AmbiguousKeyError(ProvenanceError):
    """Raised when keys collide under Unicode normalization (NFKC) or escape representation."""

    def __init__(
        self, key1: str, key2: str, path: str = "$", message: str | None = None
    ) -> None:
        self.key1 = key1
        self.key2 = key2
        self.path = path
        super().__init__(
            message
            or f"Ambiguous key collision detected: '{key1}' vs '{key2}' at path '{path}'"
        )


class StrictProvenanceParser:
    """Strict JSON parser that rejects duplicate and ambiguous keys at all nesting levels."""

    @staticmethod
    def parse(raw_json: str | bytes) -> dict[str, Any]:
        """Parses JSON text/bytes into a dictionary, enforcing key uniqueness and NFKC normalization.

        Raises:
            ProvenanceError: If input is invalid UTF-8, malformed, truncated, or not a JSON object.
            DuplicateKeyError: If duplicate keys are encountered at any nesting level.
            AmbiguousKeyError: If keys collide under Unicode NFKC normalization.
        """
        if isinstance(raw_json, (bytes, bytearray)):
            try:
                text = raw_json.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProvenanceError(
                    f"Malformed or truncated JSON: invalid UTF-8 bytes: {exc}"
                ) from exc
        elif isinstance(raw_json, str):
            text = raw_json
        else:
            raise ProvenanceError(
                f"Malformed or truncated JSON: expected str or bytes, got {type(raw_json).__name__}"
            )

        if not text.strip():
            raise ProvenanceError("Malformed or truncated JSON: input string is empty")

        def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            seen_exact: set[str] = set()
            seen_normalized: dict[str, str] = {}
            obj: dict[str, Any] = {}
            for key, value in pairs:
                if key in seen_exact:
                    raise DuplicateKeyError(key=key, path="$")
                seen_exact.add(key)
                norm_key = unicodedata.normalize("NFKC", key)
                if norm_key in seen_normalized:
                    orig_key = seen_normalized[norm_key]
                    if orig_key != key:
                        raise AmbiguousKeyError(key1=orig_key, key2=key, path="$")
                seen_normalized[norm_key] = key
                obj[key] = value
            return obj

        decoder = json.JSONDecoder(object_pairs_hook=_pairs_hook)
        try:
            parsed = decoder.decode(text)
        except json.JSONDecodeError as exc:
            raise ProvenanceError(f"Malformed or truncated JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ProvenanceError(
                f"Malformed or truncated JSON: Expected JSON object at root, got {type(parsed).__name__}"
            )

        return parsed


IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
SLSA_PREDICATE_TYPE_V1 = "https://slsa.dev/provenance/v1"
RUSH_BUILD_TYPE_DRAFT_V1 = "https://rush-cli.org/build/draft/v1"
RUSH_BUILDER_ID_V1 = "https://rush-cli.org/builder/v1"


@dataclasses.dataclass(frozen=True)
class SubjectV1:
    name: str
    digest: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "digest": dict(self.digest),
        }


@dataclasses.dataclass(frozen=True)
class ExternalParametersV1:
    source_uri: str
    commit: str
    entry_point: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceUri": self.source_uri,
            "commit": self.commit,
            "entryPoint": self.entry_point,
        }


@dataclasses.dataclass(frozen=True)
class InternalParametersV1:
    builder_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "builderId": self.builder_id,
        }


@dataclasses.dataclass(frozen=True)
class BuildDefinitionV1:
    build_type: str
    external_parameters: ExternalParametersV1
    internal_parameters: InternalParametersV1

    def to_dict(self) -> dict[str, Any]:
        return {
            "buildType": self.build_type,
            "externalParameters": self.external_parameters.to_dict(),
            "internalParameters": self.internal_parameters.to_dict(),
        }


@dataclasses.dataclass(frozen=True)
class BuilderDetailsV1:
    id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
        }


@dataclasses.dataclass(frozen=True)
class RunMetadataV1:
    invocation_id: str
    started_on: str
    finished_on: str
    assurance: str = "unsigned_draft"

    def to_dict(self) -> dict[str, Any]:
        return {
            "invocationId": self.invocation_id,
            "startedOn": self.started_on,
            "finishedOn": self.finished_on,
            "assurance": self.assurance,
        }


@dataclasses.dataclass(frozen=True)
class RunDetailsV1:
    builder: BuilderDetailsV1
    metadata: RunMetadataV1

    def to_dict(self) -> dict[str, Any]:
        return {
            "builder": self.builder.to_dict(),
            "metadata": self.metadata.to_dict(),
        }


@dataclasses.dataclass(frozen=True)
class SLSAPredicateV1:
    build_definition: BuildDefinitionV1
    run_details: RunDetailsV1

    def to_dict(self) -> dict[str, Any]:
        return {
            "buildDefinition": self.build_definition.to_dict(),
            "runDetails": self.run_details.to_dict(),
        }


@dataclasses.dataclass(frozen=True)
class StatementV1:
    type: str
    subject: tuple[SubjectV1, ...]
    predicate_type: str
    predicate: SLSAPredicateV1

    def __post_init__(self) -> None:
        if not isinstance(self.subject, tuple):
            object.__setattr__(self, "subject", tuple(self.subject))

    def to_dict(self) -> dict[str, Any]:
        return {
            "_type": self.type,
            "subject": [s.to_dict() for s in self.subject],
            "predicateType": self.predicate_type,
            "predicate": self.predicate.to_dict(),
        }


@dataclasses.dataclass(frozen=True)
class ProvenanceDraft:
    statement: StatementV1
    assurance: str = "unsigned_draft"
    is_signed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.statement.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceDraft:
        if not isinstance(data, dict):
            raise SchemaMismatchError(
                f"Statement must be a dictionary, got {type(data).__name__}"
            )
        if "statement" in data and isinstance(data["statement"], dict):
            stmt = validate_provenance_statement(data["statement"])
            assurance = str(
                data.get("assurance", stmt.predicate.run_details.metadata.assurance)
            )
            is_signed = bool(data.get("is_signed", False))
            return cls(statement=stmt, assurance=assurance, is_signed=is_signed)
        stmt = validate_provenance_statement(data)
        assurance = stmt.predicate.run_details.metadata.assurance
        return cls(statement=stmt, assurance=assurance, is_signed=False)


def validate_provenance_statement(data: dict[str, Any]) -> StatementV1:
    """Validates an in-toto Statement v1 with SLSA Provenance v1 predicate."""
    if not isinstance(data, dict):
        raise SchemaMismatchError(
            f"Statement must be a dictionary, got {type(data).__name__}"
        )

    allowed_top_keys = {"_type", "subject", "predicateType", "predicate"}
    data_keys = set(data.keys())
    if data_keys != allowed_top_keys:
        unexpected = data_keys - allowed_top_keys
        if unexpected:
            raise SchemaMismatchError(
                f"Unexpected top-level key(s): {', '.join(sorted(unexpected))}"
            )
        missing = allowed_top_keys - data_keys
        raise SchemaMismatchError(
            f"Missing top-level key(s): {', '.join(sorted(missing))}"
        )

    if data["_type"] != IN_TOTO_STATEMENT_TYPE:
        raise SchemaMismatchError(
            f"Invalid _type: expected '{IN_TOTO_STATEMENT_TYPE}', got '{data['_type']}'"
        )

    if data["predicateType"] != SLSA_PREDICATE_TYPE_V1:
        raise SchemaMismatchError(
            f"Invalid predicateType: expected '{SLSA_PREDICATE_TYPE_V1}', got '{data['predicateType']}'"
        )

    # Subject validation
    subject_raw = data["subject"]
    if not isinstance(subject_raw, (list, tuple)) or not subject_raw:
        raise SchemaMismatchError("subject must be a non-empty list of subject objects")

    subjects: list[SubjectV1] = []
    for i, item in enumerate(subject_raw):
        if not isinstance(item, dict):
            raise SchemaMismatchError(f"subject[{i}] must be a dictionary")
        allowed_subj_keys = {"name", "digest"}
        item_keys = set(item.keys())
        if item_keys != allowed_subj_keys:
            unexpected = item_keys - allowed_subj_keys
            if unexpected:
                raise SchemaMismatchError(
                    f"Unexpected key(s) in subject[{i}]: {', '.join(sorted(unexpected))}"
                )
            raise SchemaMismatchError(f"Missing key(s) in subject[{i}]")

        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            raise SchemaMismatchError(f"subject[{i}].name must be a non-empty string")

        digest = item["digest"]
        if not isinstance(digest, dict) or "sha256" not in digest:
            raise SchemaMismatchError(
                f"subject[{i}].digest must be a dictionary containing 'sha256'"
            )
        if not isinstance(digest["sha256"], str) or not digest["sha256"].strip():
            raise SchemaMismatchError(
                f"subject[{i}].digest['sha256'] must be a non-empty string"
            )
        subjects.append(SubjectV1(name=name, digest=digest))

    # Predicate validation
    predicate_raw = data["predicate"]
    if not isinstance(predicate_raw, dict):
        raise SchemaMismatchError("predicate must be a dictionary")

    allowed_pred_keys = {"buildDefinition", "runDetails"}
    pred_keys = set(predicate_raw.keys())
    if pred_keys != allowed_pred_keys:
        unexpected = pred_keys - allowed_pred_keys
        if unexpected:
            raise SchemaMismatchError(
                f"Unexpected key in predicate: {', '.join(sorted(unexpected))}"
            )
        missing = allowed_pred_keys - pred_keys
        raise SchemaMismatchError(
            f"Missing key(s) in predicate: {', '.join(sorted(missing))}"
        )

    # buildDefinition validation
    bdef_raw = predicate_raw["buildDefinition"]
    if not isinstance(bdef_raw, dict):
        raise SchemaMismatchError("predicate.buildDefinition must be a dictionary")

    allowed_bdef_keys = {"buildType", "externalParameters", "internalParameters"}
    bdef_keys = set(bdef_raw.keys())
    if bdef_keys != allowed_bdef_keys:
        unexpected = bdef_keys - allowed_bdef_keys
        if unexpected:
            raise SchemaMismatchError(
                f"Unexpected key in buildDefinition: {', '.join(sorted(unexpected))}"
            )
        missing = allowed_bdef_keys - bdef_keys
        raise SchemaMismatchError(
            f"Missing key(s) in buildDefinition: {', '.join(sorted(missing))}"
        )

    build_type = bdef_raw["buildType"]
    if build_type != RUSH_BUILD_TYPE_DRAFT_V1:
        raise SchemaMismatchError(
            f"Invalid buildType: expected '{RUSH_BUILD_TYPE_DRAFT_V1}', got '{build_type}'"
        )

    ext_raw = bdef_raw["externalParameters"]
    if not isinstance(ext_raw, dict):
        raise SchemaMismatchError(
            "buildDefinition.externalParameters must be a dictionary"
        )
    allowed_ext_keys = {"sourceUri", "commit", "entryPoint"}
    ext_keys = set(ext_raw.keys())
    if ext_keys != allowed_ext_keys:
        unexpected = ext_keys - allowed_ext_keys
        if unexpected:
            raise SchemaMismatchError(
                f"Unexpected key in externalParameters: {', '.join(sorted(unexpected))}"
            )
        missing = allowed_ext_keys - ext_keys
        raise SchemaMismatchError(
            f"Missing key(s) in externalParameters: {', '.join(sorted(missing))}"
        )
    for k in ("sourceUri", "commit", "entryPoint"):
        if not isinstance(ext_raw[k], str):
            raise SchemaMismatchError(f"externalParameters.{k} must be a string")

    external_parameters = ExternalParametersV1(
        source_uri=ext_raw["sourceUri"],
        commit=ext_raw["commit"],
        entry_point=ext_raw["entryPoint"],
    )

    int_raw = bdef_raw["internalParameters"]
    if not isinstance(int_raw, dict):
        raise SchemaMismatchError(
            "buildDefinition.internalParameters must be a dictionary"
        )
    allowed_int_keys = {"builderId"}
    int_keys = set(int_raw.keys())
    if int_keys != allowed_int_keys:
        unexpected = int_keys - allowed_int_keys
        if unexpected:
            raise SchemaMismatchError(
                f"Unexpected key in internalParameters: {', '.join(sorted(unexpected))}"
            )
        missing = allowed_int_keys - int_keys
        raise SchemaMismatchError(
            f"Missing key(s) in internalParameters: {', '.join(sorted(missing))}"
        )
    if not isinstance(int_raw["builderId"], str):
        raise SchemaMismatchError("internalParameters.builderId must be a string")

    internal_parameters = InternalParametersV1(builder_id=int_raw["builderId"])

    build_definition = BuildDefinitionV1(
        build_type=build_type,
        external_parameters=external_parameters,
        internal_parameters=internal_parameters,
    )

    # runDetails validation
    rdet_raw = predicate_raw["runDetails"]
    if not isinstance(rdet_raw, dict):
        raise SchemaMismatchError("predicate.runDetails must be a dictionary")
    allowed_rdet_keys = {"builder", "metadata"}
    rdet_keys = set(rdet_raw.keys())
    if rdet_keys != allowed_rdet_keys:
        unexpected = rdet_keys - allowed_rdet_keys
        if unexpected:
            raise SchemaMismatchError(
                f"Unexpected key in runDetails: {', '.join(sorted(unexpected))}"
            )
        missing = allowed_rdet_keys - rdet_keys
        raise SchemaMismatchError(
            f"Missing key(s) in runDetails: {', '.join(sorted(missing))}"
        )

    builder_raw = rdet_raw["builder"]
    if not isinstance(builder_raw, dict):
        raise SchemaMismatchError("runDetails.builder must be a dictionary")
    allowed_builder_keys = {"id"}
    builder_keys = set(builder_raw.keys())
    if builder_keys != allowed_builder_keys:
        unexpected = builder_keys - allowed_builder_keys
        if unexpected:
            raise SchemaMismatchError(
                f"Unexpected key in builder: {', '.join(sorted(unexpected))}"
            )
        missing = allowed_builder_keys - builder_keys
        raise SchemaMismatchError(
            f"Missing key(s) in builder: {', '.join(sorted(missing))}"
        )
    if not isinstance(builder_raw["id"], str) or not builder_raw["id"].strip():
        raise SchemaMismatchError("builder.id must be a non-empty string")
    builder_details = BuilderDetailsV1(id=builder_raw["id"])

    meta_raw = rdet_raw["metadata"]
    if not isinstance(meta_raw, dict):
        raise SchemaMismatchError("runDetails.metadata must be a dictionary")
    allowed_meta_keys = {"invocationId", "startedOn", "finishedOn", "assurance"}
    meta_keys = set(meta_raw.keys())
    required_meta_keys = {"invocationId", "startedOn", "finishedOn"}
    if not meta_keys.issubset(allowed_meta_keys) or required_meta_keys - meta_keys:
        unexpected = meta_keys - allowed_meta_keys
        if unexpected:
            raise SchemaMismatchError(
                f"Unexpected key in runDetails metadata: {', '.join(sorted(unexpected))}"
            )
        missing = required_meta_keys - meta_keys
        raise SchemaMismatchError(
            f"Missing key(s) in runDetails metadata: {', '.join(sorted(missing))}"
        )
    for k in ("invocationId", "startedOn", "finishedOn"):
        if not isinstance(meta_raw[k], str):
            raise SchemaMismatchError(f"metadata.{k} must be a string")

    run_metadata = RunMetadataV1(
        invocation_id=meta_raw["invocationId"],
        started_on=meta_raw["startedOn"],
        finished_on=meta_raw["finishedOn"],
        assurance=str(meta_raw.get("assurance", "unsigned_draft")),
    )

    run_details = RunDetailsV1(builder=builder_details, metadata=run_metadata)

    slsa_predicate = SLSAPredicateV1(
        build_definition=build_definition,
        run_details=run_details,
    )

    return StatementV1(
        type=data["_type"],
        subject=tuple(subjects),
        predicate_type=data["predicateType"],
        predicate=slsa_predicate,
    )


__all__ = [
    "IN_TOTO_STATEMENT_TYPE",
    "RUSH_BUILDER_ID_V1",
    "RUSH_BUILD_TYPE_DRAFT_V1",
    "SLSA_PREDICATE_TYPE_V1",
    "AmbiguousKeyError",
    "BuildDefinitionV1",
    "BuilderDetailsV1",
    "DuplicateKeyError",
    "ExternalParametersV1",
    "InternalParametersV1",
    "ProvenanceDraft",
    "ProvenanceError",
    "RunDetailsV1",
    "RunMetadataV1",
    "SLSAPredicateV1",
    "SchemaMismatchError",
    "StatementV1",
    "StrictProvenanceParser",
    "SubjectV1",
    "validate_provenance_statement",
]
