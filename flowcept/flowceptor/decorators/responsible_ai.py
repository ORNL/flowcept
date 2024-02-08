import shap
from thop import profile
import numpy as np
from time import time


def model_explainer(background_size=100, test_data_size=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            error_format_msg = (
                "You must return a dict in the form:"
                " {'model': model,"
                " 'test_data': test_data}"
            )
            if type(result) != dict:
                raise Exception(error_format_msg)
            model = result.get("model", None)
            test_data = result.get("test_data", None)

            if model is None or test_data is None:
                raise Exception(error_format_msg)
            if not hasattr(test_data, "__getitem__"):
                raise Exception("Test_data must be subscriptable.")

            background = test_data[:background_size]
            test_images = test_data[background_size:test_data_size]

            e = shap.DeepExplainer(model, background)
            shap_values = e.shap_values(test_images)
            # result["shap_values"] = shap_values
            if "responsible_ai_metrics" not in result:
                result["responsible_ai_metrics"] = {}
            result["responsible_ai_metrics"]["shap_sum"] = float(
                np.sum(np.concatenate(shap_values))
            )
            return result

        return wrapper

    return decorator


def model_profiler(name=None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            error_format_msg = (
                "You must return a dict in the form:"
                " {'model': model,"
                " 'test_data': test_data}"
            )
            if type(result) != dict:
                raise Exception(error_format_msg)
            model = result.pop("model", None)
            test_data = result.pop("test_data", None)

            flops, params = profile(model, inputs=(test_data,))
            fully_connected_layers = model.fc_layers
            convolutional_layers = model.conv_layers
            n_fc_layers = len(fully_connected_layers)
            n_cv_layers = len(convolutional_layers)
            depth = n_fc_layers + n_cv_layers
            max_width = -1
            for p in model.parameters():
                m = np.max(p.shape)
                if m > max_width:
                    max_width = m

            # TODO: create a class
            this_result = {
                "flops": int(flops),
                "params": int(params),
                "max_width": int(max_width),
                "depth": int(depth),
                "n_fc_layers": int(n_fc_layers),
                "n_cv_layers": int(n_cv_layers),
                "convolutional_layers": str(convolutional_layers),
                "fully_connected_layers": str(fully_connected_layers),
            }
            if name is not None:
                this_result["name"] = name
            if "responsible_ai_metrics" not in result:
                result["responsible_ai_metrics"] = {}
            result["responsible_ai_metrics"].update(this_result)
            return result

        return wrapper

    return decorator
