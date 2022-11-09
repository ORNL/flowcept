import yaml
from flowcept.commons.configs import SETTINGS_PATH
from flowcept.commons.common_classes import MQSettings, KeyValuesToFilter


def get_mq_settings(setting_name) -> MQSettings:
    with open(SETTINGS_PATH) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    settings = data['plugins'][setting_name]
    mq_settings = MQSettings(**settings)
    mq_settings.key_values_to_filter = [KeyValuesToFilter(**item) for item
                                        in mq_settings.key_values_to_filter]
    return mq_settings



