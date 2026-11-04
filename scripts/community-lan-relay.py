"""Windows userspace TCP/UDP forwarding into WSL for a routed LAN test.

No system routes/firewall policy are changed. Bind a specific test interface.
"""
import argparse
import asyncio
import socket
import time


class UDPRelay(asyncio.DatagramProtocol):
    def __init__(self, target):
        self.target = target
        self.peers = {}

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, peer):
        if peer not in self.peers:
            if len(self.peers) >= 64:
                return
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            sock.connect(self.target)
            self.peers[peer] = [sock, time.monotonic()]
            asyncio.create_task(self.receive(peer, sock))
        self.peers[peer][1] = time.monotonic()
        try:
            self.peers[peer][0].send(data)
        except OSError:
            pass

    async def receive(self, peer, sock):
        try:
            while True:
                try:
                    packet = await asyncio.wait_for(asyncio.get_running_loop().sock_recv(sock, 65535), 10)
                    self.transport.sendto(packet, peer)
                except TimeoutError:
                    if time.monotonic() - self.peers[peer][1] > 120:
                        return
        finally:
            self.peers.pop(peer, None)
            sock.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--api-port', type=int, default=18080)
    parser.add_argument('--game-port', type=int, default=43210)
    args = parser.parse_args()

    async def tcp(reader, writer):
        upstream_writer = None
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(args.target, args.api_port)

            async def pump(source, destination):
                while chunk := await source.read(65536):
                    destination.write(chunk)
                    await destination.drain()
                if destination.can_write_eof():
                    destination.write_eof()
            tasks = [asyncio.create_task(pump(reader, upstream_writer)), asyncio.create_task(pump(upstream_reader, writer))]
            await asyncio.gather(*tasks, return_exceptions=True)
        except OSError:
            pass
        finally:
            writer.close()
            if upstream_writer:
                upstream_writer.close()

    server = await asyncio.start_server(tcp, args.bind, args.api_port)
    transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: UDPRelay((args.target, args.game_port)), local_addr=(args.bind, args.game_port))
    print(f'LAN relay ready: {args.bind} TCP {args.api_port}, UDP {args.game_port} -> {args.target}', flush=True)
    try:
        async with server:
            await server.serve_forever()
    finally:
        transport.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
