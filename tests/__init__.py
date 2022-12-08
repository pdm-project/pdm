from pathlib import Path

import packaging
from packaging.version import Version

FIXTURES = Path(__file__).parent / "fixtures"
PACKAGING_22 = Version(packaging.__version__) >= Version("22.0")
