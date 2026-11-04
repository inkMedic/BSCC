# Community backend

FastAPI + PostgreSQL + Redis account, server directory and join preparation service.

See [deployment and development instructions](../docs/community/operations.md),
[protocol](../docs/community/protocol.md) and [verification status](../docs/community/acceptance.md).

Python 3.13; install `requirements.lock`, generate a random `COMMUNITY_SECRET`,
configure dedicated database/Redis in `.env`, run `alembic upgrade head`, then:

```bash
uvicorn community_backend.app:create_app --factory --workers 1
```

Create server keys with `python -m community_backend.cli create-server --name NAME`.
Never use player tokens as server credentials. OpenAPI is available at `/docs`.

Wallets, catalog purchases, global profile upgrades and monthly leagues are
documented in [community progression](../docs/community/progression.md).
Free test currency/card purchases require explicit
`COMMUNITY_TEST_PURCHASES_ENABLED=1` (default: disabled).

Free co-op tournament entry and client-reported standings use the stock game
windows; see [tournaments](../docs/community/tournaments.md) for their verification
and reward boundaries. Apply migration 0004 with `alembic upgrade head`.

Migration 0005 adds rotating events, reward settlement, a four-slot chest dock,
overflow inbox and transactional opening; see [rewards](../docs/community/rewards.md).
`COMMUNITY_TOURNAMENT_PERIOD_SECONDS` defaults to21600; the LAN script uses900.
