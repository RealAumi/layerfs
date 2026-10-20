#[cfg(target_os = "linux")]
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 || args[1] != "--config" {
        return Err("usage: layerfs-remote-daemon --config <private-file>".into());
    }
    layerfs_daemon::application::remote::run(std::path::Path::new(&args[2]))?;
    Ok(())
}
#[cfg(not(target_os = "linux"))]
fn main() {
    eprintln!("remote FUSE daemon requires Linux");
    std::process::exit(1);
}
