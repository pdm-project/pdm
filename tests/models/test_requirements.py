import pytest

from pdm.models.requirements import Requirement

REQUIREMENTS = [
    ("requests", ("requests", "*")),
    ("requests<2.21.0,>=2.20.0", ("requests", "<2.21.0,>=2.20.0")),
    (
        'requests==2.19.0;os_name == "nt"',
        ("requests", {"version": "==2.19.0", "marker": 'os_name == "nt"'}),
    ),
    (
        'requests[security,tests]==2.8.*,>=2.8.1;python_version < "2.7"',
        (
            "requests",
            {
                "version": "==2.8.*,>=2.8.1",
                "marker": 'python_version < "2.7"',
                "extras": ["security", "tests"],
            },
        ),
    ),
    (
        "pip @ https://github.com/pypa/pip/archive/1.3.1.zip",
        ("pip", {"url": "https://github.com/pypa/pip/archive/1.3.1.zip"}),
    ),
    (
        "-e git+http://git.example.com/MyProject#egg=MyProject",
        ("MyProject", {"editable": True, "git": "http://git.example.com/MyProject"}),
    ),
    (
        "https://github.com/pypa/pip/archive/1.3.1.zip",
        (None, {"url": "https://github.com/pypa/pip/archive/1.3.1.zip"}),
    ),
    ("./models", (None, {"path": "./models"})),
    ("./myproject.whl", (None, {"path": "./myproject.whl"})),
]


@pytest.mark.parametrize("req, req_dict", REQUIREMENTS)
def test_convert_req_dict_to_req_line(req, req_dict):
    r = Requirement.from_line(req)
    assert r.as_req_dict() == req_dict
    r = Requirement.from_req_dict(*req_dict)
    assert r.as_line() == req
