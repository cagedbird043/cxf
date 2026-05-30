package main

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
)

// execCommand is a package-level variable so tests can inject a fake.
var execCommand = exec.Command

var (
	rootCmd = &cobra.Command{
		Use:   "cxf",
		Short: "Codex / Claude provider manager",
		Long: `cxf manages LLM provider configurations for Codex and Claude Code.

It reads and writes TOML provider files and injects them into
~/.codex/config.toml and ~/.claude/settings.json.`,
		PersistentPreRun: func(cmd *cobra.Command, args []string) {
			quiet, _ = cmd.Flags().GetBool("quiet")
		},
	}
)

func init() {
	rootCmd.PersistentFlags().BoolVarP(&quiet, "quiet", "q", false, "suppress normal output")
	rootCmd.CompletionOptions.DisableDefaultCmd = true

	// Codex commands
	rootCmd.AddCommand(initCmd)
	rootCmd.AddCommand(listCmd)
	rootCmd.AddCommand(currentCmd)
	rootCmd.AddCommand(useCmd)
	rootCmd.AddCommand(addCmd)
	rootCmd.AddCommand(editCmd)
	rootCmd.AddCommand(removeCmd)
	rootCmd.AddCommand(renameCmd)
	rootCmd.AddCommand(statusCmd)

	// Claude parent command
	rootCmd.AddCommand(claudeCmd)
	claudeCmd.AddCommand(claudeInitCmd)
	claudeCmd.AddCommand(claudeListCmd)
	claudeCmd.AddCommand(claudeCurrentCmd)
	claudeCmd.AddCommand(claudeUseCmd)
	claudeCmd.AddCommand(claudeAddCmd)
	claudeCmd.AddCommand(claudeEditCmd)
	claudeCmd.AddCommand(claudeRemoveCmd)
	claudeCmd.AddCommand(claudeRenameCmd)
	claudeCmd.AddCommand(claudeStatusCmd)

	// Wire completion providers
	useCmd.ValidArgsFunction = providerCompletion
	editCmd.ValidArgsFunction = providerCompletion
	removeCmd.ValidArgsFunction = providerCompletion
	renameCmd.ValidArgsFunction = providerCompletion
	claudeUseCmd.ValidArgsFunction = claudeProviderCompletion
	claudeEditCmd.ValidArgsFunction = claudeProviderCompletion
	claudeRemoveCmd.ValidArgsFunction = claudeProviderCompletion

	// Add command flags
	addCmd.Flags().String("provider-id", "", "provider identifier")
	addCmd.Flags().String("model-providers", "OpenAI", "model providers name (default: OpenAI)")
	addCmd.Flags().String("base-url", "", "API base URL")
	addCmd.Flags().String("api-key", "", "API key")
	addCmd.Flags().String("wire-api", "responses", "wire API type (responses/chat)")
	addCmd.Flags().Bool("no-websocket", false, "disable websocket support")
	addCmd.Flags().Int("context-window", 0, "context window size")
	addCmd.Flags().Int("auto-compact", 0, "auto compact token limit")

	claudeAddCmd.Flags().String("provider-id", "", "provider identifier")
	claudeAddCmd.Flags().String("base-url", "", "API base URL")
	claudeAddCmd.Flags().String("api-key", "", "API key")
	claudeAddCmd.Flags().String("model", "", "model name")

	// Edit commands
	editCmd.Flags().BoolP("yes", "y", false, "skip confirmation")
	claudeEditCmd.Flags().BoolP("yes", "y", false, "skip confirmation")
	removeCmd.Flags().BoolP("yes", "y", false, "skip confirmation")
	claudeRemoveCmd.Flags().BoolP("yes", "y", false, "skip confirmation")

	// Rename args
	renameCmd.Flags().BoolP("yes", "y", false, "skip confirmation")
	claudeRenameCmd.Flags().BoolP("yes", "y", false, "skip confirmation")
}

// ── Completion helpers ─────────────────────────────────────────────────

func providerCompletion(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
	names, err := listProviders()
	if err != nil || names == nil {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}
	return names, cobra.ShellCompDirectiveNoFileComp
}

func claudeProviderCompletion(cmd *cobra.Command, args []string, toComplete string) ([]string, cobra.ShellCompDirective) {
	names, err := listClaudeProviders()
	if err != nil || names == nil {
		return nil, cobra.ShellCompDirectiveNoFileComp
	}
	return names, cobra.ShellCompDirectiveNoFileComp
}

// ── Interactive input ──────────────────────────────────────────────────

var stdinReader = bufio.NewReader(os.Stdin)

func prompt(label, defaultValue string) string {
	if defaultValue != "" {
		fmt.Printf("  %s [%s]: ", label, defaultValue)
	} else {
		fmt.Printf("  %s: ", label)
	}
	text, _ := stdinReader.ReadString('\n')
	text = strings.TrimSpace(text)
	if text == "" {
		return defaultValue
	}
	return text
}

func promptYesNo(label string, defaultYes bool) bool {
	suffix := "[y/N]"
	if defaultYes {
		suffix = "[Y/n]"
	}
	fmt.Printf("  %s %s: ", label, suffix)
	text, _ := stdinReader.ReadString('\n')
	text = strings.TrimSpace(strings.ToLower(text))
	if text == "" {
		return defaultYes
	}
	return text == "y" || text == "yes"
}

// ── Main ───────────────────────────────────────────────────────────────

func main() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

// ═══════════════════════════════════════════════════════════════════════
// Codex commands
// ═══════════════════════════════════════════════════════════════════════

var initCmd = &cobra.Command{
	Use:   "init [name]",
	Short: "Initialize providers from current Codex config",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := ensureLayout(); err != nil {
			return err
		}
		if err := writeDefaultBase(); err != nil {
			return err
		}

		providers, err := extractAllProviders()
		if err != nil {
			return fmt.Errorf("extract providers: %w", err)
		}
		if len(providers) == 0 {
			warn("no model_providers found in Codex config")
			return nil
		}

		for _, p := range providers {
			if len(args) > 0 {
				p.ProviderID = args[0]
			}
			if err := writeProvider(p); err != nil {
				fail("write provider %s: %v", p.ProviderID, err)
				continue
			}
			ok("provider %s (%s)", p.ProviderID, p.BaseURL)
		}
		ok("initialized %d provider(s)", len(providers))
		return nil
	},
}

var listCmd = &cobra.Command{
	Use:   "list",
	Short: "List Codex providers",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := ensureLayout(); err != nil {
			return err
		}
		names, err := listProviders()
		if err != nil {
			return err
		}
		active, _ := getCurrentCodexProvider()

		var providers []*Provider
		for _, name := range names {
			p, err := readProvider(name)
			if err != nil {
				warn("skip %s: %v", name, err)
				continue
			}
			providers = append(providers, p)
		}
		printProviderTable(providers, active)
		return nil
	},
}

var currentCmd = &cobra.Command{
	Use:   "current",
	Short: "Show active Codex provider",
	RunE: func(cmd *cobra.Command, args []string) error {
		probe, err := getCurrentCodexProvider()
		if err != nil {
			return err
		}
		if probe == "" {
			info("no active codex provider")
			return nil
		}
		p, err := readProvider(probe)
		if err != nil {
			info("active provider: %s (provider file not found)", probe)
			return nil
		}
		printCodexCurrent(probe, p)
		return nil
	},
}

var useCmd = &cobra.Command{
	Use:   "use <provider>",
	Short: "Switch to a Codex provider",
	Args:  cobra.ExactArgs(1),
	ValidArgsFunction: providerCompletion,
	RunE: func(cmd *cobra.Command, args []string) error {
		name := args[0]
		if !providerExists(name) {
			return fmt.Errorf("provider %q not found", name)
		}
		p, err := readProvider(name)
		if err != nil {
			return err
		}

		// Check drift
		drifted, err := detectCodexDrift(p)
		if err != nil {
			return fmt.Errorf("drift check: %w", err)
		}
		if len(drifted) > 0 {
			warn("configuration drift in: %s", strings.Join(drifted, ", "))
			expected := renderProviderConfig(p)
			current := extractManagedValues()
			diffText := renderUnifiedDiff(expected, current)
			fmt.Println()
			fmt.Println(diffText)
			if !promptYesNo("overwrite?", false) {
				info("cancelled")
				return nil
			}
		}

		// Take snapshot
		if err := takeSnapshot(); err != nil {
			warn("snapshot: %v", err)
		}

		// Apply
		if err := applyProvider(p); err != nil {
			return fmt.Errorf("apply provider: %w", err)
		}
		ok("switched to %s", name)
		return nil
	},
}

var addCmd = &cobra.Command{
	Use:   "add",
	Short: "Add a Codex provider (interactive or flags)",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := ensureLayout(); err != nil {
			return err
		}
		if err := writeDefaultBase(); err != nil {
			return err
		}

		p := &Provider{}

		// Read flags
		p.ProviderID, _ = cmd.Flags().GetString("provider-id")
		p.ModelProviders, _ = cmd.Flags().GetString("model-providers")
		p.BaseURL, _ = cmd.Flags().GetString("base-url")
		p.APIKey, _ = cmd.Flags().GetString("api-key")
		p.WireAPI, _ = cmd.Flags().GetString("wire-api")
		noWebsocket, _ := cmd.Flags().GetBool("no-websocket")
		p.Websocket = !noWebsocket
		p.RequiresOpenAIAuth = true
		if cw, _ := cmd.Flags().GetInt("context-window"); cw > 0 {
			p.ContextWindow = &cw
		}
		if ac, _ := cmd.Flags().GetInt("auto-compact"); ac > 0 {
			p.AutoCompactTokenLimit = &ac
		}

		// Interactive prompts for missing values
		if p.ProviderID == "" {
			p.ProviderID = prompt("provider-id", "")
		}
		if p.BaseURL == "" {
			p.BaseURL = prompt("base-url", "")
		}
		if p.APIKey == "" {
			p.APIKey = prompt("api-key", "")
		}
		if p.WireAPI == "" {
			p.WireAPI = prompt("wire-api (responses/chat)", "responses")
		}

		// Validate
		if p.ProviderID == "" {
			return fmt.Errorf("provider-id is required")
		}
		if providerExists(p.ProviderID) {
			return fmt.Errorf("provider %q already exists", p.ProviderID)
		}

		if err := writeProvider(p); err != nil {
			return err
		}
		ok("added provider %s", p.ProviderID)
		return nil
	},
}

var editCmd = &cobra.Command{
	Use:   "edit <provider>",
	Short: "Edit a Codex provider in $EDITOR",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		name := args[0]
		if !providerExists(name) {
			return fmt.Errorf("provider %q not found", name)
		}

		editor := os.Getenv("EDITOR")
		if editor == "" {
			editor = "vim"
		}
		path := filepath.Join(providersDir, name+".toml")

		cmdEdit := execCommand(editor, path)
		cmdEdit.Stdin = os.Stdin
		cmdEdit.Stdout = os.Stdout
		cmdEdit.Stderr = os.Stderr
		if err := cmdEdit.Run(); err != nil {
			return fmt.Errorf("editor: %w", err)
		}
		ok("edited %s", name)
		return nil
	},
}

var removeCmd = &cobra.Command{
	Use:   "remove <provider>",
	Short: "Remove a Codex provider",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		name := args[0]
		if !providerExists(name) {
			return fmt.Errorf("provider %q not found", name)
		}
		yes, _ := cmd.Flags().GetBool("yes")
		if !yes && !promptYesNo(fmt.Sprintf("remove %s?", name), false) {
			info("cancelled")
			return nil
		}
		if err := deleteProvider(name); err != nil {
			return err
		}
		ok("removed %s", name)
		return nil
	},
}

var renameCmd = &cobra.Command{
	Use:   "rename <old> <new>",
	Short: "Rename a Codex provider",
	Args:  cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		oldName, newName := args[0], args[1]
		if !providerExists(oldName) {
			return fmt.Errorf("provider %q not found", oldName)
		}
		if providerExists(newName) {
			return fmt.Errorf("provider %q already exists", newName)
		}
		yes, _ := cmd.Flags().GetBool("yes")
		if !yes && !promptYesNo(fmt.Sprintf("rename %s → %s?", oldName, newName), true) {
			info("cancelled")
			return nil
		}

		p, err := readProvider(oldName)
		if err != nil {
			return err
		}
		p.ProviderID = newName
		if err := writeProvider(p); err != nil {
			return err
		}
		if err := deleteProvider(oldName); err != nil {
			return err
		}
		ok("renamed %s → %s", oldName, newName)
		return nil
	},
}

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Check if cxf controls the active Codex provider",
	RunE: func(cmd *cobra.Command, args []string) error {
		probe, err := getCurrentCodexProvider()
		if err != nil {
			return err
		}
		if probe == "" {
			warn("no cxf probe found in Codex config")
			info("  run 'cxf use <provider>' to set up")
			return nil
		}

		if !providerExists(probe) {
			warn("cxf probe points to %q, but provider file not found", probe)
			return nil
		}

		p, err := readProvider(probe)
		if err != nil {
			return err
		}

		drifted, err := detectCodexDrift(p)
		if err != nil {
			return err
		}
		if len(drifted) > 0 {
			warn("configuration drift detected in: %s", strings.Join(drifted, ", "))
			return nil
		}

		ok("cxf controls the active provider (%s)", probe)
		return nil
	},
}

// ═══════════════════════════════════════════════════════════════════════
// Claude commands
// ═══════════════════════════════════════════════════════════════════════

var claudeCmd = &cobra.Command{
	Use:   "claude",
	Short: "Manage Claude providers",
}

var claudeInitCmd = &cobra.Command{
	Use:   "init [name]",
	Short: "Initialize from current Claude settings",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := ensureClaudeLayout(); err != nil {
			return err
		}

		settings, err := readClaudeSettings()
		if err != nil {
			return err
		}

		// Extract env as a ClaudeProvider
		name := "default"
		if len(args) > 0 {
			name = args[0]
		}

		cp := &ClaudeProvider{
			ProviderID: name,
			Env:        make(map[string]string),
		}
		for k, v := range settings.Env {
			if k != claudeProbeEnvKey {
				cp.Env[k] = v
			}
		}

		if err := writeClaudeProvider(cp); err != nil {
			return err
		}
		ok("initialized claude provider %s with %d env vars", name, len(cp.Env))
		return nil
	},
}

var claudeListCmd = &cobra.Command{
	Use:   "list",
	Short: "List Claude providers",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := ensureClaudeLayout(); err != nil {
			return err
		}
		names, err := listClaudeProviders()
		if err != nil {
			return err
		}
		active, _ := getCurrentClaudeProvider()

		var providers []*ClaudeProvider
		for _, name := range names {
			cp, err := readClaudeProvider(name)
			if err != nil {
				warn("skip %s: %v", name, err)
				continue
			}
			providers = append(providers, cp)
		}
		printClaudeProviderTable(providers, active)
		return nil
	},
}

var claudeCurrentCmd = &cobra.Command{
	Use:   "current",
	Short: "Show active Claude provider",
	RunE: func(cmd *cobra.Command, args []string) error {
		probe, err := getCurrentClaudeProvider()
		if err != nil {
			return err
		}
		if probe == "" {
			info("no active claude provider")
			return nil
		}
		cp, err := readClaudeProvider(probe)
		if err != nil {
			info("active provider: %s (provider file not found)", probe)
			return nil
		}
		printClaudeCurrent(probe, cp)
		return nil
	},
}

var claudeUseCmd = &cobra.Command{
	Use:   "use <provider>",
	Short: "Switch to a Claude provider",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		name := args[0]
		if !claudeProviderExists(name) {
			return fmt.Errorf("claude provider %q not found", name)
		}
		cp, err := readClaudeProvider(name)
		if err != nil {
			return err
		}

		// Check drift
		drifted, err := detectClaudeDrift(cp)
		if err != nil {
			return fmt.Errorf("drift check: %w", err)
		}
		if len(drifted) > 0 {
			warn("configuration drift in: %s", strings.Join(drifted, ", "))
			expected := renderClaudeProviderConfig(cp)
			current := extractClaudeManagedValues()
			diffText := renderUnifiedDiff(expected, current)
			fmt.Println()
			fmt.Println(diffText)
			if !promptYesNo("overwrite?", false) {
				info("cancelled")
				return nil
			}
		}

		// Take snapshot
		if err := takeClaudeSnapshot(); err != nil {
			warn("snapshot: %v", err)
		}

		if err := applyClaudeProvider(cp); err != nil {
			return fmt.Errorf("apply claude provider: %w", err)
		}
		ok("switched to claude provider %s", name)
		return nil
	},
}

var claudeAddCmd = &cobra.Command{
	Use:   "add",
	Short: "Add a Claude provider (interactive or flags)",
	RunE: func(cmd *cobra.Command, args []string) error {
		if err := ensureClaudeLayout(); err != nil {
			return err
		}

		cp := &ClaudeProvider{Env: make(map[string]string)}

		providerID, _ := cmd.Flags().GetString("provider-id")
		baseURL, _ := cmd.Flags().GetString("base-url")
		apiKey, _ := cmd.Flags().GetString("api-key")
		model, _ := cmd.Flags().GetString("model")

		// Interactive prompts for missing values
		if providerID == "" {
			providerID = prompt("provider-id", "")
		}
		if baseURL == "" {
			baseURL = prompt("base-url", "")
		}
		if apiKey == "" {
			apiKey = prompt("api-key", "")
		}
		if model == "" {
			model = prompt("model", "")
		}

		cp.ProviderID = providerID
		if baseURL != "" {
			cp.Env["ANTHROPIC_BASE_URL"] = baseURL
		}
		if apiKey != "" {
			cp.Env["ANTHROPIC_AUTH_TOKEN"] = apiKey
		}
		if model != "" {
			cp.Env["ANTHROPIC_MODEL"] = model
		}
		// Set reasonable defaults for other managed keys
		if model != "" {
			cp.Env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model
			cp.Env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model
			cp.Env["CLAUDE_CODE_SUBAGENT_MODEL"] = model
		}
		cp.Env["CLAUDE_CODE_EFFORT_LEVEL"] = "max"

		if cp.ProviderID == "" {
			return fmt.Errorf("provider-id is required")
		}
		if claudeProviderExists(cp.ProviderID) {
			return fmt.Errorf("claude provider %q already exists", cp.ProviderID)
		}

		if err := writeClaudeProvider(cp); err != nil {
			return err
		}
		ok("added claude provider %s", cp.ProviderID)
		return nil
	},
}

var claudeEditCmd = &cobra.Command{
	Use:   "edit <provider>",
	Short: "Edit a Claude provider in $EDITOR",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		name := args[0]
		if !claudeProviderExists(name) {
			return fmt.Errorf("claude provider %q not found", name)
		}

		editor := os.Getenv("EDITOR")
		if editor == "" {
			editor = "vim"
		}
		path := filepath.Join(claudeProvidersDir, name+".toml")

		cmdEdit := execCommand(editor, path)
		cmdEdit.Stdin = os.Stdin
		cmdEdit.Stdout = os.Stdout
		cmdEdit.Stderr = os.Stderr
		if err := cmdEdit.Run(); err != nil {
			return fmt.Errorf("editor: %w", err)
		}
		ok("edited %s", name)
		return nil
	},
}

var claudeRemoveCmd = &cobra.Command{
	Use:   "remove <provider>",
	Short: "Remove a Claude provider",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		name := args[0]
		if !claudeProviderExists(name) {
			return fmt.Errorf("claude provider %q not found", name)
		}
		yes, _ := cmd.Flags().GetBool("yes")
		if !yes && !promptYesNo(fmt.Sprintf("remove %s?", name), false) {
			info("cancelled")
			return nil
		}
		if err := deleteClaudeProvider(name); err != nil {
			return err
		}
		ok("removed %s", name)
		return nil
	},
}

var claudeRenameCmd = &cobra.Command{
	Use:   "rename <old> <new>",
	Short: "Rename a Claude provider",
	Args:  cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		oldName, newName := args[0], args[1]
		if !claudeProviderExists(oldName) {
			return fmt.Errorf("claude provider %q not found", oldName)
		}
		if claudeProviderExists(newName) {
			return fmt.Errorf("claude provider %q already exists", newName)
		}
		yes, _ := cmd.Flags().GetBool("yes")
		if !yes && !promptYesNo(fmt.Sprintf("rename %s → %s?", oldName, newName), true) {
			info("cancelled")
			return nil
		}

		cp, err := readClaudeProvider(oldName)
		if err != nil {
			return err
		}
		cp.ProviderID = newName
		if err := writeClaudeProvider(cp); err != nil {
			return err
		}
		if err := deleteClaudeProvider(oldName); err != nil {
			return err
		}
		ok("renamed %s → %s", oldName, newName)
		return nil
	},
}

var claudeStatusCmd = &cobra.Command{
	Use:   "status",
	Short: "Check if cxf controls the active Claude provider",
	RunE: func(cmd *cobra.Command, args []string) error {
		probe, err := getCurrentClaudeProvider()
		if err != nil {
			return err
		}
		if probe == "" {
			warn("no cxf probe found in Claude settings")
			info("  run 'cxf claude use <provider>' to set up")
			return nil
		}

		if !claudeProviderExists(probe) {
			warn("cxf probe points to %q, but provider file not found", probe)
			return nil
		}

		cp, err := readClaudeProvider(probe)
		if err != nil {
			return err
		}

		drifted, err := detectClaudeDrift(cp)
		if err != nil {
			return err
		}
		if len(drifted) > 0 {
			warn("configuration drift detected in: %s", strings.Join(drifted, ", "))
			return nil
		}

		ok("cxf controls the active claude provider (%s)", probe)
		return nil
	},
}

// ── Snapshot helpers ───────────────────────────────────────────────────

func takeClaudeSnapshot() error {
	data, err := os.ReadFile(claudeSettingsPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	probe, _ := getCurrentClaudeProvider()
	if probe == "" {
		probe = "unknown"
	}
	safeName := strings.ReplaceAll(probe, "/", "_")
	path := filepath.Join(snapshotsDir, fmt.Sprintf("claude-settings-%s.json", safeName))
	if err := os.MkdirAll(snapshotsDir, 0755); err != nil {
		return err
	}
	return os.WriteFile(path, data, 0600)
}

// ── Version command ───────────────────────────────────────────────────

var version = "0.1.0"

// We don't use the version command directly, cobra will handle --version
// via the root command's Version field.

func init() {
	rootCmd.Version = version
	// Add version as a separate command too
	rootCmd.AddCommand(&cobra.Command{
		Use:   "version",
		Short: "Print version",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Println("cxf", version)
			return nil
		},
	})
}
