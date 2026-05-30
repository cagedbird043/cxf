use std::path::PathBuf;

use anyhow::{Result, bail};
use toml_edit::{DocumentMut, Item, table, value};

use crate::config::{claude_providers_dir, providers_dir};

pub const PROBE_PREFIX: &str = "# cxf: provider = ";
pub const CLAUDE_PROVIDER_ENV: &str = "CXF_CLAUDE_PROVIDER";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Provider {
    pub provider_id: String,
    pub model_providers: String,
    pub base_url: String,
    pub api_key: String,
    pub wire_api: String,
    pub requires_openai_auth: bool,
    pub websocket: bool,
    pub context_window: Option<i64>,
    pub auto_compact_token_limit: Option<i64>,
}

impl Provider {
    pub fn path(&self) -> PathBuf {
        providers_dir().join(format!("{}.toml", self.provider_id))
    }

    pub fn from_doc(provider_id: impl Into<String>, doc: &DocumentMut) -> Self {
        Self {
            provider_id: provider_id.into(),
            model_providers: get_str(doc, "model_providers")
                .unwrap_or_else(|| "OpenAI".to_string()),
            base_url: get_str(doc, "base_url").unwrap_or_default(),
            api_key: get_str(doc, "api_key").unwrap_or_default(),
            wire_api: get_str(doc, "wire_api").unwrap_or_else(|| "responses".to_string()),
            requires_openai_auth: get_bool(doc, "requires_openai_auth").unwrap_or(true),
            websocket: get_bool(doc, "websocket").unwrap_or(true),
            context_window: get_i64(doc, "context_window"),
            auto_compact_token_limit: get_i64(doc, "auto_compact_token_limit"),
        }
    }

    pub fn to_doc(&self) -> DocumentMut {
        let mut doc = DocumentMut::new();
        doc["model_providers"] = value(&self.model_providers);
        doc["base_url"] = value(&self.base_url);
        doc["api_key"] = value(&self.api_key);
        doc["wire_api"] = value(&self.wire_api);
        doc["requires_openai_auth"] = value(self.requires_openai_auth);
        doc["websocket"] = value(self.websocket);
        if let Some(v) = self.context_window {
            doc["context_window"] = value(v);
        }
        if let Some(v) = self.auto_compact_token_limit {
            doc["auto_compact_token_limit"] = value(v);
        }
        doc
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClaudeProvider {
    pub provider_id: String,
    pub env: Vec<(String, String)>,
}

impl ClaudeProvider {
    pub fn path(&self) -> PathBuf {
        claude_providers_dir().join(format!("{}.toml", self.provider_id))
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        self.env
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.as_str())
    }

    pub fn from_doc(provider_id: impl Into<String>, doc: &DocumentMut) -> Self {
        let mut env = Vec::new();
        if let Some(tbl) = doc.get("env").and_then(Item::as_table_like) {
            for (k, item) in tbl.iter() {
                if let Some(v) = item.as_str() {
                    env.push((k.to_string(), v.to_string()));
                }
            }
        }
        Self {
            provider_id: provider_id.into(),
            env,
        }
    }

    pub fn to_doc(&self) -> DocumentMut {
        let mut doc = DocumentMut::new();
        doc["env"] = table();
        for (k, v) in &self.env {
            doc["env"][k] = value(v);
        }
        doc
    }
}

pub fn provider_table_items(provider: &Provider) -> Vec<(&'static str, Item)> {
    vec![
        ("name", value(&provider.model_providers)),
        ("base_url", value(&provider.base_url)),
        ("wire_api", value(&provider.wire_api)),
        ("supports_websockets", value(provider.websocket)),
        ("requires_openai_auth", value(provider.requires_openai_auth)),
    ]
}

pub fn provider_id_from_model_provider(name: &str) -> String {
    let mut out = String::new();
    let mut dash = false;
    for ch in name.trim().chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' || ch == '-' {
            out.push(ch.to_ascii_lowercase());
            dash = false;
        } else if !dash && !out.is_empty() {
            out.push('-');
            dash = true;
        }
    }
    while out.ends_with('-') {
        out.pop();
    }
    if out.is_empty() {
        "provider".to_string()
    } else {
        out
    }
}

pub fn ensure_provider_id(id: &str) -> Result<()> {
    if id.trim().is_empty() {
        bail!("provider id is required");
    }
    if id.contains('/') || id.contains('\\') || id == "." || id == ".." {
        bail!("invalid provider id: {id}");
    }
    Ok(())
}

pub fn get_str(doc: &DocumentMut, key: &str) -> Option<String> {
    doc.get(key).and_then(Item::as_str).map(ToString::to_string)
}

pub fn get_bool(doc: &DocumentMut, key: &str) -> Option<bool> {
    doc.get(key).and_then(Item::as_bool)
}

pub fn get_i64(doc: &DocumentMut, key: &str) -> Option<i64> {
    doc.get(key).and_then(Item::as_integer)
}
