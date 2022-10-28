# Powershell completion script for pdm

if ((Test-Path Function:\TabExpansion) -and -not (Test-Path Function:\_pdm_completeBackup)) {
    Rename-Item Function:\TabExpansion _pdm_completeBackup
}

$PDM_PYTHON = "%{python_executable}"
$PDM_PIP_INDEX = (& $PDM_PYTHON -m pdm config pypi.url).Trim()
$CONFIG_DIR = "$env:LOCALAPPDATA\pdm"

class Option {
    [string[]] $Opts
    [string[]] $Values

    Option([string[]] $opts) {
        $this.Opts = $opts
    }

    [Option] WithValues([string[]] $values) {
        $this.Values = $values
        return $this
    }

    [bool] Match([string] $word) {
        foreach ($opt in $this.Opts) {
            if ($word -eq $opt) {
                return $true
            }
        }
        return $false
    }

    [bool] TakesArg() {
        return $null -ne $this.Values
    }
}

class Completer {

    [string []] $params
    [bool] $multiple = $false
    [Option[]] $opts = @()

    Completer() {
    }

    [string[]] Complete([string[]] $words) {
        $expectArg = $null
        $lastWord = $words[-1]
        $paramUsed = $false
        if ($words.Length -gt 1) {
            foreach ($word in $words[0..($words.Length - 2)]) {
                if ($expectArg) {
                    $expectArg = $null
                    continue
                }
                if ($word.StartsWith("-")) {
                    $opt = $this.opts.Where( { $_.Match($word) })[0]
                    if ($null -ne $opt -and $opt.TakesArg()) {
                        $expectArg = $opt
                    }
                }
                elseif (-not $this.multiple) {
                    $paramUsed = $true
                }
            }
        }
        $candidates = @()
        if ($lastWord.StartsWith("-")) {
            foreach ($opt in $this.opts) {
                $candidates += $opt.Opts
            }
        }
        elseif ($null -ne $expectArg) {
            $candidates = $expectArg.Values
        }
        elseif ($null -ne $this.params -and -not $paramUsed) {
            $candidates = $this.params
        }
        return $candidates.Where( { $_.StartsWith($lastWord) })
    }

    [void] AddOpts([Option[]] $options) {
        $this.opts += $options
    }

    [void] AddParams([string[]] $params, [bool]$multiple = $false) {
        $this.params = $params
        $this.multiple = $multiple
    }
}

function getSections() {
    if (-not (Test-Path -Path "pyproject.toml")) {
        return @()
    }
    [string[]] $sections = @()
    [bool] $inSection = $false
    foreach ($line in (Get-Content "pyproject.toml")) {
        if (($line -match ' *\[project\.optional-dependencies\]') -or ($line -match ' *\[tool\.pdm.dev-dependencies\]')) {
            $inSection = $true
        }
        elseif ($inSection -and ($line -match '(\S+) *= *\[')) {
            $sections += $Matches[1]
        }
        elseif ($line -like '`[*`]') {
            $inSection = $false
        }
    }
    return $sections
}

function _fetchPackageListFromPyPI() {
    if (-not (Test-Path -Path $CONFIG_DIR)) {
        mkdir $CONFIG_DIR
    }
    (Invoke-WebRequest $PDM_PIP_INDEX).Links | ForEach-Object { $_.innerText } | Out-File -FilePath "$CONFIG_DIR\.pypiPackages"
}

function getPyPIPackages() {
    # $cacheFile = "$CONFIG_DIR\.pypiPackages"
    # if (-not (Test-Path -Path $cacheFile) -or (Get-Item $cacheFile).LastWriteTime -lt (Get-Date).AddDays(-28)) {
    #     _fetchPackageListFromPyPI
    # }
    # Get-Content $cacheFile
}

function getPdmPackages() {
    & $PDM_PYTHON -c "
import sys
if sys.version_info >= (3, 11):
  import tomllib
else:
  import tomli as tomllib
import os, re
PACKAGE_REGEX = re.compile(r'^[A-Za-z][A-Za-z0-9._-]*')
def get_packages(lines):
    return [PACKAGE_REGEX.match(line).group() for line in lines]

with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
packages = get_packages(data.get('project', {}).get('dependencies', []))
for reqs in data.get('project', {}).get('optional-dependencies', {}).values():
    packages.extend(get_packages(reqs))
for reqs in data.get('tool', {}).get('pdm', {}).get('dev-dependencies', {}).values():
    packages.extend(get_packages(reqs))
print(*set(packages), sep='\n')
"
}

$_cachedConfigKeys = $null
function getConfigKeys() {
    if ($null -eq $_cachedConfigKeys) {
        [string[]] $keys = @()
        $config = @(& $PDM_PYTHON -m pdm config)
        foreach ($line in $config) {
            if ($line -match ' *(\S+) *=') {
                $keys += $Matches[1]
            }
        }
        $_cachedConfigKeys = $keys
    }
    return $_cachedConfigKeys
}

function getScripts() {
    [string[]] $scripts = @()
    $packagesDir = (& $PDM_PYTHON -m pdm info --packages)
    if (Test-Path -Path "pyproject.toml") {
        [bool] $inScripts = $false
        foreach ($line in (Get-Content "pyproject.toml")) {
            if ($line -match ' *\[tool\.pdm\.scripts\]') {
                $inScripts = $true
            }
            elseif ($inScripts -and ($line -match '(\S+) *= *')) {
                $scripts += $Matches[1]
            }
            elseif ($line -like '`[*`]') {
                $inScripts = $false
            }
        }
    }
    if ($packagesDir -ne "None") {
        $scripts += (Get-ChildItem "$packagesDir\Scripts" | ForEach-Object { $_.Basename })
    }
    return $scripts

}

function TabExpansion($line, $lastWord) {
    $lastBlock = [regex]::Split($line, '[|;]')[-1].TrimStart()

    if ($lastBlock -match "^pdm ") {
        [string[]]$words = $lastBlock.Split()[1..$lastBlock.Length]
        [string[]]$AllCommands = ("add", "build", "cache", "completion", "config", "export", "import", "info", "init", "install", "list", "lock", "plugin", "publish", "remove", "run", "search", "show", "sync", "update", "use")
        [string[]]$commands = $words.Where( { $_ -notlike "-*" })
        $command = $commands[0]
        $completer = [Completer]::new()
        $completer.AddOpts(([Option]::new(("-h", "--help", "-v", "--verbose"))))
        $sectionOption = [Option]::new(@("-G", "--group")).WithValues(@(getSections))
        $projectOption = [Option]::new(@("-p", "--project")).WithValues(@())
        $skipOption = [Option]::new(@("-k", "--skip")).WithValues(@())
        $formatOption = [Option]::new(@("-f", "--format")).WithValues(@("setuppy", "requirements", "poetry", "flit"))

        Switch ($command) {

            "add" {
                $completer.AddOpts(@(
                        [Option]::new(("-d", "--dev", "--save-compatible", "--save-wildcard", "--dry-run", "--save-exact", "--save-minimum", "--update-eager", "--update-reuse", "--update-all", "-g", "--global", "--no-sync", "--no-editable", "--no-self", "-u", "--unconstrained", "--no-isolation", "--pre", "--prerelease", "-L", "--lockfile")),
                        $sectionOption,
                        $projectOption,
                        $skipOption
                        [Option]::new(@("-e", "--editable")).WithValues(@(getPyPIPackages))
                    ))
                $completer.AddParams(@(getPyPIPackages), $true)
                break
            }
            "build" { $completer.AddOpts(@([Option]::new(@("-d", "--dest", "--no-clean", "--no-sdist", "--no-wheel", "-C", "--config-setting", "--no-isolation")), $projectOption, $skipOption)) }
            "cache" {
                $subCommand = $commands[1]
                switch ($subCommand) {
                    "clear" {
                        $completer.AddParams(@("wheels", "http", "hashes", "metadata"), $false)
                        $command = $subCommand
                        break
                    }
                    Default {
                        $completer.AddParams(@("clear", "remove", "info", "list"), $false)
                        break
                    }
                }
                break
            }
            "completion" { $completer.AddParams(@("powershell", "bash", "zsh", "fish")); break }
            "config" {
                $completer.AddOpts(@([Option]::new(@("--delete", "--global", "--local", "-d", "-l", "-g")), $projectOption))
                $completer.AddParams(@(getConfigKeys), $false)
                break
            }
            "export" {
                $completer.AddOpts(@(
                        [Option]::new(@("--dev", "--output", "--global", "--no-default", "--prod", "--production", "-g", "-d", "-o", "--without-hashes", "-L", "--lockfile")),
                        $formatOption,
                        $sectionOption,
                        $projectOption
                    ))
                break
            }
            "import" {
                $completer.AddOpts(@(
                        [Option]::new(@("--dev", "--global", "--no-default", "-g", "-d")),
                        $formatOption,
                        $sectionOption,
                        $projectOption
                    ))
                break
            }
            "info" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("--env", "--global", "-g", "--python", "--where", "--packages")),
                        $projectOption
                    ))
                break
            }
            "init" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("-g", "--global", "--non-interactive", "-n", "--python")),
                        $projectOption,
                        $skipOption
                    ))
                break
            }
            "install" {
                $completer.AddOpts(@(
                        [Option]::new(("-d", "--dev", "-g", "--global", "--dry-run", "--no-default", "--no-lock", "--prod", "--production", "--no-editable", "--no-self", "--no-isolation", "--check", "-L", "--lockfile")),
                        $sectionOption,
                        $skipOption,
                        $projectOption
                    ))
                break
            }
            "list" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("--graph", "--global", "-g", "--reverse", "-r", "--freeze", "--json", "--csv", "--markdown", "--fields", "--sort", "--include", "--exclude", "--resolve")),
                        $projectOption
                    ))
                break
            }
            "lock" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("--global", "-g", "--no-isolation", "--refresh", "-L", "--lockfile", "--check")),
                        $skipOption,
                        $projectOption
                    ))
                break
            }
            "self" {
                $subCommand = $commands[1]
                switch ($subCommand) {
                    "add" {
                        $completer.AddOpts(([Option]::new(("--pip-args"))))
                        $completer.AddParams(@(getPyPIPackages), $true)
                        $command = $subCommand
                        break
                    }
                    "remove" {
                        $completer.AddOpts(([Option]::new(("--pip-args", "-y", "--yes"))))
                        $command = $subCommand
                        break
                    }
                    "list" {
                        $completer.AddOpts(([Option]::new(("--plugins"))))
                        $command = $subCommand
                        break
                    }
                    "update" {
                        $completer.AddOpts(([Option]::new(("--pip-args", "--head", "--pre"))))
                        $command = $subCommand
                        break
                    }
                    Default {
                        $completer.AddParams(@("add", "remove", "list", "update"), $false)
                        break
                    }
                }
                break
            }
            "publish" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("-r", "--repository", "-u", "--username", "-P", "--password", "-S", "--sign", "-i", "--identity", "-c", "--comment", "--no-build", "--ca-certs")),
                        $skipOption,
                        $projectOption
                    ))
                break
            }
            "remove" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("--global", "-g", "--dev", "-d", "--dry-run", "--no-sync", "--no-editable", "--no-self", "--no-isolation", "-L", "--lockfile")),
                        $projectOption,
                        $skipOption,
                        $sectionOption
                    ))
                $completer.AddParams(@(getPdmPackages), $true)
                break
            }
            "run" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("--global", "-g", "-l", "--list", "-s", "--site-packages")),
                        $skipOption,
                        $projectOption
                    ))
                $completer.AddParams(@(getScripts), $false)
                break
            }
            "search" { break }
            "show" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("--global", "-g", "--name", "--version", "--summary", "--license", "--platform", "--keywords")),
                        $projectOption
                    ))
                break
            }
            "sync" {
                $completer.AddOpts(@(
                        [Option]::new(("-d", "--dev", "-g", "--global", "--no-default", "--clean", "--only-keep", "--dry-run", "-r", "--reinstall", "--prod", "--production", "--no-editable", "--no-self", "--no-isolation", "-L", "--lockfile")),
                        $sectionOption,
                        $skipOption,
                        $projectOption
                    ))
                break
            }
            "update" {
                $completer.AddOpts(@(
                        [Option]::new(("-d", "--dev", "--save-compatible", "--prod", "--production", "--save-wildcard", "--save-exact", "--save-minimum", "--update-eager", "--update-reuse", "--update-all", "-g", "--global", "--dry-run", "--outdated", "--top", "-u", "--unconstrained", "--no-editable", "--no-self", "--no-isolation", "--no-sync", "--pre", "--prerelease", "-L", "--lockfile")),
                        $sectionOption,
                        $skipOption,
                        $projectOption
                    ))
                $completer.AddParams(@(getPdmPackages), $true)
                break
            }
            "use" {
                $completer.AddOpts(
                    @(
                        [Option]::new(@("--global", "-g", "-f", "--first", "-i", "--ignore-remembered", "--skip")),
                        $projectOption
                    ))
                break
            }

            default {
                # No command
                $command = $null
                $completer.AddOpts(([Option]::new(("--pep582", "-I", "--ignore-python", "-c", "--config"))))
                $completer.AddParams($AllCommands, $false)
            }
        }
        $start = [array]::IndexOf($words, $command) + 1
        $completer.Complete($words[$start..$words.Length])
    }
    elseif (Test-Path Function:\_pdm_completeBackup) {
        # Fall back on existing tab expansion
        _pdm_completeBackup $line $lastWord
    }
}
