import pika
import sys
import json
from flowcept.flowceptor.plugins.base_interceptor import (
    BaseInterceptor,
)


class ZambezeInterceptor(BaseInterceptor):
    def __init__(self, plugin_key="zambeze"):
        super().__init__(plugin_key)

    def intercept(self, message: dict):

        # TODO: make constants
        intercepted_message = {
            "application_msg": {},
        }
        for key in self.settings.keys_to_intercept:
            if key in message:
                intercepted_message["application_msg"][key] = message[key]

        super().post_intercept(intercepted_message)

    def observe(self):
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.settings.host, port=self.settings.port
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue=self.settings.queue_name)
        channel.basic_consume(
            queue=self.settings.queue_name,
            on_message_callback=self.callback,
            auto_ack=True,
        )

        print(" [*] Waiting for Zambeze messages. To exit press CTRL+C")
        channel.start_consuming()

    def callback(self, ch, method, properties, body):
        # TODO: consider making it a superclass method
        """
        function that decides what do to when a change is identified.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        body_obj = json.loads(body)

        for key_value in self.settings.key_values_to_filter:
            if key_value.key in body_obj:
                if body_obj[key_value.key] == key_value.value:
                    print(
                        f"I'm an interceptor and I need to intercept this:"
                        f"\n\t{json.dumps(body_obj)}"
                    )
                    self.intercept(message=body_obj)
                    break


if __name__ == "__main__":
    try:
        # TODO: allow passing the interceptor key in the argv
        interceptor = ZambezeInterceptor("zambeze1")
        interceptor.observe()
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
