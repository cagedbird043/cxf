package main

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	toml "github.com/pelletier/go-toml"
)

const codexProbePrefix = "# cxf: provider = "

// ── Probe helpers ──────────────────────────────────────────────────────

// extractProbe finds the current probe line from raw config content.
// Returns the provider name if found, empty string otherwise.
func extractProbe(lines []string) string {
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, codexProbePrefix) {
			return strings.TrimSpace(strings.TrimPrefix(trimmed, codexProbePrefix))
		}
	}
	return ""
}

// removeProbeLines removes all probe lines from raw config lines.
func removeProbeLines(lines []string) []string {
	var result []string
	for _, line := range lines {
		if !strings.Contains(line, codexProbePrefix) {
			result = append(result, line)
		}
	}
	return result
}

// injectProbe inserts the probe line after the #:schema line if present,
// otherwise at the beginning of the content.
func injectProbe(content string, probe string) string {
	lines := strings.Split(content, "\n")
	probeLine := codexProbePrefix + probe

	// Find #:schema line
	insertAt := 0 // default: top
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "#:schema") {
			insertAt = i + 1
			break
		}
	}

	// Insert probe line
	var result []string
	result = append(result, lines[:insertAt]...)
	result = append(result, probeLine)
	if insertAt < len(lines) {
		result = append(result, lines[insertAt:]...)
	}

	return strings.Join(result, "\n")
}

// ── Codex config operations ────────────────────────────────────────────

// CodexConfigModels holds the dynamic model_providers section of config.toml.
type CodexConfigModels struct {
	Providers map[string]*toml.Tree `toml:"-"` // keyed by table name
}

// readCodexConfigRaw reads the Codex config.toml as raw text and as a go-toml Tree.
func readCodexConfigRaw() (string, *toml.Tree, error) {
	data, err := os.ReadFile(codexConfigPath)
	if err != nil {
		if os.IsNotExist(err) {
			emptyTree, _ := toml.TreeFromMap(map[string]interface{}{})
			return "", emptyTree, nil
		}
		return "", nil, err
	}
	raw := string(data)
	tree, err := toml.Load(raw)
	if err != nil {
		return "", nil, fmt.Errorf("parse Codex config: %w", err)
	}
	return raw, tree, nil
}

// writeCodexConfigRaw writes modified content to Codex config.toml.
func writeCodexConfigRaw(content string) error {
	if err := os.MkdirAll(filepath.Dir(codexConfigPath), 0755); err != nil {
		return err
	}
	return os.WriteFile(codexConfigPath, []byte(content), 0600)
}

// applyProvider injects a Provider's settings into Codex config.toml and auth.json.
func applyProvider(p *Provider) error {
	raw, tree, err := readCodexConfigRaw()
	if err != nil {
		return err
	}

	probe := p.ProviderID

	if raw == "" {
		// No existing config — create from scratch
		raw = "# cxf: provider = " + probe + "\n"
		tree, _ = toml.TreeFromMap(map[string]interface{}{})
	}

	// ── Remove old probe from raw text ──
	lines := strings.Split(raw, "\n")
	cleanedLines := removeProbeLines(lines)
	cleanedRaw := strings.Join(cleanedLines, "\n")

	// If we had a probe, re-parse without it (clean tree)
	if extractProbe(lines) != "" {
		newTree, err := toml.Load(cleanedRaw)
		if err != nil {
			// If clean parse fails, use original tree
			newTree = tree
		}
		tree = newTree
	}

	// ── Modify tree values ──
	base, err := loadBase()
	if err != nil {
		return err
	}

	// Top-level keys
	tree.Set("model", base.Model)
	tree.Set("model_provider", p.ModelProviders)
	tree.Set("review_model", base.ReviewModel)
	tree.Set("model_reasoning_effort", base.ModelReasoningEffort)
	tree.Set("model_context_window", base.ModelContextWindow)
	tree.Set("model_auto_compact_token_limit", base.ModelAutoCompactLimit)

	// Provider-specific overrides
	if p.ContextWindow != nil {
		tree.Set("model_context_window", *p.ContextWindow)
	}
	if p.AutoCompactTokenLimit != nil {
		tree.Set("model_auto_compact_token_limit", *p.AutoCompactTokenLimit)
	}

	// ── model_providers section ──
	mpSection, _ := toml.TreeFromMap(map[string]interface{}{})

	// Add the new provider's table
	tableName := p.ProviderTableName()
	tableData := providerTableMapping(p)
	tableTree, _ := toml.TreeFromMap(tableData)
	mpSection.Set(tableName, tableTree)

	// Carry over any non-cxf-managed model_providers tables
	existingMP := tree.Get("model_providers")
	if existingMP != nil {
		if mpTree, ok := existingMP.(*toml.Tree); ok {
			for _, k := range mpTree.Keys() {
				if !isManagedProviderName(k) {
					mpSection.Set(k, mpTree.Get(k))
				}
			}
		}
	}

	tree.Set("model_providers", mpSection)

	// ── features section ──
	featSection, _ := toml.TreeFromMap(map[string]interface{}{})
	if existingFeat := tree.Get("features"); existingFeat != nil {
		if featTree, ok := existingFeat.(*toml.Tree); ok {
			for _, k := range featTree.Keys() {
				featSection.Set(k, featTree.Get(k))
			}
		}
	}
	featSection.Set("responses_websockets_v2", p.Websocket)
	tree.Set("features", featSection)

	// ── Write tree back to string ──
	var buf bytes.Buffer
	if _, err := tree.WriteTo(&buf); err != nil {
		return err
	}
	treeContent := buf.String()

	// ── Inject probe ──
	finalContent := injectProbe(treeContent, probe)

	// ── Write config ──
	if err := writeCodexConfigRaw(finalContent); err != nil {
		return err
	}

	// ── Write auth ──
	if err := writeAuth(p.APIKey); err != nil {
		return err
	}

	return nil
}

// isManagedProviderName checks if a model_providers table name is managed by cxf.
func isManagedProviderName(name string) bool {
	names, err := listProviders()
	if err != nil {
		return false
	}
	for _, n := range names {
		p, err := readProvider(n)
		if err != nil {
			continue
		}
		if p.ProviderTableName() == name {
			return true
		}
	}
	return false
}

// detectCodexDrift checks if the active Codex config differs from what would be written.
// Returns list of drifted field names.
func detectCodexDrift(p *Provider) ([]string, error) {
	raw, tree, err := readCodexConfigRaw()
	if err != nil {
		return nil, err
	}
	if raw == "" {
		return []string{"(no config)"}, nil
	}

	var drifted []string

	// Get current probe
	lines := strings.Split(raw, "\n")
	currentProbe := extractProbe(lines)
	if currentProbe != p.ProviderID {
		drifted = append(drifted, "probe (expected: "+p.ProviderID+")")
	}

	// Compare known keys
	base, _ := loadBase()
	checks := map[string]func() string{
		"model": func() string {
			if v := tree.Get("model"); v != nil {
				return fmt.Sprintf("%v", v)
			}
			return "<missing>"
		},
		"model_provider": func() string {
			if v := tree.Get("model_provider"); v != nil {
				return fmt.Sprintf("%v", v)
			}
			return "<missing>"
		},
	}

	_ = base // used for expected comparison below

	expectedModel := p.ModelProviders
	if v := tree.Get("model_provider"); v != nil {
		if fmt.Sprintf("%v", v) != expectedModel {
			drifted = append(drifted, "model_provider")
		}
	}

	// Check model
	if v := tree.Get("model"); v != nil {
		if fmt.Sprintf("%v", v) != base.Model {
			drifted = append(drifted, "model")
		}
	} else {
		drifted = append(drifted, "model (missing)")
	}

	// Check review_model
	if v := tree.Get("review_model"); v != nil {
		if fmt.Sprintf("%v", v) != base.ReviewModel {
			drifted = append(drifted, "review_model")
		}
	}

	// Check model_reasoning_effort
	if v := tree.Get("model_reasoning_effort"); v != nil {
		if fmt.Sprintf("%v", v) != base.ModelReasoningEffort {
			drifted = append(drifted, "model_reasoning_effort")
		}
	}

	// Check context_window
	expectedCtx := base.ModelContextWindow
	if p.ContextWindow != nil {
		expectedCtx = *p.ContextWindow
	}
	if v := tree.Get("model_context_window"); v != nil {
		if n, ok := toInt(v); ok && n != expectedCtx {
			drifted = append(drifted, "model_context_window")
		}
	}

	// Check auto_compact
	expectedAC := base.ModelAutoCompactLimit
	if p.AutoCompactTokenLimit != nil {
		expectedAC = *p.AutoCompactTokenLimit
	}
	if v := tree.Get("model_auto_compact_token_limit"); v != nil {
		if n, ok := toInt(v); ok && n != expectedAC {
			drifted = append(drifted, "model_auto_compact_token_limit")
		}
	}

	// Check features.responses_websockets_v2
	if v := tree.Get("features.responses_websockets_v2"); v != nil {
		if fmt.Sprintf("%v", v) != fmt.Sprintf("%v", p.Websocket) {
			drifted = append(drifted, "features.responses_websockets_v2")
		}
	}

	_ = checks // keep compiler happy, re-use unused var
	// Note: checks map intentionally unused inline above, keeping for docs

	return drifted, nil
}

// getCurrentCodexProvider reads the probe from Codex config.
func getCurrentCodexProvider() (string, error) {
	data, err := os.ReadFile(codexConfigPath)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", err
	}
	lines := strings.Split(string(data), "\n")
	return extractProbe(lines), nil
}

// extractAllProviders scans Codex config.toml and extracts all [model_providers.XXX]
// tables as Provider objects. Used for `cxf init`.
func extractAllProviders() ([]*Provider, error) {
	_, tree, err := readCodexConfigRaw()
	if err != nil {
		return nil, err
	}

	var providers []*Provider
	usedIDs := map[string]bool{}

	mpSection := tree.Get("model_providers")
	if mpSection == nil {
		return nil, nil
	}
	mpTree, ok := mpSection.(*toml.Tree)
	if !ok {
		return nil, nil
	}

	for _, tableName := range mpTree.Keys() {
		subTree := mpTree.Get(tableName)
		sub, ok := subTree.(*toml.Tree)
		if !ok {
			continue
		}

		p := &Provider{
			ProviderID: tableName,
		}

		// Read fields from the table
		if v := sub.Get("name"); v != nil {
			p.ModelProviders = fmt.Sprintf("%v", v)
		} else {
			p.ModelProviders = tableName
		}
		if v := sub.Get("base_url"); v != nil {
			p.BaseURL = fmt.Sprintf("%v", v)
		}
		if v := sub.Get("wire_api"); v != nil {
			p.WireAPI = fmt.Sprintf("%v", v)
		}
		if v := sub.Get("supports_websockets"); v != nil {
			p.Websocket = v.(bool)
		}
		if v := sub.Get("requires_openai_auth"); v != nil {
			p.RequiresOpenAIAuth = v.(bool)
		}
		if v := sub.Get("api_key"); v != nil {
			p.APIKey = fmt.Sprintf("%v", v)
		}

		// Handle context_window and auto_compact from top-level
		if v := tree.Get("model_context_window"); v != nil {
			if n, ok := toInt(v); ok {
				p.ContextWindow = &n
			}
		}
		if v := tree.Get("model_auto_compact_token_limit"); v != nil {
			if n, ok := toInt(v); ok {
				p.AutoCompactTokenLimit = &n
			}
		}

		// Deduplicate provider_id
		originalID := p.ProviderID
		suffix := 2
		for usedIDs[p.ProviderID] {
			p.ProviderID = fmt.Sprintf("%s-%d", originalID, suffix)
			suffix++
		}
		usedIDs[p.ProviderID] = true

		providers = append(providers, p)
	}

	return providers, nil
}

// ── Snapshot ───────────────────────────────────────────────────────────

func takeSnapshot() error {
	data, err := os.ReadFile(codexConfigPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	// Get current provider name for the snapshot filename
	probe, _ := getCurrentCodexProvider()
	if probe == "" {
		probe = "unknown"
	}
	// Clean the probe for use in filename
	safeName := strings.ReplaceAll(probe, "/", "_")
	path := filepath.Join(snapshotsDir, fmt.Sprintf("codex-config-%s.toml", safeName))
	return os.WriteFile(path, data, 0600)
}

// ── Generate provider rendering for drift display ──────────────────────

func renderProviderConfig(p *Provider) string {
	var buf strings.Builder
	base, _ := loadBase()

	buf.WriteString(fmt.Sprintf("model = %q\n", base.Model))
	buf.WriteString(fmt.Sprintf("model_provider = %q\n", p.ModelProviders))
	buf.WriteString(fmt.Sprintf("review_model = %q\n", base.ReviewModel))
	buf.WriteString(fmt.Sprintf("model_reasoning_effort = %q\n", base.ModelReasoningEffort))
	buf.WriteString(fmt.Sprintf("model_context_window = %d\n", base.ModelContextWindow))
	buf.WriteString(fmt.Sprintf("model_auto_compact_token_limit = %d\n", base.ModelAutoCompactLimit))

	if p.ContextWindow != nil {
		buf.WriteString(fmt.Sprintf("model_context_window = %d  (provider override)\n", *p.ContextWindow))
	}
	if p.AutoCompactTokenLimit != nil {
		buf.WriteString(fmt.Sprintf("model_auto_compact_token_limit = %d  (provider override)\n", *p.AutoCompactTokenLimit))
	}

	buf.WriteString(fmt.Sprintf("\n[model_providers.%s]\n", p.ProviderTableName()))
	mapping := providerTableMapping(p)
	keys := make([]string, 0, len(mapping))
	for k := range mapping {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		buf.WriteString(fmt.Sprintf("%s = %v\n", k, mapping[k]))
	}

	buf.WriteString(fmt.Sprintf("\n[features]\nresponses_websockets_v2 = %v\n", p.Websocket))

	return buf.String()
}
