import json
import pathlib

from knowledge_reuse.sources.lean_mathlib.ilean_graph import (
    SourceUsage,
    constant_identity,
    parse_ilean,
)


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
