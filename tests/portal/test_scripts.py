"""Защита справочных скриптов редактора, в том числе на файловой системе Windows."""

from pathlib import Path

import pytest

from swarmlab.server.scripts import ScriptError, ScriptStore


@pytest.mark.parametrize(("name", "requested"), [
    ("template.py", "Template.py"),
    ("template.py", "TEMPLATE.py"),
    ("example_a.py", "Example_a.py"),
    ("example_a.py", "EXAMPLE_a.py"),
])
@pytest.mark.parametrize("operation", ["write", "delete"])
def test_reference_script_case_variant_cannot_change_script_or_blocks(
    tmp_path: Path, name: str, requested: str, operation: str,
):
    store = ScriptStore(tmp_path, tmp_path)
    script = tmp_path / name
    blocks = store.blocks_path(script)
    original_code = b"def loop(self):\n    self.wait(1)\n"
    original_blocks = b'{"format": 1, "mode": "blocks", "workspace": {"original": true}}'
    script.write_bytes(original_code)
    blocks.write_bytes(original_blocks)

    with pytest.raises(ScriptError) as error:
        if operation == "write":
            store.write(requested, "# changed\n", {
                "format": 1, "mode": "blocks", "workspace": {"changed": True},
            })
        else:
            store.delete(requested)

    assert error.value.status == 403
    assert script.read_bytes() == original_code
    assert blocks.read_bytes() == original_blocks
    assert {path.name for path in tmp_path.iterdir()} == {script.name, blocks.name}


def test_own_mixed_case_script_remains_writable_and_deletable(tmp_path: Path):
    store = ScriptStore(tmp_path, tmp_path)
    name = "My_agents.py"
    blocks = {"format": 1, "mode": "blocks", "workspace": {"blocks": []}}

    saved = store.write(name, "# first version\n", blocks)
    assert saved["ok"] and not saved["readonly"]
    saved = store.write(name, "# changed\n")
    assert saved["ok"] and not saved["readonly"]
    data = store.read(name)
    assert data["text"] == "# changed\n"
    assert data["blocks"] == blocks

    store.delete(name)
    assert not (tmp_path / name).exists()
    assert not store.blocks_path(tmp_path / name).exists()
