#!/usr/bin/env bash
# Run a single service locally with hot-reload
# Usage: ./scripts/dev-local.sh auth
# Usage: ./scripts/dev-local.sh setup

set -e

SERVICE=$1
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

get_port() {
    case "$1" in
        auth) echo 47810 ;;
        strategy) echo 47820 ;;
        backtest) echo 47830 ;;
        market-data) echo 47840 ;;
        trading) echo 47850 ;;
        portfolio) echo 47860 ;;
        notification) echo 47870 ;;
        billing) echo 47880 ;;
        *) echo 8000 ;;
    esac
}

setup_venv() {
    local svc=$1
    local svc_dir="$PROJECT_ROOT/services/$svc"
    local venv_dir="$svc_dir/.venv"

    echo "Setting up $svc..."

    if [ ! -d "$venv_dir" ]; then
        echo "  Creating virtual environment..."
        python3 -m venv "$venv_dir"
    fi

    echo "  Installing dependencies..."
    source "$venv_dir/bin/activate"
    pip install -q --upgrade pip
    # Install shared libraries first (with their dependencies)
    pip install -q -e "$PROJECT_ROOT/libs/common"
    pip install -q -e "$PROJECT_ROOT/libs/db"
    # Install the service (which may have additional deps)
    pip install -q -e "$svc_dir"
    deactivate

    echo "  Done: $svc"
}

run_service() {
    local svc=$1
    local svc_dir="$PROJECT_ROOT/services/$svc"
    local venv_dir="$svc_dir/.venv"
    local port=$(get_port "$svc")

    echo "Starting $svc on port $port..."

    source "$venv_dir/bin/activate"
    cd "$svc_dir"

    uvicorn src.main:app --host 0.0.0.0 --port "$port" --reload --reload-dir src
}

setup_all() {
    echo "Setting up all services..."
    echo ""

    for svc in auth strategy backtest market-data trading portfolio notification billing; do
        setup_venv "$svc"
    done

    echo ""
    echo "All virtual environments created!"
    echo ""
    echo "Next steps:"
    echo "  1. Start infrastructure: make dev-infra"
    echo "  2. Run all services:     make dev-local"
    echo ""
    echo "Or run individual services:"
    echo "  ./scripts/dev-local.sh auth"
    echo "  ./scripts/dev-local.sh strategy"
    echo "  etc."
}

case "$SERVICE" in
    setup)
        setup_all
        ;;
    auth|strategy|backtest|market-data|trading|portfolio|notification|billing)
        if [ ! -d "$PROJECT_ROOT/services/$SERVICE/.venv" ]; then
            setup_venv "$SERVICE"
        fi
        run_service "$SERVICE"
        ;;
    *)
        echo "Usage: $0 {setup|auth|strategy|backtest|market-data|trading|portfolio|notification|billing}"
        echo ""
        echo "Commands:"
        echo "  setup    - Create virtual environments for all services"
        echo "  <name>   - Run a specific service with hot-reload"
        exit 1
        ;;
esac
