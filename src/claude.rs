use std::fs;

use anyhow::{Result, bail};
use serde_json::{Map, Value};

use crate::{
    config::{
        claude_providers_dir, claude_settings_path, ensure_claude_layout, read_json, read_text,
        read_toml, take_snapshot, write_json, write_toml,
    },
    models::{CLAUDE_PROVIDER_ENV, ClaudeProvider, ensure_provider_id},
    ux::{controlled_no, controlled_partial, controlled_yes, ok, print_diff},
};

pub const CLAUDE_MANAGED_KEYS: [&str; 13] = [
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_CUSTOM_MODEL_OPTION",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
    "ENABLE_TOOL_SEARCH",
];

pub fn default_deepseek_provider(api_key: &str) -> ClaudeProvider {
    ClaudeProvider {
        provider_id: "deepseek".to_string(),
        env: vec![
            (
                "ANTHROPIC_BASE_URL".to_string(),
                "https://api.deepseek.com/anthropic".to_string(),
            ),
            ("ANTHROPIC_AUTH_TOKEN".to_string(), api_key.to_string()),
            (
                "ANTHROPIC_MODEL".to_string(),
                "deepseek-v4-pro[1m]".to_string(),
            ),
            (
                "ANTHROPIC_DEFAULT_OPUS_MODEL".to_string(),
                "deepseek-v4-pro[1m]".to_string(),
            ),
            (
                "ANTHROPIC_DEFAULT_SONNET_MODEL".to_string(),
                "deepseek-v4-pro[1m]".to_string(),
            ),
            (
                "ANTHROPIC_DEFAULT_HAIKU_MODEL".to_string(),
                "deepseek-v4-flash".to_string(),
            ),
            (
                "CLAUDE_CODE_SUBAGENT_MODEL".to_string(),
                "deepseek-v4-flash".to_string(),
            ),
            ("CLAUDE_CODE_EFFORT_LEVEL".to_string(), "max".to_string()),
        ],
    }
}

pub fn claude_provider_ids() -> Result<Vec<String>> {
    let dir = claude_providers_dir();
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut ids = Vec::new();
    for entry in fs::read_dir(dir)? {
        let path = entry?.path();
        if path.is_file()
            && path.extension().and_then(|s| s.to_str()) == Some("toml")
            && let Some(stem) = path.file_stem().and_then(|s| s.to_str())
        {
            ids.push(stem.to_string());
        }
    }
    ids.sort();
    Ok(ids)
}

pub fn load_claude_provider(provider_id: &str) -> Result<ClaudeProvider> {
    ensure_provider_id(provider_id)?;
    let path = claude_providers_dir().join(format!("{provider_id}.toml"));
    if !path.exists() {
        bail!("claude provider not found: {provider_id}");
    }
    Ok(ClaudeProvider::from_doc(provider_id, &read_toml(&path)?))
}

pub fn write_claude_provider(provider: &ClaudeProvider) -> Result<()> {
    ensure_provider_id(&provider.provider_id)?;
    write_toml(&provider.path(), &provider.to_doc())
}

pub fn extract_current_claude_provider(name: &str) -> Result<ClaudeProvider> {
    let settings = read_json(&claude_settings_path())?;
    let env = settings.get("env").and_then(Value::as_object);
    let mut provider_env = Vec::new();
    for key in CLAUDE_MANAGED_KEYS {
        if let Some(value) = env.and_then(|e| e.get(key)).and_then(Value::as_str)
            && !value.is_empty()
        {
            provider_env.push((key.to_string(), value.to_string()));
        }
    }
    if !provider_env.iter().any(|(k, _)| k == "ANTHROPIC_MODEL")
        && let Some(model) = settings.get("model").and_then(Value::as_str)
    {
        provider_env.push(("ANTHROPIC_MODEL".to_string(), model.to_string()));
    }
    Ok(ClaudeProvider {
        provider_id: name.to_string(),
        env: provider_env,
    })
}

pub fn apply_claude_provider(
    mut settings: Map<String, Value>,
    provider: &ClaudeProvider,
) -> Map<String, Value> {
    if !settings.get("env").is_some_and(Value::is_object) {
        settings.insert("env".to_string(), Value::Object(Map::new()));
    }
    let env = settings.get_mut("env").and_then(Value::as_object_mut);
    if let Some(env) = env {
        for key in CLAUDE_MANAGED_KEYS {
            env.remove(key);
        }
        env.remove(CLAUDE_PROVIDER_ENV);
        env.insert(
            CLAUDE_PROVIDER_ENV.to_string(),
            Value::String(provider.provider_id.clone()),
        );
        for (key, val) in &provider.env {
            if !val.is_empty() {
                env.insert(key.clone(), Value::String(val.clone()));
            }
        }
    }
    if let Some(model) = provider.get("ANTHROPIC_MODEL").filter(|v| !v.is_empty()) {
        settings.insert("model".to_string(), Value::String(model.to_string()));
    } else {
        settings.remove("model");
    }
    settings
}

pub fn cmd_claude_init(name: Option<&str>) -> Result<()> {
    ensure_claude_layout()?;
    let deepseek = claude_providers_dir().join("deepseek.toml");
    if !deepseek.exists() {
        write_claude_provider(&default_deepseek_provider(""))?;
    }
    let current_name = name.unwrap_or("anthropic");
    let current = claude_providers_dir().join(format!("{current_name}.toml"));
    if !current.exists() {
        write_claude_provider(&extract_current_claude_provider(current_name)?)?;
    }
    println!("initialized: {}", claude_providers_dir().display());
    for id in claude_provider_ids()? {
        let provider = load_claude_provider(&id)?;
        println!(
            "claude provider: {} -> {} {}",
            provider.provider_id,
            provider.get("ANTHROPIC_BASE_URL").unwrap_or("-"),
            provider.get("ANTHROPIC_MODEL").unwrap_or("-")
        );
    }
    Ok(())
}

pub fn cmd_claude_use(provider_id: &str) -> Result<()> {
    ensure_claude_layout()?;
    let provider = load_claude_provider(provider_id)?;
    let settings_path = claude_settings_path();
    let before = read_text(&settings_path)?;
    take_snapshot(&settings_path, "claude-settings", provider_id, "json")?;
    let settings = read_json(&settings_path)?;
    let after_doc = apply_claude_provider(settings, &provider);
    let after = serde_json::to_string_pretty(&after_doc)? + "\n";
    write_json(&settings_path, &after_doc)?;
    let d = crate::ux::diff(
        &before,
        &after,
        &settings_path.display().to_string(),
        &settings_path.display().to_string(),
    );
    print_diff(&d);
    ok(format!(
        "claude current: {} -> {} {}",
        provider.provider_id,
        provider.get("ANTHROPIC_BASE_URL").unwrap_or("-"),
        provider.get("ANTHROPIC_MODEL").unwrap_or("-")
    ));
    Ok(())
}

pub fn cmd_claude_status() -> Result<i32> {
    let settings = read_json(&claude_settings_path())?;
    let env = settings.get("env").and_then(Value::as_object);
    let provider_id = env
        .and_then(|e| e.get(CLAUDE_PROVIDER_ENV))
        .and_then(Value::as_str)
        .unwrap_or_default();
    if provider_id.is_empty() {
        controlled_no("-", &["env.CXF_CLAUDE_PROVIDER is missing".to_string()]);
        return Ok(1);
    }
    let provider = match load_claude_provider(provider_id) {
        Ok(p) => p,
        Err(_) => {
            controlled_no(
                "-",
                &[format!("claude provider file is missing: {provider_id}")],
            );
            return Ok(1);
        }
    };
    let mut drift = Vec::new();
    for (key, value) in &provider.env {
        if !value.is_empty()
            && env.and_then(|e| e.get(key)).and_then(Value::as_str) != Some(value.as_str())
        {
            drift.push(format!("env.{key}"));
        }
    }
    for key in CLAUDE_MANAGED_KEYS {
        if !provider.env.iter().any(|(k, v)| k == key && !v.is_empty())
            && env.and_then(|e| e.get(key)).is_some()
        {
            drift.push(format!("env.{key}"));
        }
    }
    let provider_label = format!(
        "{} -> {}",
        provider.provider_id,
        provider.get("ANTHROPIC_BASE_URL").unwrap_or("-")
    );
    if drift.is_empty() {
        controlled_yes(&provider_label);
        return Ok(0);
    }
    controlled_partial(
        &provider_label,
        &drift,
        &format!("fix: cxf claude use {}", provider.provider_id),
    );
    Ok(2)
}

pub fn cmd_claude_current() -> Result<()> {
    let settings = read_json(&claude_settings_path())?;
    let env = settings.get("env").and_then(Value::as_object);
    let get = |key: &str| {
        env.and_then(|e| e.get(key))
            .and_then(Value::as_str)
            .unwrap_or("-")
    };
    let model = env
        .and_then(|e| e.get("ANTHROPIC_MODEL"))
        .and_then(Value::as_str)
        .or_else(|| settings.get("model").and_then(Value::as_str))
        .unwrap_or("-");
    println!("claude_provider\t{}", get(CLAUDE_PROVIDER_ENV));
    println!("base_url\t{}", get("ANTHROPIC_BASE_URL"));
    println!("model\t{model}");
    println!("opus\t{}", get("ANTHROPIC_DEFAULT_OPUS_MODEL"));
    println!("sonnet\t{}", get("ANTHROPIC_DEFAULT_SONNET_MODEL"));
    println!("haiku\t{}", get("ANTHROPIC_DEFAULT_HAIKU_MODEL"));
    println!("subagent\t{}", get("CLAUDE_CODE_SUBAGENT_MODEL"));
    Ok(())
}
