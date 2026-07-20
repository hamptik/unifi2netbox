"""Tests for the optional device-tag hook (SYNC_DEVICE_TAG env var)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main
from main import apply_extra_device_tag


def _device(existing_tag_ids=None):
    """A fake nb_device whose .tags list is observable via .save() calls."""
    tags = []
    for tid in (existing_tag_ids or []):
        t = SimpleNamespace(id=tid, slug=f"tag-{tid}")
        tags.append(t)
    dev = SimpleNamespace(name="dev1", tags=tags, save=MagicMock())
    return dev


class TestApplyExtraDeviceTagNoop:
    def test_empty_tag_name_is_noop(self):
        nb = MagicMock()
        dev = _device()
        apply_extra_device_tag(nb, dev, "")
        nb.extras.tags.get.assert_not_called()
        dev.save.assert_not_called()

    def test_none_tag_name_is_noop(self):
        nb = MagicMock()
        dev = _device()
        apply_extra_device_tag(nb, dev, None)
        dev.save.assert_not_called()

    def test_whitespace_only_tag_name_is_noop(self):
        # Caller is expected to .strip() before calling, but helper is defensive.
        nb = MagicMock()
        dev = _device()
        apply_extra_device_tag(nb, dev, "   ")
        dev.save.assert_not_called()


class TestApplyExtraDeviceTagAttach:
    def _setup_nb(self, tag_slug, tag_id):
        nb = MagicMock()
        nb.extras.tags.get.return_value = SimpleNamespace(id=tag_id, slug=tag_slug, name=tag_slug)
        return nb

    def test_adds_tag_when_missing(self):
        nb = self._setup_nb("zabbix", 99)
        dev = _device(existing_tag_ids=[1, 2])
        apply_extra_device_tag(nb, dev, "zabbix")
        # Save called once, new tag id 99 appended.
        dev.save.assert_called_once()
        # Helper stores tag IDs (ints), not tag objects, on nb_device.tags.
        assert dev.tags[-1] == 99
        assert 99 in dev.tags

    def test_does_not_duplicate_when_already_present(self):
        nb = self._setup_nb("zabbix", 99)
        dev = _device(existing_tag_ids=[1, 99, 2])
        apply_extra_device_tag(nb, dev, "zabbix")
        # Already has id 99 — should not save again.
        dev.save.assert_not_called()
        assert len(dev.tags) == 3

    def test_uses_ensure_tag_to_create_if_missing_in_netbox(self):
        # ensure_tag falls back to .create when .get returns None/empty.
        nb = MagicMock()
        nb.extras.tags.get.return_value = None
        nb.extras.tags.create.return_value = SimpleNamespace(id=77, slug="monitoring", name="monitoring")
        dev = _device(existing_tag_ids=[])
        with patch.object(main, "ensure_tag", return_value=SimpleNamespace(id=77, slug="monitoring")) as _mock_ensure:
            apply_extra_device_tag(nb, dev, "monitoring")
            _mock_ensure.assert_called_once_with(nb, "monitoring")
        dev.save.assert_called_once()


class TestApplyExtraDeviceTagFailure:
    def test_ensure_tag_returning_none_does_not_save(self):
        nb = MagicMock()
        dev = _device()
        with patch.object(main, "ensure_tag", return_value=None):
            apply_extra_device_tag(nb, dev, "ghost-tag")
        dev.save.assert_not_called()
