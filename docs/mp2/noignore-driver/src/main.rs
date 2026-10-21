//! Campaign orchestration through public Init and SDK method-table APIs.
use layerfs_bridge::{control::{SdkCall, SdkValue}, duplex};
use layerfs_history::{BranchId, HistoryName, LayerStackId, HistoryCatalogConfig};
use layerfs_persistence::{Handles, PersistenceConfig, SqlitePersistenceProfile, SqliteAcquisitionSchema};
use layerfs_project::{init, InitRequest};
use layerfs_remote_store::{Config, config::{hex, unhex}};
use layerfs_storage::{Storage, StoragePolicy};
use layerfs_store_service::StoreService;
use layerfs_telemetry::timer::Timing;
use std::{path::Path, fs, os::unix::fs::PermissionsExt, time::{Instant, Duration}};
const BINDING: &[u8] = b"cxn-noignore01";
const CURSOR: [u8; 32] = [43; 32];
fn private(path: &str, text: String) {
    fs::write(path, text).unwrap();
    fs::set_permissions(path, fs::Permissions::from_mode(0o600)).unwrap();
}
fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args[1].as_str() {
        "init" => {
            fs::create_dir_all("/state/store").unwrap();
            fs::create_dir_all("/state/server-overlay").unwrap();
            let config = PersistenceConfig::sqlite("/state/store/store.sqlite")
                .with_sqlite_profile(SqlitePersistenceProfile::Disposable)
                .with_sqlite_acquisition(SqliteAcquisitionSchema::Tables);
            let handles = Handles::create(config, StoragePolicy::frozen_default(),
                &HistoryCatalogConfig { binding_key: BINDING.to_vec(), cursor_key: CURSOR, incarnation: 1 }).unwrap();
            let storage = Storage::new(handles.storage.clone()).unwrap();
            let result = Timing::disabled("noignore.init", |timing| init(&storage, &handles.history,
                InitRequest { source: Path::new("/state/initial"), acquisition: &handles.acquisition,
                    stack: LayerStackId::from_authority([23; 16]), name: HistoryName::new("installed").unwrap(),
                    scope_seed: [31; 32], deadline: Instant::now() + Duration::from_secs(10) }, timing)).0.unwrap();
            println!("Init {result:?}");
            drop(storage);
            handles.seal().unwrap();
            let server = duplex::generate_keypair().unwrap();
            let token = duplex::generate_keypair().unwrap().private;
            let daemon = duplex::generate_keypair().unwrap();
            private("/state/server.setup", format!("listen=0.0.0.0:7800\nstore=/state/store/store.sqlite\nbinding={}\ncursor={}\noverlay=/state/server-overlay/template.sqlite\nprivate_key={}\ntoken={}\n",hex(BINDING),hex(&CURSOR),hex(&server.private),hex(&token)));
            private("/state/daemon.setup", format!("server=127.0.0.1:7800\nserver_key={}\ntoken={}\nprivate_key={}\ncontrol=127.0.0.1:7801\nlisten=127.0.0.1:7801\nuid=1000\ngid=1000\ncache=/state/cache/objects.sqlite\noverlay=/state/overlay/template.sqlite\nmounts=/workspaces\n",hex(&server.public),hex(&token),hex(&daemon.private)));
        },
        "id" => println!("{}", hex(&BranchId::named(LayerStackId::from_authority([23; 16]), &HistoryName::new(&args[2]).unwrap()).to_bytes())),
        "call" => {
            let config = Config::read(Path::new("/state/server.setup")).unwrap();
            let service = StoreService::open_direct(Path::new(config.get("store").unwrap()),
                &unhex(config.get("binding").unwrap()).unwrap(), config.key("cursor").unwrap(),
                Path::new(&format!("/state/sdk-{}.sqlite", std::process::id()))).unwrap();
            let mut fields = vec![("project".to_owned(), SdkValue::text("installed"))];
            for arg in &args[3..] {
                let (key,value) = arg.split_once('=').unwrap();
                fields.push((key.to_owned(),SdkValue::text(value)));
            }
            let start=Instant::now();
            let result=layerfs_api::call(&service,&SdkCall {method:args[2].clone(),args:SdkValue::Map(fields)});
            println!("{result:?}\nwall_ns={}",start.elapsed().as_nanos());
            service.close().unwrap();
            if result.is_err() { std::process::exit(1); }
        },
        _ => panic!("unknown operation"),
    }
}
