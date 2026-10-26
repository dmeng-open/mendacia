import pytest

from agents.inventory import problems, scan_module, sources

BOT = "sim.detective_bot"


def bot_source() -> str:
    return dict(sources())[BOT]


def test_the_detective_bot_has_no_oracle() -> None:
    use = scan_module(BOT, bot_source())

    assert problems([use]) == []
    assert "engine" not in use.imports
    assert not use.reads_files
    assert not use.reads_truth


@pytest.mark.parametrize(
    ("line", "found"),
    [
        ("from engine.schema import Case", "imports 'engine'"),
        ("import engine.solver", "imports 'engine'"),
        ("text = open('cases/manor.json').read()", "reads files"),
        ("text = Path('cases/manor.json').read_text()", "reads files"),
        ("who = case.culprit", "reads the truth layer"),
    ],
)
def test_an_oracle_in_the_bot_fails_the_inventory(line: str, found: str) -> None:
    use = scan_module(BOT, f"{bot_source()}\n{line}\n")

    assert any(found in p for p in problems([use]))
