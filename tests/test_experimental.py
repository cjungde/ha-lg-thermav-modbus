"""Layout of the undocumented-register sensors and the write whitelist.

The experimental sensors exist to record addresses nobody understands, so what
matters is that they never collide with a documented register, that every one
is read, and that none can be written. No Home Assistant install is needed:
experimental.py and const.py import nothing from it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

COMPONENT = (
    Path(__file__).resolve().parent.parent / "custom_components" / "lg_therma_v_r290"
)


def _load(module_name: str):
    package = "lg_therma_v_r290_under_test"
    if package not in sys.modules:
        stub = types.ModuleType(package)
        stub.__path__ = [str(COMPONENT)]
        sys.modules[package] = stub

    qualified = f"{package}.{module_name}"
    if qualified not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            qualified, COMPONENT / f"{module_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
    return sys.modules[qualified]


experimental = _load("experimental")
const = _load("const")

# What the integration documents and reads today: input 0-13 and 16-24 (the
# manual covers 0-13, the rest comes from the community), holding 0-9.
DOCUMENTED_INPUT = set(range(0, 14)) | set(range(16, 25)) | {9997, 9998}
DOCUMENTED_HOLDING = set(range(0, 10))


def _registers(kind: str) -> set[int]:
    return {r.address for r in experimental.EXPERIMENTAL_REGISTERS if r.kind == kind}


def test_the_scan_found_eighteen_registers() -> None:
    """Input 14, 17 and 63, holding 10-22, 62 and 63."""
    assert len(experimental.EXPERIMENTAL_REGISTERS) == 18


def test_no_experimental_register_is_a_documented_one() -> None:
    # 17 lies in the documented block 16-24 but is not itself documented.
    assert not _registers("input") & (DOCUMENTED_INPUT - {17})
    assert not _registers("holding") & DOCUMENTED_HOLDING


def test_input_17_comes_from_the_main_read() -> None:
    """Inside the block 16-24 already read; not requested a second time."""
    assert 17 in _registers("input")
    for kind, start, count in experimental.EXPERIMENTAL_BLOCKS:
        if kind == "input":
            assert not start <= 17 < start + count


def test_every_register_is_read_exactly_once() -> None:
    covered = [
        (kind, start + offset)
        for kind, start, count in experimental.EXPERIMENTAL_BLOCKS
        for offset in range(count)
    ]
    covered += [("input", a) for a in experimental.INPUT_FROM_MAIN_READ]
    assert len(covered) == len(set(covered))
    assert set(covered) == {
        (r.kind, r.address) for r in experimental.EXPERIMENTAL_REGISTERS
    }


def test_keys_and_names_are_unique() -> None:
    registers = experimental.EXPERIMENTAL_REGISTERS
    assert len({r.key for r in registers}) == len(registers)
    assert len({r.data_key for r in registers}) == len(registers)
    assert len({r.name for r in registers}) == len(registers)


def test_numbers_follow_the_manuals_notation() -> None:
    by_key = {r.key: r for r in experimental.EXPERIMENTAL_REGISTERS}
    assert by_key["experimental_input_30015"].address == 14
    assert by_key["experimental_input_30018"].address == 17
    assert by_key["experimental_holding_40011"].address == 10
    assert by_key["experimental_holding_40064"].address == 63
    assert by_key["experimental_holding_40011"].name == "Experimental Holding 40011"


def test_key_is_the_name_as_an_entity_id_slug() -> None:
    """docs/naming.md: entity key = name slugified."""
    for register in experimental.EXPERIMENTAL_REGISTERS:
        assert register.key == register.name.lower().replace(" ", "_")


def test_data_key_is_register_type_and_number() -> None:
    by_key = {r.key: r for r in experimental.EXPERIMENTAL_REGISTERS}
    assert by_key["experimental_input_30015"].data_key == "input_30015"
    assert by_key["experimental_holding_40011"].data_key == "holding_40011"
    assert experimental.data_key("input", 17) == "input_30018"


def test_nothing_experimental_is_writable() -> None:
    assert not _registers("holding") & const.WRITABLE_HOLDING_REGISTERS


def test_the_write_whitelist_is_the_set_the_entities_use() -> None:
    assert {0, 1, 2, 4, 5, 7, 8} == const.WRITABLE_HOLDING_REGISTERS
    assert {0, 1, 2, 3, 4} == const.WRITABLE_COILS
    # Coil 5 triggers emergency operation; only its option makes it writable.
    assert 5 not in const.WRITABLE_COILS
    assert {5} == const.EMERGENCY_OPERATION_WRITABLE_COILS


def test_gate_gives_up_on_a_refused_block_at_once() -> None:
    gate = experimental.BlockGate()
    assert gate.should_read("holding", 10)
    assert gate.record("holding", 10, ok=False, refused=True) is True
    assert not gate.should_read("holding", 10)
    assert gate.should_read("input", 14)  # other blocks are unaffected


def test_gate_gives_up_after_misses_in_a_row() -> None:
    gate = experimental.BlockGate()
    for _ in range(experimental.MISSES_BEFORE_GIVING_UP - 1):
        assert gate.record("input", 63, ok=False) is False
        assert gate.should_read("input", 63)
    assert gate.record("input", 63, ok=False) is True
    assert not gate.should_read("input", 63)
    assert gate.given_up == {("input", 63)}


def test_gate_an_answer_resets_the_misses() -> None:
    gate = experimental.BlockGate()
    gate.record("input", 63, ok=False)
    gate.record("input", 63, ok=False)
    gate.record("input", 63, ok=True)
    gate.record("input", 63, ok=False)
    gate.record("input", 63, ok=False)
    assert gate.should_read("input", 63)  # two misses since the answer
