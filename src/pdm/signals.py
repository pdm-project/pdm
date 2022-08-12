"""
The signal definition for PDM.

Example:
    ```python
    from pdm.signals import post_init, post_install

    def on_post_init(project):
        project.core.ui.echo("Project initialized")
    # Connect to the signal
    post_init.connect(on_post_init)
    # Or use as a decorator
    @post_install.connect
    def on_post_install(project, candidates, dry_run):
        project.core.ui.echo("Project install succeeded")
    ```
"""
from blinker import NamedSignal, Namespace

pdm_signals = Namespace()

post_init: NamedSignal = pdm_signals.signal("post_init")
"""Called after a project is initialized.
Args:
    project (Project): The project object
"""
pre_lock: NamedSignal = pdm_signals.signal("pre_lock")
"""Called before a project is locked.
Args:
    project (Project): The project object
    requirements (list[Requirement]): The requirements to lock
    dry_run (bool): If true, won't perform any actions
"""
post_lock: NamedSignal = pdm_signals.signal("post_lock")
"""Called after a project is locked.

Args:
    project (Project): The project object
    resolution (dict[str, Candidate]): The resolved candidates
    dry_run (bool): If true, won't perform any actions
"""
pre_install: NamedSignal = pdm_signals.signal("pre_install")
"""Called before a project is installed.

Args:
    project (Project): The project object
    candidates (dict[str, Candidate]): The candidates to install
    dry_run (bool): If true, won't perform any actions
"""
post_install: NamedSignal = pdm_signals.signal("post_install")
"""Called after a project is installed.

Args:
    project (Project): The project object
    candidates (dict[str, Candidate]): The candidates installed
    dry_run (bool): If true, won't perform any actions
"""
pre_build: NamedSignal = pdm_signals.signal("pre_build")
"""Called before a project is built.

Args:
    project (Project): The project object
    dest (str): The destination location
    config_settings (dict[str, str]|None): Additional config settings passed via args
"""
post_build: NamedSignal = pdm_signals.signal("post_build")
"""Called after a project is built.

Args:
    project (Project): The project object
    artifacts (Sequence[str]): The locations of built artifacts
    config_settings (dict[str, str]|None): Additional config settings passed via args
"""
pre_publish: NamedSignal = pdm_signals.signal("pre_publish")
"""Called before a project is published.

Args:
    project (Project): The project object
"""
post_publish: NamedSignal = pdm_signals.signal("post_publish")
"""Called after a project is published.

Args:
    project (Project): The project object
"""
pre_run: NamedSignal = pdm_signals.signal("pre_run")
"""Called before any run.

Args:
    project (Project): The project object
    script (str): the script name
    args (Sequence[str]): the command line provided arguments
"""
post_run: NamedSignal = pdm_signals.signal("post_run")
"""Called after any run.

Args:
    project (Project): The project object
    script (str): the script name
    args (Sequence[str]): the command line provided arguments
"""
pre_script: NamedSignal = pdm_signals.signal("pre_script")
"""Called before any script.

Args:
    project (Project): The project object
    script (str): the script name
    args (Sequence[str]): the command line provided arguments
"""
post_script: NamedSignal = pdm_signals.signal("post_script")
"""Called after any script.

Args:
    project (Project): The project object
    script (str): the script name
    args (Sequence[str]): the command line provided arguments
"""
post_use: NamedSignal = pdm_signals.signal("post_use")
"""Called after use switched to a new Python version.

Args:
    project (Project): The project object
    python (PythonInfo): Information about the new Python interpreter
"""
