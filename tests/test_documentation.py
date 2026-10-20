"""Check documentation navigation and execute guide examples with a fake cloud."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml
from homeassistant.core import Context
from homeassistant.helpers.script import Script

from . import test_entities

configured = test_entities.configured

README = Path(__file__).resolve().parents[1] / "README.md"
USER_GUIDE = README.parent / "docs/USER_GUIDE.md"


@pytest.mark.parametrize("index", [0, 1, 2])
async def test_user_guide_scripts_work_with_actual_guarded_entities(
    hass, configured, device_payload, index
):
    entry, api, coordinator = configured
    examples = re.findall(r"```yaml\n(.*?)```", USER_GUIDE.read_text(), re.S)
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


def _anchors(text):
    headings = re.findall(r"^#+ (.+)$", text, re.M)
    return {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in headings}


@pytest.mark.parametrize(
    "document", [README, USER_GUIDE], ids=["overview", "user-guide"]
)
def test_documentation_internal_links_and_anchors_exist(document):
    text = document.read_text()
    for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = urlsplit(link)
        if target.scheme or target.netloc:
            continue
        destination = (
            document.parent / unquote(target.path) if target.path else document
        )
        assert destination.is_file(), f"{document.name}: {link}"
        if target.fragment:
            assert unquote(target.fragment) in _anchors(destination.read_text()), link
