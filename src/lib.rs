use pyo3::prelude::*;

mod tableau;
use tableau::Tableau;

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__doc__", "aaronson native core: CHP stabilizer tableau engine.")?;

    m.add_class::<Tableau>()?;

    Ok(())
}
