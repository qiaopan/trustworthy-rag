#!/usr/bin/env bash
# Read-only GPU memory sampler. It neither starts models nor touches Slurm.
set -euo pipefail

interval_seconds="${1:-60}"
output_file="${2:-outputs/monitoring/h200_gpu_memory.csv}"
gpu_indices="${GPU_INDICES:-}"

mkdir -p "$(dirname "$output_file")"
if [[ ! -s "$output_file" ]]; then
  echo "timestamp,gpu_index,gpu_name,memory_used_mib,memory_free_mib,utilization_percent" > "$output_file"
fi

while true; do
  nvidia-smi --query-gpu=timestamp,index,name,memory.used,memory.free,utilization.gpu \
    --format=csv,noheader,nounits | \
    awk -F ', ' -v wanted="$gpu_indices" '
      BEGIN { split(wanted, ids, ","); for (i in ids) selected[ids[i]] = 1 }
      wanted == "" || selected[$2] { print }
    ' >> "$output_file"
  sleep "$interval_seconds"
done
