use std::{env, fs, process::Command};

use anyhow::{Result, bail};
use clap::{Args, Parser, Subcommand};

use crate::{
    claude::{
        claude_provider_ids, cmd_claude_current, cmd_claude_init, cmd_claude_status,
        cmd_claude_use, load_claude_provider, write_claude_provider,
    },
    codex::{
        cmd_current, cmd_init, cmd_status, cmd_use, load_provider, provider_ids, write_provider,
    },
    config::{claude_providers_dir, ensure_claude_layout, ensure_layout, providers_dir},
    models::{ClaudeProvider, Provider, ensure_provider_id},
    ux::{confirm, ok, print_rows, prompt, prompt_bool},
};

#[derive(Parser)]
#[command(
    name = "cxf",
    version,
    about = "Codex / Claude provider pointer manager"
)]
struct Cli {
    #[command(subcommand)]
    command: Option<CommandKind>,
}

#[derive(Subcommand)]
enum CommandKind {
    Init {
        name: Option<String>,
    },
    List,
    Current,
    Use {
        provider: String,
    },
    Add(AddArgs),
    Edit {
        provider: String,
        #[arg(short, long)]
        yes: bool,
    },
    Remove {
        provider: String,
        #[arg(short, long)]
        yes: bool,
    },
    Rename {
        old: String,
        new: String,
    },
    Status,
    Completion {
        #[arg(default_value = "zsh")]
        shell: String,
    },
    Claude {
        #[command(subcommand)]
        command: ClaudeCommand,
    },
}

#[derive(Args)]
struct AddArgs {
    #[arg(long)]
    provider_id: Option<String>,
    #[arg(long)]
    model_providers: Option<String>,
    #[arg(long)]
    base_url: Option<String>,
    #[arg(long)]
    api_key: Option<String>,
    #[arg(long)]
    oauth: bool,
    #[arg(long)]
    wire_api: Option<String>,
    #[arg(long)]
    no_websocket: bool,
    #[arg(long)]
    context_window: Option<i64>,
    #[arg(long)]
    auto_compact: Option<i64>,
}

#[derive(Subcommand)]
enum ClaudeCommand {
    Init {
        name: Option<String>,
    },
    List,
    Current,
    Use {
        provider: String,
    },
    Add(ClaudeAddArgs),
    Edit {
        provider: String,
    },
    Remove {
        provider: String,
        #[arg(short, long)]
        yes: bool,
    },
    Rename {
        old: String,
        new: String,
    },
    Status,
}

#[derive(Args)]
struct ClaudeAddArgs {
    #[arg(long)]
    provider_id: Option<String>,
    #[arg(long)]
    base_url: Option<String>,
    #[arg(long)]
    api_key: Option<String>,
    #[arg(long)]
    model: Option<String>,
}

pub fn run() -> Result<()> {
    let cli = Cli::parse();
    let code = match cli.command {
        None => {
            use clap::CommandFactory;
            Cli::command().print_help()?;
            println!();
            0
        }
        Some(CommandKind::Init { name }) => {
            cmd_init(name.as_deref())?;
            0
        }
        Some(CommandKind::List) => {
            cmd_list()?;
            0
        }
        Some(CommandKind::Current) => {
            cmd_current()?;
            0
        }
        Some(CommandKind::Use { provider }) => {
            cmd_use(&provider)?;
            0
        }
        Some(CommandKind::Add(args)) => {
            cmd_add(args)?;
            0
        }
        Some(CommandKind::Edit { provider, yes }) => {
            cmd_edit(&provider, yes)?;
            0
        }
        Some(CommandKind::Remove { provider, yes }) => {
            cmd_remove(&provider, yes)?;
            0
        }
        Some(CommandKind::Rename { old, new }) => {
            cmd_rename(&old, &new)?;
            0
        }
        Some(CommandKind::Status) => cmd_status()?,
        Some(CommandKind::Completion { shell }) => {
            cmd_completion(&shell)?;
            0
        }
        Some(CommandKind::Claude { command }) => match command {
            ClaudeCommand::Init { name } => {
                cmd_claude_init(name.as_deref())?;
                0
            }
            ClaudeCommand::List => {
                cmd_claude_list()?;
                0
            }
            ClaudeCommand::Current => {
                cmd_claude_current()?;
                0
            }
            ClaudeCommand::Use { provider } => {
                cmd_claude_use(&provider)?;
                0
            }
            ClaudeCommand::Add(args) => {
                cmd_claude_add(args)?;
                0
            }
            ClaudeCommand::Edit { provider } => {
                cmd_claude_edit(&provider)?;
                0
            }
            ClaudeCommand::Remove { provider, yes } => {
                cmd_claude_remove(&provider, yes)?;
                0
            }
            ClaudeCommand::Rename { old, new } => {
                cmd_claude_rename(&old, &new)?;
                0
            }
            ClaudeCommand::Status => cmd_claude_status()?,
        },
    };
    if code != 0 {
        std::process::exit(code);
    }
    Ok(())
}

fn cmd_list() -> Result<()> {
    ensure_layout()?;
    let mut rows = Vec::new();
    for id in provider_ids()? {
        let p = load_provider(&id)?;
        rows.push(vec![
            p.provider_id.clone(),
            p.model_providers,
            p.base_url,
            if p.websocket { "ws" } else { "sse" }.to_string(),
        ]);
    }
    print_rows(
        &["provider", "model_provider", "base_url", "websocket"],
        &rows,
    );
    Ok(())
}

fn cmd_add(args: AddArgs) -> Result<()> {
    ensure_layout()?;
    let interactive = args.provider_id.is_none();
    let provider_id = args
        .provider_id
        .unwrap_or_else(|| prompt("provider id", None));
    ensure_provider_id(&provider_id)?;
    let base_url = if args.oauth {
        args.base_url.unwrap_or_default()
    } else {
        args.base_url.unwrap_or_else(|| prompt("base_url", None))
    };
    let api_key = if args.oauth {
        String::new()
    } else {
        args.api_key.unwrap_or_else(|| prompt("api_key", None))
    };
    if !args.oauth && base_url.is_empty() {
        bail!("base_url is required");
    }
    let model_providers = args.model_providers.unwrap_or_else(|| {
        if interactive {
            prompt("model_providers", Some("OpenAI"))
        } else {
            "OpenAI".to_string()
        }
    });
    let wire_api = args.wire_api.unwrap_or_else(|| {
        if interactive {
            prompt("wire_api", Some("responses"))
        } else {
            "responses".to_string()
        }
    });
    let websocket = if interactive {
        prompt_bool("websocket", true)
    } else {
        !args.no_websocket
    };
    let requires_openai_auth = if interactive {
        prompt_bool("requires_openai_auth", false)
    } else {
        args.oauth
    };
    let provider = Provider {
        provider_id,
        model_providers,
        base_url,
        api_key,
        wire_api,
        requires_openai_auth,
        websocket,
        context_window: args.context_window,
        auto_compact_token_limit: args.auto_compact,
    };
    write_provider(&provider)?;
    ok(format!("created: {}", provider.path().display()));
    Ok(())
}

fn editor() -> Result<String> {
    env::var("EDITOR")
        .or_else(|_| env::var("VISUAL"))
        .map_err(|_| anyhow::anyhow!("EDITOR is not set"))
}

fn cmd_edit(provider_id: &str, yes: bool) -> Result<()> {
    ensure_layout()?;
    let path = providers_dir().join(format!("{provider_id}.toml"));
    if !path.exists() {
        if !confirm(
            &format!("provider '{provider_id}' does not exist. Create it?"),
            yes,
        ) {
            bail!("aborted");
        }
        write_provider(&Provider {
            provider_id: provider_id.to_string(),
            model_providers: "OpenAI".to_string(),
            base_url: String::new(),
            api_key: String::new(),
            wire_api: "responses".to_string(),
            requires_openai_auth: true,
            websocket: true,
            context_window: None,
            auto_compact_token_limit: None,
        })?;
    }
    let status = Command::new(editor()?).arg(&path).status()?;
    if !status.success() {
        bail!("editor failed");
    }
    let edited = load_provider(provider_id)?;
    if edited.api_key.is_empty() && !edited.requires_openai_auth {
        bail!(
            "api_key is empty and requires_openai_auth is false in provider '{provider_id}'. Aborting apply."
        );
    }
    cmd_use(provider_id)
}

fn cmd_remove(provider_id: &str, yes: bool) -> Result<()> {
    ensure_layout()?;
    let path = providers_dir().join(format!("{provider_id}.toml"));
    if !path.exists() {
        bail!("provider not found: {provider_id}");
    }
    if !confirm(&format!("remove provider '{provider_id}'?"), yes) {
        bail!("aborted");
    }
    fs::remove_file(path)?;
    ok(format!("removed: {provider_id}"));
    Ok(())
}

fn cmd_rename(old: &str, new: &str) -> Result<()> {
    ensure_layout()?;
    let old_path = providers_dir().join(format!("{old}.toml"));
    let new_path = providers_dir().join(format!("{new}.toml"));
    if !old_path.exists() {
        bail!("provider not found: {old}");
    }
    if new_path.exists() {
        bail!("provider already exists: {new}");
    }
    fs::rename(old_path, new_path)?;
    ok(format!("renamed: {old} -> {new}"));
    Ok(())
}

fn cmd_claude_list() -> Result<()> {
    ensure_claude_layout()?;
    let mut rows = Vec::new();
    for id in claude_provider_ids()? {
        let p = load_claude_provider(&id)?;
        rows.push(vec![
            p.provider_id.clone(),
            p.get("ANTHROPIC_BASE_URL").unwrap_or("-").to_string(),
            p.get("ANTHROPIC_MODEL").unwrap_or("-").to_string(),
        ]);
    }
    print_rows(&["provider", "base_url", "model"], &rows);
    Ok(())
}

fn cmd_claude_add(args: ClaudeAddArgs) -> Result<()> {
    ensure_claude_layout()?;
    let provider_id = args
        .provider_id
        .unwrap_or_else(|| prompt("provider id", None));
    ensure_provider_id(&provider_id)?;
    let base_url = args
        .base_url
        .unwrap_or_else(|| prompt("ANTHROPIC_BASE_URL", None));
    let api_key = args
        .api_key
        .unwrap_or_else(|| prompt("ANTHROPIC_AUTH_TOKEN", None));
    let model = args
        .model
        .unwrap_or_else(|| prompt("ANTHROPIC_MODEL", Some("deepseek-v4-flash")));
    if base_url.is_empty() {
        bail!("base_url is required");
    }
    if api_key.is_empty() {
        bail!("api_key is required");
    }
    let mut env = vec![
        ("ANTHROPIC_BASE_URL".to_string(), base_url),
        ("ANTHROPIC_AUTH_TOKEN".to_string(), api_key),
    ];
    if !model.is_empty() {
        env.push(("ANTHROPIC_MODEL".to_string(), model));
    }
    let provider = ClaudeProvider { provider_id, env };
    write_claude_provider(&provider)?;
    ok(format!("created: {}", provider.path().display()));
    Ok(())
}

fn cmd_claude_edit(provider_id: &str) -> Result<()> {
    ensure_claude_layout()?;
    let path = claude_providers_dir().join(format!("{provider_id}.toml"));
    if !path.exists() {
        write_claude_provider(&crate::claude::extract_current_claude_provider(
            provider_id,
        )?)?;
    }
    let status = Command::new(editor()?).arg(&path).status()?;
    if !status.success() {
        bail!("editor failed");
    }
    let edited = load_claude_provider(provider_id)?;
    if edited
        .get("ANTHROPIC_AUTH_TOKEN")
        .unwrap_or_default()
        .is_empty()
    {
        bail!("ANTHROPIC_AUTH_TOKEN is empty in claude provider '{provider_id}'. Aborting apply.");
    }
    cmd_claude_use(provider_id)
}

fn cmd_claude_remove(provider_id: &str, yes: bool) -> Result<()> {
    ensure_claude_layout()?;
    let path = claude_providers_dir().join(format!("{provider_id}.toml"));
    if !path.exists() {
        bail!("claude provider not found: {provider_id}");
    }
    if !confirm(&format!("remove claude provider '{provider_id}'?"), yes) {
        bail!("aborted");
    }
    fs::remove_file(path)?;
    ok(format!("removed: {provider_id}"));
    Ok(())
}

fn cmd_claude_rename(old: &str, new: &str) -> Result<()> {
    ensure_claude_layout()?;
    let old_path = claude_providers_dir().join(format!("{old}.toml"));
    let new_path = claude_providers_dir().join(format!("{new}.toml"));
    if !old_path.exists() {
        bail!("claude provider not found: {old}");
    }
    if new_path.exists() {
        bail!("claude provider already exists: {new}");
    }
    fs::rename(old_path, new_path)?;
    ok(format!("renamed: {old} -> {new}"));
    Ok(())
}

fn cmd_completion(shell: &str) -> Result<()> {
    match shell {
        "zsh" => print!("{}", include_str!("../completions/_cxf")),
        "bash" => println!(
            "complete -W 'init list current use add edit remove rename status completion claude' cxf"
        ),
        other => bail!("unsupported shell: {other}"),
    }
    Ok(())
}
