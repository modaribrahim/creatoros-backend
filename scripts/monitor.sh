#!/usr/bin/env bash
#
# CreatorOS VPS monitor
# ---------------------
# Samples RAM / CPU / disk / container health and appends a timestamped row to
# the trend CSV. Optionally writes a human-readable snapshot to stdout/log.
#
# Intended to run on a schedule (see cron example below):
#   * * * * * /root/creatoros-backend/scripts/monitor.sh >> /root/creatoros-backend/logs/monitor.log 2>&1
#
# Copy of the bytes in the same container
# ----------------------------
set -euo pipefail

BASE_DIR="/root/creatoros-backend"
LOG_DIR="${BASE_DIR}/logs"
TREND_FILE="${LOG_DIR}/trends.csv"
mkdir -p "${LOG_DIR}"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --- memory (MB) ---
mem_total="$(awk '/MemTotal/{print $2}' /proc/meminfo)"
mem_avail="$(awk '/MemAvailable/{print $2}' /proc/meminfo)"
mem_used=$((mem_total - mem_avail))
swap_used_kb="$(awk '/^SwapTotal:/{t=$2} /^SwapFree:/{f=$2} END{print t-f}' /proc/meminfo)"
mem_used_mb=$((mem_used / 1024))
mem_avail_mb=$((mem_avail / 1024))
swap_used_mb=$((swap_used_kb / 1024))

# --- CPU % over 1s (two samples of /proc/stat) ---
read_cpu() {
  awk '/^cpu /{print $5, 0; exit}'
}
cpu_sample() {
  read total j1 j2 j3 j4 idle j5 j6 j7 j8 < <(awk '/^cpu /{for(i=2;i<=NF;i++){s+=$i}; print s, $5}' /proc/stat)
  echo "$total $idle"
}
t1=($(cpu_sample))
sleep 1
t2=($(cpu_sample))
total_d=$((t2[0] - t1[0]))
idle_d=$((t2[1] - t1[1]))
if [ "$total_d" -le 0 ]; then
  cpu_pct=0
else
  cpu_pct=$((100 * (total_d - idle_d) / total_d))
fi

# --- load average ---
read load1 load5 load15 x < <(cut -d' ' -f1-3 /proc/loadavg)

# --- disk ---
disk_use_pct="$(df -h / | awk 'NR==2{gsub(/%/,""); print $5}')"

# --- containers ---
containers="$(docker ps --format '{{.Names}}={{.Status}}' 2>/dev/null | tr '\n' ';')"

# --- container RSS (MB) via docker stats once ---
if docker info >/dev/null 2>&1; then
  api_mem="$(docker stats --no-stream --format '{{.Name}}={{.MemUsage}}' 2>/dev/null | grep 'api' || true)"
else
  api_mem=""
fi

# append trend row (CSV)
if [ ! -f "${TREND_FILE}" ]; then
  printf 'ts,mem_used_mb,mem_avail_mb,swap_used_mb,cpu_pct,disk_use_pct,load1,load5,load15\n' > "${TREND_FILE}"
fi
printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
  "${ts}" "${mem_used_mb}" "${mem_avail_mb}" "${swap_used_mb}" "${cpu_pct}" "${disk_use_pct}" "${load1}" "${load5}" "${load15}" >> "${TREND_FILE}"

# human-readable snapshot to stdout (goes to monitor.log via cron redirect)
printf '%s | mem used=%sMB avail=%sMB swap=%sMB cpu=%s%% disk=%s%% load=%s %s %s\n' \
  "${ts}" "${mem_used_mb}" "${mem_avail_mb}" "${swap_used_mb}" "${cpu_pct}" "${disk_use_pct}" "${load1}" "${load5}" "${load15}"
printf '%s | containers: %s\n' "${ts}" "${containers}"
if [ -n "${api_mem}" ]; then
  printf '%s | %s\n' "${ts}" "${api_mem}"
fi

# truncate the log if it grows huge (keep last ~5000 lines)
[ -f "${LOG_DIR}/monitor.log" ] && tail -n 5000 "${LOG_DIR}/monitor.log" > "${LOG_DIR}/monitor.log.tmp" && mv "${LOG_DIR}/monitor.log.tmp" "${LOG_DIR}/monitor.log"
