import tomlkit


def check_fingerprint(filename):
    with open(filename, encoding="utf-8") as fp:
        data = tomlkit.parse(fp.read())

    return "tool" in data and "poetry" in data["tool"]
