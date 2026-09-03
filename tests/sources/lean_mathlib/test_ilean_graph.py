import json
import pathlib

import polars as pl

from knowledge_reuse.sources.lean_mathlib.ilean_graph import (
    USAGE_SCHEMA,
    SourceUsage,
    classify_parent_usages,
    constant_identity,
    parse_ilean,
)
from knowledge_reuse.sources.lean_mathlib.layout import SCHEMA_ROOT


def test_atomic_usage_schema_matches_parquet_columns() -> None:
    schema = json.loads((SCHEMA_ROOT / "lean-source-graph-v1.json").read_text())
    assert set(schema["required"]) == set(USAGE_SCHEMA.names)


def test_constant_identity_keeps_global_constants_and_skips_locals() -> None:
    assert constant_identity('{"c":{"m":"Mathlib.Data.FunLike.Basic","n":"DFunLike.coe"}}') == (
        "Mathlib.Data.FunLike.Basic",
        "DFunLike.coe",
    )
    assert constant_identity('{"f":{"m":"Fixture","i":"x"}}') is None


def test_parse_ilean_keeps_distinct_ranges_and_unattributed_usages(
    tmp_path: pathlib.Path,
) -> None:
    target = json.dumps(
        {"c": {"m": "Mathlib.Data.FunLike.Basic", "n": "DFunLike.coe"}},
        separators=(",", ":"),
    )
    local = json.dumps({"f": {"m": "Fixture", "i": "x"}}, separators=(",", ":"))
    path = tmp_path / "Fixture.ilean"
    path.write_text(
        json.dumps(
            {
                "version": 5,
                "module": "Fixture",
                "references": {
                    target: {
                        "definition": None,
                        "usages": [
                            [1, 2, 1, 5, "Fixture.consumer"],
                            [1, 2, 1, 5, "Fixture.consumer"],
                            [2, 2, 2, 5, "Fixture.consumer"],
                            [3, 0, 3, 3],
                        ],
                    },
                    local: {"definition": None, "usages": [[4, 0, 4, 1, "Fixture.consumer"]]},
                },
            }
        )
    )

    observed = parse_ilean(path, "snapshot", "Fixture")

    assert observed == [
        SourceUsage(
            "snapshot",
            "Fixture",
            None,
            "Mathlib.Data.FunLike.Basic",
            "DFunLike.coe",
            3,
            0,
            3,
            3,
        ),
        SourceUsage(
            "snapshot",
            "Fixture",
            "Fixture.consumer",
            "Mathlib.Data.FunLike.Basic",
            "DFunLike.coe",
            1,
            2,
            1,
            5,
        ),
        SourceUsage(
            "snapshot",
            "Fixture",
            "Fixture.consumer",
            "Mathlib.Data.FunLike.Basic",
            "DFunLike.coe",
            2,
            2,
            2,
            5,
        ),
    ]


def test_parent_attribution_requires_environment_name_and_matching_module() -> None:
    usages = pl.DataFrame(
        {
            "module": ["Fixture", "Fixture", "Fixture", "Fixture"],
            "parent_decl": ["Fixture.local", "Other.foreign", "Missing", None],
            "target_decl": ["Target"] * 4,
        }
    )
    nodes = pl.DataFrame(
        {
            "name": ["Fixture.local", "Other.foreign"],
            "module": ["Fixture", "Other"],
        }
    )

    attributed, unparented, unresolved, mismatched = classify_parent_usages(usages, nodes)

    assert attributed["parent_decl"].to_list() == ["Fixture.local"]
    assert unparented.height == 1
    assert unresolved["parent_decl"].to_list() == ["Missing"]
    assert mismatched.select("parent_decl", "parent_node_module").row(0) == (
        "Other.foreign",
        "Other",
    )
    assert mismatched.item(0, "exclusion_reason") == "parent_module_mismatch"
