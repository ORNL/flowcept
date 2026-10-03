"""Tests for the generic JSON encoder."""

import json
import unittest

import numpy as np

from flowcept.commons.utils import GenericJSONEncoder


class TestGenericJSONEncoder(unittest.TestCase):
    """Tests the encoder used for captured task arguments and results."""

    def test_numpy_scalars_keep_their_numeric_type(self):
        """numpy integers and floats serialise as numbers, not strings."""
        encoded = json.loads(
            json.dumps(
                {"count": np.int64(5), "small": np.int32(7), "ratio": np.float64(1.5)},
                cls=GenericJSONEncoder,
            )
        )
        self.assertEqual(encoded, {"count": 5, "small": 7, "ratio": 1.5})
        self.assertIsInstance(encoded["count"], int)
        self.assertIsInstance(encoded["small"], int)
        self.assertIsInstance(encoded["ratio"], float)
