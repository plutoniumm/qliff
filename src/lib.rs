use pyo3::prelude::*;

mod tableau;
use tableau::{ColTableau, RowTableau};

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__doc__", "aaronson native core: CHP stabilizer tableau engine.")?;

    m.add_class::<RowTableau>()?;
    m.add_class::<ColTableau>()?;

    Ok(())
}
