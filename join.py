import asyncio, sys

async def try_join(i):
    r, w = await asyncio.open_connection("127.0.0.1", 9000)
    w.write(b"frame 0\n")
    await w.drain()
    try:
        line = await asyncio.wait_for(r.readline(), 1.0)
    except asyncio.TimeoutError:
        line = b""
    if line.strip() == b"BUSY":
        print(f"user {i}: REJECTED (worker full)")
        w.close()
        return
    print(f"user {i}: accepted, got {line.strip().decode()!r}")
    await asyncio.sleep(1.5)          # stay connected so the others see a full worker
    w.close()

async def main():
    n = int(sys.argv[1])
    await asyncio.gather(*(try_join(i) for i in range(n)))

asyncio.run(main())