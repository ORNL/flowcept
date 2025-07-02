import json


class DynamicSchemaTracker:
    def __init__(self, max_examples=3, max_str_len=70):
        self.schema = {}  # {activity_id: {"i": [...], "o": [...]}}

        # {normalized_field: {"v": [...], "t": ..., "s": ..., "et": ...}}
        self.values = {}

        self.max_examples = max_examples
        self.max_str_len = max_str_len

    def _flatten_dict(self, d, parent_key='', sep='.'):
        """Flatten dictionary but preserve lists as single units."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def _truncate_if_needed(self, val):
        """Truncate if stringified length exceeds max_str_len."""
        try:
            s = json.dumps(val)
        except Exception:
            s = str(val)

        if len(s) > self.max_str_len:
            return s[:self.max_str_len] + '...'
        return val

    def _get_type(self, val):
        if isinstance(val, bool):
            return "bool"
        elif isinstance(val, int):
            return "int"
        elif isinstance(val, float):
            return "float"
        elif isinstance(val, list):
            return "list"
        else:
            return "str"

    def _get_shape(self, val):
        if not isinstance(val, list):
            return None
        shape = []
        while isinstance(val, list):
            shape.append(len(val))
            val = val[0] if val else []
        return shape

    def _get_list_element_type(self, val):
        if not isinstance(val, list):
            return None

        def describe(elem):
            if isinstance(elem, list):
                return f"list[{describe(elem[0])}]" if elem else "list[unknown]"
            elif isinstance(elem, dict):
                return "dict"
            elif isinstance(elem, bool):
                return "bool"
            elif isinstance(elem, int):
                return "int"
            elif isinstance(elem, float):
                return "float"
            elif isinstance(elem, str):
                return "str"
            else:
                return "unknown"

        return describe(val[0]) if val else "unknown"

    def _add_schema_field(self, activity_id, field_name, direction):
        key = "i" if direction == "used" else "o"
        if field_name not in self.schema[activity_id][key]:
            self.schema[activity_id][key].append(field_name)

    def _add_value_info(self, normalized_field, val):
        val_type = self._get_type(val)
        truncated_val = self._truncate_if_needed(val)

        entry = self.values.setdefault(normalized_field, {
            "v": [],
            "t": val_type
        })

        # Always reflect latest observed type
        entry["t"] = val_type

        if val_type == "list":
            entry["s"] = self._get_shape(val)
            entry["et"] = self._get_list_element_type(val)
        else:
            entry.pop("s", None)
            entry.pop("et", None)

        if truncated_val not in entry["v"]:
            entry["v"].append(truncated_val)

        if len(entry["v"]) > self.max_examples:
            entry["v"] = sorted(entry["v"], key=lambda x: str(x))[:self.max_examples]

    def update_with_tasks(self, tasks):
        for task in tasks:
            activity = task.get("activity_id")
            if activity not in self.schema:
                self.schema[activity] = {"i": [], "o": []}

            for direction in ["used", "generated"]:
                data = task.get(direction, {})
                flat_data = self._flatten_dict(data)
                for field, val in flat_data.items():
                    prefixed_field = f"{direction}.{field}"
                    normalized_field = field  # role-agnostic key for value descriptions

                    self._add_schema_field(activity, prefixed_field, direction)
                    self._add_value_info(normalized_field, val)

    def get_schema(self):
        return self.schema  # fields with 'used.' or 'generated.' prefix

    def get_example_values(self):
        return self.values  # deduplicated field schemas
