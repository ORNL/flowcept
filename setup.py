from sys import platform
import os
from setuptools import setup, find_packages

with open("flowcept/version.py") as f:
    exec(f.read())
    version = locals()["__version__"]

with open("README.md") as fh:
    long_description = fh.read()


def get_requirements(file_path):
    with open(file_path) as f:
        _requirements = []
        for line in f.read().splitlines():
            if not line.startswith("#"):
                _requirements.append(line)
    return _requirements


requirements = get_requirements("requirements.txt")
full_requirements = requirements

# We don't install dev requirements in the user lib.
_EXTRA_REQUIREMENTS = [
    "zambeze",
    "mlflow",
    "tensorboard",
    "mongo",
    "dask",
    "webserver",
]

MAC_REQUIRES = ["tensorboard"]

extras_requires = dict()
for req in _EXTRA_REQUIREMENTS:
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
    extras_requires[req] = get_requirements(req_path)
    full_requirements.extend(extras_requires[req])

extras_requires["full"] = full_requirements

setup(
    name="flowcept",
    version=version,
    license="MIT",
    author="Oak Ridge National Laboratory",
    author_email="support@flowcept.org",
    description="A tool to intercept dataflows",  # TODO: change later
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ORNL/flowcept",
    include_package_data=True,
    install_requires=requirements,
    extras_require=extras_requires,
    packages=find_packages(),
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.8",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Natural Language :: English",
        # "Topic :: Documentation :: Sphinx",
        "Topic :: System :: Distributed Computing",
    ],
    python_requires=">=3.8",
    # scripts=["bin/flowcept"],
)
