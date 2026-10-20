//! Standalone bounded encoding of the existing coherent Branch snapshot.
use crate::{
    control::ControlError,
    control_history,
    wire::{Reader, Writer},
};
use layerfs_history::BranchSnapshot;
const MAGIC: &[u8] = b"LFBS\x01";
/// Encodes the existing binding vocabulary without inventing a control operation.
pub fn encode(value: &BranchSnapshot) -> Result<Vec<u8>, ControlError> {
    let mut out = Writer::new(MAGIC);
    control_history::put_binding(&mut out, value)?;
    Ok(out.0)
}
/// Decodes one complete binding; trailing bytes and unsupported versions fail.
pub fn decode(bytes: &[u8]) -> Result<BranchSnapshot, ControlError> {
    let mut input = Reader::new(bytes, MAGIC)?;
    let value = control_history::binding(&mut input)?;
    input.finish()?;
    Ok(value)
}
