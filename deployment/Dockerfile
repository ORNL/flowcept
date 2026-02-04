# Use the command `make build` to build this image.
# Use conda-forge base image consistently across local/CI.
FROM condaforge/miniforge3:23.11.0-0

WORKDIR /flowcept

COPY pyproject.toml Makefile README.md ./
COPY src ./src
COPY resources ./resources
COPY notebooks ./notebooks
COPY tests ./tests
COPY examples ./examples

RUN export FLOWCEPT_SETTINGS_PATH=$(realpath resources/sample_settings.yaml) \
    && echo "export FLOWCEPT_SETTINGS_PATH=$FLOWCEPT_SETTINGS_PATH" >> ~/.bashrc

RUN conda create -n flowcept python=3.11.10 -y \
    && echo "conda activate flowcept" >> ~/.bashrc

# The following command is an overkill and will install many things you might not need. Please modify this Dockerfile in case you do not need to install "all" dependencies.
RUN conda run -n flowcept pip install -e .[all]

CMD ["bash"]
