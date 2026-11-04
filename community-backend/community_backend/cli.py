"""Offline administrative CLI; raw server keys are printed once."""
import argparse
import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .config import Settings
from .models import Server
from .security import token, digest


async def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('create-server').add_argument('--name', required=True)
    sub.add_parser('revoke-server').add_argument('server_id')
    args = parser.parse_args()
    engine = create_async_engine(Settings().database_url)
    try:
        async with async_sessionmaker(engine)() as db:
            if args.action == 'create-server':
                key, sid = token(), str(uuid.uuid4())
                db.add(Server(id=sid, name=args.name, key_hash=digest(key)))
                await db.commit()
                print(f'COMMUNITY_SERVER_ID={sid}\nCOMMUNITY_SERVER_KEY={key}')
            else:
                server = await db.get(Server, args.server_id)
                if not server:
                    parser.error('unknown server_id')
                server.revoked = True
                await db.commit()
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
