#!/usr/bin/env bash
set -euo pipefail

# PDM Installer Script
# Downloads and installs PDM from GitHub released binaries

REPO="pdm-project/pdm"
INSTALL_DIR="${PDM_HOME:-}"
VERSION="${PDM_VERSION:-latest}"
SKIP_ADD_TO_PATH="${PDM_SKIP_ADD_TO_PATH:-false}"
SKIP_CHECKSUM="${PDM_SKIP_CHECKSUM:-false}"

# Color output
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    CYAN=''
    BOLD=''
    NC=''
fi

log() {
    echo -e "${GREEN}${BOLD}PDM${NC}: ${CYAN}$1${NC}"
}

warn() {
    echo -e "${YELLOW}Warning:${NC} $1" >&2
}

error() {
    echo -e "${RED}Error:${NC} $1" >&2
    exit 1
}

# Detect OS and architecture
detect_platform() {
    local os arch target

    # Detect OS
    case "$(uname -s)" in
        Linux)
            os="unknown-linux-gnu"
            ;;
        Darwin)
            os="apple-darwin"
            ;;
        MINGW* | MSYS* | CYGWIN* | Windows_NT)
            os="pc-windows-msvc"
            ;;
        *)
            error "Unsupported OS: $(uname -s)"
            ;;
    esac

    # Detect architecture
    case "$(uname -m)" in
        x86_64 | amd64)
            arch="x86_64"
            ;;
        aarch64 | arm64)
            arch="aarch64"
            ;;
        armv7l)
            arch="armv7"
            ;;
        i686 | i386)
            arch="i686"
            ;;
        *)
            error "Unsupported architecture: $(uname -m)"
            ;;
    esac

    # Construct target triple
    target="${arch}-${os}"

    # Handle special cases
    if [ "$os" = "apple-darwin" ] && [ "$arch" = "aarch64" ]; then
        # aarch64-apple-darwin is the correct name for ARM64 Macs
        target="aarch64-apple-darwin"
    elif [ "$os" = "pc-windows-msvc" ] && [ "$arch" = "i686" ]; then
        # Windows 32-bit (limited support)
        target="i686-pc-windows-msvc"
    fi

    echo "$target"
}

# Get the download URL for a specific version
get_download_url() {
    local version="$1"
    local platform="$2"
    local release_url

    if [ "$version" = "latest" ]; then
        release_url="https://api.github.com/repos/${REPO}/releases/latest"
    else
        release_url="https://api.github.com/repos/${REPO}/releases/tags/${version}"
    fi

    # Use curl or wget
    local json
    if command -v curl >/dev/null 2>&1; then
        json=$(curl -s "$release_url")
    elif command -v wget >/dev/null 2>&1; then
        json=$(wget -qO- "$release_url")
    else
        error "Neither curl nor wget found. Please install one of them."
    fi

    # Extract download URL for the platform
    # PDM binaries are named like: pdm-2.26.1-x86_64-unknown-linux-gnu.tar.gz
    local pattern="pdm-[^-]*-${platform}\\.tar\\.gz"
    local url
    url=$(echo "$json" | grep -o "https://github.com[^\"]*${pattern}" | head -1)

    if [ -z "$url" ]; then
        error "No binary found for platform ${platform}"
    fi

    echo "$url"
}

# Determine install directory
determine_install_dir() {
    if [ -n "$INSTALL_DIR" ]; then
        echo "$INSTALL_DIR"
    else
        # Default to ~/.local/bin on Unix-like systems
        echo "$HOME/.local/bin"
    fi
}

# Download and extract PDM
download_and_install() {
    local url="$1"
    local install_dir="$2"
    local temp_dir temp_file checksum_file

    temp_dir=$(mktemp -d)
    temp_file="${temp_dir}/pdm.tar.gz"
    checksum_file="${temp_dir}/pdm.tar.gz.sha256"

    log "Downloading PDM from $url"

    # First try to download checksum file
    local checksum_url="${url}.sha256"
    local checksum_downloaded=false

    if command -v curl >/dev/null 2>&1; then
        if curl -sL -o "$checksum_file" "$checksum_url" 2>/dev/null; then
            if [ -s "$checksum_file" ]; then
                checksum_downloaded=true
            fi
        fi
    elif command -v wget >/dev/null 2>&1; then
        if wget -O "$checksum_file" "$checksum_url" 2>/dev/null; then
            if [ -s "$checksum_file" ]; then
                checksum_downloaded=true
            fi
        fi
    fi

    # Download the binary
    if command -v curl >/dev/null 2>&1; then
        curl -sL -o "$temp_file" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$temp_file" "$url"
    fi

    # Verify checksum if we downloaded it
    if [ "$checksum_downloaded" = true ]; then
        verify_checksum_from_file "$checksum_file" "$temp_file"
    else
        log "No checksum file found. Skipping verification."
    fi

    log "Extracting to $install_dir"

    # Create install directory
    mkdir -p "$install_dir"

    # Extract tar.gz file
    if command -v tar >/dev/null 2>&1; then
        tar -xzf "$temp_file" -C "$temp_dir"
    else
        error "tar not found. Please install tar to extract the archive."
    fi

    # Find and copy the binary
    local binary
    if [ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ]; then
        binary=$(find "$temp_dir" -name "pdm" -type f | head -1)
        if [ -z "$binary" ]; then
            error "PDM binary not found in archive"
        fi
        cp "$binary" "$install_dir/pdm"
        chmod +x "$install_dir/pdm"
    else
        # Windows
        binary=$(find "$temp_dir" -name "pdm.exe" -type f | head -1)
        if [ -z "$binary" ]; then
            error "PDM binary not found in archive"
        fi
        cp "$binary" "$install_dir/pdm.exe"
    fi

    # Cleanup
    rm -rf "$temp_dir"
}

# Verify checksum from a checksum file
verify_checksum_from_file() {
    local checksum_file="$1"
    local file_path="$2"
    local expected_checksum actual_checksum

    # Skip verification if explicitly disabled
    if [ "$SKIP_CHECKSUM" = "true" ]; then
        log "Checksum verification skipped (--skip-checksum)."
        return 0
    fi

    # Read expected checksum from file
    expected_checksum=$(awk '{print $1}' "$checksum_file")

    # If no checksum found, skip verification
    if [ -z "$expected_checksum" ]; then
        log "No checksum found in file. Skipping verification."
        return 0
    fi

    # Check if sha256sum is available
    if ! command -v sha256sum >/dev/null 2>&1; then
        log "sha256sum not found. Skipping verification."
        return 0
    fi

    log "Verifying checksum..."

    # Calculate actual checksum
    actual_checksum=$(sha256sum "$file_path" | awk '{print $1}')

    if [ "$expected_checksum" = "$actual_checksum" ]; then
        log "Checksum verification passed."
        return 0
    else
        error "Checksum verification failed!"
        echo "Expected: $expected_checksum"
        echo "Actual:   $actual_checksum"
        return 1
    fi
}

# Add to PATH
add_to_path() {
    local bin_dir="$1"

    if [ "$SKIP_ADD_TO_PATH" = "true" ]; then
        return 0
    fi

    case "$(uname -s)" in
        Linux* | Darwin*)
            # Detect shell
            local shell_name="$SHELL"
            local rcfile=""

            if [[ "$shell_name" == *bash* ]]; then
                rcfile="$HOME/.bashrc"
            elif [[ "$shell_name" == *zsh* ]]; then
                rcfile="$HOME/.zshrc"
            elif [[ "$shell_name" == *fish* ]]; then
                rcfile="$HOME/.config/fish/config.fish"
            else
                warn "Cannot detect shell. Please manually add $bin_dir to your PATH."
                return 0
            fi

            # Check if already in PATH
            if echo ":$PATH:" | grep -q ":${bin_dir}:"; then
                return 0
            fi

            # Add to rcfile
            log "Adding $bin_dir to PATH in $rcfile"
            if [[ "$shell_name" == *fish* ]]; then
                echo "set -gx PATH $bin_dir \$PATH" >> "$rcfile"
            else
                echo "export PATH=\"$bin_dir:\$PATH\"" >> "$rcfile"
            fi

            echo
            echo -e "${YELLOW}Please restart your terminal or run:${NC}"
            if [[ "$shell_name" == *fish* ]]; then
                echo -e "${CYAN}    source $rcfile${NC}"
            else
                echo -e "${CYAN}    source $rcfile${NC}"
            fi
            ;;
        MINGW* | MSYS* | CYGWIN* | Windows_NT)
            warn "Please manually add $bin_dir to your PATH environment variable."
            ;;
    esac
}

# Verify installation
verify_installation() {
    local bin_path="$1"
    local pdm_cmd

    if [ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ]; then
        pdm_cmd="$bin_path/pdm"
    else
        pdm_cmd="$bin_path/pdm.exe"
    fi

    if [ ! -x "$pdm_cmd" ]; then
        error "PDM binary not found or not executable at $pdm_cmd"
    fi

    log "Verifying installation..."
    "$pdm_cmd" --version
}

# Print help
usage() {
    cat << EOF
PDM Installer - Install PDM from GitHub released binaries

Usage: $0 [OPTIONS]

OPTIONS:
    -v, --version VERSION    Install specific version (default: latest)
    -p, --path PATH          Installation directory (default: ~/.local/bin)
    -h, --help               Show this help message
        --skip-add-to-path   Skip adding to PATH
        --skip-checksum      Skip checksum verification

ENVIRONMENT VARIABLES:
    PDM_VERSION              Version to install (overridden by -v)
    PDM_HOME                 Installation directory (overridden by -p)
    PDM_SKIP_ADD_TO_PATH     Whether to skip adding to PATH (overridden by --skip-add-to-path)
    PDM_SKIP_CHECKSUM        Whether to skip checksum verification (overridden by --skip-checksum)

Examples:
    $0                       # Install latest version
    $0 -v 2.17.0             # Install version 2.17.0
    $0 -p /usr/local/bin     # Install to /usr/local/bin
    $0 --skip-checksum       # Skip checksum verification

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -p|--path)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --skip-add-to-path)
            SKIP_ADD_TO_PATH="true"
            shift
            ;;
        --skip-checksum)
            SKIP_CHECKSUM="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Main installation process
main() {
    log "Detecting platform..."
    local platform
    platform=$(detect_platform)
    echo "  Platform: $platform"

    log "Getting download URL for $VERSION..."
    local download_url
    download_url=$(get_download_url "$VERSION" "$platform")
    echo "  URL: $download_url"

    local install_dir
    install_dir=$(determine_install_dir)
    echo "  Install directory: $install_dir"

    # Install
    download_and_install "$download_url" "$install_dir"
    echo

    # Verify
    verify_installation "$install_dir"
    echo

    # Add to PATH
    add_to_path "$install_dir"

    log "Installation completed successfully!"
}

# Run main function
main "$@"
