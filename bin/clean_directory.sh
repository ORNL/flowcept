# Make sure you run this from the directory root
rm -rf  .pytest_cache \
        .build \
        .dist \
        build \
        dist \
        *egg* \
        mlruns \
        mlflow.db

rm -rf **/*mlruns*
rm -rf */*/*mlruns*
