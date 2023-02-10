content = ""
with open("dask.ipynb") as f:
    content = f.read()
    content = content.replace(
        '"execution_count": null', '"execution_count": "null"'
    )

with open("dask.ipynb", "w") as f:
    f.write(content)
