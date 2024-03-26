# BASH completion script for pdm
# Generated by pycomplete 0.4.0

_pdm_a919b69078acdf0a_complete()
{
    local cur script coms opts com
    COMPREPLY=()
    _get_comp_words_by_ref -n : cur words

    # for an alias, get the real script behind it
    if [[ $(type -t ${words[0]}) == "alias" ]]; then
        script=$(alias ${words[0]} | sed -E "s/alias ${words[0]}='(.*)'/\\1/")
    else
        script=${words[0]}
    fi

    # lookup for command
    for word in ${words[@]:1}; do
        if [[ $word != -* ]]; then
            com=$word
            break
        fi
    done

    # completing for an option
    if [[ ${cur} == --* ]] ; then
        opts="--config --help --ignore-python --no-cache --pep582 --quiet --verbose --version"

        case "$com" in

            (add)
            opts="--config-setting --dev --dry-run --editable --fail-fast --frozen-lockfile --global --group --help --lockfile --no-editable --no-isolation --no-self --no-sync --prerelease --project --quiet --save-compatible --save-exact --save-minimum --save-wildcard --skip --stable --unconstrained --update-all --update-eager --update-reuse --update-reuse-installed --venv --verbose"
            ;;

            (build)
            opts="--config-setting --dest --help --no-clean --no-isolation --no-sdist --no-wheel --project --quiet --skip --verbose"
            ;;

            (cache)
            opts="--help --quiet --verbose"
            ;;

            (completion)
            opts="--help"
            ;;

            (config)
            opts="--delete --edit --global --help --local --project --quiet --verbose"
            ;;

            (export)
            opts="--dev --editable-self --expandvars --format --global --group --help --lockfile --no-default --no-markers --output --production --project --pyproject --quiet --self --verbose --without --without-hashes"
            ;;

            (fix)
            opts="--dry-run --global --help --project --quiet --verbose"
            ;;

            (import)
            opts="--dev --format --global --group --help --project --quiet --verbose"
            ;;

            (info)
            opts="--env --global --help --json --packages --project --python --quiet --venv --verbose --where"
            ;;

            (init)
            opts="--backend --cookiecutter --copier --dist --global --help --non-interactive --overwrite --project --python --quiet --skip --verbose"
            ;;

            (install)
            opts="--check --config-setting --dev --dry-run --fail-fast --frozen-lockfile --global --group --help --lockfile --no-default --no-editable --no-isolation --no-self --plugins --production --project --quiet --skip --venv --verbose --without"
            ;;

            (list)
            opts="--csv --exclude --fields --freeze --global --graph --help --include --json --markdown --project --quiet --resolve --reverse --sort --venv --verbose"
            ;;

            (lock)
            opts="--check --config-setting --dev --exclude-newer --global --group --help --lockfile --no-cross-platform --no-default --no-isolation --no-static-urls --production --project --quiet --refresh --skip --static-urls --strategy --update-reuse --update-reuse-installed --verbose --without"
            ;;

            (outdated)
            opts="--global --help --json --project --quiet --verbose"
            ;;

            (plugin)
            opts="--help --quiet --verbose"
            ;;

            (publish)
            opts="--ca-certs --comment --help --identity --no-build --no-very-ssl --password --project --quiet --repository --sign --skip --skip-existing --username --verbose"
            ;;

            (py)
            opts="--help"
            ;;

            (python)
            opts="--help"
            ;;

            (remove)
            opts="--config-setting --dev --dry-run --fail-fast --frozen-lockfile --global --group --help --lockfile --no-editable --no-isolation --no-self --no-sync --project --quiet --skip --venv --verbose"
            ;;

            (run)
            opts="--global --help --json --list --project --quiet --site-packages --skip --venv --verbose"
            ;;

            (search)
            opts="--help --quiet --verbose"
            ;;

            (self)
            opts="--help --quiet --verbose"
            ;;

            (show)
            opts="--global --help --keywords --license --name --platform --project --quiet --summary --venv --verbose --version"
            ;;

            (sync)
            opts="--clean --config-setting --dev --dry-run --fail-fast --global --group --help --lockfile --no-default --no-editable --no-isolation --no-self --only-keep --production --project --quiet --reinstall --skip --venv --verbose --without"
            ;;

            (update)
            opts="--config-setting --dev --fail-fast --frozen-lockfile --global --group --help --lockfile --no-default --no-editable --no-isolation --no-self --no-sync --outdated --prerelease --production --project --quiet --save-compatible --save-exact --save-minimum --save-wildcard --skip --stable --top --unconstrained --update-all --update-eager --update-reuse --update-reuse-installed --venv --verbose --without"
            ;;

            (use)
            opts="--first --global --help --ignore-remembered --project --quiet --skip --venv --verbose"
            ;;

            (venv)
            opts="--help --path --project --python"
            ;;

        esac

        COMPREPLY=($(compgen -W "${opts}" -- ${cur}))
        __ltrim_colon_completions "$cur"

        return 0;
    fi

    # completing for a command
    if [[ $cur == $com ]]; then
        coms="add build cache completion config export fix import info init install list lock outdated plugin publish py python remove run search self show sync update use venv"

        COMPREPLY=($(compgen -W "${coms}" -- ${cur}))
        __ltrim_colon_completions "$cur"

        return 0
    fi
}

complete -o default -F _pdm_a919b69078acdf0a_complete pdm
