//! Opt-in canonical-object transport. SQLite Store ownership stays on the server.
#![forbid(unsafe_code)]
mod cache;
pub mod client;
pub mod config;
pub mod metadata;
mod restore;
pub mod server;
pub mod wire;
pub use client::Client;
pub use config::Config;
