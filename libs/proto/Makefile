.PHONY: generate lint format clean

# Generate Python code from proto files
generate:
	@echo "Generating Python gRPC code..."
	buf generate
	@echo "Done!"

# Lint proto files
lint:
	@echo "Linting proto files..."
	buf lint
	@echo "Lint passed!"

# Format proto files
format:
	@echo "Formatting proto files..."
	buf format -w
	@echo "Done!"

# Check for breaking changes
breaking:
	@echo "Checking for breaking changes..."
	buf breaking --against 'https://github.com/nbaghiro/llamatrade.git#branch=main,subdir=libs/proto'

# Clean generated files
clean:
	@echo "Cleaning generated files..."
	rm -rf ../grpc/llamatrade_grpc/generated/*
	@echo "Done!"

# Install buf CLI
install-buf:
	@echo "Installing buf CLI..."
	@if command -v brew > /dev/null; then \
		brew install bufbuild/buf/buf; \
	else \
		echo "Please install buf manually: https://docs.buf.build/installation"; \
	fi

# All checks
check: lint
	@echo "All checks passed!"
