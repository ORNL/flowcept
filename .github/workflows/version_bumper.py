import os
import re
from git import Repo
from flowcept.configs import PROJECT_DIR_PATH, SRC_DIR_PATH
from flowcept.version import __version__

version_file_path = os.path.join(SRC_DIR_PATH, "version.py")
local_repo = Repo(path=PROJECT_DIR_PATH)
local_branch = local_repo.active_branch.name

regex = (
    r"(0|(?:[1-9]\d*))(?:\.(0|(?:[1-9]\d*))(?:\.(0|(?:[1-9]\d*)))?"
    r"(?:\-([\w][\w\.\-_]*))?)?"
)

patch_number = int(re.findall(regex, __version__)[0][2])
new_version = re.sub(
    regex, r"\1.\2." + str(patch_number + 1) + f"-{local_branch}", __version__
)
print(f"New version: {new_version}")

with open(version_file_path, "w") as f:
    f.write(f'__version__ = "{new_version}"\n')
