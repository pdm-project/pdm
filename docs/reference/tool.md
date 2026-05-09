# `[tool.pdm]`

<style>
/* Temporary hack pending guidance to show compact summary tables without double-displaying each attribute */
.doc-class .doc-children {
  display: none;
}
</style>

::: pdm.project.project_file.ToolPDMTable
    options:
      heading: "[tool.pdm]"
      toc_label: "[tool.pdm]"
      heading_level: 2
      show_bases: false
      show_root_heading: true
      show_root_toc_entry: true
      show_source: false
      show_if_no_docstring: true
      summary:
        attributes: true

::: pdm.project.project_file.BuildTable
    options:
      heading: "[tool.pdm.build]"
      toc_label: "[tool.pdm.build]"
      heading_level: 2
      show_bases: false
      show_root_heading: true
      show_root_toc_entry: true
      show_source: false
      show_if_no_docstring: true
      summary:
        attributes: true

(placeholder pending figuring out rendering docs for functional form typeddicts)

::: pdm.project.project_file.OptionsTable
    options:
      heading: "[tool.pdm.options]"
      toc_label: "[tool.pdm.options]"
      heading_level: 2
      show_bases: false
      show_root_heading: true
      show_root_toc_entry: true
      show_source: false
      show_if_no_docstring: true
      summary:
        attributes: true

::: pdm.project.project_file.ResolutionTable
    options:
      heading: "[tool.pdm.resolution]"
      toc_label: "[tool.pdm.resolution]"
      heading_level: 2
      show_bases: false
      show_root_heading: true
      show_root_toc_entry: true
      show_source: false
      show_if_no_docstring: true
      summary:
        attributes: true

(placeholder pending figuring out rendering docs for functional form typeddicts)

::: pdm.project.project_file.UserScript
    options:
      heading: "[tool.pdm.scripts]"
      toc_label: "[tool.pdm.scripts]"
      heading_level: 2
      show_bases: false
      show_root_heading: true
      show_root_toc_entry: true
      show_source: false
      show_if_no_docstring: true
      summary:
        attributes: true

::: pdm.project.project_file.SourceTable
    options:
      heading: "[[tool.pdm.source]]"
      toc_label: "[[tool.pdm.source]]"
      heading_level: 2
      show_bases: false
      show_root_heading: true
      show_root_toc_entry: true
      show_source: false
      show_if_no_docstring: true
      summary:
        attributes: true

::: pdm.project.project_file.VersionTable
    options:
      heading: "[tool.pdm.version]"
      toc_label: "[tool.pdm.version]"
      heading_level: 2
      show_bases: false
      show_root_heading: true
      show_root_toc_entry: true
      show_source: false
      show_if_no_docstring: true
      summary:
        attributes: true

## Functional TypedDicts

::: pdm.project.project_file
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_source: false
      heading_level: 3
      group_by_category: false
      show_bases: false
      show_if_no_docstring: true
      show_labels: false
      show_signature_annotations: true
      signature_crossrefs: true
      members:
      - BuildTable
      - ResolutionTable