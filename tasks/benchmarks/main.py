import os
import shutil

from utils import Executor, benchmark, project


@project(os.getenv("PIPENV", "pipenv"), "Pipfile")
def run_pipenv(executor: Executor):
    cache_dir = executor.project_file.with_name(".cache")
    os.environ["PIPENV_CACHE_DIR"] = str(cache_dir)
    executor.measure("Lock dependencies without cache", ["lock"])
    executor.measure("Lock dependencies with cache", ["lock"])
    executor.measure("Install dependencies", ["install", "--dev"])
    executor.measure(
        "Add dependencies with cache", ["install", "--keep-outdated", "click"]
    )
    shutil.rmtree(cache_dir)
    executor.measure(
        "Add dependencies without cache", ["install", "--keep-outdated", "pytz"]
    )


@project(os.getenv("POETRY", "poetry"), "pyproject.poetry.toml")
def run_poetry(executor: Executor):
    cache_dir = executor.project_file.with_name(".cache")
    executor.run(["config", "--local", "cache-dir", str(cache_dir)])
    executor.measure("Lock dependencies without cache", ["lock"])
    executor.measure("Lock dependencies with cache", ["lock"])
    executor.measure("Install dependencies", ["install"])
    executor.measure("Add dependencies with cache", ["add", "click"])
    shutil.rmtree(cache_dir)
    executor.measure("Add dependencies without cache", ["add", "pytz"])


@project(os.getenv("PDM", "pdm"), "pyproject.pdm.toml")
def run_pdm(executor: Executor):
    cache_dir = executor.project_file.with_name(".cache")
    executor.run(["config", "cache_dir", str(cache_dir)])
    executor.measure("Lock dependencies without cache", ["lock"])
    executor.measure("Lock dependencies with cache", ["lock"])
    executor.measure("Install dependencies", ["install"])
    executor.measure("Add dependencies with cache", ["add", "click"])
    shutil.rmtree(cache_dir)
    executor.measure("Add dependencies without cache", ["add", "pytz"])
    executor.run(["config", "--delete", "cache_dir"])


def main():
    benchmark(run_pipenv)
    benchmark(run_poetry)
    benchmark(run_pdm)


if __name__ == "__main__":
    main()
