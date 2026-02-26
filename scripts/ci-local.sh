#!/usr/bin/env bash
#
# Local CI runner - mimics GitHub Actions CI workflow
# Usage: ./scripts/ci-local.sh [options]
#
# Options:
#   --lint-only      Run only linting (ruff + mypy)
#   --test-only      Run only tests
#   --backend-only   Skip frontend checks
#   --frontend-only  Skip backend checks
#   --integration    Run integration tests (requires Docker)
#   --fix            Auto-fix linting issues
#   -h, --help       Show this help message

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
RUN_LINT=true
RUN_TESTS=true
RUN_BACKEND=true
RUN_FRONTEND=true
RUN_INTEGRATION=false
FIX_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --lint-only)
            RUN_TESTS=false
            shift
            ;;
        --test-only)
            RUN_LINT=false
            shift
            ;;
        --backend-only)
            RUN_FRONTEND=false
            shift
            ;;
        --frontend-only)
            RUN_BACKEND=false
            shift
            ;;
        --integration)
            RUN_INTEGRATION=true
            shift
            ;;
        --fix)
            FIX_MODE=true
            shift
            ;;
        -h|--help)
            head -25 "$0" | tail -20
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Track failures
FAILED=()

# Helper functions
print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo -e "\n${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

run_step() {
    local name="$1"
    shift
    print_step "$name"
    if "$@"; then
        print_success "$name passed"
        return 0
    else
        print_error "$name failed"
        FAILED+=("$name")
        return 1
    fi
}

# Ensure we're in project root
cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)

print_header "Local CI Runner"
echo "Project root: $PROJECT_ROOT"

# ═══════════════════════════════════════════════════════════════
# BACKEND LINTING
# ═══════════════════════════════════════════════════════════════
if [[ "$RUN_LINT" == "true" && "$RUN_BACKEND" == "true" ]]; then
    print_header "Python Linting"

    if [[ "$FIX_MODE" == "true" ]]; then
        run_step "Ruff lint (with fixes)" ruff check --fix --config pyproject.toml services/ libs/ || true
        run_step "Ruff format" ruff format --config pyproject.toml services/ libs/ || true
    else
        run_step "Ruff lint" ruff check --config pyproject.toml services/ libs/
        run_step "Ruff format check" ruff format --config pyproject.toml --check services/ libs/
    fi

    print_header "Python Type Checking (mypy)"

    # Run mypy per-service to avoid "Duplicate module named src" error
    run_step "mypy libs/common" mypy libs/common --ignore-missing-imports || true
    run_step "mypy libs/db" mypy libs/db --ignore-missing-imports || true
    run_step "mypy services/auth" mypy services/auth --ignore-missing-imports || true
    run_step "mypy services/strategy" mypy services/strategy --ignore-missing-imports || true
    run_step "mypy services/backtest" mypy services/backtest --ignore-missing-imports || true
    run_step "mypy services/market-data" mypy services/market-data --ignore-missing-imports || true
    run_step "mypy services/trading" mypy services/trading --ignore-missing-imports || true
    run_step "mypy services/portfolio" mypy services/portfolio --ignore-missing-imports || true
    run_step "mypy services/notification" mypy services/notification --ignore-missing-imports || true
    run_step "mypy services/billing" mypy services/billing --ignore-missing-imports || true
fi

# ═══════════════════════════════════════════════════════════════
# FRONTEND LINTING
# ═══════════════════════════════════════════════════════════════
if [[ "$RUN_LINT" == "true" && "$RUN_FRONTEND" == "true" ]]; then
    print_header "Frontend Linting"

    if [[ -d "apps/web" ]]; then
        cd apps/web
        if [[ -f "package.json" ]]; then
            run_step "ESLint" npm run lint || true
            run_step "TypeScript check" npx tsc --noEmit || true
        else
            echo "No package.json found in apps/web, skipping frontend lint"
        fi
        cd "$PROJECT_ROOT"
    else
        echo "No apps/web directory found, skipping frontend lint"
    fi
fi

# ═══════════════════════════════════════════════════════════════
# BACKEND TESTS
# ═══════════════════════════════════════════════════════════════
if [[ "$RUN_TESTS" == "true" && "$RUN_BACKEND" == "true" ]]; then
    print_header "Backend Tests"

    # Create/activate virtual environment if needed
    if [[ ! -d ".venv" ]]; then
        print_step "Creating virtual environment"
        python3 -m venv .venv
    fi

    # shellcheck disable=SC1091
    source .venv/bin/activate

    # Install shared libs
    print_step "Installing shared libraries"
    pip install -e "libs/common[dev]" -q
    pip install -e "libs/db[dev]" -q

    # Test auth service
    print_step "Testing auth service"
    pip install -e "services/auth[dev]" -q
    if (cd services/auth && pytest tests -v); then
        print_success "Auth tests passed"
    else
        print_error "Auth tests failed"
        FAILED+=("Auth tests")
    fi
    pip uninstall -y llamatrade-auth -q 2>/dev/null || true

    # Test strategy service
    print_step "Testing strategy service"
    pip install -e "services/strategy[dev]" -q
    if (cd services/strategy && pytest tests -v); then
        print_success "Strategy tests passed"
    else
        print_error "Strategy tests failed"
        FAILED+=("Strategy tests")
    fi
    pip uninstall -y llamatrade-strategy -q 2>/dev/null || true
fi

# ═══════════════════════════════════════════════════════════════
# FRONTEND TESTS
# ═══════════════════════════════════════════════════════════════
if [[ "$RUN_TESTS" == "true" && "$RUN_FRONTEND" == "true" ]]; then
    print_header "Frontend Tests"

    if [[ -d "apps/web" ]]; then
        cd apps/web
        if [[ -f "package.json" ]]; then
            run_step "Frontend tests" npm test -- --run --passWithNoTests || true
        fi
        cd "$PROJECT_ROOT"
    fi
fi

# ═══════════════════════════════════════════════════════════════
# INTEGRATION TESTS (Optional - run with --integration flag)
# ═══════════════════════════════════════════════════════════════
if [[ "$RUN_TESTS" == "true" && "$RUN_INTEGRATION" == "true" ]]; then
    print_header "Integration Tests"

    # Ensure testcontainers dependencies are installed
    pip install -q "testcontainers[postgres,redis]>=4.0.0" pytest-xdist pytest-timeout

    # Run integration tests (services against real DB)
    print_step "Service integration tests"
    if pytest tests/integration/services -v -m integration --timeout=60 2>/dev/null; then
        print_success "Service integration tests passed"
    else
        print_error "Service integration tests failed"
        FAILED+=("Service integration tests")
    fi

    # Run security tests (tenant isolation - critical)
    print_step "Security tests (tenant isolation)"
    if pytest tests/integration/security -v -m security --timeout=60 2>/dev/null; then
        print_success "Security tests passed"
    else
        print_error "Security tests failed"
        FAILED+=("Security tests")
    fi
fi

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print_header "Summary"

if [[ ${#FAILED[@]} -eq 0 ]]; then
    print_success "All checks passed!"
    exit 0
else
    print_error "The following checks failed:"
    for item in "${FAILED[@]}"; do
        echo "  - $item"
    done
    exit 1
fi
