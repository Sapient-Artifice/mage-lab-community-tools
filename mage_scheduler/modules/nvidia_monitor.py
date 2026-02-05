"""
Utilities to retrieve and parse NVIDIA GPU statistics via nvidia-smi.
"""

import subprocess


def get_nvidia_smi_output():
    """
    Executes nvidia-smi to query GPU utilization and memory stats.
    Returns the raw CSV output as a string, or an empty string on error.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,utilization.gpu,memory.total,memory.used,memory.free",
                "--format=csv,nounits,noheader",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def parse_nvidia_smi(output):
    """
    Parses CSV output from nvidia-smi and returns a flat dict of GPU stats.
    For each GPU index, keys are suffixed with the index:
      gpu_<index>_utilization_percent,
      gpu_<index>_memory_total_mb,
      gpu_<index>_memory_used_mb,
      gpu_<index>_memory_free_mb
    """
    data = {}
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        gpu_index, util, total, used, free_mem = parts[:5]
        try:
            util = int(util)
        except ValueError:
            pass
        try:
            total = int(total)
        except ValueError:
            pass
        try:
            used = int(used)
        except ValueError:
            pass
        try:
            free_mem = int(free_mem)
        except ValueError:
            pass
        data[f"gpu_{gpu_index}_utilization_percent"] = util
        data[f"gpu_{gpu_index}_memory_total_mb"] = total
        data[f"gpu_{gpu_index}_memory_used_mb"] = used
        data[f"gpu_{gpu_index}_memory_free_mb"] = free_mem
    return data