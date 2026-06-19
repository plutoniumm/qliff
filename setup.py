from setuptools import find_packages, setup

# No pyproject.toml: setup_requires (below) tells the build frontend to install
# setuptools-rust into the build env, then re-run this file with it importable.
# The first pass runs before that happens, so guard the import.
try:
    from setuptools_rust import Binding, RustExtension

    rust_extensions = [
        RustExtension(
            "qliff._core",
            path="Cargo.toml",
            binding=Binding.PyO3,
            py_limited_api=True,
        )
    ]
except ImportError:
    rust_extensions = []

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="qliff",
    version="1.0.0",
    description=(
        "Clifford + noisy stabilizer simulator: noise-free and noisy "
        "(importance-sampled) stabilizer simulation with a native core."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="plutoniumm",
    author_email="haskell-game@manav.ch",
    url="https://github.com/plutoniumm/qliff",
    license="MIT",
    keywords=[
        "quantum",
        "clifford",
        "stabilizer",
        "simulator",
        "noise",
        "qec",
        "tableau",
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Rust",
        "Topic :: Scientific/Engineering :: Physics",
    ],
    python_requires=">=3.11",
    packages=find_packages(include=["qliff", "qliff.*"]),
    install_requires=["numpy"],
    extras_require={
        "dev": ["setuptools-rust", "twine", "black", "wheel"],
        "bench": ["stim", "pymatching"],
    },
    setup_requires=["setuptools-rust"],
    rust_extensions=rust_extensions,
    zip_safe=False,
)
