"""SLSA Provenance v1 / in-toto Statement v1 policy enforcement and schema types."""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from rush.release.provenance import ProvenanceError


class SchemaMismatchError(ProvenanceError):
    """Raised when a provenance statement fails in-toto / SLSA schema validation."""


class UntrustedSignerError(ProvenanceError):
    """Raised when an envelope is signed by an unauthorized or untrusted signer/root."""


class SubjectMismatchError(ProvenanceError):
    """Raised when artifact digest does not match provenance statement subject."""


class BuilderMismatchError(ProvenanceError):
    """Raised when builder ID or build type does not match policy expectations."""


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


def validate_provenance_statement(
    data: dict[str, Any], expected_build_type: str | None = RUSH_BUILD_TYPE_DRAFT_V1
) -> StatementV1:
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
    if not isinstance(build_type, str) or not build_type.strip():
        raise SchemaMismatchError(
            "buildDefinition.buildType must be a non-empty string"
        )
    if expected_build_type is not None and build_type != expected_build_type:
        raise SchemaMismatchError(
            f"Invalid buildType: expected '{expected_build_type}', got '{build_type}'"
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


def _normalize_pubkey(key_input: str | bytes) -> bytes:
    """Normalizes raw bytes, hex, base64, or PEM encoded Ed25519 public key to 32 raw bytes."""
    if isinstance(key_input, (bytes, bytearray)):
        raw = bytes(key_input)
        if len(raw) == 32:
            return raw
        try:
            h = bytes.fromhex(raw.decode("ascii"))
            if len(h) == 32:
                return h
        except (ValueError, UnicodeDecodeError):
            pass
        try:
            b = base64.b64decode(raw)
            if len(b) == 32:
                return b
        except (ValueError, binascii.Error):
            pass
        return raw

    if isinstance(key_input, str):
        key_str = key_input.strip()
        if "BEGIN PUBLIC KEY" in key_str:
            pub_obj = serialization.load_pem_public_key(key_str.encode())
            return pub_obj.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        if len(key_str) == 64:
            try:
                return bytes.fromhex(key_str)
            except ValueError:
                pass
        try:
            b = base64.b64decode(key_str)
            if len(b) == 32:
                return b
        except (ValueError, binascii.Error):
            pass
        try:
            return bytes.fromhex(key_str)
        except ValueError:
            pass
    raise ValueError(f"Unable to parse Ed25519 public key from {key_input!r}")


@dataclasses.dataclass(frozen=True)
class SignedProvenancePolicy:
    trusted_roots: tuple[str, ...] = ()
    allowed_signers: tuple[str, ...] = ()
    allowed_builders: tuple[str, ...] = ()
    expected_build_type: str = RUSH_BUILD_TYPE_DRAFT_V1
    source_uri_pattern: str = r"^https://github\.com/rush-cli/rush.*$"
    allow_unsigned: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.trusted_roots, tuple):
            object.__setattr__(self, "trusted_roots", tuple(self.trusted_roots))
        if not isinstance(self.allowed_signers, tuple):
            object.__setattr__(self, "allowed_signers", tuple(self.allowed_signers))
        if not isinstance(self.allowed_builders, tuple):
            object.__setattr__(self, "allowed_builders", tuple(self.allowed_builders))


@dataclasses.dataclass(frozen=True)
class ProvenanceVerificationResult:
    is_valid: bool
    signer_id: str | None
    builder_id: str
    subject_digest: str
    statement: StatementV1
    summary: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.warnings, tuple):
            object.__setattr__(self, "warnings", tuple(self.warnings))


class ProvenancePolicyVerifier:
    """Verifies cryptographic in-toto DSSE provenance envelopes against SignedProvenancePolicy."""

    def __init__(self, policy: SignedProvenancePolicy) -> None:
        self.policy = policy

    def verify(
        self,
        raw_envelope: str | bytes,
        expected_artifact_path: Path | None = None,
    ) -> ProvenanceVerificationResult:
        """Verifies DSSE envelope cryptographic signature, SLSA statement, and security policies.

        Raises:
            UntrustedSignerError: If signer key ID or public root is unauthorized or allowlists are empty.
            BuilderMismatchError: If builder ID or build type does not match policy constraints.
            SubjectMismatchError: If expected artifact hash does not match statement subject.
            DuplicateKeyError: If raw envelope or statement JSON contains duplicate keys.
            AmbiguousKeyError: If JSON keys collide under Unicode normalization.
            ProvenanceError: If payload or signature is tampered, malformed, or violates source URI.
        """
        if isinstance(raw_envelope, dict):
            raw_input = json.dumps(raw_envelope)
        else:
            raw_input = raw_envelope

        envelope = StrictProvenanceParser.parse(raw_input)
        if not isinstance(envelope, dict):
            raise ProvenanceError("Malformed envelope: expected JSON object")

        for req_field in ("payloadType", "payload", "signatures"):
            if req_field not in envelope:
                raise ProvenanceError(
                    f"Envelope missing required DSSE field: '{req_field}'"
                )

        payload_type = envelope["payloadType"]
        if payload_type != "application/vnd.in-toto+json":
            raise ProvenanceError(
                f"Unsupported payloadType: expected 'application/vnd.in-toto+json', got '{payload_type}'"
            )

        signatures = envelope.get("signatures")
        if not isinstance(signatures, (list, tuple)):
            raise ProvenanceError("Envelope signatures field must be a list")

        # Fail-closed allowlist checks
        if not self.policy.allow_unsigned:
            if not signatures:
                raise UntrustedSignerError(
                    "Envelope does not contain signatures and unsigned envelopes are disallowed by policy"
                )
            if not self.policy.trusted_roots:
                raise UntrustedSignerError("Policy trusted_roots is empty: fail-closed")
            if not self.policy.allowed_signers:
                raise UntrustedSignerError(
                    "Policy allowed_signers is empty: fail-closed"
                )

        # Signer ID verification
        signer_id: str | None = None
        if signatures:
            sig_entry = signatures[0]
            if not isinstance(sig_entry, dict):
                raise ProvenanceError("Signature entry must be a dictionary")
            signer_id = sig_entry.get("keyid")
            if not signer_id or signer_id not in self.policy.allowed_signers:
                raise UntrustedSignerError(
                    f"Signer '{signer_id}' is not in policy allowed_signers: {self.policy.allowed_signers}"
                )

        # Decode base64 payload
        raw_payload_b64 = envelope["payload"]
        if not isinstance(raw_payload_b64, str):
            raise ProvenanceError("Envelope payload must be a base64-encoded string")
        try:
            payload_bytes = base64.b64decode(raw_payload_b64)
        except Exception as exc:
            raise ProvenanceError(
                f"Envelope payload is not valid base64: {exc}"
            ) from exc

        # Parse and validate in-toto Statement v1 / SLSA Predicate v1
        stmt_dict = StrictProvenanceParser.parse(payload_bytes)
        statement = validate_provenance_statement(stmt_dict, expected_build_type=None)

        # Cryptographic signature verification over DSSE PAE
        if signatures:
            sig_entry = signatures[0]
            sig_b64 = sig_entry.get("sig")
            if not isinstance(sig_b64, str):
                raise ProvenanceError("Signature 'sig' must be a base64 string")
            try:
                sig_bytes = base64.b64decode(sig_b64)
            except Exception as exc:
                raise ProvenanceError(f"Invalid base64 signature: {exc}") from exc

            pae = (
                f"DSSEv1 {len(payload_type)} {payload_type} {len(payload_bytes)} ".encode()
                + payload_bytes
            )

            trusted_raw_roots: list[bytes] = []
            for root in self.policy.trusted_roots:
                try:
                    trusted_raw_roots.append(_normalize_pubkey(root))
                except Exception as exc:
                    raise UntrustedSignerError(
                        f"Invalid trusted root key in policy: {exc}"
                    ) from exc

            if "publicKey" in envelope:
                try:
                    env_pub_raw = _normalize_pubkey(envelope["publicKey"])
                except Exception as exc:
                    raise UntrustedSignerError(
                        f"Invalid publicKey in envelope: {exc}"
                    ) from exc
                if env_pub_raw not in trusted_raw_roots:
                    raise UntrustedSignerError(
                        "Envelope publicKey is not present in policy trusted_roots"
                    )
                candidate_keys = [env_pub_raw]
            else:
                candidate_keys = trusted_raw_roots

            if not candidate_keys:
                raise UntrustedSignerError(
                    "No trusted root keys available for signature verification"
                )

            verified = False
            for cand_bytes in candidate_keys:
                try:
                    pub_obj = ed25519.Ed25519PublicKey.from_public_bytes(cand_bytes)
                    pub_obj.verify(sig_bytes, pae)
                    verified = True
                    break
                except InvalidSignature:
                    continue
                except Exception as exc:
                    raise ProvenanceError(
                        f"Cryptographic verification error: {exc}"
                    ) from exc

            if not verified:
                raise ProvenanceError(
                    "Cryptographic signature verification failed: invalid signature"
                )

        # Builder ID verification
        if not self.policy.allowed_builders:
            raise BuilderMismatchError("Policy allowed_builders is empty: fail-closed")

        builder_id = statement.predicate.run_details.builder.id
        int_builder_id = (
            statement.predicate.build_definition.internal_parameters.builder_id
        )
        if builder_id not in self.policy.allowed_builders:
            raise BuilderMismatchError(
                f"Builder ID '{builder_id}' is not in policy allowed_builders: {self.policy.allowed_builders}"
            )
        if int_builder_id not in self.policy.allowed_builders:
            raise BuilderMismatchError(
                f"Internal builder ID '{int_builder_id}' is not in policy allowed_builders: {self.policy.allowed_builders}"
            )

        # Build type verification
        build_type = statement.predicate.build_definition.build_type
        if build_type != self.policy.expected_build_type:
            raise BuilderMismatchError(
                f"Build type '{build_type}' does not match expected '{self.policy.expected_build_type}'"
            )

        # Source URI verification
        source_uri = statement.predicate.build_definition.external_parameters.source_uri
        if not re.match(self.policy.source_uri_pattern, source_uri):
            raise ProvenanceError(
                f"Source URI '{source_uri}' does not match policy pattern '{self.policy.source_uri_pattern}'"
            )

        # Expected artifact hash verification
        if expected_artifact_path is not None:
            art_file = Path(expected_artifact_path)
            if not art_file.is_file():
                raise SubjectMismatchError(
                    f"Specified artifact file '{art_file}' does not exist"
                )
            hasher = hashlib.sha256()
            with open(art_file, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            actual_sha = hasher.hexdigest()

            subject_digests = [
                s.digest.get("sha256")
                for s in statement.subject
                if isinstance(s.digest, dict) and "sha256" in s.digest
            ]
            if actual_sha not in subject_digests:
                raise SubjectMismatchError(
                    f"Artifact SHA-256 '{actual_sha}' does not match statement subject digests: {subject_digests}"
                )

        first_subject = statement.subject[0] if statement.subject else None
        subject_name = first_subject.name if first_subject else "artifact"
        subject_digest = (
            first_subject.digest.get("sha256", "")
            if first_subject and isinstance(first_subject.digest, dict)
            else ""
        )
        summary = (
            f"Verified signed provenance for {subject_name} "
            f"(signer: {signer_id or 'unsigned'}, builder: {builder_id})"
        )

        warnings: tuple[str, ...] = ()
        if not signatures and self.policy.allow_unsigned:
            warnings = ("Unsigned envelope verified under allow_unsigned policy",)

        return ProvenanceVerificationResult(
            is_valid=True,
            signer_id=signer_id,
            builder_id=builder_id,
            subject_digest=subject_digest,
            statement=statement,
            summary=summary,
            warnings=warnings,
        )


__all__ = [
    "IN_TOTO_STATEMENT_TYPE",
    "RUSH_BUILDER_ID_V1",
    "RUSH_BUILD_TYPE_DRAFT_V1",
    "SLSA_PREDICATE_TYPE_V1",
    "AmbiguousKeyError",
    "BuildDefinitionV1",
    "BuilderDetailsV1",
    "BuilderMismatchError",
    "DuplicateKeyError",
    "ExternalParametersV1",
    "InternalParametersV1",
    "ProvenanceDraft",
    "ProvenanceError",
    "ProvenancePolicyVerifier",
    "ProvenanceVerificationResult",
    "RunDetailsV1",
    "RunMetadataV1",
    "SLSAPredicateV1",
    "SchemaMismatchError",
    "SignedProvenancePolicy",
    "StatementV1",
    "StrictProvenanceParser",
    "SubjectMismatchError",
    "SubjectV1",
    "UntrustedSignerError",
    "validate_provenance_statement",
]
