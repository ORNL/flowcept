import json


class DynamicSchemaTracker:
    """
    DynamicSchemaTracker maintains and updates a dynamic schema of tasks,
    tracking both input and output fields along with example values and type
    information. It is designed to help build lightweight, evolving schemas
    from observed task executions.

    The tracker flattens nested structures, deduplicates fields, and captures
    examples of values (truncated when necessary) to provide insight into
    the shape and types of task data over time.

    Parameters
    ----------
    max_examples : int, default=3
        Maximum number of example values to store for each field.
    max_str_len : int, default=70
        Maximum string length for stored example values. Longer values are
        truncated with ellipsis.

    Attributes
    ----------
    schema : dict
        Maps activity IDs to dictionaries containing lists of input ("i")
        and output ("o") fields. Example:
        ``{"train_model": {"i": ["used.dataset"], "o": ["generated.metrics"]}}``.
    values : dict
        Maps normalized field names to metadata about their values, including:
        - ``v`` : list of example values (up to ``max_examples``).
        - ``t`` : type of the field ("int", "float", "list", "str", etc.).
        - ``s`` : shape of lists (if applicable).
        - ``et`` : element type for lists (if applicable).
    max_examples : int
        Maximum number of examples per field.
    max_str_len : int
        Maximum stored string length for example values.

    Methods
    -------
    update_with_tasks(tasks)
        Update the schema and value examples with a list of tasks.
    get_schema()
        Retrieve the current schema with prefixed "used." and "generated." fields.
    get_example_values()
        Retrieve deduplicated example values and type information for fields.

    Examples
    --------
    >>> tracker = DynamicSchemaTracker(max_examples=2, max_str_len=20)
    >>> tasks = [
    ...     {"activity_id": "task1",
    ...      "used": {"input": [1, 2, 3]},
    ...      "generated": {"output": {"score": 0.95}}}
    ... ]
    >>> tracker.update_with_tasks(tasks)
    >>> tracker.get_schema()
    {'task1': {'i': ['used.input'], 'o': ['generated.output.score']}}
    >>> tracker.get_example_values()
    {'input': {'v': [[1, 2, 3]], 't': 'list', 's': [3], 'et': 'int'},
     'output.score': {'v': [0.95], 't': 'float'}}
    """

    def __init__(self, max_examples=3, max_str_len=70):
        self.schema = {}  # {activity_id: {"i": [...], "o": [...]}}

        # {normalized_field: {"v": [...], "t": ..., "s": ..., "et": ...}}
        self.values = {}

        self.max_examples = max_examples
        self.max_str_len = max_str_len

    def _flatten_dict(self, d, parent_key="", sep="."):
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
            return s[: self.max_str_len] + "..."
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
            if not val:  # Empty list -> stop
                break
            val = val[0]
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

        entry = self.values.setdefault(normalized_field, {"v": [], "t": val_type})

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
            entry["v"] = sorted(entry["v"], key=lambda x: str(x))[: self.max_examples]

    def update_with_tasks(self, tasks):
        """Update the schema with tasks."""
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
        """Get the current schema."""
        return self.schema  # fields with 'used.' or 'generated.' prefix

    def get_example_values(self):
        """Get example values."""
        return self.values  # deduplicated field schemas
