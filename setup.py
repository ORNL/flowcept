from setuptools import setup, find_packages

from flowcept import __version__
from flowcept.configs import PROJECT_NAME

with open("README.md") as fh:
    long_description = fh.read()

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

with open("extra_requirements/zambeze-requirements.txt") as f:
    zambeze_plugin_requirements = f.read().splitlines()

with open("extra_requirements/mlflow-requirements.txt") as f:
    mlflow_plugin_requirements = f.read().splitlines()

full_requirements = (
    requirements + zambeze_plugin_requirements + mlflow_plugin_requirements
)

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
    extras_require={
        "full": full_requirements,
        "mlflow": mlflow_plugin_requirements,
        "zambeze": zambeze_plugin_requirements,
    },
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
    python_requires=">=3.9",  # TODO: try a lower version
    # scripts=["bin/flowcept"],
)
