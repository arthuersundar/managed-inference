import asyncio, sys
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9001

FRAME_MS = 20           # pretend one frame takes 20 ms on the "GPU"
MAX_SESSIONS = 1        # admission limit: how many sessions this worker accepts
gpu = asyncio.Lock()    # only ONE frame can use the GPU at a time
active = 0              # sessions currently being served

async def handle(reader, writer):
    global active
    if active >= MAX_SESSIONS:                 # full: refuse politely instead of degrading everyone
        writer.write(b"BUSY\n")
        await writer.drain()
        writer.close()
        print(f"[{PORT}] rejected a session (active {active}/{MAX_SESSIONS})")
        return
    active += 1
    print(f"[{PORT}] session started (active {active}/{MAX_SESSIONS})")

    slot = {"frame": None, "closed": False}   # a one-frame mailbox: only the newest frame is kept
    ready = asyncio.Event()
    stats = {"processed": 0, "dropped": 0}

    async def receive():
        while True:
            line = await reader.readline()
            if not line:
                break
            if slot["frame"] is not None:
                stats["dropped"] += 1
            slot["frame"] = line
            ready.set()
        slot["closed"] = True
        ready.set()

    task = asyncio.create_task(receive())
    try:
        while True:
            await ready.wait()
            ready.clear()
            frame, slot["frame"] = slot["frame"], None
            if frame is not None:
                async with gpu:
                    await asyncio.sleep(FRAME_MS / 1000)
                writer.write(frame.upper())
                await writer.drain()
                stats["processed"] += 1
            if slot["closed"] and slot["frame"] is None:
                break
    except ConnectionError:
        pass
    finally:
        active -= 1
        task.cancel()
        writer.close()
        print(f"[{PORT}] session ended: processed {stats['processed']}, dropped {stats['dropped']}")

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", PORT)
    print(f"worker listening on 127.0.0.1:{PORT} (max {MAX_SESSIONS} session)")
    async with server:
        await server.serve_forever()

asyncio.run(main())