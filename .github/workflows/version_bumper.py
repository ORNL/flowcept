# This script ensures consistent and automatic version updates across the project.
#
# We often forget to manually update the version string in all the necessary places,
# especially during merges to the main branch. To avoid human error and ensure
# systematic versioning, we run this script as part of our main branch merge process in the CI.
#
# It performs the following:
# - Reads the current version from src/flowcept/version.py
# - Increments the patch number (e.g., 0.1.4 -> 0.1.5)
# - Updates version.py with the new version
# - Reads the current flowcept_version from resources/sample_settings.yaml
# - Replaces the old version with the new one using simple string replacement (not YAML dumping)
#
# This guarantees that both source code and configuration files remain synchronized with respect to versioning.


import re
import yaml

version_file_path = "src/flowcept/version.py"
with open(version_file_path) as f:
    code_str = f.read()
    exec(code_str)
    version = locals()["__version__"]

split_version = version.split(".")
old_patch_str = split_version[2]
re_found = re.findall(r"(\d+)(.*)", old_patch_str)[0]
old_patch_number = re_found[0]

new_patch_str = old_patch_str.replace(old_patch_number, str(int(old_patch_number) + 1))

split_version[2] = new_patch_str
new_version = ".".join(split_version)

print("New version: " + new_version)
new_code_str = code_str.replace(version, new_version)

with open(version_file_path, "w") as f:
    f.write(new_code_str)

yaml_file_path = "resources/sample_settings.yaml"
with open(yaml_file_path) as f:
    yaml_data = yaml.safe_load(f)
    old_yaml_version = yaml_data.get("flowcept_version")

# Replace the old version string with the new one using str.replace()
with open(yaml_file_path) as f:
    yaml_text = f.read()

new_yaml_text = yaml_text.replace(f"flowcept_version: {old_yaml_version}", f"flowcept_version: {new_version}")

with open(yaml_file_path, "w") as f:
    f.write(new_yaml_text)
