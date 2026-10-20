//! Explicit Linux receive cancellation; no detach, abort or request replay.
use std::os::fd::{AsFd, OwnedFd};

use nix::errno::Errno;
use nix::fcntl::{FcntlArg, OFlag, fcntl};
use nix::poll::{PollFd, PollFlags, PollTimeout, poll};
use nix::unistd::{pipe2, read};
use parking_lot::Mutex;

use crate::channel::Channel;

#[derive(Debug)]
pub(super) struct ReceiveStop {
    read: OwnedFd,
    // Closing the sole writer is a persistent broadcast HUP. No receiver
    // consumes the signal, so all receivers observe it even if not yet polling.
    write: Mutex<Option<OwnedFd>>,
}
impl ReceiveStop {
    pub(super) fn new() -> nix::Result<Self> {
        let (read, write) = pipe2(OFlag::O_CLOEXEC | OFlag::O_NONBLOCK)?;
        Ok(Self {
            read,
            write: Mutex::new(Some(write)),
        })
    }
    pub(super) fn stop(&self) {
        drop(self.write.lock().take());
    }
    pub(super) fn prepare(channel: &Channel) -> nix::Result<()> {
        let flags = OFlag::from_bits_retain(fcntl(channel, FcntlArg::F_GETFL)?);
        fcntl(channel, FcntlArg::F_SETFL(flags | OFlag::O_NONBLOCK))?;
        Ok(())
    }
    pub(super) fn receive(
        &self,
        channel: &Channel,
        buffer: &mut [u8],
    ) -> nix::Result<Option<usize>> {
        loop {
            let mut fds = [
                PollFd::new(channel.as_fd(), PollFlags::POLLIN),
                PollFd::new(self.read.as_fd(), PollFlags::POLLIN),
            ];
            match poll(&mut fds, PollTimeout::NONE) {
                Ok(_) => (),
                Err(Errno::EINTR) => continue,
                Err(error) => return Err(error),
            }
            if fds.iter().any(|fd| {
                fd.revents()
                    .unwrap_or(PollFlags::empty())
                    .contains(PollFlags::POLLNVAL)
            }) {
                return Err(Errno::EBADF);
            }
            if fds[1]
                .revents()
                .unwrap_or(PollFlags::empty())
                .contains(PollFlags::POLLHUP)
            {
                return Ok(None);
            }
            // Another receiver may have consumed the readable request. The
            // descriptor must be nonblocking or that race defeats cancellation.
            match read(channel, buffer) {
                Ok(size) => return Ok(Some(size)),
                Err(Errno::ENOENT | Errno::EINTR | Errno::EAGAIN) => continue,
                Err(error) => return Err(error),
            }
        }
    }
}
