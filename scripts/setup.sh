#!/bin/bash
set -e

echo "Setting up LlamaTrade development environment..."

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed."; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose is required but not installed."; exit 1; }

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << 'EOF'
# Alpaca API (Paper Trading)
ALPACA_API_KEY=
ALPACA_API_SECRET=

# JWT Secret (change in production!)
JWT_SECRET=dev-secret-change-in-production

# Encryption Key (change in production!)
ENCRYPTION_KEY=dev-encryption-key-change-me

# Database (port 47532 to avoid conflicts)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:47532/llamatrade

# Redis (port 47379 to avoid conflicts)
REDIS_URL=redis://localhost:47379

# Stripe (optional)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# SMTP (optional)
SMTP_HOST=
SMTP_USER=
SMTP_PASSWORD=
EOF
    echo "Created .env file. Please update with your API keys."
fi

# Install Python dev tools
echo "Installing Python dev tools (ruff, mypy, pre-commit)..."
pip install ruff mypy pre-commit

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -e libs/common[dev]

for service in auth strategy backtest market-data trading portfolio notification billing; do
    pip install -e services/$service[dev] 2>/dev/null || pip install -e services/$service
done

# Install frontend dependencies
echo "Installing frontend dependencies..."
cd apps/web && npm install && cd ../..

# Install pre-commit hooks
echo "Installing pre-commit hooks..."
pre-commit install

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Update .env with your Alpaca API keys"
echo "  2. Run 'make dev' to start all services"
echo "  3. Open http://localhost:47300 in your browser"
echo ""
echo "Quality tools installed:"
echo "  - Pre-commit hooks (runs on every commit)"
echo "  - Run 'make lint' to check all code"
echo "  - Run 'make lint-fix' to auto-fix issues"
