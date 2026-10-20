//! Small atomic restore records; presence/closure validation belongs to creation.
use crate::{
    wire::{self, error, Decode, Encode, Result},
    Client,
};
use layerfs_content::{FinalizedObject, InodeScope, ObjectId, ObjectRole};
use layerfs_history::BranchSnapshot;
use layerfs_store_service::store::ignore::{RestorePoint, Seed};
use layerfs_store_service::store::RemoteStore;
use layerfs_telemetry::timer::Timing;
use std::collections::HashSet;
impl Client {
    /// Most recent keyed creation decision in this client.
    pub fn restore_status(&self) -> &'static str {
        *self
            .0
            .restore_status
            .lock()
            .unwrap_or_else(|e| e.into_inner())
    }
    pub(crate) fn load_restore(
        &self,
        head: &BranchSnapshot,
        key: &str,
    ) -> Result<Option<RestorePoint>> {
        let bytes = self
            .0
            .cache
            .restore(head.scope, &head.branch.id.to_bytes(), key)?;
        let mut status = self.0.restore_status.lock().map_err(error)?;
        *status = "not-found";
        let Some(bytes) = bytes else { return Ok(None) };
        let decoded = decode(&bytes).and_then(|point| {
            if point.binding.scope != head.scope || point.binding.branch.id != head.branch.id {
                return Err(error("restore identity"));
            }
            Ok(point)
        });
        let Ok(point) = decoded else {
            *status = "invalid-record";
            return Ok(None);
        };
        *status = "validation-unavailable";
        if let Some(reason) = self.check_restore(&point)? {
            *status = reason;
            return Ok(None);
        }
        *status = "restored";
        Ok(Some(point))
    }
    fn check_restore(&self, point: &RestorePoint) -> Result<Option<&'static str>> {
        let (mut seen, mut pending, mut absent) = (HashSet::new(), vec![point.local], Vec::new());
        while let Some(id) = pending.pop() {
            if !seen.insert(id) {
                continue;
            }
            match self.0.cache.presence(id)? {
                None => absent.push(id),
                Some((true, _)) => (), // The Store owns this entire subtree.
                Some((false, code)) => {
                    let Some(role) = code.and_then(|code| ObjectRole::from_code(code).ok()) else {
                        return Ok(Some("invalid-local-objects"));
                    };
                    if matches!(
                        role,
                        ObjectRole::WholeFile
                            | ObjectRole::Chunk
                            | ObjectRole::DirectoryLeaf
                            | ObjectRole::Symlink
                    ) {
                        continue;
                    }
                    let Some(body) = self.0.cache.body(id)? else {
                        return Ok(Some("invalid-local-objects"));
                    };
                    let Ok(object) = Timing::disabled("restore.references", |t| {
                        FinalizedObject::admit(
                            id,
                            role,
                            body,
                            self.policy().construction(),
                            InodeScope::from_object(point.binding.scope),
                            t.child("object"),
                        )
                    })
                    .0
                    else {
                        return Ok(Some("invalid-local-objects"));
                    };
                    pending.extend_from_slice(object.references());
                }
            }
        }
        // One batched absence phase, windowed only by the existing wire limit.
        for ids in absent.chunks(wire::IDS) {
            let mut out = Encode::new();
            wire::put_ids(&mut out, ids);
            let missing = self.call(false, wire::LACKING, out)?;
            if missing.len() != ids.len() || missing.iter().any(|v| *v > 1) {
                return Err(error("invalid LACKING response"));
            }
            if missing.contains(&1) {
                return Ok(Some("missing-local-objects"));
            }
        }
        Ok(None)
    }
    pub(crate) fn keep_restore(&self, key: &str, point: &RestorePoint) -> Result<()> {
        let mut out = Encode::new();
        out.blob(&layerfs_bridge::snapshot::encode(&point.binding).map_err(error)?);
        out.raw(point.local.as_bytes());
        out.raw(point.published.as_bytes());
        out.number(point.seeds.len() as u64);
        for seed in &point.seeds {
            match seed {
                Seed::Path(path) => {
                    out.byte(0);
                    out.text(path);
                }
                Seed::Directory(serial) => {
                    out.byte(1);
                    out.number(*serial);
                }
            }
        }
        self.0.cache.save_restore(
            point.binding.scope,
            &point.binding.branch.id.to_bytes(),
            key,
            &out.0,
        )
    }
}
fn decode(bytes: &[u8]) -> Result<RestorePoint> {
    let mut input = Decode(bytes);
    let binding = layerfs_bridge::snapshot::decode(input.blob(bytes.len())?).map_err(error)?;
    let local = ObjectId::from_bytes(input.take(32)?).map_err(error)?;
    let published = ObjectId::from_bytes(input.take(32)?).map_err(error)?;
    let mut seeds = Vec::new();
    for _ in 0..input.number()? {
        seeds.push(match input.byte()? {
            0 => Seed::Path(input.text(bytes.len())?),
            1 => Seed::Directory(input.number()?),
            _ => return Err(error("restore seed")),
        });
    }
    input.finish()?;
    Ok(RestorePoint {
        binding,
        local,
        published,
        seeds,
    })
}
