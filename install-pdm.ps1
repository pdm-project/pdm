#!/usr/bin/env pwsh
<#
.SYNOPSIS
    PDM Installer Script for Windows
    Downloads and installs PDM from GitHub released binaries

.DESCRIPTION
    This script downloads PDM binaries from GitHub releases, verifies checksums,
    and installs PDM on Windows systems.

.PARAMETER Version
    Specify the version to be installed (default: latest)

.PARAMETER InstallPath
    Specify the installation directory (default: $env:LOCALAPPDATA\Programs\pdm)

.PARAMETER SkipAddToPath
    Do not add binary to the PATH

.PARAMETER SkipChecksum
    Skip checksum verification

.EXAMPLE
    .\install-pdm.ps1
    Install latest version of PDM

.EXAMPLE
    .\install-pdm.ps1 -Version "2.26.1"
    Install specific version of PDM

.EXAMPLE
    .\install-pdm.ps1 -InstallPath "C:\Tools\pdm"
    Install to custom location

.EXAMPLE
    .\install-pdm.ps1 -SkipChecksum
    Skip checksum verification
#>

[CmdletBinding()]
param(
    [string]$Version = $env:PDM_VERSION,
    [string]$InstallPath = $env:PDM_HOME,
    [switch]$SkipAddToPath = [bool]$env:PDM_SKIP_ADD_TO_PATH,
    [switch]$SkipChecksum = [bool]$env:PDM_SKIP_CHECKSUM
)

# Set strict mode
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Configuration
$Repo = $env:PDM_REPO -or "pdm-project/pdm"
$DefaultInstallPath = "$env:LOCALAPPDATA\Programs\pdm"

# Color output
$Colors = @{
    Green = "`e[32m"
    Yellow = "`e[33m"
    Cyan = "`e[36m"
    Red = "`e[31m"
    Bold = "`e[1m"
    Reset = "`e[0m"
}

# Check if ANSI is supported
$SupportsAnsi = $Host.UI.SupportsVirtualTerminal -or $env:TERM -eq "xterm"

function Write-ColorOutput {
    param(
        [string]$Text,
        [string]$Color = "Cyan",
        [switch]$Bold
    )
    
    if ($SupportsAnsi) {
        $output = $Colors[$Color] + $Text + $Colors.Reset
        if ($Bold) {
            $output = $Colors.Bold + $output
        }
        Write-Host $output -NoNewline
    } else {
        Write-Host $Text -NoNewline
    }
}

function Write-PDMLog {
    param([string]$Message)
    Write-ColorOutput -Text "PDM: " -Color Green -Bold
    Write-ColorOutput -Text $Message -Color Cyan
    Write-Host
}

function Write-PDMWarning {
    param([string]$Message)
    Write-ColorOutput "Warning: " -Color Yellow
    Write-Host $Message
}

function Write-PDMError {
    param([string]$Message)
    Write-ColorOutput "Error: " -Color Red
    Write-Host $Message
    exit 1
}

# Detect Windows platform and architecture
function Get-Platform {
    $arch = $env:PROCESSOR_ARCHITECTURE
    
    switch ($arch) {
        "AMD64" { $archName = "x86_64" }
        "ARM64" { $archName = "aarch64" }
        "x86" { $archName = "i686" }
        default { Write-PDMError "Unsupported architecture: $arch" }
    }
    
    # Windows target triple
    return "${archName}-pc-windows-msvc"
}

# Get the download URL from GitHub API
function Get-DownloadUrl {
    param(
        [string]$Version,
        [string]$Platform
    )
    
    $headers = @{}
    if ($env:GITHUB_TOKEN) {
        $headers["Authorization"] = "token $env:GITHUB_TOKEN"
    }
    
    if ($Version -eq "latest" -or -not $Version) {
        $apiUrl = "https://api.github.com/repos/$Repo/releases/latest"
    } else {
        $apiUrl = "https://api.github.com/repos/$Repo/releases/tags/$Version"
    }
    
    try {
        $releaseInfo = Invoke-RestMethod -Uri $apiUrl -Headers $headers
    } catch {
        Write-PDMError "Failed to fetch release info: $_"
    }
    
    # Find the asset matching our platform
    $pattern = "pdm-.*-$Platform\.tar\.gz"
    $asset = $releaseInfo.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
    
    if (-not $asset) {
        Write-PDMError "No binary found for platform $Platform"
    }
    
    return $asset.browser_download_url
}

# Download a file with progress
function Invoke-Download {
    param(
        [string]$Url,
        [string]$OutputPath
    )
    
    Write-PdmLog "Downloading from $Url"
    
    try {
        # Use Invoke-WebRequest with progress
        $progressPreference = 'Continue'
        Invoke-WebRequest -Uri $Url -OutFile $OutputPath -UseBasicParsing
        $progressPreference = 'SilentlyContinue'
    } catch {
        Write-PDMError "Download failed: $_"
    }
}

# Verify checksum using PowerShell's Get-FileHash
function Test-Checksum {
    param(
        [string]$ChecksumFile,
        [string]$FilePath
    )
    
    if ($SkipChecksum) {
        Write-PDMLog "Checksum verification skipped (--skip-checksum)"
        return $true
    }
    
    if (-not (Test-Path $ChecksumFile)) {
        Write-PDMLog "No checksum file found. Skipping verification."
        return $true
    }
    
    Write-PDMLog "Verifying checksum..."
    
    # Read expected checksum
    $expectedChecksum = (Get-Content $ChecksumFile -Raw).Trim().Split()[0]
    
    if (-not $expectedChecksum) {
        Write-PDMLog "No checksum found in file. Skipping verification."
        return $true
    }
    
    # Calculate actual checksum
    $actualChecksum = (Get-FileHash -Path $FilePath -Algorithm SHA256).Hash.ToLower()
    $expectedChecksum = $expectedChecksum.ToLower()
    
    if ($expectedChecksum -eq $actualChecksum) {
        Write-PDMLog "Checksum verification passed."
        return $true
    } else {
        Write-PDMError "Checksum verification failed!`nExpected: $expectedChecksum`nActual:   $actualChecksum"
    }
}

# Extract tar.gz archive
function Expand-TarGz {
    param(
        [string]$ArchivePath,
        [string]$DestinationPath
    )
    
    Write-PDMLog "Extracting to $DestinationPath"
    
    # Check if tar is available (Git for Windows, WSL, etc.)
    $tar = Get-Command tar -ErrorAction SilentlyContinue
    if ($tar) {
        try {
            & $tar -xzf $ArchivePath -C $DestinationPath
            return
        } catch {
            Write-PDMWarning "tar extraction failed, trying alternative method"
        }
    }
    
    # Fallback: Extract in memory using .NET
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        
        # This is a simple approach - for tar.gz we'd need more complex handling
        # Since PDM ships as .tar.gz, we'll use the windows tar if available
        # or suggest installing it
        Write-PDMError "This script requires 'tar' to extract .tar.gz files. Please install Git for Windows or Windows Subsystem for Linux."
    } catch {
        Write-PDMError "Failed to extract archive: $_"
    }
}

# Add directory to PATH in registry
function Add-ToPath {
    param([string]$BinPath)
    
    if ($SkipAddToPath) {
        Write-PDMLog "Skipping PATH modification (--skip-add-to-path)"
        return
    }
    
    Write-PDMLog "Adding $BinPath to user PATH..."
    
    try {
        $regPath = "Registry::HKEY_CURRENT_USER\Environment"
        $currentPath = (Get-ItemProperty -Path $regPath -Name PATH -ErrorAction SilentlyContinue).PATH
        
        # Check if already in PATH
        if ($currentPath -and $currentPath -split ';' -contains $BinPath) {
            Write-PDMLog "Already in PATH"
            return
        }
        
        # Add to PATH
        if ($currentPath) {
            $newPath = $currentPath + ";" + $BinPath
        } else {
            $newPath = $BinPath
        }
        
        Set-ItemProperty -Path $regPath -Name PATH -Value $newPath
        
        Write-Host
        Write-ColorOutput -Color Yellow -Text "Note: "
        Write-ColorOutput -Color Cyan -Text "Please restart your terminal or run:"
        Write-Host "    `$env:PATH = '$BinPath;' + `$env:PATH"
        Write-Host
    } catch {
        Write-PDMWarning "Failed to add to PATH: $_"
        Write-PDMLog "Please manually add '$BinPath' to your PATH"
    }
}

# Verify PDM installation
function Test-PdmInstall {
    param([string]$PdmPath)
    
    Write-PDMLog "Verifying installation..."
    
    if (-not (Test-Path $PdmPath)) {
        Write-PDMError "PDM binary not found at $PdmPath"
    }
    
    try {
        $versionOutput = & $PdmPath --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            return $versionOutput
        } else {
            Write-PDMError "PDM verification failed: $versionOutput"
        }
    } catch {
        Write-PDMError "PDM verification failed: $_"
    }
}

# Main installation function
function Install-Pdm {
    Write-ColorOutput -Color Green -Bold -Text "PDM Installer for Windows"
    Write-Host
    
    # Detect platform
    $platform = Get-Platform
    Write-PDMLog "Detected platform: $platform"
    
    # Get download URL
    $downloadUrl = Get-DownloadUrl -Version $Version -Platform $platform
    Write-PDMLog "Download URL: $downloadUrl"
    
    # Determine install directory
    if (-not $InstallPath) {
        $InstallPath = $DefaultInstallPath
    }
    Write-PDMLog "Install directory: $InstallPath"
    
    # Create temp directory
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    
    try {
        # Download files
        $archivePath = Join-Path $tempDir "pdm.tar.gz"
        $checksumPath = Join-Path $tempDir "pdm.tar.gz.sha256"
        
        # Download checksum first (optional)
        try {
            Invoke-Download -Url "$downloadUrl.sha256" -OutputPath $checksumPath
        } catch {
            Write-PDMLog "No checksum file available, skipping verification"
            $SkipChecksum = $true
        }
        
        # Download binary
        Invoke-Download -Url $downloadUrl -OutputPath $archivePath
        
        # Verify checksum if available
        if ((Test-Path $checksumPath) -and -not $SkipChecksum) {
            if (-not (Test-Checksum -ChecksumFile $checksumPath -FilePath $archivePath)) {
                return
            }
        }
        
        # Extract archive
        Expand-TarGz -ArchivePath $archivePath -DestinationPath $tempDir
        
        # Find and copy binary
        $binary = Get-ChildItem -Path $tempDir -Filter "pdm.exe" -Recurse | Select-Object -First 1
        if (-not $binary) {
            Write-PDMError "PDM binary not found in archive"
        }
        
        # Create install directory
        $binPath = Join-Path $InstallPath "bin"
        $null = New-Item -ItemType Directory -Path $binPath -Force
        
        # Copy binary
        $pdmPath = Join-Path $binPath "pdm.exe"
        Copy-Item -Path $binary.FullName -Destination $pdmPath -Force
        
        Write-PDMLog "Successfully installed PDM"
        
        # Verify installation
        $version = Test-PdmInstall -PdmPath $pdmPath
        Write-Host
        Write-ColorOutput -Color Green -Bold -Text "Successfully installed: "
        Write-ColorOutput -Color Green -Text "PDM"
        Write-ColorOutput -Color Yellow -Text " ($version)"
        Write-ColorOutput -Color Cyan -Text " at "
        Write-ColorOutput -Color Green -Text $pdmPath
        Write-Host
        
        # Add to PATH
        Add-ToPath -BinPath $binPath
        
        Write-PDMLog "Installation completed successfully!"
        
    } finally {
        # Cleanup
        if (Test-Path $tempDir) {
            Remove-Item -Path $tempDir -Recurse -Force
        }
    }
}

# Run installation
Install-Pdm