"""Post-install wheel smoke test (run by cibuildwheel's CIBW_TEST_COMMAND).

Imports qliff, forces the native PyO3 core (`qliff._core`) to load, and runs a
tiny stabilizer simulation whose outcome is deterministic, so a broken/missing
extension fails loudly. Core-only: no numpy-heavy work, no studio/qec extras.
"""

import qliff
from qliff import Simulator


def main() -> None:
    # Importing the package already pulls in qliff._core (the abi3 cdylib); a bad
    # build would have raised ImportError before reaching here.
    assert qliff.__version__, "qliff.__version__ is empty"

    # Prepare a Bell pair: H(0) then CX(0, 1). The two qubits must measure equal.
    sim = Simulator(2, seed=0)
    sim.H(0)
    sim.CX(0, 1)
    a = sim.M(0)
    b = sim.M(1)
    assert a == b, f"Bell pair measured uncorrelated: {a} != {b}"

    # The post-measurement stabilizers pin the state; +ZZ proves the correlation.
    stabs = sim.stabilizers()
    assert any("ZZ" in s for s in stabs), f"missing +ZZ stabilizer: {stabs}"

    print(f"qliff {qliff.__version__} smoke test OK (Bell measure {a}=={b})")


if __name__ == "__main__":
    main()
