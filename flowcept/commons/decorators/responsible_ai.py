import shap
import numpy as np


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
                "You must return a dict in the form:" " {'model': model,"
            )
            if type(result) != dict:
                raise Exception(error_format_msg)
            model = result.pop("model", None)

            # TODO: :ml-refactor:
            if hasattr(model, "model_type"):
                model_type = str(model.model_type)
            elif hasattr(model, "type"):
                model_type = str(model.type)
            else:
                model_type = "unknown"

            nparams = 0
            max_width = -1
            for p in model.parameters():
                m = np.max(p.shape)
                nparams += p.numel()
                if m > max_width:
                    max_width = m

            n_layers = 0
            n_modules = 0
            modules = []
            for m in model.modules():
                n_modules += 1
                module_children = list(m.children())
                n_modules += len(module_children)
                n_layers += (
                    1 if len(module_children) == 0 else len(module_children)
                )  # TODO :ml-refactor: improve code
                module = {
                    "id": id(m),
                    "class": str(m.__class__.__name__),
                    "n_layers": 1
                    if len(module_children) == 0
                    else len(module_children),
                }
                modules.append(module)

            # fully_connected_layers = model.fc_layers
            # convolutional_layers = model.conv_layers
            # n_fc_layers = len(fully_connected_layers)
            # n_cv_layers = len(convolutional_layers)
            # depth = n_fc_layers + n_cv_layers

            # TODO: :ml-refactor: create a class; check for model.named_children
            this_result = {
                "params": nparams,
                "max_width": int(max_width),
                "n_modules": n_modules,
                "model_type": model_type,
                "modules": modules,
                "n_layers": n_layers,
                "model_repr": repr(model),
            }
            if name is not None:
                this_result["name"] = name
            if "responsible_ai_metrics" not in result:
                result["responsible_ai_metrics"] = {}
            result["responsible_ai_metrics"].update(this_result)
            return result

        return wrapper

    return decorator
