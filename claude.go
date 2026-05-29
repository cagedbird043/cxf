package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const claudeProbeEnvKey = "CXF_CLAUDE_PROVIDER"

// Managed env keys that cxf controls in Claude settings.
var claudeManagedKeys = []string{
	"ANTHROPIC_BASE_URL",
	"ANTHROPIC_AUTH_TOKEN",
	"ANTHROPIC_API_KEY",
	"ANTHROPIC_MODEL",
	"ANTHROPIC_DEFAULT_OPUS_MODEL",
	"ANTHROPIC_DEFAULT_SONNET_MODEL",
	"ANTHROPIC_DEFAULT_HAIKU_MODEL",
	"CLAUDE_CODE_SUBAGENT_MODEL",
	"CLAUDE_CODE_SUBAGENT_MODEL_PROVIDER",
	"CLAUDE_CODE_EFFORT_LEVEL",
	"CLAUDE_CODE_VISION",
	"CLAUDE_CODE_NATIVE_TOOLS",
	"CLAUDE_CODE_TARGET_TOOL",
	"CLAUDE_CODE_AUTO_UPDATES",
	claudeProbeEnvKey,
}

// ClaudeSettings represents the ~/.claude/settings.json file.
type ClaudeSettings struct {
	Model string            `json:"model,omitempty"`
	Env   map[string]string `json:"env,omitempty"`
}

// readClaudeSettings reads and parses Claude settings.json.
func readClaudeSettings() (*ClaudeSettings, error) {
	data, err := os.ReadFile(claudeSettingsPath)
	if err != nil {
		if os.IsNotExist(err) {
			return &ClaudeSettings{Env: map[string]string{}}, nil
		}
		return nil, err
	}
	var s ClaudeSettings
	if err := json.Unmarshal(data, &s); err != nil {
		// Corrupted — return empty
		return &ClaudeSettings{Env: map[string]string{}}, nil
	}
	if s.Env == nil {
		s.Env = map[string]string{}
	}
	return &s, nil
}

// writeClaudeSettings writes Claude settings.json.
func writeClaudeSettings(s *ClaudeSettings) error {
	if err := os.MkdirAll(filepath.Dir(claudeSettingsPath), 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(claudeSettingsPath, append(data, '\n'), 0600)
}

// applyClaudeProvider injects a ClaudeProvider's settings into Claude settings.json.
func applyClaudeProvider(cp *ClaudeProvider) error {
	settings, err := readClaudeSettings()
	if err != nil {
		return err
	}

	// Clear all managed env keys first
	for _, key := range claudeManagedKeys {
		delete(settings.Env, key)
	}

	// Set provider env values
	for k, v := range cp.Env {
		if v != "" {
			settings.Env[k] = v
		}
	}

	// Set the probe marker
	settings.Env[claudeProbeEnvKey] = cp.ProviderID

	// Set model if ANTHROPIC_MODEL is defined
	if model, ok := cp.Env["ANTHROPIC_MODEL"]; ok && model != "" {
		settings.Model = model
	}

	return writeClaudeSettings(settings)
}

// detectClaudeDrift checks if the active Claude settings differ from what
// would be written. Returns list of drifted field names.
func detectClaudeDrift(cp *ClaudeProvider) ([]string, error) {
	settings, err := readClaudeSettings()
	if err != nil {
		return nil, err
	}

	var drifted []string

	// Check probe
	currentProbe := settings.Env[claudeProbeEnvKey]
	if currentProbe != cp.ProviderID {
		drifted = append(drifted, "probe (expected: "+cp.ProviderID+")")
	}

	// Check each managed env key
	for _, key := range claudeManagedKeys {
		if key == claudeProbeEnvKey {
			continue
		}
		expected := cp.Env[key]
		current := settings.Env[key]
		if current != expected {
			drifted = append(drifted, key)
		}
	}

	return drifted, nil
}

// getCurrentClaudeProvider reads the probe from Claude settings.
func getCurrentClaudeProvider() (string, error) {
	settings, err := readClaudeSettings()
	if err != nil {
		return "", err
	}
	return settings.Env[claudeProbeEnvKey], nil
}

// renderClaudeProviderConfig returns a string representation of what the
// Claude provider would write, for drift display.
func renderClaudeProviderConfig(cp *ClaudeProvider) string {
	var buf strings.Builder
	buf.WriteString(fmt.Sprintf("// probe: %s\n", cp.ProviderID))
	for k, v := range cp.Env {
		if v != "" {
			redacted := v
			if strings.Contains(strings.ToLower(k), "token") || strings.Contains(strings.ToLower(k), "key") {
				if len(v) > 8 {
					redacted = v[:8] + "..."
				}
			}
			buf.WriteString(fmt.Sprintf("%s = %q\n", k, redacted))
		}
	}
	return buf.String()
}
