package main

import "fmt"

// Provider represents a Codex backend provider configuration.
type Provider struct {
	ProviderID             string `toml:"-"`
	ModelProviders         string `toml:"model_providers"`
	BaseURL                string `toml:"base_url"`
	APIKey                 string `toml:"api_key"`
	WireAPI                string `toml:"wire_api"`
	RequiresOpenAIAuth     bool   `toml:"requires_openai_auth"`
	Websocket              bool   `toml:"websocket"`
	ContextWindow          *int   `toml:"context_window,omitempty"`
	AutoCompactTokenLimit  *int   `toml:"auto_compact_token_limit,omitempty"`
}

// ClaudeProvider represents a Claude Code provider configuration.
type ClaudeProvider struct {
	ProviderID string            `toml:"-"`
	Env        map[string]string `toml:"env"`
}

// Canonical field mapping for Codex model_providers table value.
func providerTableMapping(p *Provider) map[string]interface{} {
	m := map[string]interface{}{
		"name":                  p.ModelProviders,
		"base_url":              p.BaseURL,
		"wire_api":              p.WireAPI,
		"supports_websockets":   p.Websocket,
		"requires_openai_auth":  p.RequiresOpenAIAuth,
	}
	return m
}

// ProviderFileName returns the provider's TOML filename.
func (p *Provider) FileName() string  { return p.ProviderID + ".toml" }

// ClaudeProviderFileName returns the Claude provider's TOML filename.
func (p *ClaudeProvider) FileName() string { return p.ProviderID + ".toml" }

// ProviderTableName returns the canonical name used in Codex config's [model_providers] table.
func (p *Provider) ProviderTableName() string {
	if p.ModelProviders != "" {
		return p.ModelProviders
	}
	return p.ProviderID
}

// String returns a short display string for a Provider.
func (p *Provider) String() string {
	return fmt.Sprintf("%s → %s", p.ProviderID, p.BaseURL)
}
