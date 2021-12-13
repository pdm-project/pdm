# Benchmark

## Run the benchmarking script

```bash
pdm run benchmark
```

## Benchmark results

### Environment

GitHub Actions Ubuntu 21.04 virtual environment(2C8G).

### Base dependencie set

(The format varies on different tools.)

```
requests @ git+https://github.com/psf/requests.git@v2.25.0  # a VCS dependency
pandas>=1.2.5,<2  # a package with heavy prebuilt binaries
pytest~=5.2   # a package with many child dependencies
```

### Result

(The time elapse is not averaged over multiple runs. One may expect some differences between runs.)

![benchmark bar chart](/assets/benchmark.png)

```
Running benchmark: pipenv, version 2021.11.23
   Lock dependencies without cache: 46.43s
      Lock dependencies with cache: 55.81s
              Install dependencies: 25.16s
       Add dependencies with cache: 83.33s
    Add dependencies without cache: 84.44s
Running benchmark: Poetry version 1.1.12
   Lock dependencies without cache: 76.95s
      Lock dependencies with cache: 39.08s
              Install dependencies: 17.82s
       Add dependencies with cache: 43.90s
    Add dependencies without cache: 37.24s
Running benchmark: Python Development Master (PDM), version 1.11.2
   Lock dependencies without cache: 27.56s
      Lock dependencies with cache: 21.91s
              Install dependencies: 12.16s
       Add dependencies with cache: 26.84s
    Add dependencies without cache: 37.26s
```

Comments:

1. `Install Dependencies` is to sync the working set with the lock file.
2. `Add Dependencies` is to add the dependencies to the working set and existing lock file.
   Poetry's command is `poetry add`, Pipenv's command is `pipenv install --keep-outdated` and
   PDM's command is `pdm add`
