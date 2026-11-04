# managed-inference

A small **simulator** of a real-time video inference platform, built to learn and measure
how session routing, admission control and failover behave when each user holds a GPU
for a live stream.

It is not a production system and it does not run Decart's (or anyone's) models.
The workers are stand-ins; the point is the platform behaviour around them.

## Status

| Part | State |
|---|---|
| Simulated worker with admission limit, newest-frame-wins dropping | done, measured |
| Session-aware router (least-loaded placement, refuses when full) | done, measured |
| Failover: move a live session when its worker dies | done, measured |
| Real model on a GPU (image-to-image diffusion stand-in) | scripts written, **not yet run** |
| Containers, EKS and GKE deployment, metrics | planned |

GPU quota requests on AWS and GCP were declined on new accounts, so the order is:
real GPU benchmark on a rented machine first, cloud clusters on CPU nodes next, GPU nodes
in the clusters if quota is approved later.

## How it works

```
user (loadtest.py) --> router.py (port 9000) --> worker.py (9001, 9002)
```

- **Worker**: one "GPU" (a lock), one frame at a time. Each session has a one-frame mailbox;
  if a newer frame arrives before the old one is processed, the old one is dropped
  (a live stream prefers fresh frames over complete ones). At `MAX_SESSIONS` it answers `BUSY`.
- **Router**: counts sessions per worker, places a new session on the least-loaded worker
  with room, answers `BUSY` when all are full. If a worker dies mid-session it moves the
  user to another worker with room, or disconnects the user if none has room.
- **Load test**: open-loop, each fake user sends frames at a fixed rate whether or not the
  server keeps up, and reports dropped %, delivered fps, latency percentiles and the
  longest silence between replies.

Capacity rule used throughout: GPU busy = sessions x fps x frame time. Above 100% the
system must drop frames, refuse users, or add GPUs.

## Measured results (laptop, simulated worker)

Windows laptop, Python asyncio, 20 fps per session, 10 s per run. The "GPU" is a 20 ms
`sleep`; on this machine it actually takes about 31 ms because of the Windows timer tick,
so one session uses about 62% of the simulated GPU. Single runs, not averaged.

### One worker, no admission limit

| Sessions | Dropped | Delivered per session | Latency p50 / p95 |
|---|---|---|---|
| 1 | 0% | 20.0 fps | 32 / 33 ms |
| 2 | 19% | 16.2 fps | 94 / 124 ms |
| 3 | 46% | 10.8 fps | 125 / 156 ms |
| 4 | 59% | 8.2 fps | 156 / 187 ms |

Total throughput stays at about 325 frames per 10 s regardless of sessions: the worker
has a fixed number of frames per second and more users only split it.

### Two workers behind the router (1 session each)

| Users | Result |
|---|---|
| 2 | both served, 0% dropped, p50 32 ms, p95 33 ms |
| 3 | 2 served cleanly (same numbers as above), 1 refused with `BUSY` |

### Failover (worker killed 5 s into a 15 s run)

| Case | Result |
|---|---|
| Baseline, no failure | 300 of 300 frames, longest silence 64 ms |
| 1 user, spare worker available | session moved, 299 of 300 frames, longest silence 94 ms |
| 2 users, no spare capacity | 1 user lost their stream; the other was unaffected (silence at baseline) |

Takeaway: failover only works with headroom. To survive one worker failure, admit at most
(N - 1) x per-worker capacity sessions.

### What these numbers do not show

- Detection was instant because killing a process closes its socket. A frozen or
  network-partitioned GPU node needs health checks and timeouts, which take seconds.
- The replacement worker was already running. A real worker has to load a model first.
- Workers hold no per-session state; real world-model sessions would lose or have to restore it.
- Everything ran on one machine over localhost.

## GPU benchmark

`bench_frame.py` measures real frame time of an image-to-image diffusion model
(`stabilityai/sd-turbo`, 2 steps, strength 0.5) at 256, 384 and 512 px, and prints the
implied sessions per GPU at 10, 20 and 30 fps. `gpu_worker.py` is the same worker protocol
with that model doing real work per frame.

Results: **pending** (to be filled in with GPU model, driver, torch and diffusers versions).

| GPU | Resolution | Frame p50 / p95 | Sessions per GPU at 20 fps |
|---|---|---|---|
| (pending) | | | |

## Run it

```bash
python worker.py 9001        # terminal 1
python worker.py 9002        # terminal 2
python router.py             # terminal 3
python loadtest.py 2 20 10   # sessions, fps, seconds
python join.py 3             # who gets in when 3 users arrive at once
```

On a GPU machine:

```bash
pip install diffusers transformers accelerate pillow
python bench_frame.py
MAX_SESSIONS=1 python gpu_worker.py 9000
python loadtest.py 1 20 10
```

## Next

1. Run the GPU benchmark and capacity test; record the numbers above.
2. Container image, then EKS and GKE on CPU nodes with the simulated worker.
3. Prometheus metrics labelled by model, chip and region; alerts.
4. Cross-cloud failover (kill one cluster, move users to the other).
5. Health checks that detect frozen workers, not only dead ones; short queue instead of immediate refusal.
6. LLM serving with vLLM: time to first token, inter-token gap, tokens per second.
