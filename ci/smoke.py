"""
Wheel smoke test (run in-container by cibuildwheel and by hand after local
builds): import the package, load the native core, run a Bell-pair stabilizer
sim. Needs numpy only.
"""

import qliff

sim = qliff.Simulator(2)
sim.H(0)
sim.CX(0, 1)

stabs = sim.stabilizers()
assert stabs == ["+XX", "+ZZ"], stabs

a, b = sim.M(0), sim.M(1)
assert a == b, (a, b)

print(f"qliff {qliff.__version__} smoke OK: {stabs}, M -> {a}{b}")
