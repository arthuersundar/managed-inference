import socket
import time

s = socket.create_connection(("127.0.0.1", 9000))
f = s.makefile("rw")
times = []
for i in range(50):
    t0 = time.perf_counter()
    f.write(f"frame {i}\n")
    f.flush()
    f.readline()                                     # wait for the result
    times.append((time.perf_counter() - t0) * 1000)  # milliseconds
times.sort()
print(f"p50 {times[25]:.1f} ms   p95 {times[47]:.1f} ms   max {times[-1]:.1f} ms")