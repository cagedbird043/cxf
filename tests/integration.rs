use std::{error::Error, fs, path::Path, process::Command};

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_cxf")
}

fn run(home: &Path, args: &[&str]) -> Result<std::process::Output, Box<dyn Error>> {
    Ok(Command::new(bin())
        .env("HOME", home)
        .env("XDG_CONFIG_HOME", home.join(".config"))
        .env("XDG_STATE_HOME", home.join(".local/state"))
        .args(args)
        .output()?)
}

#[test]
fn codex_use_preserves_unrelated_config_and_status_is_clean_with_overrides()
-> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;
    fs::write(
        home.join(".codex/config.toml"),
        r#"model_provider = "Other"

[model_providers.Other]
base_url = "https://other.example"

[projects."/home/user/project"]
trust_level = "trusted"

[features]
shell_tool = true
"#,
    )?;
    fs::write(
        home.join(".config/cxf/base.toml"),
        r#"model = "gpt-5.5"
review_model = "gpt-5.4"
model_reasoning_effort = "high"
model_context_window = 272000
model_auto_compact_token_limit = 240000
"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/timi.toml"),
        r#"model_providers = "OpenAI"
base_url = "https://timicc.com"
api_key = "sk-test"
wire_api = "responses"
requires_openai_auth = true
websocket = true
context_window = 1000000
auto_compact_token_limit = 900000
"#,
    )?;

    let out = run(home, &["use", "timi"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let config = fs::read_to_string(home.join(".codex/config.toml"))?;
    assert!(config.contains("# cxf: provider = timi"));
    assert!(config.contains("base_url = \"https://timicc.com\""));
    assert!(config.contains("trust_level = \"trusted\""));
    assert!(config.contains("shell_tool = true"));
    assert!(config.contains("model_context_window = 1000000"));
    assert!(config.contains("model_auto_compact_token_limit = 900000"));

    let status = run(home, &["status"])?;
    assert!(
        status.status.success(),
        "{}",
        String::from_utf8_lossy(&status.stdout)
    );
    assert!(String::from_utf8_lossy(&status.stdout).contains("controlled: yes"));
    Ok(())
}

#[test]
fn claude_use_cleans_managed_keys_and_status_is_clean() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".claude"))?;
    fs::create_dir_all(home.join(".config/cxf/claude/providers"))?;
    fs::write(
        home.join(".claude/settings.json"),
        r#"{
  "model": "old-model",
  "env": {
    "GITHUB_TOKEN": "keep",
    "ANTHROPIC_API_KEY": "old",
    "ANTHROPIC_MODEL": "old-model"
  }
}
"#,
    )?;
    fs::write(
        home.join(".config/cxf/claude/providers/deepseek.toml"),
        r#"[env]
ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
ANTHROPIC_AUTH_TOKEN = "sk-test"
"#,
    )?;

    let out = run(home, &["claude", "use", "deepseek"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let settings = fs::read_to_string(home.join(".claude/settings.json"))?;
    assert!(settings.contains("\"GITHUB_TOKEN\": \"keep\""));
    assert!(settings.contains("\"CXF_CLAUDE_PROVIDER\": \"deepseek\""));
    assert!(!settings.contains("ANTHROPIC_API_KEY"));
    assert!(!settings.contains("\"model\""));

    let status = run(home, &["claude", "status"])?;
    assert!(
        status.status.success(),
        "{}",
        String::from_utf8_lossy(&status.stdout)
    );
    Ok(())
}

#[test]
fn init_extracts_existing_codex_provider_and_current_reports_it() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::write(
        home.join(".codex/config.toml"),
        r#"model = "gpt-5.5"
model_provider = "OpenAI"

[model_providers.OpenAI]
name = "OpenAI"
base_url = "https://api.openai.example"
wire_api = "responses"
supports_websockets = true
requires_openai_auth = true
"#,
    )?;
    fs::write(
        home.join(".codex/auth.json"),
        r#"{"OPENAI_API_KEY":"sk-existing"}"#,
    )?;

    let out = run(home, &["init", "openai"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let provider = fs::read_to_string(home.join(".config/cxf/providers/openai.toml"))?;
    assert!(provider.contains("base_url = \"https://api.openai.example\""));
    assert!(provider.contains("api_key = \"sk-existing\""));
    let config = fs::read_to_string(home.join(".codex/config.toml"))?;
    assert!(config.contains("# cxf: provider = openai"));

    assert_eq!(
        fs::read_to_string(home.join(".config/cxf/auth/codex/openai.json"))?,
        r#"{"OPENAI_API_KEY":"sk-existing"}"#,
        "init should save the current live auth profile before any future switch"
    );
    fs::write(
        home.join(".codex/auth.json"),
        r#"{"OPENAI_API_KEY":"sk-refreshed"}"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/timi.toml"),
        r#"model_providers = "OpenAI"
base_url = "https://timicc.com"
api_key = "sk-timi"
wire_api = "responses"
requires_openai_auth = true
websocket = false
"#,
    )?;
    let switched = run(home, &["use", "timi"])?;
    assert!(
        switched.status.success(),
        "{}",
        String::from_utf8_lossy(&switched.stderr)
    );
    assert_eq!(
        fs::read_to_string(home.join(".config/cxf/auth/codex/openai.json"))?,
        r#"{"OPENAI_API_KEY":"sk-refreshed"}"#,
        "first post-init switch should save refreshed live auth using the init probe"
    );

    let list = run(home, &["list"])?;
    assert!(
        list.status.success(),
        "{}",
        String::from_utf8_lossy(&list.stderr)
    );
    assert!(String::from_utf8_lossy(&list.stdout).contains("openai"));
    Ok(())
}

#[test]
fn add_remove_and_rename_provider_noninteractive() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    let add = run(
        home,
        &[
            "add",
            "--provider-id",
            "one",
            "--base-url",
            "https://one.example",
            "--api-key",
            "sk-one",
            "--wire-api",
            "chat",
            "--no-websocket",
        ],
    )?;
    assert!(
        add.status.success(),
        "{}",
        String::from_utf8_lossy(&add.stderr)
    );
    let provider = fs::read_to_string(home.join(".config/cxf/providers/one.toml"))?;
    assert!(provider.contains("wire_api = \"chat\""));
    assert!(provider.contains("websocket = false"));

    let rename = run(home, &["rename", "one", "two"])?;
    assert!(
        rename.status.success(),
        "{}",
        String::from_utf8_lossy(&rename.stderr)
    );
    assert!(!home.join(".config/cxf/providers/one.toml").exists());
    assert!(home.join(".config/cxf/providers/two.toml").exists());

    let remove = run(home, &["remove", "two", "-y"])?;
    assert!(
        remove.status.success(),
        "{}",
        String::from_utf8_lossy(&remove.stderr)
    );
    assert!(!home.join(".config/cxf/providers/two.toml").exists());
    Ok(())
}

#[test]
fn claude_current_falls_back_to_top_level_model() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".claude"))?;
    fs::write(
        home.join(".claude/settings.json"),
        r#"{
  "model": "top-level-model",
  "env": {
    "CXF_CLAUDE_PROVIDER": "anthropic",
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com"
  }
}
"#,
    )?;
    let current = run(home, &["claude", "current"])?;
    assert!(
        current.status.success(),
        "{}",
        String::from_utf8_lossy(&current.stderr)
    );
    assert!(String::from_utf8_lossy(&current.stdout).contains("top-level-model"));
    Ok(())
}

#[test]
fn codex_status_with_drift() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;
    fs::write(
        home.join(".codex/config.toml"),
        r#"model_provider = "OpenAI"

[model_providers.OpenAI]
base_url = "https://timicc.com"
wire_api = "responses"
supports_websockets = false
requires_openai_auth = true
"#,
    )?;
    fs::write(
        home.join(".config/cxf/base.toml"),
        r#"model = "gpt-5.5"
review_model = "gpt-5.5"
"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/timi.toml"),
        r#"model_providers = "OpenAI"
base_url = "https://timicc.com"
api_key = "sk-test"
wire_api = "responses"
requires_openai_auth = true
websocket = false
"#,
    )?;
    fs::write(
        home.join(".codex/auth.json"),
        r#"{"OPENAI_API_KEY":"sk-test"}"#,
    )?;

    // Apply provider first so config is fully populated by cxf
    let apply = run(home, &["use", "timi"])?;
    assert!(
        apply.status.success(),
        "{}",
        String::from_utf8_lossy(&apply.stderr)
    );

    // Status should be clean after apply
    let status = run(home, &["status"])?;
    assert!(
        status.status.success(),
        "{}",
        String::from_utf8_lossy(&status.stdout)
    );
    assert!(String::from_utf8_lossy(&status.stdout).contains("controlled: yes"));

    // Introduce drift: change base_url
    let config_path = home.join(".codex/config.toml");
    let mut config = fs::read_to_string(&config_path)?;
    config = config.replace("https://timicc.com", "https://drifted.example");
    fs::write(&config_path, config)?;

    let status2 = run(home, &["status"])?;
    assert!(
        !status2.status.success(),
        "status should exit non-zero with drift"
    );
    let out = String::from_utf8_lossy(&status2.stdout);
    assert!(
        out.contains("controlled: partial"),
        "expected partial, got: {out}"
    );
    Ok(())
}

#[test]
fn codex_use_before_init_warns_when_base_toml_missing() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;
    // No base.toml
    fs::write(
        home.join(".codex/config.toml"),
        r##"# cxf: provider = timi
model_provider = "OpenAI"

[model_providers.OpenAI]
base_url = "https://timicc.com"
"##,
    )?;
    fs::write(
        home.join(".config/cxf/providers/timi.toml"),
        r#"model_providers = "OpenAI"
base_url = "https://timicc.com"
api_key = "sk-test"
wire_api = "responses"
requires_openai_auth = true
websocket = false
"#,
    )?;
    fs::write(
        home.join(".codex/auth.json"),
        r#"{"OPENAI_API_KEY":"sk-test"}"#,
    )?;

    let out = run(home, &["use", "timi"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("warning") && stderr.contains("base.toml"),
        "expected warning about base.toml, stderr: {stderr}"
    );
    Ok(())
}

#[test]
fn codex_use_rejects_malformed_auth_json() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;
    fs::write(
        home.join(".codex/config.toml"),
        r##"# cxf: provider = timi
model_provider = "OpenAI"

[model_providers.OpenAI]
base_url = "https://timicc.com"
"##,
    )?;
    fs::write(
        home.join(".config/cxf/base.toml"),
        r#"model = "gpt-5.5"
review_model = "gpt-5.5"
"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/timi.toml"),
        r#"model_providers = "OpenAI"
base_url = "https://timicc.com"
api_key = "sk-test"
wire_api = "responses"
requires_openai_auth = true
websocket = false
"#,
    )?;
    // Broken JSON
    fs::write(home.join(".codex/auth.json"), r#"{broken"#)?;

    let out = run(home, &["use", "timi"])?;
    assert!(
        !out.status.success(),
        "should fail with malformed auth.json"
    );
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("invalid JSON"),
        "expected JSON parse error, got: {stderr}"
    );
    Ok(())
}

#[test]
fn claude_add_and_rename_noninteractive() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    let add = run(
        home,
        &[
            "claude",
            "add",
            "--provider-id",
            "my-provider",
            "--base-url",
            "https://my.example",
            "--api-key",
            "sk-my",
            "--model",
            "my-model",
        ],
    )?;
    assert!(
        add.status.success(),
        "{}",
        String::from_utf8_lossy(&add.stderr)
    );

    let provider = fs::read_to_string(home.join(".config/cxf/claude/providers/my-provider.toml"))?;
    assert!(provider.contains(r#"ANTHROPIC_BASE_URL = "https://my.example""#));
    assert!(provider.contains(r#"ANTHROPIC_AUTH_TOKEN = "sk-my""#));
    assert!(provider.contains(r#"ANTHROPIC_MODEL = "my-model""#));

    let rename = run(home, &["claude", "rename", "my-provider", "renamed"])?;
    assert!(
        rename.status.success(),
        "{}",
        String::from_utf8_lossy(&rename.stderr)
    );
    assert!(
        !home
            .join(".config/cxf/claude/providers/my-provider.toml")
            .exists()
    );
    assert!(
        home.join(".config/cxf/claude/providers/renamed.toml")
            .exists()
    );
    Ok(())
}

#[test]
fn completion_contains_provider_functions() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let out = run(tmp.path(), &["completion", "zsh"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(text.contains("_cxf_provider_ids"));
    assert!(text.contains("_cxf_claude_provider_ids"));
    Ok(())
}

#[test]
fn codex_use_oauth_without_profile_preserves_existing_auth_json() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;

    fs::write(
        home.join(".codex/config.toml"),
        r##"# cxf: provider = timi
model_provider = "OpenAI"

[model_providers.OpenAI]
base_url = "https://timicc.com"
"##,
    )?;
    fs::write(
        home.join(".config/cxf/base.toml"),
        r#"model = "gpt-5.5"
review_model = "gpt-5.5"
"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/oauth.toml"),
        r#"model_providers = "OpenAI"
base_url = ""
api_key = ""
wire_api = "responses"
requires_openai_auth = true
websocket = true
"#,
    )?;

    let existing_auth = "{\n  \"OPENAI_API_KEY\": \"sk-test\"\n}\n";
    fs::write(home.join(".codex/auth.json"), existing_auth)?;

    let out = run(home, &["use", "oauth"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let content = fs::read_to_string(home.join(".codex/auth.json"))?;
    assert_eq!(
        content, existing_auth,
        "OAuth provider without auth profile should not destroy live auth"
    );
    assert_eq!(
        fs::read_to_string(home.join(".config/cxf/auth/codex/timi.json"))?,
        existing_auth,
        "previous provider auth should be saved as a profile"
    );

    Ok(())
}

#[test]
fn codex_use_api_key_saves_oauth_profile_and_bootstraps_target() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;

    fs::write(
        home.join(".codex/config.toml"),
        r##"# cxf: provider = official
model_provider = "OpenAI"

[model_providers.OpenAI]
"##,
    )?;
    fs::write(
        home.join(".config/cxf/base.toml"),
        r#"model = "gpt-5.5"
review_model = "gpt-5.5"
"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/timi.toml"),
        r#"model_providers = "OpenAI"
base_url = "https://timicc.com"
api_key = "sk-test"
wire_api = "responses"
requires_openai_auth = true
websocket = false
"#,
    )?;
    let oauth_auth = r#"{
  "auth_mode": "chatgpt",
  "OPENAI_API_KEY": null,
  "tokens": {
    "id_token": "id",
    "access_token": "access",
    "refresh_token": "refresh",
    "account_id": "account"
  },
  "last_refresh": "2026-06-05T16:05:15.057134715Z"
}
"#;
    fs::write(home.join(".codex/auth.json"), oauth_auth)?;

    let out = run(home, &["use", "timi"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let api_auth = "{\n  \"OPENAI_API_KEY\": \"sk-test\"\n}\n";
    assert_eq!(fs::read_to_string(home.join(".codex/auth.json"))?, api_auth);
    assert_eq!(
        fs::read_to_string(home.join(".config/cxf/auth/codex/official.json"))?,
        oauth_auth,
        "OAuth auth should be saved as an opaque provider profile"
    );
    assert_eq!(
        fs::read_to_string(home.join(".config/cxf/auth/codex/timi.json"))?,
        api_auth,
        "API-key auth should be bootstrapped as a provider profile"
    );

    Ok(())
}

#[test]
fn codex_use_restores_target_auth_profile_byte_for_byte() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;
    fs::create_dir_all(home.join(".config/cxf/auth/codex"))?;

    fs::write(
        home.join(".codex/config.toml"),
        r##"# cxf: provider = timi
model_provider = "OpenAI"

[model_providers.OpenAI]
base_url = "https://timicc.com"
"##,
    )?;
    fs::write(
        home.join(".config/cxf/base.toml"),
        r#"model = "gpt-5.5"
review_model = "gpt-5.5"
"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/official.toml"),
        r#"model_providers = "OpenAI"
base_url = ""
api_key = ""
wire_api = "responses"
requires_openai_auth = true
websocket = true
"#,
    )?;

    let api_auth = "{\n  \"OPENAI_API_KEY\": \"sk-test\"\n}\n";
    fs::write(home.join(".codex/auth.json"), api_auth)?;
    let oauth_auth = r#"{
  "auth_mode": "chatgpt",
  "OPENAI_API_KEY": null,
  "tokens": {
    "refresh_token": "refresh"
  },
  "last_refresh": "2026-06-05T16:05:15.057134715Z"
}
"#;
    fs::write(
        home.join(".config/cxf/auth/codex/official.json"),
        oauth_auth,
    )?;

    let out = run(home, &["use", "official"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(
        fs::read_to_string(home.join(".codex/auth.json"))?,
        oauth_auth,
        "target auth profile should be restored byte-for-byte"
    );
    assert_eq!(
        fs::read_to_string(home.join(".config/cxf/auth/codex/timi.json"))?,
        api_auth,
        "previous live auth should be saved before restore"
    );

    Ok(())
}

#[test]
fn codex_use_imports_legacy_auth_snapshot_as_profile() -> Result<(), Box<dyn Error>> {
    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;
    fs::create_dir_all(home.join(".local/state/cxf/snapshots"))?;

    fs::write(
        home.join(".codex/config.toml"),
        r##"# cxf: provider = timi
model_provider = "OpenAI"

[model_providers.OpenAI]
base_url = "https://timicc.com"
"##,
    )?;
    fs::write(
        home.join(".config/cxf/base.toml"),
        r#"model = "gpt-5.5"
review_model = "gpt-5.5"
"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/official.toml"),
        r#"model_providers = "OpenAI"
base_url = ""
api_key = ""
wire_api = "responses"
requires_openai_auth = true
websocket = true
"#,
    )?;

    fs::write(
        home.join(".codex/auth.json"),
        "{\n  \"OPENAI_API_KEY\": \"sk-test\"\n}\n",
    )?;
    let oauth_auth = r#"{
  "auth_mode": "chatgpt",
  "OPENAI_API_KEY": null,
  "tokens": {
    "refresh_token": "refresh"
  }
}
"#;
    fs::write(
        home.join(".local/state/cxf/snapshots/codex-auth-official.json"),
        oauth_auth,
    )?;

    let out = run(home, &["use", "official"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(
        fs::read_to_string(home.join(".codex/auth.json"))?,
        oauth_auth
    );
    assert_eq!(
        fs::read_to_string(home.join(".config/cxf/auth/codex/official.json"))?,
        oauth_auth,
        "legacy snapshot should be imported into normal auth profile storage"
    );

    Ok(())
}

#[cfg(unix)]
#[test]
fn codex_use_restored_auth_profile_resets_live_auth_permissions() -> Result<(), Box<dyn Error>> {
    use std::os::unix::fs::PermissionsExt;

    let tmp = tempfile::tempdir()?;
    let home = tmp.path();
    fs::create_dir_all(home.join(".codex"))?;
    fs::create_dir_all(home.join(".config/cxf/providers"))?;
    fs::create_dir_all(home.join(".config/cxf/auth/codex"))?;

    fs::write(
        home.join(".codex/config.toml"),
        r##"# cxf: provider = timi
model_provider = "OpenAI"

[model_providers.OpenAI]
base_url = "https://timicc.com"
"##,
    )?;
    fs::write(
        home.join(".config/cxf/base.toml"),
        r#"model = "gpt-5.5"
review_model = "gpt-5.5"
"#,
    )?;
    fs::write(
        home.join(".config/cxf/providers/official.toml"),
        r#"model_providers = "OpenAI"
base_url = ""
api_key = ""
wire_api = "responses"
requires_openai_auth = true
websocket = true
"#,
    )?;

    let auth_path = home.join(".codex/auth.json");
    fs::write(&auth_path, "{\n  \"OPENAI_API_KEY\": \"sk-test\"\n}\n")?;
    let mut perms = fs::metadata(&auth_path)?.permissions();
    perms.set_mode(0o644);
    fs::set_permissions(&auth_path, perms)?;

    let oauth_auth = r#"{
  "auth_mode": "chatgpt",
  "OPENAI_API_KEY": null,
  "tokens": {
    "refresh_token": "refresh"
  }
}
"#;
    fs::write(
        home.join(".config/cxf/auth/codex/official.json"),
        oauth_auth,
    )?;

    let out = run(home, &["use", "official"])?;
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(fs::metadata(auth_path)?.permissions().mode() & 0o777, 0o600);

    Ok(())
}
