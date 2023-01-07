from setuptools import setup, find_packages

from flowcept import __version__
from flowcept.configs import PROJECT_NAME

with open("README.md") as fh:
    long_description = fh.read()

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

full_requirements = requirements

_EXTRA_REQUIREMENTS = [
    "zambeze",
    "mlflow",
    "tensorboard",
    "mongo",
    "dask"
]

extras_requires = dict()
for req in _EXTRA_REQUIREMENTS:
    with open(f"extra_requirements/{req}-requirements.txt") as f:
        extras_requires[req] = f.read().splitlines()
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
    python_requires=">=3.9",  # TODO: Do we really need py3.9?
    # scripts=["bin/flowcept"],
)
