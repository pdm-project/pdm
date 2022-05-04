# Benchmark

## Run the benchmarking script

```bash
pdm run benchmark
```

## Benchmark results

### Environment

GitHub Actions Ubuntu 21.04 virtual environment(2C8G).

### Base dependency set

(The format varies on different tools.)

```
requests @ git+https://github.com/psf/requests.git@v2.25.0  # a VCS dependency
pandas>=1.2.5,<2  # a package with heavy prebuilt binaries
pytest~=5.2   # a package with many child dependencies
```

### Result

(The time elapse is not averaged over multiple runs. One may expect some differences between runs.)

<script src="https://code.highcharts.com/highcharts.js"></script>
<script src="https://code.highcharts.com/modules/accessibility.js"></script>

<figure class="highcharts-figure">
    <div id="container"></div>
</figure>

<script>
Highcharts.chart('container', {
    chart: {
        type: 'column'
    },
    title: {
        text: 'Benchmark'
    },
    xAxis: {
        categories: [
            'Lock',
            'Lock+cache',
            'Install',
            'Add',
            'Add+cache'
        ],
        crosshair: true
    },
    yAxis: {
        min: 0,
        title: {
            text: 'Time (s)'
        }
    },
    tooltip: {
        headerFormat: '<span style="font-size:10px">{point.key}</span><table>',
        pointFormat: '<tr><td style="color:{series.color};padding:0">{series.name}: </td>' +
            '<td style="padding:0"><b>{point.y:.1f}s</b></td></tr>',
        footerFormat: '</table>',
        shared: true,
        useHTML: true
    },
    plotOptions: {
        column: {
            pointPadding: 0.2,
            borderWidth: 0
        }
    },
    series: [{
        name: 'Pipenv',
        data: [46.43, 55.81, 25.16, 84.44, 83.33]

    }, {
        name: 'Poetry',
        data: [76.95, 39.08, 17.82, 37.24, 43.90]

    }, {
        name: 'PDM',
        data: [27.56, 21.91, 12.16, 37.26, 26.84]

    }]
});
</script>

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
Running benchmark: Python Development Manager (PDM), version 1.11.2
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
