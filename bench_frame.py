"""Step 1 on the rented GPU: how long does ONE real frame take?
Usage: python bench_frame.py            (tests 256, 384, 512 px)
       python bench_frame.py 512        (tests only 512 px)
"""
import sys, time, statistics
import torch
from diffusers import AutoPipelineForImage2Image
from PIL import Image

PROMPT = "a watercolor painting, detailed"
SIZES = [int(a) for a in sys.argv[1:]] or [256, 384, 512]
N = 50

print("GPU:", torch.cuda.get_device_name(0), "| torch", torch.__version__, "| CUDA", torch.version.cuda)
pipe = AutoPipelineForImage2Image.from_pretrained(
    "stabilityai/sd-turbo", torch_dtype=torch.float16, variant="fp16")
pipe.to("cuda")
pipe.set_progress_bar_config(disable=True)

for size in SIZES:
    img = Image.linear_gradient("L").convert("RGB").resize((size, size))

    def one_frame():
        t = time.perf_counter()
        pipe(PROMPT, image=img, num_inference_steps=2, strength=0.5,
             guidance_scale=0.0)       # full pipeline incl. image decode: a real finished frame
        torch.cuda.synchronize()
        return (time.perf_counter() - t) * 1000

    for _ in range(5):                                       # warm-up, not counted
        one_frame()
    ms = sorted(one_frame() for _ in range(N))
    p50, p95, mx = ms[N // 2], ms[int(N * 0.95)], ms[-1]
    print(f"\n{size}x{size}: p50 {p50:.1f} ms  p95 {p95:.1f} ms  max {mx:.1f} ms  ({N} frames)")
    for fps in (10, 20, 30):
        print(f"   at {fps} fps -> {1000 / (fps * p50):.1f} sessions per GPU (GPU 100% busy)")
