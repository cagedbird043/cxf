package main

import (
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

// ── Line-level config editing ──────────────────────────────────────────

// flattenModelProviders removes the empty `[model_providers]` parent header and
// flattens its sub-sections to top-level (matching Codex native style).
func flattenModelProviders(lines []string) []string {
	// Find `[model_providers]` at some indentation level
	parentIdx := -1
	var parentIndent string
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "[model_providers]" {
			parentIdx = i
			parentIndent = line[:len(line)-len(trimmed)]
			break
		}
	}
	if parentIdx < 0 {
		return lines
	}

	// Find the end of the parent section: stop at first non-model_providers section
	endIdx := len(lines)
	for i := parentIdx + 1; i < len(lines); i++ {
		trimmed := strings.TrimSpace(lines[i])
		if strings.HasPrefix(trimmed, "[") && strings.HasSuffix(trimmed, "]") {
			if !strings.HasPrefix(trimmed, "[model_providers.") {
				endIdx = i
				break
			}
		}
	}

	// Build result: skip parent, flatten sub-sections within scope
	var result []string
	for i := 0; i < len(lines); i++ {
		if i == parentIdx {
			continue // remove parent header
		}
		if i > parentIdx && i < endIdx {
			trimmed := strings.TrimSpace(lines[i])
			if trimmed == "" {
				continue // skip blank lines under parent
			}
			// De-indent by removing leading whitespace up to 2 levels
			// Level 1: `  [model_providers.XXX]` → `[model_providers.XXX]`
			// Level 2: `    key = val` → `  key = val`
			cleaned := strings.TrimLeft(lines[i], " \t")
			// If it was a body line (had more indent than header), add back 2 spaces
			if len(lines[i])-len(cleaned) > len(parentIndent)+2 {
				result = append(result, "  "+cleaned)
			} else {
				result = append(result, cleaned)
			}
			continue
		}
		result = append(result, lines[i])
	}
	return result
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

// removeCxfManagedSections removes [model_providers.XXX] sections that are managed
// by cxf but don't match the current tableName. Returns modified lines.
func removeCxfManagedSections(lines []string, keepTableName string) []string {
	var result []string
	i := 0
	for i < len(lines) {
		trimmed := strings.TrimSpace(lines[i])
		// Check if this line starts a model_providers sub-section
		if strings.HasPrefix(trimmed, "[model_providers.") && strings.HasSuffix(trimmed, "]") {
			// Extract the table name
			tableName := trimmed[len("[model_providers.") : len(trimmed)-1]
			// Check if it's managed by cxf but not the current one
			if tableName != keepTableName && isManagedProviderName(tableName) {
				// Skip this section (header + body until next section)
				i++
				for i < len(lines) {
					t := strings.TrimSpace(lines[i])
					if strings.HasPrefix(t, "[") && strings.HasSuffix(t, "]") {
						break
					}
					i++
				}
				continue
			}
		}
		result = append(result, lines[i])
		i++
	}
	return result
}

// replaceLineForKey finds a line starting with `key = ` and replaces its value.
// Returns the original lines if key not found.
func replaceLineForKey(lines []string, key, newValue string) []string {
	prefix := key + " ="
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, prefix) {
			// Preserve original indentation
			indent := line[:len(line)-len(strings.TrimLeft(line, " \t"))]
			lines[i] = indent + key + " = " + newValue
			break
		}
	}
	return lines
}

// replaceSection finds a TOML section header `[sectionName]` and replaces
// its body lines with the given content lines. Detects original indentation.
// If not found, appends at end with no indentation.
func replaceSection(lines []string, sectionName string, bodyLines []string) []string {
	startIdx := -1
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == sectionName {
			startIdx = i
			break
		}
	}

	// Section not found — append at end
	if startIdx < 0 {
		result := make([]string, len(lines))
		copy(result, lines)
		result = append(result, "")
		result = append(result, sectionName)
		result = append(result, bodyLines...)
		return result
	}

	// Detect indentation from the section header itself
	headerIndent := ""
	if len(lines[startIdx]) > len(strings.TrimSpace(lines[startIdx])) {
		headerIndent = lines[startIdx][:len(lines[startIdx])-len(strings.TrimSpace(lines[startIdx]))]
	}
	// Body gets headerIndent + 2 spaces (standard TOML sub-table body indentation)
	bodyIndent := headerIndent + "  "

	// Apply body indentation
	indentedBody := make([]string, len(bodyLines))
	for i, bl := range bodyLines {
		indentedBody[i] = bodyIndent + bl
	}

	// Find end of section (next `[...]` or EOF)
	endIdx := len(lines)
	for i := startIdx + 1; i < len(lines); i++ {
		trimmed := strings.TrimSpace(lines[i])
		if strings.HasPrefix(trimmed, "[") && strings.HasSuffix(trimmed, "]") {
			endIdx = i
			break
		}
	}

	// Keep the section header, remove old body, insert new body
	var result []string
	result = append(result, lines[:startIdx+1]...)
	result = append(result, indentedBody...)
	result = append(result, lines[endIdx:]...)
	return result
}

// applyProvider injects a Provider's settings into Codex config.toml
// using targeted line edits — no full-file rewrite.
func applyProvider(p *Provider) error {
	// ── Read raw file ──
	raw, err := os.ReadFile(codexConfigPath)
	if err != nil {
		if !os.IsNotExist(err) {
			return err
		}
		// No file yet — build from scratch
		return applyProviderNew(p)
	}
	lines := strings.Split(string(raw), "\n")

	base, err := loadBase()
	if err != nil {
		return err
	}

	// ── 1. Remove old probe line ──
	lines = removeProbeLines(lines)

	// ── 2. Replace managed top-level keys ──
	lines = replaceLineForKey(lines, "model", fmt.Sprintf("%q", base.Model))
	lines = replaceLineForKey(lines, "model_provider", fmt.Sprintf("%q", p.ModelProviders))
	lines = replaceLineForKey(lines, "review_model", fmt.Sprintf("%q", base.ReviewModel))
	lines = replaceLineForKey(lines, "model_reasoning_effort", fmt.Sprintf("%q", base.ModelReasoningEffort))

	ctx := int64(base.ModelContextWindow)
	if p.ContextWindow != nil {
		ctx = int64(*p.ContextWindow)
	}
	lines = replaceLineForKey(lines, "model_context_window", fmt.Sprintf("%d", ctx))

	ac := int64(base.ModelAutoCompactLimit)
	if p.AutoCompactTokenLimit != nil {
		ac = int64(*p.AutoCompactTokenLimit)
	}
	lines = replaceLineForKey(lines, "model_auto_compact_token_limit", fmt.Sprintf("%d", ac))

	// ── 3. Replace features.responses_websockets_v2 ──
	lines = replaceLineForKey(lines, "responses_websockets_v2", fmt.Sprintf("%v", p.Websocket))

	// ── 4. Clean stale cxf-managed [model_providers.XXX] sections ──
	tableName := p.ProviderTableName()
	lines = removeCxfManagedSections(lines, tableName)

	// ── 4b. Flatten model_providers section (remove parent header, de-indent) ──
	lines = flattenModelProviders(lines)

	// ── 5. Replace/create [model_providers.<tableName>] body ──
	mapping := providerTableMapping(p)
	mpKeys := make([]string, 0, len(mapping))
	for k := range mapping {
		mpKeys = append(mpKeys, k)
	}
	sort.Strings(mpKeys)
	var mpBody []string
	for _, k := range mpKeys {
		mpBody = append(mpBody, fmt.Sprintf("%s = %s", k, formatTOMLValue(mapping[k])))
	}
	sectionHeader := fmt.Sprintf("[model_providers.%s]", tableName)
	lines = replaceSection(lines, sectionHeader, mpBody)

	// ── 5. Inject new probe ──
	// Find #:schema or insert at top
	var schemaIdx int
	for i, line := range lines {
		if strings.HasPrefix(strings.TrimSpace(line), "#:schema") {
			schemaIdx = i + 1
			break
		}
	}
	probeLine := codexProbePrefix + p.ProviderID
	// Insert probe at correct position
	var newLines []string
	newLines = append(newLines, lines[:schemaIdx]...)
	newLines = append(newLines, probeLine)
	newLines = append(newLines, lines[schemaIdx:]...)

	// ── 6. Write ──
	if err := writeCodexConfigRaw(strings.Join(newLines, "\n")); err != nil {
		return err
	}

	// ── 7. Auth ──
	if err := writeAuth(p.APIKey); err != nil {
		return err
	}

	return nil
}

// applyProviderNew creates a fresh Codex config from scratch.
func applyProviderNew(p *Provider) error {
	base, err := loadBase()
	if err != nil {
		return err
	}

	var buf strings.Builder
	buf.WriteString(fmt.Sprintf("%s%s\n", codexProbePrefix, p.ProviderID))
	buf.WriteString(fmt.Sprintf("model = %s\n", formatTOMLValue(base.Model)))
	buf.WriteString(fmt.Sprintf("model_provider = %s\n", formatTOMLValue(p.ModelProviders)))
	buf.WriteString(fmt.Sprintf("review_model = %s\n", formatTOMLValue(base.ReviewModel)))
	buf.WriteString(fmt.Sprintf("model_reasoning_effort = %s\n", formatTOMLValue(base.ModelReasoningEffort)))
	ctx := int64(base.ModelContextWindow)
	if p.ContextWindow != nil {
		ctx = int64(*p.ContextWindow)
	}
	buf.WriteString(fmt.Sprintf("model_context_window = %s\n", formatTOMLValue(ctx)))
	ac := int64(base.ModelAutoCompactLimit)
	if p.AutoCompactTokenLimit != nil {
		ac = int64(*p.AutoCompactTokenLimit)
	}
	buf.WriteString(fmt.Sprintf("model_auto_compact_token_limit = %s\n", formatTOMLValue(ac)))

	tableName := p.ProviderTableName()
	buf.WriteString(fmt.Sprintf("\n[model_providers.%s]\n", tableName))
	mapping := providerTableMapping(p)
	mpKeys := make([]string, 0, len(mapping))
	for k := range mapping {
		mpKeys = append(mpKeys, k)
	}
	sort.Strings(mpKeys)
	for _, k := range mpKeys {
		buf.WriteString(fmt.Sprintf("%s = %s\n", k, formatTOMLValue(mapping[k])))
	}

	buf.WriteString(fmt.Sprintf("\n[features]\nresponses_websockets_v2 = %s\n", formatTOMLValue(p.Websocket)))

	if err := writeCodexConfigRaw(buf.String()); err != nil {
		return err
	}
	return writeAuth(p.APIKey)
}

// renderAuthDiff returns a string describing the api_key change in auth.json.
func renderAuthDiff(p *Provider) string {
	auth, err := readAuth()
	if err != nil {
		return ""
	}
	currentKey, _ := auth["OPENAI_API_KEY"].(string)
	if currentKey == p.APIKey || currentKey == "" {
		return ""
	}
	var buf strings.Builder
	buf.WriteString("\n" + bold("~/.codex/auth.json:") + "\n")
	buf.WriteString(red("- api_key = "+formatTOMLValue(currentKey)+" (current)") + "\n")
	buf.WriteString(green("+ api_key = "+formatTOMLValue(p.APIKey)+" (new)") + "\n")
	return buf.String()
}

func extractManagedValues() string {
	_, tree, err := readCodexConfigRaw()
	if err != nil || tree == nil {
		return ""
	}
	var buf strings.Builder

	// Top-level managed keys (same order as renderProviderConfig)
	keys := []struct {
		key string
		def interface{}
	}{
		{"model", ""},
		{"model_provider", ""},
		{"review_model", ""},
		{"model_reasoning_effort", ""},
		{"model_context_window", int64(0)},
		{"model_auto_compact_token_limit", int64(0)},
	}
	for _, k := range keys {
		if v := tree.Get(k.key); v != nil {
			buf.WriteString(fmt.Sprintf("%s = %s\n", k.key, formatTOMLValue(v)))
		}
	}

	// model_providers section
	if mp := tree.Get("model_providers"); mp != nil {
		if mpTree, ok := mp.(*toml.Tree); ok {
			tableNames := mpTree.Keys()
			sort.Strings(tableNames)
			for _, tableName := range tableNames {
				sectionName := fmt.Sprintf("[model_providers.%s]", tableName)
				buf.WriteString(fmt.Sprintf("\n%s\n", sectionName))
				if table := mpTree.Get(tableName); table != nil {
					if tTree, ok := table.(*toml.Tree); ok {
						keys := tTree.Keys()
						sort.Strings(keys)
						for _, k := range keys {
							if v := tTree.Get(k); v != nil {
								buf.WriteString(fmt.Sprintf("%s = %s\n", k, formatTOMLValue(v)))
							}
						}
					}
				}
			}
		}
	}

	// features
	buf.WriteString("\n[features]\n")
	if v := tree.Get("features.responses_websockets_v2"); v != nil {
		buf.WriteString(fmt.Sprintf("responses_websockets_v2 = %v\n", v))
	} else {
		buf.WriteString("responses_websockets_v2 = false\n")
	}

	return buf.String()
}

func formatTOMLValue(v interface{}) string {
	switch x := v.(type) {
	case string:
		return fmt.Sprintf("%q", x)
	case int64, float64, bool:
		return fmt.Sprintf("%v", x)
	default:
		return fmt.Sprintf("%v", x)
	}
}

func renderProviderConfig(p *Provider) string {
	var buf strings.Builder
	base, _ := loadBase()

	buf.WriteString(fmt.Sprintf("model = %s\n", formatTOMLValue(base.Model)))
	buf.WriteString(fmt.Sprintf("model_provider = %s\n", formatTOMLValue(p.ModelProviders)))
	buf.WriteString(fmt.Sprintf("review_model = %s\n", formatTOMLValue(base.ReviewModel)))
	buf.WriteString(fmt.Sprintf("model_reasoning_effort = %s\n", formatTOMLValue(base.ModelReasoningEffort)))

	ctx := int64(base.ModelContextWindow)
	if p.ContextWindow != nil {
		ctx = int64(*p.ContextWindow)
	}
	buf.WriteString(fmt.Sprintf("model_context_window = %s\n", formatTOMLValue(ctx)))

	ac := int64(base.ModelAutoCompactLimit)
	if p.AutoCompactTokenLimit != nil {
		ac = int64(*p.AutoCompactTokenLimit)
	}
	buf.WriteString(fmt.Sprintf("model_auto_compact_token_limit = %s\n", formatTOMLValue(ac)))

	buf.WriteString(fmt.Sprintf("\n[model_providers.%s]\n", p.ProviderTableName()))
	mapping := providerTableMapping(p)
	keys := make([]string, 0, len(mapping))
	for k := range mapping {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		buf.WriteString(fmt.Sprintf("%s = %s\n", k, formatTOMLValue(mapping[k])))
	}

	buf.WriteString(fmt.Sprintf("\n[features]\nresponses_websockets_v2 = %s\n", formatTOMLValue(p.Websocket)))

	return buf.String()
}
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
	// Ensure snapshots dir exists
	if err := os.MkdirAll(snapshotsDir, 0755); err != nil {
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

// managedCodexKeys returns the top-level keys that cxf manages.
func managedCodexKeys() []string {
	return []string{
		"model",
		"model_provider",
		"review_model",
		"model_reasoning_effort",
		"model_context_window",
		"model_auto_compact_token_limit",
	}
}

// extractManagedValues reads only the cxf-managed fields from the current
// Codex config and returns them in the SAME format as renderProviderConfig.
