BINARY = cxf
VERSION = $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS = -s -w

.PHONY: all build install clean test

all: build

build:
	go build -ldflags="$(LDFLAGS) -X main.version=$(VERSION)" -o $(BINARY) .

install: build
	mkdir -p $(HOME)/.local/bin
	cp $(BINARY) $(HOME)/.local/bin/$(BINARY)
	@echo "✓ installed to $(HOME)/.local/bin/$(BINARY)"

clean:
	rm -f $(BINARY)
	@echo "✓ cleaned"

test:
	go test ./... -v

# Cross-compilation
build-linux:
	GOOS=linux GOARCH=amd64 go build -ldflags="$(LDFLAGS)" -o $(BINARY)-linux-amd64 .

build-macos:
	GOOS=darwin GOARCH=arm64 go build -ldflags="$(LDFLAGS)" -o $(BINARY)-darwin-arm64 .
