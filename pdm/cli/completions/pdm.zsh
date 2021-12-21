#compdef pdm

PDM_PYTHON="%{python_executable}"
PDM_PIP_INDEXES=($(command ${PDM_PYTHON} -m pdm config pypi.url))

_pdm() {
  emulate -L zsh -o extended_glob

  typeset -A opt_args
  local context state state_descr line

  local curcontext=$curcontext ret=1
  local -a arguments=(
    {-h,--help}'[Show help message and exit]'
    {-v,--verbose}'[Show detailed output]'
  )
  local sub_commands=(
    'add:Add package(s) to pyproject.toml and install them'
    'build:Build artifacts for distribution'
    'cache:Control the caches of PDM'
    'completion:Generate completion scripts for the given shell'
    'config:Display the current configuration'
    'export:Export the locked packages set to other formats'
    'import:Import project metadata from other formats'
    'info:Show the project information'
    'init:Initialize a pyproject.toml for PDM'
    'install:Install dependencies from lock file'
    'list:List packages installed in the current working set'
    'lock:Resolve and lock dependencies'
    'plugin:Manage the PDM plugins'
    'remove:Remove packages from pyproject.toml'
    'run:Run commands or scripts with local packages loaded'
    'search:Search for PyPI packages'
    'show:Show the package information'
    'sync:Synchronize the current working set with lock file'
    'update:Update package(s) in pyproject.toml'
    'use:Use the given python version or path as base interpreter'
  )

  _arguments -s -C -A '-*' \
    $arguments \
    {-V,--version}'[Show the version and exit]' \
    {-I,--ignore-python}'[Ignore the Python path saved in the pdm.toml config]' \
    '--pep582=[Print the command line to be eval by the shell]:shell:(zsh bash fish tcsh csh)' \
    '*:: :->_subcmds' \
    && return 0

  if (( CURRENT == 1 )); then
    _describe -t commands 'pdm subcommand' sub_commands
    return
  fi

  curcontext=${curcontext%:*}:$words[1]

  case $words[1] in
    add)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-d,--dev}'[Add packages into dev dependencies]'
        {-G,--group}'[Specify the target dependency group to add into]:group:_pdm_groups'
        '--no-sync[Only write pyproject.toml and do not sync the working set]'
        '--save-compatible[Save compatible version specifiers]'
        '--save-wildcard[Save wildcard version specifiers]'
        '--save-exact[Save exact version specifiers]'
        '--save-minimum[Save minimum version specifiers]'
        '--update-reuse[Reuse pinned versions already present in lock file if possible]'
        '--update-eager[Try to update the packages and their dependencies recursively]'
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        {-u,--unconstrained}'[Ignore the version constraint of packages]'
        {--pre,--prerelease}'[Allow prereleases to be pinned]'
        {-e+,--editable+}'[Specify editable packages]:packages'
        "--no-isolation[do not isolate the build in a clean environment]"
        "--dry-run[Show the difference only without modifying the lockfile content]"
        '*:packages:_pdm_pip_packages'
      )
      ;;
    build)
      arguments+=(
        "--no-sdist[Don't build source tarballs]"
        "--no-wheel[Don't build wheels]"
        {-d+,--dest+}'[Target directory to put artifacts]:directory:_files -/'
        '--no-clean[Do not clean the target directory]'
        {-C,--config-setting}'[Pass options to the backend. options with a value must be specified after "=": "--config-setting=--opt(=value)" or "-C--opt(=value)"]'
        "--no-isolation[do not isolate the build in a clean environment]"
      )
      ;;
    cache)
      _arguments -C \
        $arguments \
        ': :->command' \
        '*:: :->args' && ret=0
      case $state in
        command)
          local -a actions=(
            "clear:Clean all the files under cache directory"
            "remove:Remove files matching the given pattern"
            "list:List the built wheels stored in the cache"
            "info:Show the info and current size of caches"
          )
          _describe -t command 'pdm cache actions' actions && ret=0
          ;;
        args)
          case $words[1] in
            clear)
              compadd -X type 'hashes' 'http' 'wheels' 'metadata' && ret=0
              ;;
            *)
              _message "pattern" && ret=0
              ;;
          esac
          ;;
      esac
      return $ret
      ;;
    config)
      _arguments -s  \
         {-g,--global}'[Use the global project, supply the project root with `-p` option]' \
         {-l,--local}"[Set config in the project's local configuration filie]" \
         {-d,--delete}'[Unset a configuration key]' \
         '1:key:->keys' \
         '2:value:_files' && return 0
      if [[ $state == keys ]]; then
        local l mbegin mend match keys=()
        for l in ${(f)"$(command ${PDM_PYTHON} -m pdm config)"}; do
          if [[ $l == (#b)" "#(*)" = "(*) ]]; then
            keys+=("$match[1]:$match[2]")
          fi
        done
        _describe -t key "key" keys && return 0
      fi
      ;;
    export)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-f+,--format+}"[Specify the export file format]:format:(pipfile poetry flit requirements setuppy)"
        "--without-hashes[Don't include artifact hashes]"
        {-o+,--output+}"[Write output to the given file, or print to stdout if not given]:output file:_files"
        {-G+,--group+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        {-d,--dev}"[Select dev dependencies]"
        {--prod,--production}"[Unselect dev dependencies]"
        "--no-default[Don't include dependencies from the default group]"
      )
      ;;
    import)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-f+,--format+}"[Specify the file format explicitly]:format:(pipfile poetry flit requirements)"
        '1:filename:_files'
      )
      ;;
    info)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        '--python[Show the interpreter path]'
        '--where[Show the project root path]'
        '--env[Show PEP 508 environment markers]'
        '--packages[Show the packages root]'
      )
      ;;
    init)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-n,--non-interactive}"[Don't ask questions but use default values]"
      )
      ;;
    install)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-G+,--group+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        {-d,--dev}"[Select dev dependencies]"
        {--prod,--production}"[Unselect dev dependencies]"
        "--no-lock[Don't do lock if lock file is not found or outdated]"
        "--no-default[Don\'t include dependencies from the default group]"
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        "--no-isolation[do not isolate the build in a clean environment]"
        "--dry-run[Show the difference only without modifying the lock file content]"
        "--check[Check if the lock file is up to date and fail otherwise]"
      )
      ;;
    list)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-r,--reverse}'[Reverse the dependency graph]'
        '--json[Show the installed dependencies in JSON document format]'
        '--graph[Display a graph of dependencies]'
        "--freeze[Show the installed dependencies as pip's requirements.txt format]"
      )
      ;;
    lock)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        "--no-isolation[Do not isolate the build in a clean environment]"
        "--refresh[Don't update pinned versions, only refresh the lock file]"
      )
      ;;
    plugin)
      _arguments -C \
        $arguments \
        ': :->command' \
        '*:: :->args' && ret=0
      case $state in
        command)
          local -a actions=(
            "add:Install new plugins with PDM"
            "remove:Remove plugins from PDM's environment"
            "list:List all plugins installed with PDM"
          )
          _describe -t command 'pdm plugin actions' actions && ret=0
          ;;
        args)
          case $words[1] in
            add)
              arguments+=(
                '--pip-args[Arguments that will be passed to pip install]:pip args:'
                '*:packages:_pdm_pip_packages'
              )
              ;;
            remove)
              arguments+=(
                '--pip-args[Arguments that will be passed to pip uninstall]:pip args:'
                {-y,--yes}'[Answer yes on the question]'
                '*:packages:_pdm_pip_packages'
              )
              ;;
            *)
              ;;
          esac
          ;;
      esac
      return $ret
      ;;
    remove)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-G,--group}'[Specify the target dependency group to remove from]:group:_pdm_groups'
        {-d,--dev}"[Remove packages from dev dependencies]"
        "--no-sync[Only write pyproject.toml and do not uninstall packages]"
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        "--no-isolation[do not isolate the build in a clean environment]"
        "--dry-run[Show the difference only without modifying the lockfile content]"
        "*:packages:_pdm_packages"
      )
      ;;
    run)
      _arguments -s \
        {-g,--global}'[Use the global project, supply the project root with `-p` option]' \
        {-l,--list}'[Show all available scripts defined in pyproject.toml]' \
        {-s,--site-packages}'[Load site-packages from the selected interpreter]' \
        '(-)1:command:->command' \
        '*:arguments: _normal ' && return 0
      if [[ $state == command ]]; then
        _command_names -e
        local local_commands=($(_pdm_scripts))
        _describe "local command" local_commands
        return 0
      fi
      ;;
    search)
      arguments+=(
        '1:query string:'
      )
      ;;
    show)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        '--name[Show name]'
        '--version[Show version]'
        '--summary[Show summary]'
        '--license[Show license]'
        '--platform[Show platform]'
        '--keywords[Show keywords]'
        '1:package:'
      )
      ;;
    sync)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-G+,--group+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        {-d,--dev}"[Select dev dependencies]"
        {--prod,--production}"[Unselect dev dependencies]"
        '--dry-run[Only prints actions without actually running them]'
        {-r,--reinstall}"[Force reinstall existing dependencies]"
        '--clean[Clean unused packages]'
        "--no-clean[Don't clean unused packages]"
        "--no-default[Don\'t include dependencies from the default group]"
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        "--no-isolation[do not isolate the build in a clean environment]"
      )
      ;;
    update)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-G+,--group+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        '--save-compatible[Save compatible version specifiers]'
        '--save-wildcard[Save wildcard version specifiers]'
        '--save-exact[Save exact version specifiers]'
        '--save-minimum[Save minimum version specifiers]'
        '--update-reuse[Reuse pinned versions already present in lock file if possible]'
        '--update-eager[Try to update the packages and their dependencies recursively]'
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        "--no-sync[Only update lock file but do not sync packages]"
        {-u,--unconstrained}'[Ignore the version constraint of packages]'
        {--pre,--prerelease}'[Allow prereleases to be pinned]'
        {-d,--dev}'[Select dev dependencies]'
        {--prod,--production}"[Unselect dev dependencies]"
        "--no-default[Don\'t include dependencies from the default group]"
        {-t,--top}'[Only update those list in pyproject.toml]'
        "--dry-run[Show the difference only without modifying the lockfile content]"
        "--outdated[Show the difference only without modifying the lockfile content]"
        "--no-isolation[do not isolate the build in a clean environment]"
        "*:packages:_pdm_packages"
      )
      ;;
    use)
      arguments+=(
        {-f,--first}'[Select the first matched interpreter]'
        '*:python:_files'
      )
      ;;
  esac

  _arguments -s $arguments && ret=0

  return ret
}

_pdm_groups() {
  if [[ ! -f pyproject.toml ]]; then
    _message "not a pdm project"
    return 1
  fi
  local l groups=() in_groups=0
  while IFS= read -r l; do
    case $l in
      "["project.optional-dependencies"]") in_groups=1 ;;
      "["tool.pdm.dev-dependencies"]") in_groups=1 ;;
      "["*"]") in_groups=0 ;;
      *"= [")
        if (( in_groups )); then
          groups+=$l[(w)1]
        fi
        ;;
    esac
  done <pyproject.toml
  compadd -X groups -a groups
}

_get_packages_with_python() {
  command ${PDM_PYTHON} - << EOF
import os, re, toml
PACKAGE_REGEX = re.compile(r'^[A-Za-z][A-Za-z0-9._-]*')
def get_packages(lines):
    return [PACKAGE_REGEX.match(line).group() for line in lines]

with open('pyproject.toml', 'rb') as f:
    data = tomli.load(f)
packages = get_packages(data.get('project', {}).get('dependencies', []))
for reqs in data.get('project', {}).get('optional-dependencies', {}).values():
    packages.extend(get_packages(reqs))
for reqs in data.get('tool', {}).get('pdm', {}).get('dev-dependencies', {}).values():
    packages.extend(get_packages(reqs))
print(*set(packages))
EOF
}

_pdm_scripts() {
  local scripts=() package_dir=$($PDM_PYTHON -m pdm info --packages)
  if [[ -f pyproject.toml ]]; then
    local l in_scripts=0
    while IFS= read -r l; do
    case $l in
      "["tool.pdm.scripts"]") in_scripts=1 ;;
      "["*"]") in_scripts=0 ;;
      *"= "*)
        if (( in_scripts )); then
            scripts+=$l[(w)1]
        fi
      ;;
    esac
    done < pyproject.toml
  fi
  if [[ $package_dir != "None" ]]; then
    scripts+=($package_dir/bin/*(N:t))
  fi
  echo $scripts
}

_pdm_packages() {
  if [[ ! -f pyproject.toml ]]; then
    _message "not a pdm project"
    return 1
  fi
  local packages=(${=$(_get_packages_with_python)})
  compadd -X packages -a packages
}

_pdm_caching_policy() {
    [[ ! -f $1 && -n "$1"(Nm+28) ]]
}

_pdm_pip_packages_update() {
  typeset -g _pdm_packages
  if _cache_invalid pdm_packages || ! _retrieve_cache pdm_packages; then
    local index
    for index in $PDM_PIP_INDEXES; do
      _pdm_packages+=($(command curl -sL $index | command sed -nE '/<a href/ s/.*>(.+)<.*/\1/p'))
    done
    _store_cache pdm_packages _pdm_packages
  fi
}

_pdm_pip_packages() {
  if (( ! $+commands[curl] || ! $+commands[sed] )); then
    _message "package name"
    return 1
  fi

  local update_policy
  zstyle ":completion:${curcontext%:}:" use-cache on
  zstyle -s ":completion:${curcontext%:}:" cache-policy update_policy
  if [[ -z $update_policy ]]; then
    zstyle ":completion:${curcontext%:}:" cache-policy _pdm_caching_policy
  fi

  local -a _pdm_packages
  _pdm_pip_packages_update
  compadd -X packages -a _pdm_packages
}

_pdm "$@"
