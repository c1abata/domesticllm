# PDS4 dual-lane tuning

`pds4 benchmark plan` is the experiment matrix. `pds4 benchmark run` records
measurements with immutable model/runtime identity and a prompt hash; it never
stores the prompt or promotes a profile.

The initial production profile is Flash 32k, one session and 6 GiB expert
cache, plus one GPU-resident Fast model at 16k. The 6 GiB value is only a
baseline. Test expert cache, NVMe prefetch, pinned buffers, CPU affinity and
power limits independently. Promote 64k only after correctness and performance
gates; promote 100k only after the mixed-lane soak.

Partial CPU offload remains experimental unless the same prompt/model/runtime
comparison demonstrates better capacity or performance. Results from another
host are not transferable performance claims.
