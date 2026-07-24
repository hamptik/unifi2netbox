"""Tests for NETBOX_USE_CUSTOM_FIELDS gating."""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main
from main import sync_device_custom_fields
from sync.runtime_config import load_use_custom_fields


# ---------------------------------------------------------------------------
#  load_use_custom_fields (env parsing)
# ---------------------------------------------------------------------------

class TestLoadUseCustomFields:
    def test_defaults_true_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            assert load_use_custom_fields() is True

    def test_explicit_true(self):
        with patch.dict(os.environ, {"NETBOX_USE_CUSTOM_FIELDS": "true"}, clear=True):
            assert load_use_custom_fields() is True

    def test_explicit_false(self):
        with patch.dict(os.environ, {"NETBOX_USE_CUSTOM_FIELDS": "false"}, clear=True):
            assert load_use_custom_fields() is False

    def test_invalid_falls_back_to_default(self):
        with patch.dict(os.environ, {"NETBOX_USE_CUSTOM_FIELDS": "maybe"}, clear=True):
            assert load_use_custom_fields() is True


# ---------------------------------------------------------------------------
#  sync_device_custom_fields gating
# ---------------------------------------------------------------------------

class TestSyncDeviceCustomFieldsGating:
    def _make(self):
        nb = MagicMock()
        nb_device = SimpleNamespace(
            name="dev1",
            custom_fields={},
            save=MagicMock(),
        )
        device = {
            "mac": "aa:bb:cc:dd:ee:ff",
            "uptimeSec": 12345,
            "lastSeen": 1700000000,
            "version": "1.2.3",
        }
        return nb, nb_device, device

    def test_disabled_skips_custom_field_creation_and_save(self):
        nb, nb_device, device = self._make()
        with patch.object(main, "USE_CUSTOM_FIELDS", False):
            sync_device_custom_fields(nb, nb_device, device)
        # No custom field should be ensured, nothing written, no save.
        nb.extras.custom_fields.filter.assert_not_called()
        nb.extras.custom_fields.create.assert_not_called()
        nb_device.save.assert_not_called()
        assert nb_device.custom_fields == {}

    def test_enabled_creates_and_updates(self):
        nb, nb_device, device = self._make()
        # Simulate custom_fields endpoint: ensure returns None on filter,
        # create returns a fake cf object.
        nb.extras.custom_fields.filter.return_value = []
        created_cf = SimpleNamespace(id=1, name="x")
        nb.extras.custom_fields.create.return_value = created_cf
        with patch.object(main, "USE_CUSTOM_FIELDS", True):
            sync_device_custom_fields(nb, nb_device, device)
        # At least one custom field should have been created.
        assert nb.extras.custom_fields.create.called
        # Values should have been written and saved.
        assert nb_device.custom_fields.get("unifi_firmware") == "1.2.3"
        assert nb_device.save.called
