from test_service import register, auth


def test_account_profiles_persist_and_validate(client):
    login, account = register(client)
    profile = dict(character='Spaz', color=[1, .4, 0], highlight=[.5, 1, 1], icon='', **{'global': False})
    path = '/v1/me/profiles/__account__'
    assert client.put(path, json=profile).status_code == 401
    assert client.put(path, headers=auth(account), json=profile).status_code == 200
    me = client.get('/v1/me', headers=auth(account)).json()
    assert me['player_profiles']['__account__']['character'] == 'Spaz'
    signed_in = client.post('/v1/auth/login', json=dict(login=login, password='correct-password')).json()
    assert signed_in['user']['player_profiles'] == me['player_profiles']
    assert client.put(path, headers=auth(account), json=profile | {'global': True}).status_code == 403
    assert client.put('/v1/me/profiles/__invalid__', headers=auth(account), json=profile).status_code == 422
    assert client.delete(path, headers=auth(account)).status_code == 200
    assert client.get('/v1/me', headers=auth(account)).json()['player_profiles'] == {}
