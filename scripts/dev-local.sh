#!/usr/bin/env bash
# Run a single service locally with hot-reload (gRPC-only)
# Usage: ./scripts/dev-local.sh auth
# Usage: ./scripts/dev-local.sh setup
#
# Services expose gRPC ports only. FastAPI runs internally for health checks
# and to trigger the lifespan which starts the gRPC server.

set -e

SERVICE=$1
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Get the gRPC port for a service
get_grpc_port() {
    case "$1" in
        auth) echo 8810 ;;
        strategy) echo 8820 ;;
        backtest) echo 8830 ;;
        market-data) echo 8840 ;;
        trading) echo 8850 ;;
        portfolio) echo 8860 ;;
        notification) echo 8870 ;;
        billing) echo 8880 ;;
        *) echo 8000 ;;
    esac
}

# Get internal HTTP port for FastAPI (health checks only, not exposed)
get_http_port() {
    case "$1" in
        auth) echo 18810 ;;
        strategy) echo 18820 ;;
        backtest) echo 18830 ;;
        market-data) echo 18840 ;;
        trading) echo 18850 ;;
        portfolio) echo 18860 ;;
        notification) echo 18870 ;;
        billing) echo 18880 ;;
        *) echo 18000 ;;
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
    pip install -q -e "$PROJECT_ROOT/libs/grpc"
    # Install the service (which may have additional deps)
    pip install -q -e "$svc_dir"
    deactivate

    echo "  Done: $svc"
}

run_service() {
    local svc=$1
    local svc_dir="$PROJECT_ROOT/services/$svc"
    local venv_dir="$svc_dir/.venv"
    local grpc_port=$(get_grpc_port "$svc")
    local http_port=$(get_http_port "$svc")

    echo "Starting $svc..."
    echo "  gRPC port: $grpc_port"
    echo "  Health check port: $http_port (internal)"

    source "$venv_dir/bin/activate"
    cd "$svc_dir"

    # Set GRPC_PORT env var and run uvicorn
    # FastAPI starts gRPC server during lifespan on GRPC_PORT
    export GRPC_PORT="$grpc_port"

    # Billing also needs HTTP_PORT for Stripe webhooks
    if [ "$svc" = "billing" ]; then
        export HTTP_PORT=8881
        echo "  Stripe webhook port: 8881"
    fi

    uvicorn src.main:app --host 0.0.0.0 --port "$http_port" --reload --reload-dir src
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
    echo ""
    echo "Service gRPC ports:"
    echo "  auth:         8810"
    echo "  strategy:     8820"
    echo "  backtest:     8830"
    echo "  market-data:  8840"
    echo "  trading:      8850"
    echo "  portfolio:    8860"
    echo "  notification: 8870"
    echo "  billing:      8880 (+ HTTP 8881 for Stripe)"
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
        echo ""
        echo "Services run gRPC servers on these ports:"
        echo "  auth:         8810"
        echo "  strategy:     8820"
        echo "  backtest:     8830"
        echo "  market-data:  8840"
        echo "  trading:      8850"
        echo "  portfolio:    8860"
        echo "  notification: 8870"
        echo "  billing:      8880 (+ HTTP 8881 for Stripe webhooks)"
        exit 1
        ;;
esac
