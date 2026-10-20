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
        if let Err(reason) = self.check_restore(&point) {
            *status = reason;
            return Ok(None);
        }
        *status = "restored";
        Ok(Some(point))
    }
    fn check_restore(&self, point: &RestorePoint) -> std::result::Result<(), &'static str> {
        let (mut seen, mut pending, mut absent) = (HashSet::new(), vec![point.local], Vec::new());
        while let Some(id) = pending.pop() {
            if !seen.insert(id) {
                continue;
            }
            match self
                .0
                .cache
                .presence(id)
                .map_err(|_| "invalid-local-objects")?
            {
                None => absent.push(id),
                Some((true, _)) => (), // The Store owns this entire subtree.
                Some((false, code)) => {
                    let role = ObjectRole::from_code(code.ok_or("invalid-local-objects")?)
                        .map_err(|_| "invalid-local-objects")?;
                    if matches!(
                        role,
                        ObjectRole::WholeFile
                            | ObjectRole::Chunk
                            | ObjectRole::DirectoryLeaf
                            | ObjectRole::Symlink
                    ) {
                        continue;
                    }
                    let Some((role, body)) = self
                        .0
                        .cache
                        .local(id)
                        .map_err(|_| "invalid-local-objects")?
                    else {
                        return Err("invalid-local-objects");
                    };
                    let object = Timing::disabled("restore.references", |t| {
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
                    .map_err(|_| "invalid-local-objects")?;
                    pending.extend_from_slice(object.references());
                }
            }
        }
        // One batched absence phase, windowed only by the existing wire limit.
        for ids in absent.chunks(wire::IDS) {
            let mut out = Encode::new();
            wire::put_ids(&mut out, ids);
            let missing = self
                .call(false, wire::LACKING, out)
                .map_err(|_| "validation-unavailable")?;
            if missing.len() != ids.len() || missing.iter().any(|v| *v > 1) {
                return Err("validation-unavailable");
            }
            if missing.contains(&1) {
                return Err("missing-local-objects");
            }
        }
        Ok(())
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
    // Older records end in a manifest. Accept that suffix but validate the tree.
    if input.0.len() % 32 != 0 {
        return Err(error("restore trailing fields"));
    }
    Ok(RestorePoint {
        binding,
        local,
        published,
        seeds,
    })
}
