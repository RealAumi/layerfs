//! Explicit Linux receive cancellation; no detach, abort or request replay.
use std::os::fd::OwnedFd;

use nix::errno::Errno;
use nix::fcntl::{FcntlArg, OFlag, fcntl};
use nix::sys::epoll::{Epoll, EpollCreateFlags, EpollEvent, EpollFlags, EpollTimeout};
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
    pub(super) fn prepare(&self, channel: &Channel) -> nix::Result<ReceiveWait> {
        let flags = OFlag::from_bits_retain(fcntl(channel, FcntlArg::F_GETFL)?);
        fcntl(channel, FcntlArg::F_SETFL(flags | OFlag::O_NONBLOCK))?;
        let wait = Epoll::new(EpollCreateFlags::EPOLL_CLOEXEC)?;
        // Each receiver registers separately. Exclusive device wakeups avoid
        // waking all readers for one frame; stop remains a broadcast to all.
        wait.add(
            channel,
            EpollEvent::new(EpollFlags::EPOLLIN | EpollFlags::EPOLLEXCLUSIVE, 0),
        )?;
        wait.add(&self.read, EpollEvent::new(EpollFlags::EPOLLIN, 1))?;
        Ok(ReceiveWait(wait))
    }
}
/// The event loop owns its channel and its monitor keeps the stop pipe alive.
#[derive(Debug)]
pub(super) struct ReceiveWait(Epoll);
impl ReceiveWait {
    pub(super) fn receive(
        &self,
        channel: &Channel,
        buffer: &mut [u8],
    ) -> nix::Result<Option<usize>> {
        loop {
            let mut events = [EpollEvent::empty(); 2];
            let count = match self.0.wait(&mut events, EpollTimeout::NONE) {
                Ok(count) => count,
                Err(Errno::EINTR) => continue,
                Err(error) => return Err(error),
            };
            for event in &events[..count] {
                if event.data() == 1 {
                    return if event.events().contains(EpollFlags::EPOLLHUP) {
                        Ok(None)
                    } else {
                        Err(Errno::EIO)
                    };
                }
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
