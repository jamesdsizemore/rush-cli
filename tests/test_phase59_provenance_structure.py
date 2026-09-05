"""Phase 59 Workstream P59.2 Contract Tests: Statement Structure and Provenance Policy."""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path

import pytest

from rush.release import (
    ProvenanceDraft,
    SchemaMismatchError,
    SLSAPredicateV1,
    StatementV1,
    SubjectV1,
    validate_provenance_statement,
)
from rush.release.provenance_policy import (
    IN_TOTO_STATEMENT_TYPE,
    RUSH_BUILD_TYPE_DRAFT_V1,
    RUSH_BUILDER_ID_V1,
    SLSA_PREDICATE_TYPE_V1,
    BuildDefinitionV1,
    BuilderDetailsV1,
    ExternalParametersV1,
    InternalParametersV1,
    RunDetailsV1,
    RunMetadataV1,
)
from rush.tools.attest import AttestationTool


def test_statement_and_predicate_types_are_exact(tmp_path: Path) -> None:
    """T-59.06: Validates in-toto Statement v1 schema exact types and fails on divergence."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    whl_file = dist_dir / "rush-0.3.0-py3-none-any.whl"
    whl_file.write_bytes(b"package bytes")

    tool = AttestationTool()
    res = tool.run(tmp_path)
    assert res["status"] == "ok"
    statement_dict = res["metadata"]["statement"]

    # Must match constants exactly
    assert statement_dict["_type"] == IN_TOTO_STATEMENT_TYPE
    assert statement_dict["_type"] == "https://in-toto.io/Statement/v1"
    assert statement_dict["predicateType"] == SLSA_PREDICATE_TYPE_V1
    assert statement_dict["predicateType"] == "https://slsa.dev/provenance/v1"

    # Validation succeeds on canonical statement
    validated = validate_provenance_statement(statement_dict)
    assert isinstance(validated, StatementV1)
    assert validated.type == IN_TOTO_STATEMENT_TYPE
    assert validated.predicate_type == SLSA_PREDICATE_TYPE_V1

    # Divergence on _type
    divergent_type = dict(statement_dict)
    divergent_type["_type"] = "https://in-toto.io/Statement/v0.1"
    with pytest.raises(SchemaMismatchError, match=r"Invalid _type"):
        validate_provenance_statement(divergent_type)

    # Divergence on predicateType
    divergent_pred_type = dict(statement_dict)
    divergent_pred_type["predicateType"] = "custom"
    with pytest.raises(SchemaMismatchError, match=r"Invalid predicateType"):
        validate_provenance_statement(divergent_pred_type)

    divergent_pred_type_slsa02 = dict(statement_dict)
    divergent_pred_type_slsa02["predicateType"] = "https://slsa.dev/provenance/v0.2"
    with pytest.raises(SchemaMismatchError, match=r"Invalid predicateType"):
        validate_provenance_statement(divergent_pred_type_slsa02)


def test_build_type_parameters_source_subject_and_extensions_are_pinned(
    tmp_path: Path,
) -> None:
    """T-59.07: Asserts buildDefinition and runDetails have exact pinned parameters and IDs."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    whl_file = dist_dir / "rush-0.3.0-py3-none-any.whl"
    whl_file.write_bytes(b"content for pinned parameters test")

    tool = AttestationTool()
    res = tool.run(tmp_path)
    assert res["status"] == "ok"
    stmt = res["metadata"]["statement"]

    # Canonical validation
    validated = validate_provenance_statement(stmt)

    # Check pinned buildType
    pred = stmt["predicate"]
    build_def = pred["buildDefinition"]
    assert build_def["buildType"] == RUSH_BUILD_TYPE_DRAFT_V1
    assert build_def["buildType"] == "https://rush-cli.org/build/draft/v1"
    assert (
        validated.predicate.build_definition.build_type
        == "https://rush-cli.org/build/draft/v1"
    )

    # Check externalParameters
    ext_params = build_def["externalParameters"]
    assert "sourceUri" in ext_params
    assert "commit" in ext_params
    assert "entryPoint" in ext_params
    assert ext_params["entryPoint"] == "rush attest"
    assert (
        validated.predicate.build_definition.external_parameters.entry_point
        == "rush attest"
    )

    # Check internalParameters
    int_params = build_def["internalParameters"]
    assert int_params["builderId"] == RUSH_BUILDER_ID_V1
    assert int_params["builderId"] == "https://rush-cli.org/builder/v1"
    assert (
        validated.predicate.build_definition.internal_parameters.builder_id
        == "https://rush-cli.org/builder/v1"
    )

    # Check runDetails.builder.id
    run_details = pred["runDetails"]
    assert run_details["builder"]["id"] == RUSH_BUILDER_ID_V1
    assert run_details["builder"]["id"] == "https://rush-cli.org/builder/v1"
    assert (
        validated.predicate.run_details.builder.id == "https://rush-cli.org/builder/v1"
    )

    # Mutated buildType must fail validation
    mutated = copy.deepcopy(stmt)
    mutated["predicate"]["buildDefinition"]["buildType"] = (
        "https://rush-cli.org/build/v2"
    )
    with pytest.raises(SchemaMismatchError, match=r"Invalid buildType"):
        validate_provenance_statement(mutated)

    # Missing externalParameters field must fail validation
    mutated_ext = copy.deepcopy(stmt)
    del mutated_ext["predicate"]["buildDefinition"]["externalParameters"]["entryPoint"]
    with pytest.raises(SchemaMismatchError, match=r"externalParameters"):
        validate_provenance_statement(mutated_ext)


def test_unknown_or_malformed_fields_fail_validation(tmp_path: Path) -> None:
    """T-59.08: Injects unknown top-level or predicate fields and asserts fail-closed rejection."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    whl_file = dist_dir / "rush-0.3.0-py3-none-any.whl"
    whl_file.write_bytes(b"package payload")

    tool = AttestationTool()
    res = tool.run(tmp_path)
    base_statement = res["metadata"]["statement"]

    # 1. Unknown top-level field
    bad_top = copy.deepcopy(base_statement)
    bad_top["malicious_field"] = 123
    with pytest.raises(SchemaMismatchError, match=r"Unexpected top-level key"):
        validate_provenance_statement(bad_top)

    # 2. Unknown predicate field
    bad_pred = copy.deepcopy(base_statement)
    bad_pred["predicate"]["rogue_key"] = "exploit"
    with pytest.raises(SchemaMismatchError, match=r"Unexpected key in predicate"):
        validate_provenance_statement(bad_pred)

    # 3. Unknown buildDefinition field
    bad_bdef = copy.deepcopy(base_statement)
    bad_bdef["predicate"]["buildDefinition"]["rogue_def"] = True
    with pytest.raises(SchemaMismatchError, match=r"Unexpected key in buildDefinition"):
        validate_provenance_statement(bad_bdef)

    # 4. Unknown runDetails field
    bad_rdet = copy.deepcopy(base_statement)
    bad_rdet["predicate"]["runDetails"]["rogue_run"] = "data"
    with pytest.raises(SchemaMismatchError, match=r"Unexpected key in runDetails"):
        validate_provenance_statement(bad_rdet)

    # 5. Malformed subject (empty list or missing sha256)
    bad_subj_empty = copy.deepcopy(base_statement)
    bad_subj_empty["subject"] = []
    with pytest.raises(SchemaMismatchError, match=r"subject must be a non-empty list"):
        validate_provenance_statement(bad_subj_empty)

    bad_subj_digest = copy.deepcopy(base_statement)
    bad_subj_digest["subject"][0]["digest"] = {"md5": "bad"}
    with pytest.raises(SchemaMismatchError, match=r"digest.*sha256"):
        validate_provenance_statement(bad_subj_digest)

    # 6. Non-dict input
    with pytest.raises(SchemaMismatchError, match=r"Statement must be a dictionary"):
        validate_provenance_statement(["not a dict"])  # type: ignore[arg-type]


def test_provenance_draft_dataclass_is_frozen_and_serializable() -> None:
    """T-59.09: Asserts all provenance dataclasses are frozen and serialize to canonical in-toto shape."""
    subj = SubjectV1(name="rush-0.3.0-py3-none-any.whl", digest={"sha256": "a" * 64})
    ext_params = ExternalParametersV1(
        source_uri="https://github.com/rush-cli/rush",
        commit="b" * 40,
        entry_point="rush attest",
    )
    int_params = InternalParametersV1(builder_id=RUSH_BUILDER_ID_V1)
    bdef = BuildDefinitionV1(
        build_type=RUSH_BUILD_TYPE_DRAFT_V1,
        external_parameters=ext_params,
        internal_parameters=int_params,
    )
    bdetails = BuilderDetailsV1(id=RUSH_BUILDER_ID_V1)
    rmeta = RunMetadataV1(
        invocation_id="rush-12345",
        started_on="2026-09-05T00:00:00Z",
        finished_on="2026-09-05T00:00:00Z",
        assurance="unsigned_draft",
    )
    rdetails = RunDetailsV1(builder=bdetails, metadata=rmeta)
    pred = SLSAPredicateV1(build_definition=bdef, run_details=rdetails)
    stmt = StatementV1(
        type=IN_TOTO_STATEMENT_TYPE,
        subject=(subj,),
        predicate_type=SLSA_PREDICATE_TYPE_V1,
        predicate=pred,
    )
    draft = ProvenanceDraft(statement=stmt, assurance="unsigned_draft", is_signed=False)

    all_instances = [
        subj,
        ext_params,
        int_params,
        bdef,
        bdetails,
        rmeta,
        rdetails,
        pred,
        stmt,
        draft,
    ]

    # Verify all are frozen dataclasses
    for inst in all_instances:
        assert dataclasses.is_dataclass(inst)
        params = getattr(inst, "__dataclass_params__", None)
        assert params is not None and params.frozen is True, (
            f"{type(inst)} must be frozen"
        )

    # Verify immutability
    with pytest.raises(dataclasses.FrozenInstanceError):
        subj.name = "mutated.whl"  # type: ignore[misc]

    with pytest.raises(dataclasses.FrozenInstanceError):
        draft.is_signed = True  # type: ignore[misc]

    with pytest.raises(dataclasses.FrozenInstanceError):
        ext_params.commit = "mutated"  # type: ignore[misc]

    # Verify each dataclass has .to_dict()
    for inst in all_instances:
        d = inst.to_dict()
        assert isinstance(d, dict), f"{type(inst)}.to_dict() must return dict"

    # Verify canonical shape matches in-toto Statement v1 exactly
    draft_dict = draft.to_dict()
    assert draft_dict["_type"] == IN_TOTO_STATEMENT_TYPE
    assert draft_dict["predicateType"] == SLSA_PREDICATE_TYPE_V1
    assert draft_dict["subject"] == [
        {"name": "rush-0.3.0-py3-none-any.whl", "digest": {"sha256": "a" * 64}}
    ]
    assert (
        draft_dict["predicate"]["buildDefinition"]["buildType"]
        == RUSH_BUILD_TYPE_DRAFT_V1
    )
    assert draft_dict["predicate"]["buildDefinition"]["externalParameters"] == {
        "sourceUri": "https://github.com/rush-cli/rush",
        "commit": "b" * 40,
        "entryPoint": "rush attest",
    }
    assert draft_dict["predicate"]["buildDefinition"]["internalParameters"] == {
        "builderId": RUSH_BUILDER_ID_V1
    }
    assert draft_dict["predicate"]["runDetails"]["builder"] == {
        "id": RUSH_BUILDER_ID_V1
    }
    assert draft_dict["predicate"]["runDetails"]["metadata"] == {
        "invocationId": "rush-12345",
        "startedOn": "2026-09-05T00:00:00Z",
        "finishedOn": "2026-09-05T00:00:00Z",
        "assurance": "unsigned_draft",
    }

    # Verify round-trip via ProvenanceDraft.from_dict
    reconstructed = ProvenanceDraft.from_dict(draft_dict)
    assert reconstructed == draft
    assert reconstructed.to_dict() == draft_dict
