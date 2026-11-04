import asyncio
import sys
import time


async def session(fps, seconds):
    reader, writer = await asyncio.open_connection("127.0.0.1", 9000)
    sent_at, rtts, rejected, lost, arrivals = {}, [], [], [], []

    async def receive():
        while True:
            line = await reader.readline()
            if not line:
                lost.append(1)
                break
            if line.startswith(b"BUSY"):
                rejected.append(1)
                break
            seq = int(line.split()[1])
            rtts.append((time.perf_counter() - sent_at[seq]) * 1000)
            arrivals.append(time.perf_counter())

    rx = asyncio.create_task(receive())
    period = 1 / fps
    next_t = time.perf_counter()
    sent = 0
    while sent < fps * seconds and not rejected and not lost:   # send at a fixed rate, whether or not the server keeps up
        sent_at[sent] = time.perf_counter()
        writer.write(f"frame {sent}\n".encode())
        sent += 1
        next_t += period
        await asyncio.sleep(max(0, next_t - time.perf_counter()))
    await asyncio.sleep(0.5)                     # let the last answers arrive
    writer.close()
    rx.cancel()
    gap = max((b - a) * 1000 for a, b in zip(arrivals, arrivals[1:])) if len(arrivals) > 1 else 0
    return sent, rtts, bool(rejected), bool(lost), gap


def pct(xs, p):
    return xs[min(len(xs) - 1, int(len(xs) * p / 100))] if xs else float("nan")


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    fps = float(sys.argv[2]) if len(sys.argv) > 2 else 20
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 10
    results = await asyncio.gather(*[session(fps, seconds) for _ in range(n)])
    refused = sum(r[2] for r in results)
    lost = sum(r[3] for r in results)
    results = [r for r in results if not r[2]]
    if refused:
        print(f"{refused} session(s) REFUSED (system full)")
    if lost:
        print(f"{lost} session(s) LOST their connection (stream ended early)")
    gap = max((r[4] for r in results), default=0)
    sent = sum(r[0] for r in results)
    rtts = sorted(x for r in results for x in r[1])
    got = len(rtts)
    print(f"{len(results)} of {n} session(s) served at {fps:g} fps | sent {sent}, answered {got}, dropped {sent - got} ({100 * (sent - got) / sent:.0f}%) | "
          f"delivered {got / seconds / max(1, len(results)):.1f} fps per session | "
          f"longest silence {gap:.0f} ms | latency p50 {pct(rtts, 50):.0f} ms  p95 {pct(rtts, 95):.0f} ms  p99 {pct(rtts, 99):.0f} ms")


asyncio.run(main())