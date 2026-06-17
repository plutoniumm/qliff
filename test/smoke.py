import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from MDR import Exam, Question, load

import aaronson


class Smoke(Question):
    def test_import(self):
        """
        `import aaronson` succeeds and exposes a version.
        """
        self.assertTrue(
            hasattr(aaronson, "__version__"), msg="aaronson must expose __version__"
        )

    def test_version(self):
        """
        Version is sourced from the Rust crate and equals 0.1.0.
        """
        self.assertEqual(aaronson.__version__, "0.1.0", msg="version must be 0.1.0")


if __name__ == "__main__":
    sys.exit(
        Exam("Smoke", "Phase 1 build + import smoke test", "smoke.md").run(load(Smoke))
    )
