//! Atomic local restore records; a manifest authenticates the private closure.
use crate::{
    client::Build,
    wire::{error, Decode, Encode, Result},
    Client,
};
use layerfs_content::{InodeScope, ObjectId};
use layerfs_history::BranchSnapshot;
use layerfs_store_service::store::ignore::{RestorePoint, Seed};
use std::sync::Mutex;
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
        let decoded = decode(&bytes).and_then(|(point, ids)| {
            if point.binding.scope != head.scope || point.binding.branch.id != head.branch.id {
                return Err(error("restore identity"));
            }
            Ok((point, ids))
        });
        let Ok((point, ids)) = decoded else {
            *status = "invalid-record";
            return Ok(None);
        };
        for id in ids {
            match self.0.cache.get(id) {
                Ok(Some(_)) => (),
                Ok(None) => {
                    *status = "missing-local-objects";
                    return Ok(None);
                }
                Err(_) => {
                    *status = "invalid-local-objects";
                    return Ok(None);
                }
            }
        }
        *status = "restored";
        Ok(Some(point))
    }
    pub(crate) fn keep_restore(&self, key: &str, point: &RestorePoint) -> Result<()> {
        let build = Build {
            client: Client(self.0.clone()),
            failure: Mutex::new(None),
        };
        let ids = build.closure(point.local, InodeScope::from_object(point.binding.scope))?;
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
        // The whole remaining suffix is the local manifest, with no object cap.
        for (id, _) in ids {
            out.raw(id.as_bytes());
        }
        self.0.cache.save_restore(
            point.binding.scope,
            &point.binding.branch.id.to_bytes(),
            key,
            &out.0,
        )
    }
}
fn decode(bytes: &[u8]) -> Result<(RestorePoint, Vec<ObjectId>)> {
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
    let mut ids = Vec::new();
    while !input.0.is_empty() {
        ids.push(ObjectId::from_bytes(input.take(32)?).map_err(error)?);
    }
    Ok((
        RestorePoint {
            binding,
            local,
            published,
            seeds,
        },
        ids,
    ))
}
