fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 || args[1] != "--config" {
        return Err("usage: layerfs-store --config <private-file>".into());
    }
    layerfs_remote_store::server::serve(layerfs_remote_store::Config::read(
        std::path::Path::new(&args[2]),
    )?)?;
    Ok(())
}
