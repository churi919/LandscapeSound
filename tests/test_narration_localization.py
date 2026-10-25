"""Guide translations are bound to source text and language, never a fallback."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from narration_localization import (ensure_localized_text, load_localized_text,
                                     store_reviewed_translation, translate_narration_with_gpt)

ZH = '前方是岩石间的浅溪，声音为依据图片设计的模拟。'
EN = 'A shallow stream lies between the rocks ahead. The sound is simulated from the image.'


def test_source_language_needs_no_translation_or_network(tmp_path):
    with patch('narration_localization.translate_narration_with_gpt') as translator:
        record = ensure_localized_text(ZH, 'zh-CN', tmp_path)
    assert record['text'] == ZH
    assert record['provenance']['translated'] is False
    translator.assert_not_called()
    assert not (tmp_path / 'assets').exists()


def test_translated_cache_is_exact_source_and_locale_bound(tmp_path):
    with patch('narration_localization.translate_narration_with_gpt', return_value={
            'text': EN, 'provenance': {'method': 'fixture translator'}}) as translator:
        first = ensure_localized_text(ZH, 'en', tmp_path)
        second = ensure_localized_text(ZH, 'en', tmp_path)
    assert first == second
    translator.assert_called_once()
    assert first['source_text_sha256'] == hashlib.sha256(ZH.encode()).hexdigest()
    assert first['text_sha256'] == hashlib.sha256(EN.encode()).hexdigest()
    assert first['language'] == 'en'
    assert load_localized_text(ZH + '新文字', 'en', tmp_path) is None
    assert load_localized_text(ZH, 'zh-CN', tmp_path)['text'] == ZH


def test_invalid_or_modified_translation_is_not_reused(tmp_path):
    with pytest.raises(ValueError, match='requested language'):
        ensure_localized_text(ZH, 'en', tmp_path, translator=lambda *_: {
            'text': ZH, 'provenance': {'method': 'invalid fixture'}})
    assert load_localized_text(ZH, 'en', tmp_path) is None
    store_reviewed_translation(ZH, EN, 'en', {'method': 'reviewed fixture'}, tmp_path)
    path = tmp_path / 'assets/narration_localization' / hashlib.sha256(ZH.encode()).hexdigest() / 'en.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    record['text'] = 'An unrelated English guide.'
    path.write_text(json.dumps(record), encoding='utf-8')
    assert load_localized_text(ZH, 'en', tmp_path) is None


def test_translation_failure_keeps_original_and_does_not_fabricate_cache(tmp_path):
    with pytest.raises(RuntimeError, match='unavailable'):
        ensure_localized_text(ZH, 'en', tmp_path,
                              translator=lambda *_: (_ for _ in ()).throw(RuntimeError('unavailable')))
    assert load_localized_text(ZH, 'en', tmp_path) is None
    assert not list(tmp_path.rglob('*.lock'))
    assert load_localized_text(ZH, 'zh-CN', tmp_path)['text'] == ZH


def test_text_only_gpt_request_keeps_tools_disabled_and_binds_output(tmp_path):
    status = {'available': True, 'logged_in': True, 'executable': 'codex.exe', 'version': 'test-client'}
    def run(command, prompt, folder, timeout):
        assert '--image' not in command
        assert '--ignore-user-config' in command and '--ephemeral' in command
        assert command[command.index('--sandbox') + 1] == 'read-only'
        assert 'SOURCE_JSON:' in prompt and ZH in prompt
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps({'text': EN}), encoding='utf-8')
        return 'test-session', [], .1
    with patch('gpt_cli_bridge.gpt_cli_status', return_value=status), \
            patch('gpt_cli_bridge._run_isolated', side_effect=run):
        result = translate_narration_with_gpt(ZH, 'en', tmp_path)
    assert result['text'] == EN
    assert result['provenance']['source_text_sha256'] == hashlib.sha256(ZH.encode()).hexdigest()
    assert result['provenance']['tools_permitted'] is False
