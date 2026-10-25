"""A short Windows sharing conflict must not abort an expensive upload job."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from panorama_pipeline import _write


def test_atomic_status_retries_sharing_conflict_without_partial_json(tmp_path):
    target = tmp_path / 'status.json'
    target.write_text('{"status":"previous"}', encoding='utf-8')
    replace = Path.replace
    attempts = []

    def briefly_locked(source, destination):
        attempts.append(str(source))
        if len(attempts) <= 2:
            assert json.loads(target.read_text(encoding='utf-8'))['status'] == 'previous'
            raise PermissionError('temporary sharing violation fixture')
        return replace(source, destination)

    with patch.object(Path, 'replace', briefly_locked), patch('panorama_pipeline.time.sleep'):
        _write(target, {'status': 'complete'})
    assert len(attempts) == 3
    assert json.loads(target.read_text(encoding='utf-8')) == {'status': 'complete'}
    assert list(tmp_path.glob('*.tmp')) == []


def test_permanent_denial_is_bounded_and_preserves_previous_status(tmp_path):
    target = tmp_path / 'status.json'
    target.write_text('{"status":"previous"}', encoding='utf-8')
    with patch.object(Path, 'replace', side_effect=PermissionError('fixture denied')) as replace:
        with patch('panorama_pipeline.time.sleep'), pytest.raises(PermissionError):
            _write(target, {'status': 'complete'})
    assert replace.call_count == 20
    assert json.loads(target.read_text(encoding='utf-8')) == {'status': 'previous'}
    assert list(tmp_path.glob('*.tmp')) == []
