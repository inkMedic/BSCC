"""The client must preserve separate saves and reconcile offline progress."""
import importlib.util
import json
from pathlib import Path

path = (Path(__file__).resolve().parents[2]
        / 'src/assets/ba_data/python/baplus/_community_progress.py')
spec = importlib.util.spec_from_file_location('solo_progress', path)
solo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solo)


class Config(dict):
    def commit(self):
        pass


def test_save_switch_after_restart_preserves_account_and_guest_progress():
    config = Config({
        'Community Profile Owner': 'a',
        'Achievements': {'First Victory': {'Complete': True}},
        'Campaigns': {'Easy': {'Test Level': {'Complete': True}}},
    })
    solo.select_progress(config, 'a')
    solo.select_progress(config, '')
    config['Achievements']['Guest'] = {'Complete': True}
    solo.select_progress(config, 'b')
    assert solo.snapshot(config, {}) == {'achievements': [], 'campaigns': {}}
    config['Achievements']['Account B'] = {'Complete': True}
    config = Config(json.loads(json.dumps(config)))
    solo.select_progress(config, 'a')
    assert solo.snapshot(config, {})['achievements'] == ['First Victory']
    assert config['Campaigns']['Easy']['Test Level']['Complete']
    solo.select_progress(config, 'b')
    assert solo.snapshot(config, {})['achievements'] == ['Account B']
    solo.select_progress(config, '')
    assert solo.snapshot(config, {})['achievements'] == ['Guest']


def test_merge_preserves_progress_and_deduplicates_faster_times():
    def progress(achievement, scores, complete):
        return {
            'achievements': [achievement],
            'campaigns': {'Easy': {'Race': {
                'complete': complete, 'rating': 0.0, 'lower_is_better': True,
                'scores': {' 2': {'1 Player': [
                    [score, {'players': [{'name': 'Player', 'character': 'Spaz'}]}]
                    for score in scores
                ]}},
            }}},
        }

    local = progress('Local', [12, 15], False)
    remote = progress('Remote', [10, 12], True)
    merged = solo.merge_progress(local, remote)
    assert merged['achievements'] == ['Local', 'Remote']
    level = merged['campaigns']['Easy']['Race']
    assert level['complete'] is True
    assert [score for score, _ in level['scores'][' 2']['1 Player']] == [10, 12, 15]
    config = Config({'Campaigns': {'Easy': {'Selection': 'Race'}}})
    solo.apply_progress(config, merged)
    assert config['Campaigns']['Easy']['Selection'] == 'Race'
    assert solo.snapshot(config, {}) == merged
    assert solo.merge_progress(merged, remote) == merged
