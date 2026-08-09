# Operations

The server uses only CPU and system RAM. `GPU_LAYERS=0` is passed explicitly,
so the runtime cannot offload model layers to a GPU.

Before every model change, compute the SHA-256 locally, update `MODEL` and
`MODEL_SHA256`, then start the server. A mismatch is a hard error.

The provided systemd unit is a template, not an installer. It assumes:

- the repository was installed read-only at `/opt/cpu-inference`;
- the operator created the `cpu-inference` system user;
- configuration is at `/etc/cpu-inference/cpu-inference.env`;
- model files are readable from `/var/lib/cpu-inference/models/` and the
  template was updated so `MODEL` uses that path.

The service is configured to listen on `0.0.0.0` and requires an API key. Keep
the key file mode `0640`, owned by `root:cpu-inference`; pass it as a Bearer
token to `/v1/*` requests. Restrict inbound TCP/8080 to the required LAN at
the host firewall before exposing it outside the trusted network.

For first tuning, record prompt-token/s and generation-token/s at fixed
prompt, context, thread and model settings. Change one parameter at a time.
