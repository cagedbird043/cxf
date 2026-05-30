use std::io::{self, IsTerminal, Write};

use similar::TextDiff;

fn color_enabled() -> bool {
    io::stdout().is_terminal() && std::env::var_os("NO_COLOR").is_none()
}

fn paint(code: &str, text: impl AsRef<str>) -> String {
    let text = text.as_ref();
    if color_enabled() {
        format!("\x1b[{code}m{text}\x1b[0m")
    } else {
        text.to_string()
    }
}

pub fn green(text: impl AsRef<str>) -> String {
    paint("32", text)
}

pub fn red(text: impl AsRef<str>) -> String {
    paint("31", text)
}

pub fn yellow(text: impl AsRef<str>) -> String {
    paint("33", text)
}

pub fn cyan(text: impl AsRef<str>) -> String {
    paint("36", text)
}

pub fn bold(text: impl AsRef<str>) -> String {
    paint("1", text)
}

pub fn diff(before: &str, after: &str, from: &str, to: &str) -> String {
    if before == after {
        return String::new();
    }
    TextDiff::from_lines(before, after)
        .unified_diff()
        .header(from, to)
        .to_string()
}

pub fn print_diff(diff_text: &str) {
    for line in diff_text.lines() {
        if line.starts_with('+') && !line.starts_with("+++") {
            println!("{}", green(line));
        } else if line.starts_with('-') && !line.starts_with("---") {
            println!("{}", red(line));
        } else if line.starts_with("@@") {
            println!("{}", cyan(line));
        } else {
            println!("{line}");
        }
    }
}

pub fn prompt(label: &str, default: Option<&str>) -> String {
    match default {
        Some(v) => print!("{label} [{v}]: "),
        None => print!("{label}: "),
    }
    let _ = io::stdout().flush();
    let mut input = String::new();
    if io::stdin().read_line(&mut input).is_err() {
        return default.unwrap_or_default().to_string();
    }
    let value = input.trim();
    if value.is_empty() {
        default.unwrap_or_default().to_string()
    } else {
        value.to_string()
    }
}

pub fn confirm(label: &str, yes: bool) -> bool {
    if yes {
        return true;
    }
    matches!(
        prompt(&format!("{label} [y/N]"), None)
            .to_ascii_lowercase()
            .as_str(),
        "y" | "yes" | "是"
    )
}

pub fn prompt_bool(label: &str, default: bool) -> bool {
    let default_text = if default { "yes" } else { "no" };
    matches!(
        prompt(label, Some(default_text))
            .to_ascii_lowercase()
            .as_str(),
        "y" | "yes" | "true" | "1" | "on" | "是"
    )
}

pub fn print_rows(headers: &[&str], rows: &[Vec<String>]) {
    let mut widths: Vec<usize> = headers.iter().map(|h| h.len()).collect();
    for row in rows {
        for (idx, cell) in row.iter().enumerate() {
            if idx < widths.len() {
                widths[idx] = widths[idx].max(cell.len());
            }
        }
    }

    for (idx, header) in headers.iter().enumerate() {
        print!("{:width$}  ", bold(header), width = widths[idx] + 9);
    }
    println!();
    for row in rows {
        for (idx, cell) in row.iter().enumerate() {
            print!("{:width$}  ", cell, width = widths[idx] + 9);
        }
        println!();
    }
}

pub fn ok(msg: impl AsRef<str>) {
    println!("{} {}", green("✓"), msg.as_ref());
}

pub fn controlled_yes(provider: &str) {
    println!("{} yes", green("controlled:"));
    println!("  provider: {provider}");
}

pub fn controlled_no(provider: &str, reasons: &[String]) {
    println!("{} no", red("controlled:"));
    println!("  provider: {provider}");
    for item in reasons {
        println!("  {} {item}", yellow("drift:"));
    }
}

pub fn controlled_partial(provider: &str, items: &[String], fix: &str) {
    println!("{} partial", yellow("controlled:"));
    println!("  provider: {provider}");
    for item in items {
        println!("  {} {item}", yellow("drift:"));
    }
    println!("  {}", bold(fix));
}
