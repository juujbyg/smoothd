"""PC tests for smoothd's bookkeeping: every value it raises goes back to stock."""
import importlib.util, os, pathlib, sys, tempfile, unittest

spec = importlib.util.spec_from_file_location("smoothd", pathlib.Path(__file__).parent.parent / "smoothd.py")
smoothd = importlib.util.module_from_spec(spec); spec.loader.exec_module(smoothd)


class KnobsTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def f(self, name, val):
        p = os.path.join(self.d, name)
        pathlib.Path(p).write_text(val)
        return p

    def test_set_then_reset_restores_stock(self):
        a, b = self.f("min_freq", "576000"), self.f("boost", "15")
        k = smoothd.Knobs()
        k.set(a, "1209600"); k.set(b, "50")
        k.set(a, "1300000")                       # a second raise keeps the first stock value
        self.assertEqual(pathlib.Path(a).read_text(), "1300000")
        k.reset_all()
        self.assertEqual(pathlib.Path(a).read_text(), "576000")
        self.assertEqual(pathlib.Path(b).read_text(), "15")

    def test_missing_file_is_skipped(self):
        k = smoothd.Knobs()
        k.set(os.path.join(self.d, "nope"), "1")
        self.assertEqual(k.stock, {})
        k.reset_all()

    def test_partial_reset(self):
        a, b = self.f("a", "1"), self.f("b", "2")
        k = smoothd.Knobs(); k.set(a, "9"); k.set(b, "9")
        k.reset([a])
        self.assertEqual(pathlib.Path(a).read_text(), "1")
        self.assertEqual(pathlib.Path(b).read_text(), "9")

    def test_interaction_values_from_vendor_json(self):
        vals = smoothd.interaction_values()      # empty on a PC without /vendor
        self.assertIsInstance(vals, dict)


if __name__ == "__main__":
    unittest.main()
