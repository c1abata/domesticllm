# Operations

The server uses only CPU and system RAM. Do not pass GPU offload flags such as
`--n-gpu-layers`; no GPU runtime is installed or selected by this project.

Before every model change, compute the SHA-256 locally, update `MODEL` and
`MODEL_SHA256`, then start the server. A mismatch is a hard error.

The provided systemd unit is a template, not an installer. It assumes:

- the repository was installed read-only at `/opt/cpu-inference`;
- the operator created the `cpu-inference` system user;
- configuration is at `/etc/cpu-inference/cpu-inference.env`;
- model files are readable from `/var/lib/cpu-inference/models/` and the
  template was updated so `MODEL` uses that path.

For first tuning, record prompt-token/s and generation-token/s at fixed
prompt, context, thread and model settings. Change one parameter at a time.
