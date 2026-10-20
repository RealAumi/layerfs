//! Git's ignore patterns: one `.gitignore` or exclude file per [`Rules`], and
//! the stack of files that apply to one directory. Paths are relative to the
//! Workspace root, `/`-separated, with no leading slash.
use std::rc::Rc;

/// One pattern line.
#[derive(Clone, Debug)]
struct Pattern {
    glob: Vec<u8>,
    negated: bool,
    /// A trailing slash: directories only.
    directory: bool,
    /// A slash before the end: matched against the path below the file's
    /// directory; otherwise against the last component only.
    anchored: bool,
}

/// The patterns of one file, which apply below `base` (`""` for the root).
#[derive(Clone, Debug, Default)]
pub struct Rules {
    base: String,
    patterns: Vec<Pattern>,
}

impl Rules {
    /// Parses one file's lines as Git does: comments, blank lines, escapes,
    /// trailing spaces, `!` negation and a trailing `/`.
    pub fn parse(base: &str, text: &[u8]) -> Self {
        let patterns = text.split(|b| *b == b'\n').filter_map(line).collect();
        Self {
            base: base.to_owned(),
            patterns,
        }
    }
    pub fn is_empty(&self) -> bool {
        self.patterns.is_empty()
    }
}

fn line(raw: &[u8]) -> Option<Pattern> {
    let mut raw = raw.strip_suffix(b"\r").unwrap_or(raw);
    if raw.is_empty() || raw[0] == b'#' {
        return None;
    }
    // Trailing spaces go unless the last one is escaped.
    while let [rest @ .., b' '] = raw {
        if rest.last() == Some(&b'\\') {
            break;
        }
        raw = rest;
    }
    let (negated, mut glob) = match raw {
        [b'!', rest @ ..] => (true, rest),
        _ => (false, raw),
    };
    let directory = glob.len() > 1 && glob.ends_with(b"/");
    if directory {
        glob = &glob[..glob.len() - 1];
    }
    let anchored = glob.contains(&b'/');
    let glob = glob.strip_prefix(b"/").unwrap_or(glob);
    (!glob.is_empty()).then(|| Pattern {
        glob: glob.to_vec(),
        negated,
        directory,
        anchored,
    })
}

/// Every file that applies to one directory, lowest precedence first.
#[derive(Clone, Debug, Default)]
pub struct Stack(Vec<Rc<Rules>>);

impl Stack {
    /// This stack and one more file below it.
    pub fn with(&self, rules: Rules) -> Self {
        let mut next = self.0.clone();
        if !rules.is_empty() {
            next.push(Rc::new(rules));
        }
        Self(next)
    }
    /// Whether `path` is ignored by the last pattern that matches it. The
    /// caller decides ancestors first: below an ignored directory nothing
    /// is re-included.
    pub fn ignored(&self, path: &str, directory: bool) -> bool {
        let name = path.rsplit('/').next().unwrap_or(path);
        for rules in self.0.iter().rev() {
            let below = if rules.base.is_empty() {
                Some(path)
            } else {
                path.strip_prefix(rules.base.as_str())
                    .and_then(|rest| rest.strip_prefix('/'))
            };
            let Some(below) = below else {
                continue;
            };
            for pattern in rules.patterns.iter().rev() {
                if pattern.directory && !directory {
                    continue;
                }
                let subject = if pattern.anchored { below } else { name };
                if wildmatch(&pattern.glob, subject.as_bytes()) {
                    return !pattern.negated;
                }
            }
        }
        false
    }
}

/// Git's wildmatch with WM_PATHNAME: `*`, `?` and classes never match `/`;
/// `**` between slashes, or at either end, matches any number of directories.
fn wildmatch(pattern: &[u8], text: &[u8]) -> bool {
    let (mut p, mut t) = (0, 0);
    while p < pattern.len() {
        match pattern[p] {
            b'*' => {
                let mut end = p;
                while end < pattern.len() && pattern[end] == b'*' {
                    end += 1;
                }
                let whole = (p == 0 || pattern[p - 1] == b'/')
                    && (end == pattern.len() || pattern[end] == b'/');
                if end - p > 1 && whole {
                    if end == pattern.len() {
                        return true;
                    }
                    let rest = &pattern[end + 1..];
                    return wildmatch(rest, &text[t..])
                        || (t..text.len())
                            .any(|i| text[i] == b'/' && wildmatch(rest, &text[i + 1..]));
                }
                let rest = &pattern[end..];
                let mut i = t;
                loop {
                    if wildmatch(rest, &text[i..]) {
                        return true;
                    }
                    if i == text.len() || text[i] == b'/' {
                        return false;
                    }
                    i += 1;
                }
            }
            b'?' => {
                if t == text.len() || text[t] == b'/' {
                    return false;
                }
                p += 1;
                t += 1;
            }
            b'[' => match class(&pattern[p..], text.get(t).copied()) {
                Some((matched, length)) => {
                    if !matched {
                        return false;
                    }
                    p += length;
                    t += 1;
                }
                None => {
                    if text.get(t) != Some(&b'[') {
                        return false;
                    }
                    p += 1;
                    t += 1;
                }
            },
            c => {
                let (c, length) = match (c, pattern.get(p + 1)) {
                    (b'\\', Some(escaped)) => (*escaped, 2),
                    _ => (c, 1),
                };
                if text.get(t) != Some(&c) {
                    return false;
                }
                p += length;
                t += 1;
            }
        }
    }
    t == text.len()
}

/// One bracket expression at the start of `pattern`: whether `c` matches it
/// and the expression's length, or `None` when it is not closed.
fn class(pattern: &[u8], c: Option<u8>) -> Option<(bool, usize)> {
    let mut i = 1;
    let negated = matches!(pattern.get(i), Some(b'!' | b'^'));
    if negated {
        i += 1;
    }
    let mut matched = false;
    let mut first = true;
    loop {
        let mut low = *pattern.get(i)?;
        if low == b']' && !first {
            break;
        }
        first = false;
        if low == b'[' && pattern.get(i + 1) == Some(&b':') {
            let close = pattern[i + 2..].windows(2).position(|w| w == b":]")?;
            let name = &pattern[i + 2..i + 2 + close];
            matched |= c.is_some_and(|c| posix(name, c));
            i += close + 4;
            continue;
        }
        if low == b'\\' {
            i += 1;
            low = *pattern.get(i)?;
        }
        i += 1;
        let mut high = low;
        if pattern.get(i) == Some(&b'-') && pattern.get(i + 1).is_some_and(|b| *b != b']') {
            high = pattern[i + 1];
            if high == b'\\' {
                high = *pattern.get(i + 2)?;
                i += 1;
            }
            i += 2;
        }
        matched |= c.is_some_and(|c| low <= c && c <= high);
    }
    let matched = c.is_some_and(|c| c != b'/') && matched != negated;
    Some((matched, i + 1))
}

fn posix(name: &[u8], c: u8) -> bool {
    match name {
        b"alnum" => c.is_ascii_alphanumeric(),
        b"alpha" => c.is_ascii_alphabetic(),
        b"blank" => c == b' ' || c == b'\t',
        b"cntrl" => c.is_ascii_control(),
        b"digit" => c.is_ascii_digit(),
        b"graph" => c.is_ascii_graphic(),
        b"lower" => c.is_ascii_lowercase(),
        b"print" => c.is_ascii_graphic() || c == b' ',
        b"punct" => c.is_ascii_punctuation(),
        b"space" => c.is_ascii_whitespace(),
        b"upper" => c.is_ascii_uppercase(),
        b"xdigit" => c.is_ascii_hexdigit(),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ignored(files: &[(&str, &str)], path: &str, directory: bool) -> bool {
        files
            .iter()
            .fold(Stack::default(), |stack, (base, text)| {
                stack.with(Rules::parse(base, text.as_bytes()))
            })
            .ignored(path, directory)
    }

    #[test]
    fn names_match_at_any_depth_and_slashes_anchor() {
        let root = [("", "target/\n*.class\n/build\ndocs/*.html\n")];
        assert!(ignored(&root, "target", true));
        assert!(ignored(&root, "a/b/target", true));
        assert!(!ignored(&root, "a/target", false), "directory-only pattern");
        assert!(ignored(&root, "src/A.class", false));
        assert!(ignored(&root, "build", false));
        assert!(!ignored(&root, "a/build", true), "leading slash anchors");
        assert!(ignored(&root, "docs/x.html", false));
        assert!(
            !ignored(&root, "docs/a/x.html", false),
            "star stops at slash"
        );
        assert!(!ignored(&root, "src/A.java", false));
    }

    #[test]
    fn double_stars_negation_and_nested_files() {
        let files = [
            (
                "",
                "**/logs\nfoo/**/bar\nout/**\n*.log\n!keep.log\n# comment\n\\#hash\n",
            ),
            ("sub", "local\n!*.class\n"),
        ];
        assert!(ignored(&files, "logs", true));
        assert!(ignored(&files, "a/b/logs", false));
        assert!(ignored(&files, "foo/bar", false));
        assert!(ignored(&files, "foo/a/b/bar", false));
        assert!(ignored(&files, "out/x/y", false));
        assert!(!ignored(&files, "out", true), "out/** matches inside only");
        assert!(ignored(&files, "a/x.log", false));
        assert!(!ignored(&files, "a/keep.log", false));
        assert!(ignored(&files, "#hash", false));
        assert!(ignored(&files, "sub/local", false));
        assert!(
            !ignored(&files, "local", false),
            "nested file applies below it"
        );
    }

    #[test]
    fn classes_escapes_and_trailing_spaces() {
        let root = [("", "[abc].txt\n[!0-9]x\nf[[:digit:]]\nsp\\ \ntrail   \n")];
        assert!(ignored(&root, "b.txt", false));
        assert!(!ignored(&root, "d.txt", false));
        assert!(ignored(&root, "ax", false));
        assert!(!ignored(&root, "1x", false));
        assert!(ignored(&root, "f7", false));
        assert!(ignored(&root, "sp ", false));
        assert!(ignored(&root, "trail", false));
        assert!(!ignored(&root, "trail ", false));
    }
}
