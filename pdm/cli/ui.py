import crayons
from click._compat import term_len
from click.formatting import iter_rows, HelpFormatter, measure_table, wrap_text


class ColoredHelpFormatter(HelpFormatter):
    """Click does not provide possibility to replace the inner formatter class
    easily, we have to use monkey patch technique.
    """

    def write_heading(self, heading):
        super().write_heading(crayons.yellow(heading, bold=True))

    def write_dl(self, rows, col_max=30, col_spacing=2):
        rows = list(rows)
        widths = measure_table(rows)
        if len(widths) != 2:
            raise TypeError("Expected two columns for definition list")

        first_col = min(widths[0], col_max) + col_spacing

        for first, second in iter_rows(rows, len(widths)):
            self.write("%*s%s" % (self.current_indent, "", crayons.cyan(first)))
            if not second:
                self.write("\n")
                continue
            if term_len(first) <= first_col - col_spacing:
                self.write(" " * (first_col - term_len(first)))
            else:
                self.write("\n")
                self.write(" " * (first_col + self.current_indent))

            text_width = max(self.width - first_col - 2, 10)
            lines = iter(wrap_text(second, text_width).splitlines())
            if lines:
                self.write(next(lines) + "\n")
                for line in lines:
                    self.write("%*s%s\n" % (first_col + self.current_indent, "", line))
            else:
                self.write("\n")
