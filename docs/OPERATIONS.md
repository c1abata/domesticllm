# Operations

```bash
sudo systemctl restart local-ai-cpu
sudo systemctl status local-ai-cpu --no-pager
journalctl -u local-ai-cpu -f
```

Health:
```bash
bash scripts/80_health_report.sh
```

LAN:
```bash
sudo bash scripts/41_net_check_1gbe.sh enp3s0
sudo ufw status verbose
```

Cache:
```bash
bash scripts/60_slot_save.sh 0 work.bin
bash scripts/61_slot_restore.sh 0 work.bin
bash scripts/62_slot_erase.sh 0
```


DS4 Intel profile:

```bash
sudo systemctl restart local-ai-ds4-intel
sudo systemctl status local-ai-ds4-intel --no-pager
journalctl -u local-ai-ds4-intel -f
curl http://127.0.0.1:8081/health
ENV_FILE=/etc/local-ai-ds4-intel.env SERVICE=local-ai-ds4-intel bash scripts/80_health_report.sh
```
