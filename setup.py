from sys import platform
from setuptools import setup, find_packages

from flowcept import __version__
from flowcept.configs import PROJECT_NAME

with open("README.md") as fh:
    long_description = fh.read()


def get_requirements(file_path):
    with open(file_path) as f:
        requirements = []
        for line in f.read().splitlines():
            if not line.startswith("#"):
                requirements.append(line)
    return requirements


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

MAC_REQUIRES = []

extras_requires = dict()
for req in _EXTRA_REQUIREMENTS:
    if req in MAC_REQUIRES and platform == "darwin":
        req_path = f"extra_requirements/{req}-requirements-mac.txt"
    else:
        req_path = f"extra_requirements/{req}-requirements.txt"
    extras_requires[req] = get_requirements(req_path)
    full_requirements.extend(extras_requires[req])

extras_requires["full"] = full_requirements

setup(
    name=PROJECT_NAME,
    version=__version__,
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
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Natural Language :: English",
        "Topic :: Documentation :: Sphinx",
        "Topic :: System :: Distributed Computing",
    ],
    python_requires=">=3.10",  # TODO: Do we really need py3.10?
    # scripts=["bin/flowcept"],
)
