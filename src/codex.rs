use std::fs;

use anyhow::{Result, bail};
use serde_json::Value;
use toml_edit::{DocumentMut, Item, table, value};

use crate::{
    config::{
        BASE_KEYS, auth_path, base_path, codex_config_path, ensure_layout, load_base,
        providers_dir, read_auth, read_text, read_toml, take_snapshot, write_auth,
        write_default_base, write_secret, write_toml,
    },
    models::{
        PROBE_PREFIX, Provider, ensure_provider_id, get_bool, get_i64, get_str,
        provider_id_from_model_provider, provider_table_items,
    },
    ux::{controlled_no, controlled_partial, controlled_yes, ok, print_diff, yellow},
};

pub fn provider_ids() -> Result<Vec<String>> {
    let dir = providers_dir();
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

pub fn load_provider(provider_id: &str) -> Result<Provider> {
    ensure_provider_id(provider_id)?;
    let path = providers_dir().join(format!("{provider_id}.toml"));
    if !path.exists() {
        bail!("provider not found: {provider_id}");
    }
    Ok(Provider::from_doc(provider_id, &read_toml(&path)?))
}

pub fn write_provider(provider: &Provider) -> Result<()> {
    ensure_provider_id(&provider.provider_id)?;
    write_toml(&provider.path(), &provider.to_doc())
}

pub fn read_provider_probe(text: &str) -> String {
    for line in text.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix(PROBE_PREFIX) {
            return rest.trim().to_string();
        }
    }
    String::new()
}

pub fn set_provider_probe(text: &str, provider_id: &str) -> String {
    let mut lines: Vec<String> = text
        .lines()
        .filter(|line| !line.trim().starts_with(PROBE_PREFIX))
        .map(ToString::to_string)
        .collect();
    let probe = format!("{PROBE_PREFIX}{provider_id}");
    if lines
        .first()
        .is_some_and(|line| line.starts_with("#:schema"))
    {
        lines.insert(1, probe);
    } else {
        lines.insert(0, probe);
    }
    lines.join("\n") + "\n"
}

fn managed_model_provider_names() -> Result<Vec<String>> {
    let mut names = Vec::new();
    for id in provider_ids()? {
        if let Ok(provider) = load_provider(&id) {
            names.push(provider.model_providers);
        }
    }
    names.sort();
    names.dedup();
    Ok(names)
}

fn ensure_table(doc: &mut DocumentMut, key: &str) {
    if !doc.get(key).is_some_and(Item::is_table_like) {
        doc[key] = table();
    }
}

pub fn apply_provider(
    mut config: DocumentMut,
    base: &DocumentMut,
    provider: &Provider,
) -> Result<DocumentMut> {
    config.remove("cxf_provider");
    config["model_provider"] = value(&provider.model_providers);
    for key in BASE_KEYS {
        if let Some(item) = base.get(key) {
            config[key] = item.clone();
        }
    }
    if let Some(v) = provider.context_window {
        config["model_context_window"] = value(v);
    }
    if let Some(v) = provider.auto_compact_token_limit {
        config["model_auto_compact_token_limit"] = value(v);
    }

    ensure_table(&mut config, "model_providers");
    for name in managed_model_provider_names()? {
        if name != provider.model_providers {
            config["model_providers"]
                .as_table_like_mut()
                .map(|tbl| tbl.remove(&name));
        }
    }
    config["model_providers"][&provider.model_providers] = table();
    for (key, item) in provider_table_items(provider) {
        config["model_providers"][&provider.model_providers][key] = item;
    }

    ensure_table(&mut config, "features");
    config["features"]["responses_websockets_v2"] = value(provider.websocket);
    Ok(config)
}

fn expected_base_value<'a>(
    base: &'a DocumentMut,
    provider: &'a Provider,
    key: &str,
) -> Option<Item> {
    match key {
        "model_context_window" => provider
            .context_window
            .map(value)
            .or_else(|| base.get(key).cloned()),
        "model_auto_compact_token_limit" => provider
            .auto_compact_token_limit
            .map(value)
            .or_else(|| base.get(key).cloned()),
        _ => base.get(key).cloned(),
    }
}

fn item_eq(actual: Option<&Item>, expected: &Item) -> bool {
    if let Some(expected) = expected.as_str() {
        return actual.and_then(Item::as_str) == Some(expected);
    }
    if let Some(expected) = expected.as_bool() {
        return actual.and_then(Item::as_bool) == Some(expected);
    }
    if let Some(expected) = expected.as_integer() {
        return actual.and_then(Item::as_integer) == Some(expected);
    }
    actual.map(ToString::to_string) == Some(expected.to_string())
}

pub fn provider_drift(
    config: &DocumentMut,
    base: &DocumentMut,
    provider: &Provider,
) -> Vec<String> {
    let mut drift = Vec::new();
    if get_str(config, "model_provider").as_deref() != Some(provider.model_providers.as_str()) {
        drift.push("model_provider".to_string());
    }
    for key in BASE_KEYS {
        if let Some(expected) = expected_base_value(base, provider, key)
            && !item_eq(config.get(key), &expected)
        {
            drift.push(key.to_string());
        }
    }

    for (key, expected) in provider_table_items(provider) {
        if config
            .get("model_providers")
            .and_then(Item::as_table_like)
            .and_then(|tbl| tbl.get(&provider.model_providers))
            .and_then(Item::as_table_like)
            .and_then(|tbl| tbl.get(key))
            .is_none_or(|actual| !item_eq(Some(actual), &expected))
        {
            drift.push(format!(
                "model_providers.{}.{}",
                provider.model_providers, key
            ));
        }
    }

    if config
        .get("features")
        .and_then(|i| i.get("responses_websockets_v2"))
        .and_then(Item::as_bool)
        != Some(provider.websocket)
    {
        drift.push("features.responses_websockets_v2".to_string());
    }
    drift
}

pub fn extract_current_provider(name: &str) -> Result<Provider> {
    let config = read_toml(&codex_config_path())?;
    let model_provider = get_str(&config, "model_provider").unwrap_or_else(|| "OpenAI".to_string());
    let provider_table = config
        .get("model_providers")
        .and_then(|i| i.get(&model_provider));
    let auth = read_auth()?;
    Ok(Provider {
        provider_id: name.to_string(),
        model_providers: model_provider,
        base_url: provider_table
            .and_then(|i| i.get("base_url"))
            .and_then(Item::as_str)
            .unwrap_or_default()
            .to_string(),
        api_key: auth
            .get("OPENAI_API_KEY")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        wire_api: provider_table
            .and_then(|i| i.get("wire_api"))
            .and_then(Item::as_str)
            .unwrap_or("responses")
            .to_string(),
        requires_openai_auth: provider_table
            .and_then(|i| i.get("requires_openai_auth"))
            .and_then(Item::as_bool)
            .unwrap_or(true),
        websocket: provider_table
            .and_then(|i| i.get("supports_websockets"))
            .and_then(Item::as_bool)
            .unwrap_or(false),
        context_window: get_i64(&config, "model_context_window"),
        auto_compact_token_limit: get_i64(&config, "model_auto_compact_token_limit"),
    })
}

pub fn extract_all_providers(current_name: Option<&str>) -> Result<Vec<Provider>> {
    let config = read_toml(&codex_config_path())?;
    let current_model_provider =
        get_str(&config, "model_provider").unwrap_or_else(|| "OpenAI".to_string());
    let Some(providers) = config.get("model_providers").and_then(Item::as_table_like) else {
        return Ok(vec![extract_current_provider(current_name.unwrap_or(
            &provider_id_from_model_provider(&current_model_provider),
        ))?]);
    };

    let auth = read_auth()?;
    let api_key = auth
        .get("OPENAI_API_KEY")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let mut out = Vec::new();
    let mut used = Vec::<String>::new();
    for (model_provider, table) in providers.iter() {
        if !table.is_table_like() {
            continue;
        }
        let mut provider_id = if current_name.is_some() && model_provider == current_model_provider
        {
            current_name.unwrap_or_default().to_string()
        } else {
            provider_id_from_model_provider(model_provider)
        };
        let original = provider_id.clone();
        let mut suffix = 2;
        while used.contains(&provider_id) {
            provider_id = format!("{original}-{suffix}");
            suffix += 1;
        }
        used.push(provider_id.clone());
        out.push(Provider {
            provider_id,
            model_providers: model_provider.to_string(),
            base_url: table
                .get("base_url")
                .and_then(Item::as_str)
                .unwrap_or_default()
                .to_string(),
            api_key: api_key.clone(),
            wire_api: table
                .get("wire_api")
                .and_then(Item::as_str)
                .unwrap_or("responses")
                .to_string(),
            requires_openai_auth: table
                .get("requires_openai_auth")
                .and_then(Item::as_bool)
                .unwrap_or(true),
            websocket: table
                .get("supports_websockets")
                .and_then(Item::as_bool)
                .unwrap_or(false),
            context_window: get_i64(&config, "model_context_window"),
            auto_compact_token_limit: get_i64(&config, "model_auto_compact_token_limit"),
        });
    }
    Ok(out)
}

pub fn cmd_init(name: Option<&str>) -> Result<()> {
    ensure_layout()?;
    write_default_base()?;
    let providers = extract_all_providers(name)?;
    for provider in &providers {
        write_provider(provider)?;
    }
    println!("initialized: {}", providers_dir().display());
    for provider in providers {
        println!(
            "provider: {} -> {} {}",
            provider.provider_id, provider.model_providers, provider.base_url
        );
    }
    Ok(())
}

fn warn_if_no_base() {
    if !base_path().exists() {
        eprintln!(
            "{} warning: {} not found, run `cxf init` first",
            yellow("!"),
            base_path().display()
        );
    }
}

pub fn cmd_use(provider_id: &str) -> Result<()> {
    ensure_layout()?;
    warn_if_no_base();
    let provider = load_provider(provider_id)?;
    let base = load_base()?;
    let config_path = codex_config_path();
    let auth_path = auth_path();
    let before_config = read_text(&config_path)?;
    let before_auth = read_text(&auth_path)?;
    take_snapshot(
        &config_path,
        "codex-config",
        &read_provider_probe(&before_config),
        "toml",
    )?;
    let config = read_toml(&config_path)?;
    let after_doc = apply_provider(config, &base, &provider)?;
    let after_config = set_provider_probe(&after_doc.to_string(), &provider.provider_id);
    write_secret(&config_path, after_config.as_bytes())?;
    if provider.api_key.is_empty() {
        // OAuth provider — clear stale API key from auth.json
        let empty = serde_json::Map::new();
        crate::config::write_json(&auth_path, &empty)?;
    } else {
        write_auth(&provider.api_key)?;
    }
    let after_auth = read_text(&auth_path)?;
    let config_diff = crate::ux::diff(
        &before_config,
        &after_config,
        &config_path.display().to_string(),
        &config_path.display().to_string(),
    );
    let auth_diff = crate::ux::diff(
        &before_auth,
        &after_auth,
        &auth_path.display().to_string(),
        &auth_path.display().to_string(),
    );
    print_diff(&config_diff);
    print_diff(&auth_diff);
    ok(format!(
        "current: {} -> {} {}",
        provider.provider_id, provider.model_providers, provider.base_url
    ));
    Ok(())
}

pub fn cmd_status() -> Result<i32> {
    warn_if_no_base();
    let raw = read_text(&codex_config_path())?;
    let provider_id = read_provider_probe(&raw);
    if provider_id.is_empty() {
        controlled_no("-", &["cxf provider comment is missing".to_string()]);
        return Ok(1);
    }
    let provider = match load_provider(&provider_id) {
        Ok(p) => p,
        Err(_) => {
            controlled_no("-", &[format!("provider file is missing: {provider_id}")]);
            return Ok(1);
        }
    };
    let config = read_toml(&codex_config_path())?;
    let auth = read_auth()?;
    let auth_ok = if provider.api_key.is_empty() {
        true // OAuth provider — no API key to check
    } else {
        auth.get("OPENAI_API_KEY").and_then(Value::as_str) == Some(provider.api_key.as_str())
    };
    let drift = provider_drift(&config, &load_base()?, &provider);
    let provider_label = format!("{} -> {}", provider.provider_id, provider.model_providers);
    if drift.is_empty() && auth_ok {
        controlled_yes(&provider_label);
        return Ok(0);
    }
    let mut items = drift;
    if !auth_ok {
        items.push("auth OPENAI_API_KEY".to_string());
    }
    controlled_partial(
        &provider_label,
        &items,
        &format!("fix: cxf use {}", provider.provider_id),
    );
    Ok(2)
}

pub fn cmd_current() -> Result<()> {
    let raw = read_text(&codex_config_path())?;
    let config = read_toml(&codex_config_path())?;
    let provider_id = read_provider_probe(&raw);
    let model_provider = get_str(&config, "model_provider").unwrap_or_else(|| "-".to_string());
    let base_url = config
        .get("model_providers")
        .and_then(|i| i.get(&model_provider))
        .and_then(|i| i.get("base_url"))
        .and_then(Item::as_str)
        .unwrap_or("-");
    println!(
        "provider\t{}",
        if provider_id.is_empty() {
            "-"
        } else {
            &provider_id
        }
    );
    println!("model_provider\t{model_provider}");
    println!(
        "model\t{}",
        get_str(&config, "model").unwrap_or_else(|| "-".to_string())
    );
    println!(
        "review_model\t{}",
        get_str(&config, "review_model").unwrap_or_else(|| "-".to_string())
    );
    println!("base_url\t{base_url}");
    println!(
        "websocket\t{}",
        get_bool(&config, "responses_websockets_v2")
            .or_else(|| config
                .get("features")
                .and_then(|i| i.get("responses_websockets_v2"))
                .and_then(Item::as_bool))
            .map(|v| if v { "on" } else { "off" })
            .unwrap_or("-")
    );
    println!(
        "context_window\t{}",
        get_i64(&config, "model_context_window")
            .map(|v| v.to_string())
            .unwrap_or_else(|| "-".to_string())
    );
    println!(
        "auto_compact\t{}",
        get_i64(&config, "model_auto_compact_token_limit")
            .map(|v| v.to_string())
            .unwrap_or_else(|| "-".to_string())
    );
    Ok(())
}
