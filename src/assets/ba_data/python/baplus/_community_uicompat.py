"""Translate community API data for the unchanged built-in windows."""
import time


def league_data(data, uid):
    me = data['me'] or dict(games=0, wins=0, points=0, rank=None, tier='Bronze')
    minutes = int((data['ends_at'] - time.time()) // 60)
    color = {'Bronze': (.8, .5, .25), 'Silver': (.8, .8, .9),
             'Gold': (1., .85, .2), 'Diamond': (.6, .9, 1.)}[me['tier']]
    result = dict(s=data['season'], sl=data['seasons'], rank=me['rank'],
        scores=[[p['rank'], p['points'], p['nickname'], p['uid'] == uid, p['uid']] for p in data['leaderboard']],
        listSize=100, l=dict(n=me['tier'], i=1, i2=False, c=color),
        se=[minutes // 1440, minutes], a=0, at=0, act=1.0)
    for trophy in ('0a', '0b', '1', '2', '3', '4'):
        result['t' + trophy] = 0
        result['t' + trophy + 'm'] = 0
    # Existing community match rules: a win is worth 30, other finishes 10.
    # Feed those real counts into the stock trophy/points breakdown.
    result.update(t1=me['wins'], t1m=30, t4=me['games'] - me['wins'], t4m=10)
    return result
