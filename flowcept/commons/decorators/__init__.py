def singleton(cls):
    instances = {}

    class SingletonWrapper(cls):
        def __new__(cls, *args, **kwargs):
            if cls not in instances:
                instances[cls] = super().__new__(cls)
            return instances[cls]

    return SingletonWrapper
