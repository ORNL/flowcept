import shap
import numpy as np
from torch import nn

from flowcept.commons.utils import replace_non_serializable
from flowcept.configs import REPLACE_NON_JSON_SERIALIZABLE


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


def _inspect_inner_modules(model, modules_dict={}, in_named=None):
    if not isinstance(model, nn.Module):
        return
    key = f"{model.__class__.__name__}_{id(model)}"
    modules_dict[key] = {
        "type": model.__class__.__name__,
    }
    if in_named is not None:
        modules_dict[key]["in_named"] = in_named
    modules_dict[key].update(
        {k: v for k, v in model.__dict__.items() if not k.startswith("_")}
    )
    for name, module in model.named_children():
        if isinstance(module, nn.Module):
            _inspect_inner_modules(module, modules_dict, in_named=name)
    return modules_dict


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
            nparams = 0
            max_width = -1
            for p in model.parameters():
                m = np.max(p.shape)
                nparams += p.numel()
                if m > max_width:
                    max_width = m

            modules = _inspect_inner_modules(model)
            if REPLACE_NON_JSON_SERIALIZABLE:
                modules = replace_non_serializable(modules)

            # TODO: :ml-refactor: create a dataclass
            this_result = {
                "params": nparams,
                "max_width": int(max_width),
                "n_modules": len(modules),
                "modules": modules,
                "model_repr": repr(model),
            }
            if name is not None:
                this_result["name"] = name
            ret = {}
            if not isinstance(result, dict):
                ret["result"] = result
            else:
                ret = result
            if "responsible_ai_metrics" not in ret:
                ret["responsible_ai_metrics"] = {}
            ret["responsible_ai_metrics"].update(this_result)

            return ret

        return wrapper

    return decorator
