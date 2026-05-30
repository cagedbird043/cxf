use std::{
    env, fs,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result, bail};
use serde_json::{Map, Value};
use toml_edit::{DocumentMut, value};

pub const BASE_KEYS: [&str; 5] = [
    "model",
    "review_model",
    "model_reasoning_effort",
    "model_context_window",
    "model_auto_compact_token_limit",
];

pub fn home_dir() -> PathBuf {
    env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

pub fn config_home() -> PathBuf {
    env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home_dir().join(".config"))
}

pub fn state_home() -> PathBuf {
    env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home_dir().join(".local/state"))
}

pub fn cxf_home() -> PathBuf {
    config_home().join("cxf")
}
pub fn providers_dir() -> PathBuf {
    cxf_home().join("providers")
}
pub fn base_path() -> PathBuf {
    cxf_home().join("base.toml")
}
pub fn claude_providers_dir() -> PathBuf {
    cxf_home().join("claude/providers")
}
pub fn snapshots_dir() -> PathBuf {
    state_home().join("cxf/snapshots")
}
pub fn codex_config_path() -> PathBuf {
    home_dir().join(".codex/config.toml")
}
pub fn auth_path() -> PathBuf {
    home_dir().join(".codex/auth.json")
}
pub fn claude_settings_path() -> PathBuf {
    home_dir().join(".claude/settings.json")
}

pub fn ensure_layout() -> Result<()> {
    fs::create_dir_all(providers_dir()).context("create providers dir")?;
    fs::create_dir_all(snapshots_dir()).context("create snapshots dir")?;
    Ok(())
}

pub fn ensure_claude_layout() -> Result<()> {
    fs::create_dir_all(claude_providers_dir()).context("create claude providers dir")?;
    Ok(())
}

pub fn read_text(path: &Path) -> Result<String> {
    match fs::read_to_string(path) {
        Ok(text) => Ok(text),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(String::new()),
        Err(err) => Err(err).with_context(|| format!("read {}", path.display())),
    }
}

pub fn read_toml(path: &Path) -> Result<DocumentMut> {
    let text = read_text(path)?;
    if text.trim().is_empty() {
        Ok(DocumentMut::new())
    } else {
        text.parse::<DocumentMut>()
            .with_context(|| format!("parse {}", path.display()))
    }
}

pub fn write_toml(path: &Path, doc: &DocumentMut) -> Result<()> {
    write_secret(path, doc.to_string().as_bytes())
}

pub fn read_json(path: &Path) -> Result<Map<String, Value>> {
    let text = read_text(path)?;
    if text.trim().is_empty() {
        return Ok(Map::new());
    }
    let value: Value = serde_json::from_str(&text)
        .with_context(|| format!("parse {}: invalid JSON", path.display()))?;
    match value {
        Value::Object(map) => Ok(map),
        other => bail!(
            "{}: expected JSON object, got {}",
            path.display(),
            match other {
                Value::Array(_) => "array",
                Value::String(_) => "string",
                Value::Number(_) => "number",
                Value::Bool(_) => "boolean",
                Value::Null => "null",
                _ => "unknown",
            }
        ),
    }
}

pub fn write_json(path: &Path, map: &Map<String, Value>) -> Result<()> {
    let text = serde_json::to_string_pretty(map).context("serialize json")? + "\n";
    write_secret(path, text.as_bytes())
}

pub fn write_secret(path: &Path, data: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).with_context(|| format!("create {}", parent.display()))?;
    }
    fs::write(path, data).with_context(|| format!("write {}", path.display()))?;
    chmod_600(path)?;
    Ok(())
}

#[cfg(unix)]
fn chmod_600(path: &Path) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    let mut perms = fs::metadata(path)?.permissions();
    perms.set_mode(0o600);
    fs::set_permissions(path, perms)?;
    Ok(())
}

#[cfg(not(unix))]
fn chmod_600(_path: &Path) -> Result<()> {
    Ok(())
}

pub fn read_auth() -> Result<Map<String, Value>> {
    read_json(&auth_path())
}

pub fn write_auth(api_key: &str) -> Result<()> {
    let mut auth = read_auth()?;
    if auth.get("OPENAI_API_KEY").and_then(Value::as_str) == Some(api_key) {
        return Ok(());
    }
    auth.insert(
        "OPENAI_API_KEY".to_string(),
        Value::String(api_key.to_string()),
    );
    auth.insert("source".to_string(), Value::String("cxf".to_string()));
    write_json(&auth_path(), &auth)
}

pub fn load_base() -> Result<DocumentMut> {
    read_toml(&base_path())
}

pub fn write_default_base() -> Result<()> {
    let path = base_path();
    if path.exists() {
        return Ok(());
    }
    let live = read_toml(&codex_config_path())?;
    let mut doc = DocumentMut::new();
    for key in BASE_KEYS {
        if let Some(item) = live.get(key) {
            doc[key] = item.clone();
        }
    }
    if !doc.contains_key("model") {
        doc["model"] = value("gpt-5.5");
    }
    if !doc.contains_key("review_model") {
        doc["review_model"] = value("gpt-5.5");
    }
    if !doc.contains_key("model_reasoning_effort") {
        doc["model_reasoning_effort"] = value("high");
    }
    if !doc.contains_key("model_context_window") {
        doc["model_context_window"] = value(272000);
    }
    if !doc.contains_key("model_auto_compact_token_limit") {
        doc["model_auto_compact_token_limit"] = value(240000);
    }
    write_toml(&path, &doc)
}

pub fn take_snapshot(source: &Path, prefix: &str, provider: &str, ext: &str) -> Result<()> {
    if !source.exists() {
        return Ok(());
    }
    fs::create_dir_all(snapshots_dir()).context("create snapshots dir")?;
    let safe = provider.replace(['/', '\\'], "_");
    let target = snapshots_dir().join(format!("{prefix}-{safe}.{ext}"));
    fs::copy(source, target).context("write snapshot")?;
    Ok(())
}
