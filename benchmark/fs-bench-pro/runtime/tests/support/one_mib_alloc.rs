//! Test-only successful allocation requests; no residency or physical-I/O claim.
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
};

pub(crate) const ONE_MIB: usize = 1_048_576;

#[derive(Clone, Copy, Debug, Default)]
pub(crate) struct Counts {
    pub(crate) alloc: u64,
    pub(crate) zeroed: u64,
    pub(crate) realloc: u64,
}

impl Counts {
    pub(crate) fn requests(self) -> u64 {
        self.alloc + self.zeroed
    }
}

thread_local! {
    static ACTIVE: Cell<bool> = const { Cell::new(false) };
    static COUNTS: Cell<Counts> = const { Cell::new(Counts { alloc: 0, zeroed: 0, realloc: 0 }) };
}

enum Kind {
    Ordinary,
    Zeroed,
    Reallocated,
}

fn record(pointer: *mut u8, size: usize, kind: Kind) {
    if pointer.is_null() || size != ONE_MIB || !ACTIVE.try_with(Cell::get).unwrap_or(false) {
        return;
    }
    let _ = COUNTS.try_with(|slot| {
        let mut counts = slot.get();
        match kind {
            Kind::Ordinary => counts.alloc += 1,
            Kind::Zeroed => counts.zeroed += 1,
            Kind::Reallocated => counts.realloc += 1,
        }
        slot.set(counts);
    });
}

struct CountingSystem;

unsafe impl GlobalAlloc for CountingSystem {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let pointer = unsafe { System.alloc(layout) };
        record(pointer, layout.size(), Kind::Ordinary);
        pointer
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let pointer = unsafe { System.alloc_zeroed(layout) };
        record(pointer, layout.size(), Kind::Zeroed);
        pointer
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        unsafe { System.dealloc(pointer, layout) };
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let result = unsafe { System.realloc(pointer, layout, size) };
        record(result, size, Kind::Reallocated);
        result
    }
}

#[global_allocator]
static ALLOCATOR: CountingSystem = CountingSystem;

pub(crate) struct Guard;

impl Guard {
    pub(crate) fn start() -> Self {
        let nested = ACTIVE.with(|slot| slot.replace(false));
        assert!(!nested, "allocation observer must not nest");
        COUNTS.with(|slot| slot.set(Counts::default()));
        ACTIVE.with(|slot| slot.set(true));
        Self
    }

    pub(crate) fn finish(self) -> Counts {
        ACTIVE.with(|slot| slot.set(false));
        COUNTS.with(Cell::get)
    }
}

impl Drop for Guard {
    fn drop(&mut self) {
        let _ = ACTIVE.try_with(|slot| slot.set(false));
    }
}
