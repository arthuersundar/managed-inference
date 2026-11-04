import asyncio, time

WORKERS = [9001, 9002]       # the kitchens
CAPACITY = 1                 # sessions each kitchen can take (same as MAX_SESSIONS in worker.py)
DEAD_FOR = 5.0               # seconds to avoid a worker after it failed
load = {p: 0 for p in WORKERS}   # sessions the router has seated in each kitchen
dead_until = {}                  # port -> time until which we avoid it

def choose():
    now = time.time()
    free = [p for p in WORKERS if load[p] < CAPACITY and dead_until.get(p, 0) < now]
    return min(free, key=lambda p: load[p]) if free else None

async def pipe(src, dst):
    """Copy bytes src -> dst. Returns True if src closed cleanly, False if something broke."""
    try:
        while True:
            data = await src.read(4096)
            if not data:
                return True
            dst.write(data)
            await dst.drain()
    except (ConnectionError, OSError):
        return False

async def handle(user_r, user_w):
    first = True
    while True:
        port = choose()
        if port is None:
            if first:                                  # nobody has room: refuse at the door
                user_w.write(b"BUSY\n")
                await user_w.drain()
                print(f"all full {load} -> rejected")
            else:                                      # mid-session and nowhere to move the user
                print(f"FAILOVER FAILED: no worker has room {load} -> user disconnected")
            user_w.close()
            return
        load[port] += 1
        try:
            w_r, w_w = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            load[port] -= 1
            dead_until[port] = time.time() + DEAD_FOR
            print(f"cannot reach {port}, marking it dead")
            continue
        print(f"{'placed' if first else 'MOVED user'} on {port}  load now {load}")
        first = False
        up = asyncio.create_task(pipe(user_r, w_w))      # user -> worker
        down = asyncio.create_task(pipe(w_r, user_w))    # worker -> user
        done, _ = await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
        user_left = up in done and up.result() is True
        for t in (up, down):
            t.cancel()
        w_w.close()
        load[port] -= 1
        print(f"freed {port}  load now {load}")
        if user_left:                                    # the user hung up: session over
            user_w.close()
            return
        dead_until[port] = time.time() + DEAD_FOR        # the worker went away: avoid it, move the user
        print(f"worker {port} lost -> looking for another worker")

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", 9000)
    print(f"router listening on 9000, workers {WORKERS}")
    async with server:
        await server.serve_forever()

asyncio.run(main())
