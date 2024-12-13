import re

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
