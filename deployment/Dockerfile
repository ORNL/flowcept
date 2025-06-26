# Use the command `make build` to build this image.
FROM miniconda:local

RUN apt-get update && \
    apt-get install -y vim curl wget make patch gcc \
    && rm -rf /var/lib/apt/lists/*

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
