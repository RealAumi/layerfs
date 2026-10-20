//! External two-container driver. All Store calls use the public SDK method table.
#[allow(dead_code)]
#[path = "../../layerfs-api/tests/support/installed_store.rs"]
mod installed;
use layerfs_bridge::{
    control::{SdkCall, SdkValue},
    duplex,
};
use layerfs_history::{BranchId, HistoryName, LayerStackId};
use layerfs_remote_store::{
    config::{hex, unhex},
    Config,
};
use layerfs_store_service::StoreService;
use std::{fs, os::unix::fs::PermissionsExt, path::Path};
fn private(path: impl AsRef<Path>, text: String) {
    fs::write(path.as_ref(), text).unwrap();
    fs::set_permissions(path, fs::Permissions::from_mode(0o600)).unwrap();
}
fn open() -> StoreService {
    let cfg = Config::read(Path::new("/state/server.setup")).unwrap();
    StoreService::open_direct(
        Path::new(cfg.get("store").unwrap()),
        &unhex(cfg.get("binding").unwrap()).unwrap(),
        cfg.key("cursor").unwrap(),
        &Path::new("/state").join(format!("sdk-{}.sqlite", std::process::id())),
    )
    .unwrap()
}
fn call(service: &StoreService, method: &str, mut fields: Vec<(&str, SdkValue)>) -> SdkValue {
    fields.push(("project", SdkValue::text("installed")));
    layerfs_api::call(
        service,
        &SdkCall {
            method: method.into(),
            args: SdkValue::Map(
                fields
                    .into_iter()
                    .map(|(k, v)| (k.to_string(), v))
                    .collect(),
            ),
        },
    )
    .unwrap()
}
fn read(service: &StoreService, path: &str) -> String {
    call(
        service,
        "fs.read",
        vec![
            ("branch", SdkValue::text("work")),
            ("path", SdkValue::text(path)),
        ],
    )
    .get_text("text")
    .unwrap()
    .to_owned()
}
#[test]
#[ignore = "run explicitly by docs/mp2 two-container script"]
fn drive() {
    match std::env::var("LFS_MODE").unwrap().as_str() {
        "init" => {
            let fixture = installed::Fixture::built("remote-e2e", |source| {
                if let Ok(input) = std::env::var("LFS_SOURCE") {
                    assert!(std::process::Command::new("cp")
                        .args(["-a", &format!("{input}/."), source.to_str().unwrap()])
                        .status()
                        .unwrap()
                        .success());
                    fn count(p: &Path) -> usize {
                        fs::read_dir(p)
                            .unwrap()
                            .map(|e| {
                                let e = e.unwrap();
                                1 + if e.file_type().unwrap().is_dir() {
                                    count(&e.path())
                                } else {
                                    0
                                }
                            })
                            .sum()
                    }
                    return count(source);
                }
                fs::create_dir(source.join("bulk")).unwrap();
                for i in 0..3000 {
                    fs::write(
                        source.join(format!("bulk/f{i:04}")),
                        format!("remote file {i}\n"),
                    )
                    .unwrap();
                }
                fs::write(source.join("server"), "server base\n").unwrap();
                fs::write(source.join("local"), "local base\n").unwrap();
                fs::write(source.join("race"), "a0\nb0\nc0\nd0\ne0\n").unwrap();
                3004
            });
            fs::create_dir_all("/state/store").unwrap();
            fs::create_dir_all("/state/server-overlay").unwrap();
            fs::copy(&fixture.config.path, "/state/store/store.sqlite").unwrap();
            fixture.cleanup();
            let server = duplex::generate_keypair().unwrap();
            let token = duplex::generate_keypair().unwrap().private;
            private("/state/server.setup",format!("listen=0.0.0.0:7800\nstore=/state/store/store.sqlite\nbinding={}\ncursor={}\noverlay=/state/server-overlay/template.sqlite\nprivate_key={}\ntoken={}\n",hex(installed::BINDING),hex(&installed::CURSOR),hex(&server.private),hex(&token)));
            for name in ["b1", "b2"] {
                let daemon = duplex::generate_keypair().unwrap();
                private(format!("/out/{name}.setup"),format!("server=127.0.0.1:7900\nserver_key={}\ntoken={}\nprivate_key={}\ncontrol=127.0.0.1:7801\nlisten=127.0.0.1:7801\nuid=1000\ngid=1000\ncache=/state/cache/objects.sqlite\noverlay=/state/overlay/template.sqlite\nmounts=/workspaces\n",hex(&server.public),hex(&token),hex(&daemon.private)));
            }
            let service = open();
            call(
                &service,
                "branch.fork",
                vec![("name", SdkValue::text("work"))],
            );
            let branch = BranchId::named(
                LayerStackId::from_authority([23; 16]),
                &HistoryName::new("work").unwrap(),
            );
            fs::write("/out/branch", hex(&branch.to_bytes())).unwrap();
            let cfg = Config::read(Path::new("/out/b1.setup")).unwrap();
            let snapshot = service
                .store
                .history()
                .branch_snapshot(branch)
                .unwrap()
                .unwrap();
            let setup = layerfs_bridge::daemon_setup::DaemonSetup {
                listen: "0.0.0.0:7801".into(),
                private_key: cfg.key("private_key").unwrap(),
                control_peer: duplex::public_key(&token).unwrap(),
                store: "/state/store/store.sqlite".into(),
                overlay: "/state/overlay/template.sqlite".into(),
                mounts: "/workspaces".into(),
                command_uid: 1000,
                command_gid: 1000,
                limits: layerfs_bridge::daemon_setup::DaemonLimits {
                    connections: 8,
                    handshake_ms: 10000,
                    cache_bytes: 64 * 1024 * 1024,
                    namespaces: 64,
                    pager_kib: 2048,
                    serial_low_water: 0,
                },
                existing_store: Some(layerfs_bridge::provision::StoreManifest {
                    provider: layerfs_bridge::provision::ProviderKind::Sqlite,
                    locator: "/state/store/store.sqlite".into(),
                    profile: layerfs_bridge::provision::StoreProfile::Disposable,
                    binding: installed::BINDING.to_vec(),
                    cursor_key: installed::CURSOR,
                    stack: LayerStackId::from_authority([23; 16]).to_bytes(),
                    branch: branch.to_bytes(),
                    root: snapshot.effective_root.to_bytes(),
                    bytes: fs::metadata("/state/store/store.sqlite").unwrap().len(),
                    host_sqlite: rusqlite::version().into(),
                    daemon_sqlite: Some(rusqlite::version().into()),
                }),
            };
            fs::write("/out/native.setup", setup.encode().unwrap()).unwrap();
            fs::set_permissions("/out/native.setup", fs::Permissions::from_mode(0o600)).unwrap();
            service.close().unwrap();
        }
        mode => {
            let service = open();
            match mode {
                "write" => {
                    call(
                        &service,
                        "fs.write",
                        vec![
                            ("branch", SdkValue::text("work")),
                            ("path", SdkValue::text(std::env::var("LFS_PATH").unwrap())),
                            (
                                "content",
                                SdkValue::text(std::env::var("LFS_TEXT").unwrap()),
                            ),
                        ],
                    );
                }
                "read" => {
                    let text = read(&service, &std::env::var("LFS_PATH").unwrap());
                    if let Ok(expected) = std::env::var("LFS_EXPECT") {
                        assert_eq!(text, expected);
                    }
                    println!("SDK_READ {text:?}");
                }
                "history" => {
                    let value = call(
                        &service,
                        "branch.list_commits",
                        vec![("branch", SdkValue::text("work"))],
                    );
                    let Some(SdkValue::List(items)) = value.get("items") else {
                        panic!("history items: {value:?}")
                    };
                    println!("HISTORY {}", items.len());
                }
                "head" => {
                    let branch = BranchId::named(
                        LayerStackId::from_authority([23; 16]),
                        &HistoryName::new("work").unwrap(),
                    );
                    let s = service
                        .store
                        .history()
                        .branch_snapshot(branch)
                        .unwrap()
                        .unwrap();
                    println!("HEAD {:?} {}", s.branch.head_commit, s.effective_root);
                }
                "oracle" => {
                    fs::create_dir_all("/state/oracle/bulk").unwrap();
                    for i in 0..3000 {
                        let p = format!("bulk/f{i:04}");
                        fs::write(
                            Path::new("/state/oracle").join(&p),
                            read(&service, &format!("/{p}")),
                        )
                        .unwrap();
                    }
                    for p in ["server", "local", "race"] {
                        fs::write(
                            Path::new("/state/oracle").join(p),
                            read(&service, &format!("/{p}")),
                        )
                        .unwrap();
                    }
                    println!("SDK_ORACLE 3003 files");
                }
                _ => panic!("unknown driver mode"),
            }
            service.close().unwrap();
        }
    }
}
