"""Same protocol as worker.py, but every frame is a REAL image-to-image pass on the GPU.
Usage: python gpu_worker.py 9000          (port; 9000 = loadtest.py talks to it directly)
Env:   MAX_SESSIONS=1  SIZE=512
"""
import asyncio, os, sys, time
import torch
from diffusers import AutoPipelineForImage2Image
from PIL import Image

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "1"))
SIZE = int(os.environ.get("SIZE", "512"))
PROMPT = "a watercolor painting, detailed"

print("GPU:", torch.cuda.get_device_name(0), "| loading model...")
pipe = AutoPipelineForImage2Image.from_pretrained(
    "stabilityai/sd-turbo", torch_dtype=torch.float16, variant="fp16")
pipe.to("cuda")
pipe.set_progress_bar_config(disable=True)
img = Image.linear_gradient("L").convert("RGB").resize((SIZE, SIZE))

def run_frame():
    """One real GPU frame. Runs in a worker thread so the event loop stays free."""
    t = time.perf_counter()
    pipe(PROMPT, image=img, num_inference_steps=2, strength=0.5,
         guidance_scale=0.0)       # full pipeline incl. image decode: a real finished frame
    torch.cuda.synchronize()
    return (time.perf_counter() - t) * 1000

for _ in range(5):
    run_frame()                                   # warm-up so the first user isn't slow
print(f"warm: one frame ~ {run_frame():.1f} ms at {SIZE}x{SIZE}")

gpu = asyncio.Lock()                              # one frame on the GPU at a time
active = 0
gpu_ms = []                                       # measured GPU time per frame

async def handle(reader, writer):
    global active
    if active >= MAX_SESSIONS:
        writer.write(b"BUSY\n")
        await writer.drain()
        writer.close()
        print(f"[{PORT}] rejected a session (active {active}/{MAX_SESSIONS})")
        return
    active += 1
    print(f"[{PORT}] session started (active {active}/{MAX_SESSIONS})")

    slot = {"frame": None, "closed": False}
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
                    gpu_ms.append(await asyncio.to_thread(run_frame))
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
        xs = sorted(gpu_ms[-200:])
        if xs:
            print(f"[{PORT}] GPU frame time p50 {xs[len(xs)//2]:.1f} ms  p95 {xs[int(len(xs)*0.95)]:.1f} ms")
        print(f"[{PORT}] session ended: processed {stats['processed']}, dropped {stats['dropped']}")

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", PORT)
    print(f"gpu_worker listening on 127.0.0.1:{PORT} (max {MAX_SESSIONS} sessions)")
    async with server:
        await server.serve_forever()

asyncio.run(main())
