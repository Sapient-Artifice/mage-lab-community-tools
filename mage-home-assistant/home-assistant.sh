#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${HA_CONTAINER_NAME:-home-assistant}"
IMAGE="${HA_IMAGE:-ghcr.io/home-assistant/home-assistant:stable}"
TZ_VALUE="${TZ:-UTC}"
CONFIG_DIR="${HA_CONFIG_DIR:-$HOME/homeassistant}"
RESTART_POLICY="${HA_RESTART_POLICY:-unless-stopped}"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi

docker_cmd() {
  "${DOCKER[@]}" "$@"
}

ensure_config_dir() {
  mkdir -p "$CONFIG_DIR"
}

run_container() {
  docker_cmd run -d \
    --name "$CONTAINER_NAME" \
    --restart="$RESTART_POLICY" \
    -e "TZ=$TZ_VALUE" \
    -v "$CONFIG_DIR:/config" \
    --network=host \
    "$IMAGE"
}

start_home_assistant() {
  ensure_config_dir

  if docker_cmd ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Home Assistant is already running (${CONTAINER_NAME})."
    return 0
  fi

  if docker_cmd ps -a --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker_cmd start "$CONTAINER_NAME" >/dev/null
    echo "Started existing container: ${CONTAINER_NAME}"
  else
    run_container >/dev/null
    echo "Created and started container: ${CONTAINER_NAME}"
  fi
}

stop_home_assistant() {
  if docker_cmd ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker_cmd stop "$CONTAINER_NAME" >/dev/null
    echo "Stopped ${CONTAINER_NAME}"
  else
    echo "Container is not running: ${CONTAINER_NAME}"
  fi
}

status_home_assistant() {
  docker_cmd ps -a \
    --filter "name=^/${CONTAINER_NAME}$" \
    --format 'name={{.Names}} status={{.Status}} image={{.Image}}'
}

logs_home_assistant() {
  docker_cmd logs -f "$CONTAINER_NAME"
}

update_home_assistant() {
  ensure_config_dir
  docker_cmd pull "$IMAGE"

  if docker_cmd ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker_cmd stop "$CONTAINER_NAME" >/dev/null
  fi

  if docker_cmd ps -a --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker_cmd rm "$CONTAINER_NAME" >/dev/null
  fi

  run_container >/dev/null
  echo "Updated and started ${CONTAINER_NAME} with image ${IMAGE}"
}

usage() {
  cat <<'EOF'
Usage:
  ./home-assistant.sh start    # Create container if missing, otherwise start it
  ./home-assistant.sh stop     # Stop container
  ./home-assistant.sh restart  # Stop then start container
  ./home-assistant.sh status   # Show container status
  ./home-assistant.sh logs     # Follow container logs
  ./home-assistant.sh update   # Pull latest image and recreate container
EOF
}

ACTION="${1:-start}"
case "$ACTION" in
  start) start_home_assistant ;;
  stop) stop_home_assistant ;;
  restart) stop_home_assistant; start_home_assistant ;;
  status) status_home_assistant ;;
  logs) logs_home_assistant ;;
  update) update_home_assistant ;;
  *) usage; exit 1 ;;
esac
