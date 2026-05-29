package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	toml "github.com/pelletier/go-toml"
)

// ── XDG-compatible paths ───────────────────────────────────────────────

func xdgConfigHome() string {
	if d := os.Getenv("XDG_CONFIG_HOME"); d != "" {
		return d
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".config")
}

func xdgStateHome() string {
	if d := os.Getenv("XDG_STATE_HOME"); d != "" {
		return d
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".local", "state")
}

func homeDir() string {
	h, _ := os.UserHomeDir()
	return h
}

// ── Derived paths (computed at init) ───────────────────────────────────

var (
	providersDir       string
	claudeProvidersDir string
	basePath           string
	snapshotsDir       string
	codexConfigPath    string
	authPath           string
	claudeSettingsPath string
)

func init() {
	cxfHome := filepath.Join(xdgConfigHome(), "cxf")
	providersDir = filepath.Join(cxfHome, "providers")
	basePath = filepath.Join(cxfHome, "base.toml")
	claudeCxfHome := filepath.Join(cxfHome, "claude")
	claudeProvidersDir = filepath.Join(claudeCxfHome, "providers")
	cxfStateHome := filepath.Join(xdgStateHome(), "cxf")
	snapshotsDir = filepath.Join(cxfStateHome, "snapshots")
	codexConfigPath = filepath.Join(homeDir(), ".codex", "config.toml")
	authPath = filepath.Join(homeDir(), ".codex", "auth.json")
	claudeSettingsPath = filepath.Join(homeDir(), ".claude", "settings.json")
}

// ── Layout ─────────────────────────────────────────────────────────────

func ensureLayout() error {
	if err := os.MkdirAll(providersDir, 0755); err != nil {
		return err
	}
	return os.MkdirAll(snapshotsDir, 0755)
}

func ensureClaudeLayout() error {
	return os.MkdirAll(claudeProvidersDir, 0755)
}

// ── toInt helper ───────────────────────────────────────────────────────

func toInt(v interface{}) (int, bool) {
	switch x := v.(type) {
	case int64:
		return int(x), true
	case float64:
		return int(x), true
	case int:
		return x, true
	case string:
		n, err := strconv.Atoi(x)
		return n, err == nil
	default:
		return 0, false
	}
}

// ── Provider file CRUD (struct-based marshal, no comment needed) ───────

func readProvider(name string) (*Provider, error) {
	path := filepath.Join(providersDir, name+".toml")
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("provider %q not found", name)
		}
		return nil, err
	}
	var p Provider
	if err := toml.Unmarshal(data, &p); err != nil {
		return nil, fmt.Errorf("parse provider %s: %w", name, err)
	}
	p.ProviderID = name
	return &p, nil
}

func writeProvider(p *Provider) error {
	data, err := toml.Marshal(*p)
	if err != nil {
		return err
	}
	path := filepath.Join(providersDir, p.FileName())
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	return os.WriteFile(path, data, 0600)
}

func deleteProvider(name string) error {
	path := filepath.Join(providersDir, name+".toml")
	if err := os.Remove(path); os.IsNotExist(err) {
		return fmt.Errorf("provider %q not found", name)
	}
	return nil
}

func listProviders() ([]string, error) {
	entries, err := os.ReadDir(providersDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var names []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".toml") {
			names = append(names, strings.TrimSuffix(e.Name(), ".toml"))
		}
	}
	return names, nil
}

func providerExists(name string) bool {
	_, err := os.Stat(filepath.Join(providersDir, name+".toml"))
	return err == nil
}

// ── Claude provider CRUD ───────────────────────────────────────────────

func readClaudeProvider(name string) (*ClaudeProvider, error) {
	path := filepath.Join(claudeProvidersDir, name+".toml")
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("claude provider %q not found", name)
		}
		return nil, err
	}
	var cp ClaudeProvider
	if err := toml.Unmarshal(data, &cp); err != nil {
		return nil, fmt.Errorf("parse claude provider %s: %w", name, err)
	}
	cp.ProviderID = name
	if cp.Env == nil {
		cp.Env = map[string]string{}
	}
	return &cp, nil
}

func writeClaudeProvider(cp *ClaudeProvider) error {
	data, err := toml.Marshal(*cp)
	if err != nil {
		return err
	}
	path := filepath.Join(claudeProvidersDir, cp.FileName())
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	return os.WriteFile(path, data, 0600)
}

func deleteClaudeProvider(name string) error {
	path := filepath.Join(claudeProvidersDir, name+".toml")
	if err := os.Remove(path); os.IsNotExist(err) {
		return fmt.Errorf("claude provider %q not found", name)
	}
	return nil
}

func listClaudeProviders() ([]string, error) {
	entries, err := os.ReadDir(claudeProvidersDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var names []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".toml") {
			names = append(names, strings.TrimSuffix(e.Name(), ".toml"))
		}
	}
	return names, nil
}

func claudeProviderExists(name string) bool {
	_, err := os.Stat(filepath.Join(claudeProvidersDir, name+".toml"))
	return err == nil
}

// ── JSON helpers ───────────────────────────────────────────────────────

func readJSONFile(path string) (map[string]interface{}, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return map[string]interface{}{}, nil
		}
		return nil, err
	}
	var result map[string]interface{}
	if err := json.Unmarshal(data, &result); err != nil {
		// Corrupted JSON — return empty map, don't crash
		return map[string]interface{}{}, nil
	}
	return result, nil
}

func writeJSONFile(path string, data map[string]interface{}) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(raw, '\n'), 0600)
}

// ── Auth helpers ───────────────────────────────────────────────────────

func readAuth() (map[string]interface{}, error) {
	return readJSONFile(authPath)
}

func writeAuth(apiKey string) error {
	existing, err := readAuth()
	if err != nil {
		return err
	}
	if existing["OPENAI_API_KEY"] == apiKey {
		return nil
	}
	existing["OPENAI_API_KEY"] = apiKey
	existing["source"] = "cxf"
	return writeJSONFile(authPath, existing)
}

// ── Base config ────────────────────────────────────────────────────────

type BaseConfig struct {
	Model                    string `toml:"model"`
	ReviewModel              string `toml:"review_model"`
	ModelReasoningEffort     string `toml:"model_reasoning_effort"`
	ModelContextWindow       int    `toml:"model_context_window"`
	ModelAutoCompactLimit    int    `toml:"model_auto_compact_token_limit"`
}

func defaultBaseConfig() *BaseConfig {
	return &BaseConfig{
		Model:                 "gpt-5.5",
		ReviewModel:           "gpt-5.5",
		ModelReasoningEffort:  "high",
		ModelContextWindow:    272000,
		ModelAutoCompactLimit: 240000,
	}
}

func loadBase() (*BaseConfig, error) {
	path := basePath
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return defaultBaseConfig(), nil
		}
		return nil, err
	}
	cfg := defaultBaseConfig()
	if err := toml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parse base.toml: %w", err)
	}
	return cfg, nil
}

func writeDefaultBase() error {
	if _, err := os.Stat(basePath); err == nil {
		return nil
	}
	cfg := defaultBaseConfig()
	return writeBase(cfg)
}

func writeBase(cfg *BaseConfig) error {
	data, err := toml.Marshal(*cfg)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(basePath), 0755); err != nil {
		return err
	}
	return os.WriteFile(basePath, data, 0600)
}
