# CLI Reference

```python exec="true"
import argparse
from pdm.core import Core

parser = Core().parser


def render_parser(
    parser: argparse.ArgumentParser, title: str, heading_level: int = 2
) -> str:
    """Render the parser help documents as a string."""
    result = [f"{'#' * heading_level} {title}\n"]
    if parser.description:
        result.append("> " + parser.description + "\n")

    for group in sorted(
        parser._action_groups, key=lambda g: g.title.lower(), reverse=True
    ):
        if not any(
            bool(action.option_strings or action.dest)
            or isinstance(action, argparse._SubParsersAction)
            for action in group._group_actions
        ):
            continue

        result.append(f"{group.title.title()}:\n")
        for action in group._group_actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, subparser in action._name_parser_map.items():
                    result.append(render_parser(subparser, name, heading_level + 1))
                continue

            opts = [f"`{opt}`" for opt in action.option_strings]
            if not opts:
                line = f"- `{action.dest}`"
            else:
                line = f"- {', '.join(opts)}"
            if action.metavar:
                line += f" `{action.metavar}`"
            line += f": {action.help}"
            if action.default and action.default != argparse.SUPPRESS:
                line += f"(default: `{action.default}`)"
            result.append(line)
        result.append("")

    return "\n".join(result)


print(render_parser(parser, "pdm"))
```
