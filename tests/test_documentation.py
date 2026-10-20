"""Execute README YAML through HA's real script engine with a fake cloud."""

import re
from pathlib import Path

import pytest
import yaml
from homeassistant.core import Context
from homeassistant.helpers.script import Script

from . import test_entities

configured = test_entities.configured

README = Path(__file__).resolve().parents[1] / "README.md"


@pytest.mark.parametrize("index", [0, 1, 2])
async def test_readme_scripts_work_with_actual_guarded_entities(
    hass, configured, device_payload, index
):
    entry, api, coordinator = configured
    examples = re.findall(r"```yaml\n(.*?)```", README.read_text(), re.S)
    assert len(examples) == 3
    example = yaml.safe_load(examples[index])
    # Setup observed no bottle; a later full read now sees the replacement.
    device_payload["shadow"]["state"]["reported"]["hardware"]["alerts"][
        "bottleMissing"
    ] = False
    reads_before = api.get_device_details.await_count
    for step in example["sequence"]:
        assert hass.states.get(step["target"]["entity_id"]) is not None
    script = Script(
        hass,
        example["sequence"],
        example["alias"],
        "fpa",
        script_mode=example.get("mode", "single"),
    )
    await script.async_run(context=Context())
    assert api.get_device_details.await_count > reads_before
    if index == 1:
        api.start_bottle.assert_not_awaited()
    else:
        api.start_bottle.assert_awaited_once_with(1001)
        assert coordinator.guard.pending
    if index == 2:
        assert coordinator.selected_id is None


def test_readme_internal_links_and_anchors_exist():
    text = README.read_text()
    headings = re.findall(r"^#+ (.+)$", text, re.M)
    anchors = {
        re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in headings
    }
    for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if link.startswith("#"):
            assert link[1:] in anchors
        elif not link.startswith(("http://", "https://")):
            assert (README.parent / link).exists(), link
