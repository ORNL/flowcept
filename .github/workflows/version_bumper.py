import re

version_file_path = "flowcept/version.py"
with open(version_file_path) as f:
    exec(f.read())
    version = locals()["__version__"]

# BRANCH_NAME = os.getenv("BRANCH_NAME", "dev")
# print("Branch Name: " + BRANCH_NAME)

split_version = version.split(".")
old_patch_str = split_version[2]
re_found = re.findall(r"(\d+)(.*)", old_patch_str)[0]
old_patch_number = re_found[0]
# old_branch = re_found[1]

new_patch_str = old_patch_str.replace(
    old_patch_number, str(int(old_patch_number) + 1)
)

split_version[2] = new_patch_str
new_version = ".".join(split_version)

print("New version: " + new_version)

with open(version_file_path, "w") as f:
    f.write(
        f"""# WARNING: CHANGE THIS FILE MANUALLY ONLY TO RESOLVE CONFLICTS!
# This file is supposed to be automatically modified by the CI Bot.
# The expected format is: <Major>.<Minor>.<Patch>
# See .github/workflows/version_bumper.py
__version__ = "{new_version}"
"""
    )

