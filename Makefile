# Improved Docker Makefile
.PHONY: test latest stable lint clean help

# Platform configuration
export PLATFORM_LATEST ?= linux/amd64
export PLATFORM_STABLE ?= linux/arm64/v8

# Registry and naming configuration
export GITHUB_GHCR ?= ghcr.io
export GITHUB_USERNAME ?= gunny26
export REPOSITORY_NAME ?= $(shell basename $(PWD))
export DESCRIPTION ?= $(shell cat ./TITLE 2>/dev/null || echo "Docker container for $(REPOSITORY_NAME)")
export DATESTRING ?= $(shell date -I)
export TAG ?= $(shell git describe --always 2>/dev/null || echo "unknown")
export REGISTRY ?= $(GITHUB_GHCR)/$(GITHUB_USERNAME)/$(REPOSITORY_NAME)
export IMAGE_NAME ?= $(REGISTRY):$(DATESTRING)-$(TAG)
export IMAGE_NAME_LATEST ?= $(REGISTRY):latest
export IMAGE_NAME_STABLE ?= $(REGISTRY):stable

# Build arguments for better caching and security
BUILDX_ARGS := --label "org.opencontainers.image.source=https://github.com/$(GITHUB_USERNAME)/$(REPOSITORY_NAME)" \
	--label "org.opencontainers.image.description=$(DESCRIPTION)" \
	--label "org.opencontainers.image.licenses=MIT" \
	--label "org.opencontainers.image.created=$(shell date -u +%Y-%m-%dT%H:%M:%SZ)" \
	--label "org.opencontainers.image.revision=$(TAG)" \
	--label "org.opencontainers.image.version=$(DATESTRING)-$(TAG)"

# Default target
help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

test: ## Test the application using docker compose
	@echo "Testing application with docker compose..."
	docker compose up -d
	@sleep 5  # Give services time to start
	docker compose ps
	docker compose down

lint: ## Run linting on Python files
	@echo "Running linting..."
	@if [ -f "build/main.py" ]; then \
		ruff check build/main.py; \
		ruff format build/main.py; \
	else \
		echo "No build/main.py found, skipping lint"; \
	fi

latest: ## Build and push latest image (development)
	@echo "Building latest image..."
	@# Ensure we're on the latest branch
	git checkout latest || git checkout -b latest
	@# Only commit if there are changes
	@if ! git diff-index --quiet HEAD --; then \
		git add .; \
		git commit -m "automatic latest image build commit"; \
	fi
	@# Only push if there are commits to push
	@if [ "$$(git rev-list --count origin/latest..HEAD 2>/dev/null || echo 1)" -gt 0 ]; then \
		git push origin latest; \
	fi
	@echo "Building image tags: $(IMAGE_NAME) and $(IMAGE_NAME_LATEST)"
	docker buildx build \
		$(BUILDX_ARGS) \
		--platform $(PLATFORM_LATEST) \
		--tag $(IMAGE_NAME) \
		--tag $(IMAGE_NAME_LATEST) \
		--push \
		.

stable: ## Build and push stable multi-platform image (production)
	@echo "Building stable image..."
	@# Ensure clean working directory before merge
	@if ! git diff-index --quiet HEAD --; then \
		echo "Working directory not clean. Please commit or stash changes."; \
		exit 1; \
	fi
	git checkout main
	git pull origin main
	@# Check if merge is needed
	@if [ "$$(git rev-list --count main..latest)" -gt 0 ]; then \
		git merge latest --no-edit; \
		git push origin main; \
	else \
		echo "No new commits to merge from latest"; \
	fi
	@echo "Building image tags: $(IMAGE_NAME) and $(IMAGE_NAME_STABLE)"
	docker buildx build \
		$(BUILDX_ARGS) \
		--platform $(PLATFORM_LATEST),$(PLATFORM_STABLE) \
		--tag $(IMAGE_NAME) \
		--tag $(IMAGE_NAME_STABLE) \
		--push \
		.
	@# Return to latest branch
	git checkout latest

clean: ## Clean up Docker build cache and unused images
	@echo "Cleaning up Docker resources..."
	docker buildx prune -f
	docker image prune -f

clean-all: clean ## Clean up all Docker resources (containers, images, volumes)
	@echo "Cleaning up all Docker resources..."
	docker system prune -af

info: ## Show current configuration
	@echo "Current configuration:"
	@echo "  Repository: $(REPOSITORY_NAME)"
	@echo "  Registry: $(REGISTRY)"
	@echo "  Tag: $(TAG)"
	@echo "  Description: $(DESCRIPTION)"
	@echo "  Latest Platform: $(PLATFORM_LATEST)"
	@echo "  Stable Platform: $(PLATFORM_STABLE)"
	@echo "  Image Name: $(IMAGE_NAME)"
	@echo "  Latest Image: $(IMAGE_NAME_LATEST)"
	@echo "  Stable Image: $(IMAGE_NAME_STABLE)"
