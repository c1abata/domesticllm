from __future__ import annotations

import csv
import io
import subprocess
from dataclasses import dataclass

from .common import PDS4Error, Paths, atomic_write


@dataclass(frozen=True)
class GPU:
    uuid: str
    index: int
    pci_bus: str
    memory_mib: int
    compute: str


def discover() -> list[GPU]:
    command = [
        "nvidia-smi", "--query-gpu=uuid,index,pci.bus_id,memory.total,compute_cap",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise PDS4Error("nvidia-smi GPU probe failed") from exc
    found: list[GPU] = []
    for row in csv.reader(io.StringIO(result.stdout), skipinitialspace=True):
        if len(row) != 5 or not row[0].startswith("GPU-"):
            raise PDS4Error("nvidia-smi returned an unexpected GPU record")
        try:
            found.append(GPU(row[0], int(row[1]), row[2].lower(), int(row[3]), row[4]))
        except ValueError as exc:
            raise PDS4Error("nvidia-smi returned invalid numeric GPU data") from exc
    if len({gpu.uuid for gpu in found}) != len(found):
        raise PDS4Error("nvidia-smi returned duplicate GPU UUIDs")
    return found


def assign(flash_uuid: str, fast_uuid: str, paths: Paths, gpus: list[GPU] | None = None) -> None:
    if flash_uuid == fast_uuid:
        raise PDS4Error("Flash and Fast must use different GPU UUIDs")
    inventory = {gpu.uuid: gpu for gpu in (gpus if gpus is not None else discover())}
    if flash_uuid not in inventory or fast_uuid not in inventory:
        raise PDS4Error("requested GPU UUID is not present")
    for lane, uuid in (("FLASH", flash_uuid), ("FAST", fast_uuid)):
        gpu = inventory[uuid]
        if gpu.compute != "8.6":
            raise PDS4Error(f"{lane} GPU compute capability is {gpu.compute}, expected 8.6")
        if gpu.memory_mib < 19_000:
            raise PDS4Error(f"{lane} GPU has less than 19000 MiB")
    config = (
        f"PDS4_FLASH_GPU={flash_uuid}\nPDS4_FAST_GPU={fast_uuid}\n"
        f"PDS4_FLASH_PCI={inventory[flash_uuid].pci_bus}\n"
        f"PDS4_FAST_PCI={inventory[fast_uuid].pci_bus}\n"
    ).encode()
    atomic_write(paths.at("/etc/pds4/gpus.conf"), config, 0o640)
    units = (("pds4-flash.service", flash_uuid), ("pds4-fast@.service", fast_uuid),
             ("pds4-flash-canary.service", flash_uuid), ("pds4-fast-canary@.service", fast_uuid))
    for unit, uuid in units:
        gpu = inventory[uuid]
        dropin = paths.at(f"/etc/systemd/system/{unit}.d/10-gpu-device.conf")
        atomic_write(dropin, f"[Service]\nDeviceAllow=/dev/nvidia{gpu.index} rw\n".encode(), 0o644)
