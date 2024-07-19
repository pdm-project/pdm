#compdef pdm

PDM_PYTHON="%{python_executable}"
PDM_PYPI_URL=$(PDM_CHECK_UPDATE=0 "${PDM_PYTHON}" -m pdm config pypi.url)

_pdm() {
  emulate -L zsh -o extended_glob

  typeset -A opt_args
  local context state state_descr line

  local curcontext=$curcontext ret=1
  local -a arguments=(
    {-h,--help}'[Show help message and exit]'
    {-v,--verbose}'[Use `-v` for detailed output and `-vv` for more detailed]'
    {-q,--quiet}'[Suppress output]'
  )
  local sub_commands=(
    'add:Add package(s) to pyproject.toml and install them'
    'build:Build artifacts for distribution'
    'cache:Control the caches of PDM'
    'completion:Generate completion scripts for the given shell'
    'config:Display the current configuration'
    'export:Export the locked packages set to other formats'
    'fix:Fix the project problems according to the latest version of PDM'
    'import:Import project metadata from other formats'
    'info:Show the project information'
    'init:Initialize a pyproject.toml for PDM'
    'install:Install dependencies from lock file'
    'list:List packages installed in the current working set'
    'lock:Resolve and lock dependencies'
    'self:Manage the PDM program itself (previously known as plugin)'
    'outdated:Check for outdated packages and list the latest versions on indexes'
    'publish:Build and publish the project to PyPI'
    'python:Manage installed Python interpreters'
    'py:Manage installed Python interpreters'
    'remove:Remove packages from pyproject.toml'
    'run:Run commands or scripts with local packages loaded'
    'search:Search for PyPI packages'
    'show:Show the package information'
    'sync:Synchronize the current working set with lock file'
    'update:Update package(s) in pyproject.toml'
    'use:Use the given python version or path as base interpreter'
    'venv:Virtualenv management'
  )

  _arguments -s -C -A '-*' \
    $arguments \
    {-c,--config}'[Specify another config file path\[env var: PDM_CONFIG_FILE\]]' \
    {-V,--version}'[Show the version and exit]' \
    {-I,--ignore-python}'[Ignore the Python path saved in .pdm-python]' \
    '--no-cache:Disable the cache for the current command. [env var: PDM_NO_CACHE]' \
    '--pep582:Print the command line to be eval by the shell for PEP 582:shell:(zsh bash fish tcsh csh)' \
    {-n,--non-interactive}"[Don't show interactive prompts but use defaults. \[env var: PDM_NON_INTERACTIVE\]]" \
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
        {-L,--lockfile}'[Specify another lockfile path, or use `PDM_LOCKFILE` env variable. Default: pdm.lock]:lockfile:_files'
        "--override+[Use the constraint file in pip-requirements format for overriding. \[env var: PDM_CONSTRAINT\] This option can be used multiple times. See https://pip.pypa.io/en/stable/user_guide/#constraints-files]:override:_files"
        '--no-sync[Only write pyproject.toml and do not sync the working set]'
        '--save-compatible[Save compatible version specifiers]'
        '--save-wildcard[Save wildcard version specifiers]'
        '--save-exact[Save exact version specifiers]'
        '--save-minimum[Save minimum version specifiers]'
        '--update-reuse[Reuse pinned versions already present in lock file if possible]'
        '--update-reuse-installed[Reuse installed packages if possible]'
        '--update-eager[Try to update the packages and their dependencies recursively]'
        '--update-all[Update all dependencies and sub-dependencies]'
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        "--frozen-lockfile[Don't try to create or update the lockfile. \[env var: PDM_FROZEN_LOCKFILE\]]"
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:'
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        {-u,--unconstrained}'[Ignore the version constraints in pyproject.toml and overwrite with new ones from the resolution result]'
        {--pre,--prerelease}'[Allow prereleases to be pinned]'
        "--stable[Only allow stable versions to be pinned]"
        {-e+,--editable+}'[Specify editable packages]:packages'
        {-x,--fail-fast}'[Abort on first installation error]'
        {-C,--config-setting}'[Pass options to the backend. options with a value must be specified after "=": "--config-setting=key(=value)" or "-Ckey(=value)"]:cs:'
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
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        '--no-clean[Do not clean the target directory]'
        {-C,--config-setting}'[Pass options to the backend. options with a value must be specified after "=": "--config-setting=key(=value)" or "-Ckey(=value)"]:cs:'
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
              compadd -X type 'hashes' 'http' 'wheels' 'metadata' 'packages' && ret=0
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
         {-l,--local}"[Set config in the project's local configuration file]" \
         {-d,--delete}'[Unset a configuration key]' \
         {-e,--edit}'[Edit the configuration file in the default editor(defined by EDITOR env var)]' \
         '1:key:->keys' \
         '2:value:_files' && return 0
      if [[ $state == keys ]]; then
        local l mbegin mend match keys=()
        for l in ${(f)"$(PDM_CHECK_UPDATE=0 command ${PDM_PYTHON} -m pdm config)"}; do
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
        {-f+,--format+}"[Only requirements.txt is supported for now.]:format:(requirements)"
        "--no-hashes[Don't include artifact hashes]"
        "--no-markers[Don't include platform markers]"
        "--no-extras[Strip extras from the requirements]"
        "--expandvars[Expand environment variables in requirements]"
        "--self[Include the project itself]"
        "--editable-self[Include the project itself as an editable dependency]"
        {-L,--lockfile}'[Specify another lockfile path, or use `PDM_LOCKFILE` env variable. Default: pdm.lock]:lockfile:_files'
        {-o+,--output+}"[Write output to the given file, or print to stdout if not given]:output file:_files"
        {-G+,--group+,--with+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        "--without+[Exclude groups of optional-dependencies or dev-dependencies]:group:_pdm_groups"
        {-d,--dev}"[Select dev dependencies]"
        {--prod,--production}"[Unselect dev dependencies]"
        "--no-default[Don't include dependencies from the default group]"
      )
      ;;
    fix)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        '--dry-run[Only show the problems]'
        '1:problem:'
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
        '--json[Dump the information in JSON]'
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:'
      )
      ;;
    init)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-n,--non-interactive}"[Don't ask questions but use default values]"
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        {-r,--overwrite}'[Overwrite existing files]'
        '--backend[Specify the build backend, which implies --dist]:backend:(pdm-backend setuptools hatchling flit)'
        {--dist,--lib}'[Create a package for distribution]'
        '--python[Specify the Python version/path to use]:python:'
        '--copier[Use Copier to generate project]'
        '--cookiecutter[Use Cookiecutter to generate project]'
        '--license[Specify the license (SPDX name)]:license:'
        "--project-version[Specify the project's version]:project_version:"
        '1:template:'
      )
      ;;
    install)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-G+,--group+,--with+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        "--without+[Exclude groups of optional-dependencies or dev-dependencies]:group:_pdm_groups"
        {-d,--dev}"[Select dev dependencies]"
        {-L,--lockfile}'[Specify another lockfile path, or use `PDM_LOCKFILE` env variable. Default: pdm.lock]:lockfile:_files'
        "--override+[Use the constraint file in pip-requirements format for overriding. \[env var: PDM_CONSTRAINT\] This option can be used multiple times. See https://pip.pypa.io/en/stable/user_guide/#constraints-files]:override:_files"
        {--prod,--production}"[Unselect dev dependencies]"
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        "--frozen-lockfile[Don't try to create or update the lockfile. \[env var: PDM_FROZEN_LOCKFILE\]]"
        "--no-default[Don\'t include dependencies from the default group]"
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        {-x,--fail-fast}'[Abort on first installation error]'
        {-C,--config-setting}'[Pass options to the backend. options with a value must be specified after "=": "--config-setting=key(=value)" or "-Ckey(=value)"]:cs:'
        "--no-isolation[do not isolate the build in a clean environment]"
        "--dry-run[Show the difference only without modifying the lock file content]"
        "--check[Check if the lock file is up to date and fail otherwise]"
        "--plugins[Install the plugins specified in pyproject.toml]"
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:'
      )
      ;;
    list)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-r,--reverse}'[Reverse the dependency tree]'
        '--fields[Select information to output as a comma separated string.]:fields:'
        "--sort[Sort the output using a given field name. If nothing is set, no sort is applied. Multiple fields can be combined with ',']:sort:"
        '--json[Output dependencies in JSON document format]'
        '--csv[Output dependencies in CSV document format]'
        '--markdown[Output dependencies and legal notices in markdown document format - best effort basis]'
        {--tree,--graph}'[Display a tree of dependencies]'
        "--freeze[Show the installed dependencies as pip's requirements.txt format]"
        "--include[Dependency groups to include in the output. By default all are included]:include:"
        "--exclude[Dependency groups to exclude from the output]:exclude:"
        "--resolve[Resolve all requirements to output licenses (instead of just showing those currently installed)]"
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:'
        '*:patterns:'
      )
      ;;
    lock)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-L,--lockfile}'[Specify another lockfile path, or use `PDM_LOCKFILE` env variable. Default: pdm.lock]:lockfile:_files'
        {-C,--config-setting}'[Pass options to the backend. options with a value must be specified after "=": "--config-setting=key(=value)" or "-Ckey(=value)"]:cs:'
        "--no-isolation[Do not isolate the build in a clean environment]"
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        "--refresh[Refresh the content hash and file hashes in the lock file]"
        "--check[Check if the lock file is up to date and quit]"
        {-G+,--group+,--with+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        "--without+[Exclude groups of optional-dependencies or dev-dependencies]:group:_pdm_groups"
        "--override+[Use the constraint file in pip-requirements format for overriding. \[env var: PDM_CONSTRAINT\] This option can be used multiple times. See https://pip.pypa.io/en/stable/user_guide/#constraints-files]:override:_files"
        {-d,--dev}"[Select dev dependencies]"
        {--prod,--production}"[Unselect dev dependencies]"
        '--update-reuse[Reuse pinned versions already present in lock file if possible]'
        '--update-reuse-installed[Reuse installed packages if possible]'
        "--static-urls[(DEPRECATED) Store static file URLs in the lockfile]"
        "--no-static-urls[(DEPRECATED) Do not store static file URLs in the lockfile]"
        "--no-default[Don\'t include dependencies from the default group]"
        "--no-cross-platform[(DEPRECATED) Only lock packages for the current platform]"
        "--exclude-newer[Exclude packages newer than the given UTC date in format YYYY-MM-DD\[THH:MM:SSZ\]]:exclude-newer:"
        {-S,--strategy}'[Specify lock strategy(cross_platform,static_urls,direct_minimal_versions). Add no_ prefix to disable. Support given multiple times or split by comma.]:strategy:_pdm_lock_strategy'
        "--append[Append the result to the current lock file]"
        "--python[The Python range to lock for. E.g. >=3.9, ==3.12.*]:python:"
        "--implementation[The Python implementation to lock for. E.g. cpython, pypy]:implementation:"
        "--platform[The platform to lock for. E.g. linux, windows, macos, alpine, windows_amd64]:platform:_pdm_lock_platform"
      )
      ;;
    outdated)
      arguments+=(
        '--json[Output in JSON format]'
        '*:patterns:'
      )
      ;;
    self)
      _arguments -C \
        $arguments \
        ': :->command' \
        '*:: :->args' && ret=0
      case $state in
        command)
          local -a actions=(
            "add:Install packages to the PDM's environment"
            "remove:Remove packages from PDM's environment"
            "list:List all packages installed with PDM"
            "update:Update PDM itself"
          )
          _describe -t command 'pdm self actions' actions && ret=0
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
            list)
              arguments+=(
                '--plugins[List plugins only]'
                '*:patterns:'
              )
              ;;
            update)
              arguments+=(
                '--head[Update to the latest commit on the main branch]'
                '--pre[Update to the latest prerelease version]'
                '--pip-args[Arguments that will be passed to pip uninstall]:pip args:'
              )
              ;;
            *)
              ;;
          esac
          ;;
      esac
      return $ret
      ;;
    python|py)
      _arguments -C \
        $arguments \
        ': :->command' \
        '*:: :->args' && ret=0
      case $state in
        command)
          local -a actions=(
            "remove:Remove a Python interpreter installed with PDM"
            "list:List all Python interpreters installed with PDM"
            "install:Install a Python interpreter with PDM"
          )
          _describe -t command 'pdm python actions' actions && ret=0
          ;;
        args)
          case $words[1] in
            remove)
              arguments+=(
                ':python:'
              )
              ;;
            install)
              arguments+=(
                '--list[List all available Python versions]'
                '--min[Use minimum instead of highest version for installation if `version` is left empty]'
                ':python:_files'
              )
              ;;
            *)
              ;;
          esac
          ;;
        esac
      return $ret
      ;;
    publish)
      arguments+=(
        {-r,--repository}'[The repository name or url to publish the package to }\[env var: PDM_PUBLISH_REPO\]]:repository:'
        {-u,--username}'[The username to access the repository \[env var: PDM_PUBLISH_USERNAME\]]:username:'
        {-P,--password}'[The password to access the repository \[env var: PDM_PUBLISH_PASSWORD\]]:password:'
        {-S,--sign}'[Upload the package with PGP signature]'
        {-i,--identity}'[GPG identity used to sign files.]:gpg identity:'
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        {-c,--comment}'[The comment to include with the distribution file.]:comment:'
        {-d,--dest}'[The directory to upload the package from]:dest:_files'
        "--no-verify-ssl[Disable SSL verification]"
        "--ca-certs[The path to a PEM-encoded Certificate Authority bundle to use for publish server validation]:cacerts:_files"
        "--no-build[Don't build the package before publishing]"
        "--skip-existing[Skip uploading files that already exist. This may not work with some repository implementations.]"
      )
      ;;
    remove)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-G,--group}'[Specify the target dependency group to remove from]:group:_pdm_groups'
        {-d,--dev}"[Remove packages from dev dependencies]"
        {-L,--lockfile}'[Specify another lockfile path, or use `PDM_LOCKFILE` env variable. Default: pdm.lock]:lockfile:_files'
        "--override+[Use the constraint file in pip-requirements format for overriding. \[env var: PDM_CONSTRAINT\] This option can be used multiple times. See https://pip.pypa.io/en/stable/user_guide/#constraints-files]:override:_files"
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        "--no-sync[Only write pyproject.toml and do not uninstall packages]"
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        "--frozen-lockfile[Don't try to create or update the lockfile. \[env var: PDM_FROZEN_LOCKFILE\]]"
        {-x,--fail-fast}'[Abort on first installation error]'
        {-C,--config-setting}'[Pass options to the backend. options with a value must be specified after "=": "--config-setting=key(=value)" or "-Ckey(=value)"]:cs:'
        "--no-isolation[do not isolate the build in a clean environment]"
        "--dry-run[Show the difference only without modifying the lockfile content]"
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:'
        "*:packages:_pdm_packages"
      )
      ;;
    run)
      _arguments -s \
        {-g,--global}'[Use the global project, supply the project root with `-p` option]' \
        {-l,--list}'[Show all available scripts defined in pyproject.toml]' \
        '--json[Output all scripts infos in JSON]' \
        '--recreate[Recreate the script environment for self-contained scripts]' \
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]' \
        {-s,--site-packages}'[Load site-packages from the selected interpreter]' \
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:' \
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
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:'
        '1:package:'
      )
      ;;
    sync)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-G+,--group+,--with+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        "--without+[Exclude groups of optional-dependencies or dev-dependencies]:group:_pdm_groups"
        {-d,--dev}"[Select dev dependencies]"
        {-L,--lockfile}'[Specify another lockfile path, or use `PDM_LOCKFILE` env variable. Default: pdm.lock]:lockfile:_files'
        {--prod,--production}"[Unselect dev dependencies]"
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        '--dry-run[Only prints actions without actually running them]'
        {-r,--reinstall}"[Force reinstall existing dependencies]"
        '--clean[Clean unused packages]'
        "--clean-unselected[Remove all but the selected packages]"
        "--only-keep[Remove all but the selected packages]"
        "--no-default[Don\'t include dependencies from the default group]"
        {-x,--fail-fast}'[Abort on first installation error]'
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        {-C,--config-setting}'[Pass options to the backend. options with a value must be specified after "=": "--config-setting=key(=value)" or "-Ckey(=value)"]:cs:'
        "--no-isolation[do not isolate the build in a clean environment]"
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:'
      )
      ;;
    update)
      arguments+=(
        {-g,--global}'[Use the global project, supply the project root with `-p` option]'
        {-G+,--group+,--with+}'[Select group of optional-dependencies or dev-dependencies(with -d). Can be supplied multiple times, use ":all" to include all groups under the same species]:group:_pdm_groups'
        "--without+[Exclude groups of optional-dependencies or dev-dependencies]:group:_pdm_groups"
        {-L,--lockfile}'[Specify another lockfile path, or use `PDM_LOCKFILE` env variable. Default: pdm.lock]:lockfile:_files'
        "--override+[Use the constraint file in pip-requirements format for overriding. \[env var: PDM_CONSTRAINT\] This option can be used multiple times. See https://pip.pypa.io/en/stable/user_guide/#constraints-files]:override:_files"
        '--save-compatible[Save compatible version specifiers]'
        '--save-wildcard[Save wildcard version specifiers]'
        '--save-exact[Save exact version specifiers]'
        '--save-minimum[Save minimum version specifiers]'
        '--update-reuse[Reuse pinned versions already present in lock file if possible]'
        '--update-eager[Try to update the packages and their dependencies recursively]'
        '--update-all[Update all dependencies and sub-dependencies]'
        '--update-reuse-installed[Reuse installed packages if possible]'
        '--no-editable[Install non-editable versions for all packages]'
        "--no-self[Don't install the project itself]"
        "--no-sync[Only update lock file but do not sync packages]"
        "--frozen-lockfile[Don't try to create or update the lockfile. \[env var: PDM_FROZEN_LOCKFILE\]]"
        {-k,--skip}'[Skip some tasks and/or hooks by their comma-separated names]'
        {-u,--unconstrained}'[Ignore the version constraints in pyproject.toml and overwrite with new ones from the resolution result]'
        {--pre,--prerelease}'[Allow prereleases to be pinned]'
        "--stable[Only allow stable versions to be pinned]"
        {-d,--dev}'[Select dev dependencies]'
        {--prod,--production}"[Unselect dev dependencies]"
        "--no-default[Don\'t include dependencies from the default group]"
        {-t,--top}'[Only update those list in pyproject.toml]'
        "--dry-run[Show the difference only without modifying the lockfile content]"
        "--outdated[Show the difference only without modifying the lockfile content]"
        {-x,--fail-fast}'[Abort on first installation error]'
        {-C,--config-setting}'[Pass options to the backend. options with a value must be specified after "=": "--config-setting=key(=value)" or "-Ckey(=value)"]:cs:'
        "--no-isolation[do not isolate the build in a clean environment]"
        '--venv[Run the command in the virtual environment with the given key. \[env var: PDM_IN_VENV\]]:venv:'
        "*:packages:_pdm_packages"
      )
      ;;
    use)
      arguments+=(
        {-f,--first}'[Select the first matched interpreter -- no auto install]'
        '--auto-install-min[If `python` argument not given, auto install minimum best match - otherwise has no effect]'
        '--auto-install-max[If `python` argument not given, auto install maximum best match - otherwise has no effect]'
        {-i,--ignore-remembered}'[Ignore the remembered selection]'
        '--venv[Use the interpreter in the virtual environment with the given name]:venv:'
        '*:python:_files'
      )
      ;;
    venv)
      _arguments -C \
        $arguments \
        ': :->command' \
        '*:: :->args' && ret=0
      case $state in
        command)
          local -a actions=(
            "create:Create a virtualenv"
            "list:List all virtualenvs associated with this project"
            "remove:Remove the virtualenv with the given name"
            "activate:Activate the virtualenv with the given name"
            "purge:Purge selected/all created Virtualenvs"
          )
          arguments+=(
            '--path[Show the path to the given virtualenv]'
            '--python[Show the Python interpreter path of the given virtualenv]'
          )
          _describe -t command 'pdm venv actions' actions && ret=0
          ;;
        args)
          case $words[1] in
            create)
              arguments+=(
                {-w,--with}'[Specify the backend to create the virtualenv]:backend:(virtualenv venv conda)'
                '--with-pip[Install pip with the virtualenv]'
                {-n,--name}'[Specify the name of the virtualenv]:name:'
                {-f,--force}'[Recreate if the virtualenv already exists]'
              )
              ;;
            remove)
              arguments+=(
                {-y,--yes}'[Answer yes on the following question]'
              )
              ;;
            purge)
              arguments+=(
                {-f,--force}'[Force purging without prompting for confirmation]'
                {-i,--interactive}'[Interactively purge selected Virtualenvs]'
              )
              ;;
            *)
              ;;
          esac
          ;;
      esac
      return $ret
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
print(*set(packages))
EOF
}

_pdm_scripts() {
  local scripts=() package_dir=$(PDM_CHECK_UPDATE=0 $PDM_PYTHON -m pdm info --packages)
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

_pdm_lock_strategy() {
  local -a strategy=(
    'cross_platform:(DEPRECATED)Lock packages for all platforms'
    'inherit_metadata:Calculate and store the markers for the packages'
    'static_urls:Store static file URLs in the lockfile'
    'direct_minimal_versions:Store the minimal versions of the dependencies'
    'no_cross_platform:Only lock packages for the current platform'
    'no_static_urls:Do not store static file URLs in the lockfile'
    'no_inherit_metadata:Do not calculate and store the markers for the packages'
    'no_direct_minimal_versions:Do not store the minimal versions of the dependencies'
  )
  _describe -t strategy "lock strategy" strategy
}

_pdm_lock_platform() {
  local -a platforms=(
    "linux"
    "windows"
    "macos"
    "alpine"
    "windows_amd64"
    "windows_x86"
    "windows_arm64"
    "macos_arm64"
    "macos_x86_64"
  )
  _describe -t platform "platform" platforms
}

_pdm_caching_policy() {
    [[ ! -f $1 && -n "$1"(Nm+28) ]]
}

_pdm_pip_packages_update() {
  typeset -g _pdm_packages
  if _cache_invalid pdm_packages || ! _retrieve_cache pdm_packages; then
    local index
    _pdm_packages+=($(command curl -sL $PDM_PYPI_URL | command sed -nE '/<a href/ s/.*>(.+)<.*/\1/p'))
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
