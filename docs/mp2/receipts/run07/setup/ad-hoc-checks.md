An early ad-hoc Python assertion expected the entire successful `umount2` trace
on one line. It failed on baseline clean cases 06, 12, 15 and 18, where strace
split the call into `umount2("/workspaces/1", 0 <unfinished ...>` and
`<... umount2 resumed>) = 0`, with receiver exits in between. This was a parser
assumption, not a product failure. All original lines are in those cases'
`results.jsonl`; no sample was rerun or removed. The final summary checks the
single invocation's flags while accepting the standard split-line format.

The raw summary output ended with an extra blank line; staged diff whitespace
checking flagged it. The original stream is retained byte-exact as
`summary-check.txt.gz`, like the other raw logs. No output was trimmed.
