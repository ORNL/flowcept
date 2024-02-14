import os
import re
import shutil
from setuptools import setup, find_packages


PROJECT_NAME = os.getenv("PROJECT_NAME", "flowcept")

with open("flowcept/version.py") as f:
    exec(f.read())
    version = locals()["__version__"]


def get_descriptions():
    with open("README.md") as f:
        readme_content = f.read()

    pattern = r"# {}\s*?\n\n(.+?)\n\n".format(re.escape(PROJECT_NAME))
    match = re.search(pattern, readme_content, re.DOTALL | re.IGNORECASE)

    if match:
        _short_description = match.group(1)
        _short_description = _short_description.strip().replace("\n", "")
        return _short_description, readme_content
    else:
        raise Exception("Could not find a match for the description!")


def get_requirements(file_path):
    with open(file_path) as f:
        __requirements = []
        for line in f.read().splitlines():
            if not line.startswith("#"):
                __requirements.append(line)
    return __requirements


def create_settings_file():
    directory_path = os.path.expanduser(f"~/.{PROJECT_NAME}")
    os.makedirs(directory_path, exist_ok=True)
    source_file = "resources/sample_settings.yaml"
    destination_file = os.path.join(directory_path, "settings.yaml")
    shutil.copyfile(source_file, destination_file)
    print(f"Copied settings file to {destination_file}")


requirements = get_requirements("requirements.txt")
full_requirements = requirements.copy()

# We don't install dev requirements in the user lib.
extras_requirement_keys = [
    "zambeze",
    "mlflow",
    "tensorboard",
    "dask",
    "nvidia",
    "amd",
    "analytics",
    "responsible_ai",
    "data_augmentation",
]

skip_full = {"amd", "nvidia"}

extras_require = dict()
for req in extras_requirement_keys:
    req_path = f"extra_requirements/{req}-requirements.txt"
    _requirements = get_requirements(req_path)
    extras_require[req] = _requirements
    if req not in skip_full:
        full_requirements.extend(_requirements)


extras_require["full"] = full_requirements

keywords = [
    "ai",
    "ml",
    "machine-learning",
    "provenance",
    "lineage",
    "responsible-ai",
    "databases",
    "big-data",
    "provenance",
    "tensorboard",
    "data-integration",
    "scientific-workflows",
    "dask",
    "reproducibility",
    "workflows",
    "parallel-processing",
    "lineage",
    "model-management",
    "mlflow",
    "responsible-ai",
    "data-analytics",
]

short_description, long_description = get_descriptions()

create_settings_file()

setup(
    name=PROJECT_NAME,
    version=version,
    license="MIT",
    author="Oak Ridge National Laboratory",
    # author_email="support@flowcept.org",
    description=short_description,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ORNL/flowcept",
    include_package_data=True,
    install_requires=requirements,
    extras_require=extras_require,
    packages=find_packages(exclude=("tests", "notebooks", "deployment")),
    keywords=keywords,
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Natural Language :: English",
        # "Topic :: Documentation :: Sphinx",
        "Topic :: System :: Distributed Computing",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: System :: Logging",
        "Topic :: System :: Monitoring",
        "Topic :: Database",
    ],
    python_requires=">=3.8",
)
