# Released under the MIT License. See LICENSE for details.
"""Local account partitions and conflict merging for personal campaign saves."""

import copy
import json

OWNER_KEY = 'Community Solo Progress Owner'
_SAVES_KEY = 'Community Solo Progress'
_SECTIONS = ('Achievements', 'Campaigns')
_SCORES_PREFIX = 'High Scores'


def select_progress(config, owner: str) -> None:
    """Bind the engine's existing config sections to one account or guest."""
    previous = config.get(OWNER_KEY, config.get('Community Profile Owner')) or ''
    saves = config.setdefault(_SAVES_KEY, {})
    # The live sections are the latest copy, including saves from old builds.
    saves[previous] = {key: config.get(key, {}) for key in _SECTIONS}
    selected = saves.setdefault(owner, {})
    for key in _SECTIONS:
        config[key] = selected.setdefault(key, {})
    config[OWNER_KEY] = owner
    config.commit()


def snapshot(config, campaigns) -> dict:
    """Read a detached cloud snapshot while leaving local UI selection alone."""
    progress = {
        'achievements': sorted(
            name for name, state in config.get('Achievements', {}).items()
            if isinstance(state, dict) and state.get('Complete') is True
        ),
        'campaigns': {},
    }
    for name, levels in config.get('Campaigns', {}).items():
        if not isinstance(levels, dict):
            continue
        campaign = campaigns.get(name)
        score_orders = (
            {level.name: level.gametype.getscoreconfig().lower_is_better
             for level in campaign.levels} if campaign is not None else {}
        )
        for level_name, state in levels.items():
            if level_name == 'Selection' or not isinstance(state, dict):
                continue
            scores = {
                key[len(_SCORES_PREFIX):]: value
                for key, value in state.items()
                if key.startswith(_SCORES_PREFIX) and isinstance(value, dict)
                and value
            }
            complete = state.get('Complete') is True
            rating = state.get('Rating', 0.0)
            if not (complete or rating or scores):
                continue
            progress['campaigns'].setdefault(name, {})[level_name] = {
                'complete': complete,
                'rating': rating,
                'lower_is_better': score_orders.get(
                    level_name, state.get('Community Lower Is Better', False)
                ),
                'scores': copy.deepcopy(scores),
            }
    return progress


def merge_progress(local: dict, remote: dict) -> dict:
    """Combine completed milestones and the best ten scores in each board."""
    merged = copy.deepcopy(local)
    merged['achievements'] = sorted(
        set(local['achievements']) | set(remote['achievements'])
    )
    for campaign, levels in remote['campaigns'].items():
        target_levels = merged['campaigns'].setdefault(campaign, {})
        for name, cloud in levels.items():
            if name not in target_levels:
                target_levels[name] = copy.deepcopy(cloud)
                continue
            level = target_levels[name]
            level['complete'] |= cloud['complete']
            level['rating'] = max(level['rating'], cloud['rating'])
            for version, boards in cloud['scores'].items():
                target_boards = level['scores'].setdefault(version, {})
                for count, scores in boards.items():
                    # Exact duplicate entries arise naturally after a retry
                    # or when both devices started with the same snapshot.
                    unique = {
                        json.dumps(score, sort_keys=True): score
                        for score in [*target_boards.get(count, []), *scores]
                    }
                    direction = 1 if level['lower_is_better'] else -1
                    ordered = sorted(
                        unique.items(),
                        key=lambda item: (direction * item[1][0], item[0]),
                    )
                    target_boards[count] = [score for _, score in ordered[:10]]
    return merged


def apply_progress(config, progress: dict) -> None:
    """Restore merged milestones into the engine's active account save."""
    achievements = config.setdefault('Achievements', {})
    for name in progress['achievements']:
        achievements.setdefault(name, {})['Complete'] = True
    campaigns = config.setdefault('Campaigns', {})
    for campaign, levels in progress['campaigns'].items():
        target_levels = campaigns.setdefault(campaign, {})
        for name, source in levels.items():
            level = target_levels.setdefault(name, {})
            level['Complete'] = source['complete']
            level['Rating'] = source['rating']
            level['Community Lower Is Better'] = source['lower_is_better']
            for version, boards in source['scores'].items():
                level[_SCORES_PREFIX + version] = boards
    config.commit()
