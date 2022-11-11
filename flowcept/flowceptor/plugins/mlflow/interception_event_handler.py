from watchdog.events import LoggingEventHandler


class InterceptionEventHandler(LoggingEventHandler):
    def __init__(self, interceptor_instance, callback_function):
        super().__init__()
        self.callback_function = callback_function
        self.interceptor_instance = interceptor_instance

    def on_modified(self, event):
        self.callback_function(self.interceptor_instance)
