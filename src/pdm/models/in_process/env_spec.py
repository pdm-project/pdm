import json
import os
import site

pdm_libs = os.getenv("PDM_LIBS")
if pdm_libs:
    site.addsitedir(pdm_libs)


def get_current_env_spec():
    from dep_logic.tags import EnvSpec

    return EnvSpec.current().as_dict()


if __name__ == "__main__":
    print(json.dumps(get_current_env_spec(), indent=2))
