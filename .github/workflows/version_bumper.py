import os
import re

from flowcept.version import __version__
from flowcept.configs import SRC_DIR_PATH

version_file_path = os.path.join(SRC_DIR_PATH, "version.py")

BRANCH_NAME = os.getenv("BRANCH_NAME", "dev")
print(BRANCH_NAME)

regex = (
    r"(0|(?:[1-9]\d*))(?:\.(0|(?:[1-9]\d*))(?:\.(0|(?:[1-9]\d*)))?"
    r"(?:\-([\w][\w\.\-_]*))?)?"
)

patch_number = int(re.findall(regex, __version__)[0][2])
new_version = re.sub(
    regex, r"\1.\2." + str(patch_number + 1) + f"-{BRANCH_NAME}", __version__
)
print(f"New version: {new_version}")

with open(version_file_path, "w") as f:
    f.write(
        f"""# WARNING: CHANGE THIS FILE MANUALLY ONLY TO RESOLVE CONFLICTS!
# This file is supposed to be automatically modified by the CI Bot.
# See .github/workflows/version_bumper.py
__version__ = "{new_version}"
"""
    )
