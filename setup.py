from sys import platform
import os
import re
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


requirements = get_requirements("requirements.txt")
full_requirements = requirements.copy()

# We don't install dev requirements in the user lib.
extras_requirement_keys = [
    "zambeze",
    "mlflow",
    "tensorboard",
    "mongo",
    "dask",
    "webserver",
]

MAC_REQUIRES = ["tensorboard"]
extras_require = dict()
for req in extras_requirement_keys:
    if req in MAC_REQUIRES and platform == "darwin":
        req_path = f"extra_requirements/{req}-requirements-mac.txt"
        # These env vars are needed to install tensorflow on mac
        # (at least on m1 chip)
        # (because of the grpcio package). See:
        # https://stackoverflow.com/questions/66640705/how-can-i-install-grpcio-on-an-apple-m1-silicon-laptop
        os.environ["GRPC_PYTHON_BUILD_SYSTEM_OPENSSL"] = "1"
        os.environ["GRPC_PYTHON_BUILD_SYSTEM_ZLIB"] = "1"
    else:
        req_path = f"extra_requirements/{req}-requirements.txt"
    _requirements = get_requirements(req_path)
    extras_require[req] = _requirements
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
]

short_description, long_description = get_descriptions()


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
    packages=find_packages(),
    keywords=keywords,
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.8",
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
    # scripts=["bin/flowcept"],
)
