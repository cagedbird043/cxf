package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ═══════════════════════════════════════════════════════════════════════
// Setup helpers
// ═══════════════════════════════════════════════════════════════════════

func newTestRoot(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	testSetRoot(root)
	return root
}

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
}

func readFile(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

// ═══════════════════════════════════════════════════════════════════════
// Provider CRUD
// ═══════════════════════════════════════════════════════════════════════

func TestWriteAndReadProvider(t *testing.T) {
	newTestRoot(t)

	cw := 100000
	ac := 90000
	p := &Provider{
		ProviderID:         "test-provider",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://api.test.com/v1",
		APIKey:             "sk-test123",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
		ContextWindow:      &cw,
		AutoCompactTokenLimit: &ac,
	}

	if err := writeProvider(p); err != nil {
		t.Fatal(err)
	}

	got, err := readProvider("test-provider")
	if err != nil {
		t.Fatal(err)
	}

	if got.ProviderID != "test-provider" {
		t.Errorf("ProviderID = %q, want %q", got.ProviderID, "test-provider")
	}
	if got.BaseURL != "https://api.test.com/v1" {
		t.Errorf("BaseURL = %q", got.BaseURL)
	}
	if got.APIKey != "sk-test123" {
		t.Errorf("APIKey = %q", got.APIKey)
	}
	if got.WireAPI != "responses" {
		t.Errorf("WireAPI = %q", got.WireAPI)
	}
	if !got.RequiresOpenAIAuth {
		t.Error("RequiresOpenAIAuth should be true")
	}
	if !got.Websocket {
		t.Error("Websocket should be true")
	}
	if got.ContextWindow == nil || *got.ContextWindow != cw {
		t.Errorf("ContextWindow = %v, want %d", got.ContextWindow, cw)
	}
	if got.AutoCompactTokenLimit == nil || *got.AutoCompactTokenLimit != ac {
		t.Errorf("AutoCompactTokenLimit = %v, want %d", got.AutoCompactTokenLimit, ac)
	}
}

func TestWriteProviderMinimal(t *testing.T) {
	newTestRoot(t)

	p := &Provider{
		ProviderID:         "minimal",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://api.test.com",
		APIKey:             "sk-key",
		WireAPI:            "chat",
		RequiresOpenAIAuth: false,
		Websocket:          false,
	}

	if err := writeProvider(p); err != nil {
		t.Fatal(err)
	}

	got, err := readProvider("minimal")
	if err != nil {
		t.Fatal(err)
	}

	if got.ProviderID != "minimal" {
		t.Errorf("ProviderID = %q", got.ProviderID)
	}
	if got.ContextWindow != nil {
		t.Error("ContextWindow should be nil for minimal provider")
	}
	if got.AutoCompactTokenLimit != nil {
		t.Error("AutoCompactTokenLimit should be nil for minimal provider")
	}
	if got.WireAPI != "chat" {
		t.Errorf("WireAPI = %q", got.WireAPI)
	}
}

func TestReadProviderNotFound(t *testing.T) {
	newTestRoot(t)
	_, err := readProvider("nonexistent")
	if err == nil {
		t.Fatal("expected error for nonexistent provider")
	}
	if !strings.Contains(err.Error(), "not found") {
		t.Errorf("error = %v, want 'not found'", err)
	}
}

func TestDeleteProvider(t *testing.T) {
	newTestRoot(t)

	p := &Provider{
		ProviderID:         "todelete",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://api.test.com",
		APIKey:             "sk-key",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          false,
	}
	if err := writeProvider(p); err != nil {
		t.Fatal(err)
	}

	if err := deleteProvider("todelete"); err != nil {
		t.Fatal(err)
	}

	if providerExists("todelete") {
		t.Error("provider should not exist after delete")
	}
}

func TestDeleteProviderNotFound(t *testing.T) {
	newTestRoot(t)
	err := deleteProvider("nonexistent")
	if err == nil {
		t.Fatal("expected error for nonexistent provider")
	}
}

func TestListProviders(t *testing.T) {
	newTestRoot(t)

	names, err := listProviders()
	if err != nil {
		t.Fatal(err)
	}
	if len(names) != 0 {
		t.Errorf("expected 0 providers, got %d", len(names))
	}

	for _, name := range []string{"alpha", "beta", "gamma"} {
		p := &Provider{
			ProviderID:         name,
			ModelProviders:     "OpenAI",
			BaseURL:            "https://" + name + ".test.com",
			APIKey:             "sk-" + name,
			WireAPI:            "responses",
			RequiresOpenAIAuth: true,
			Websocket:          false,
		}
		if err := writeProvider(p); err != nil {
			t.Fatal(err)
		}
	}

	names, err = listProviders()
	if err != nil {
		t.Fatal(err)
	}
	if len(names) != 3 {
		t.Errorf("expected 3 providers, got %d: %v", len(names), names)
	}
}

func TestProviderExists(t *testing.T) {
	newTestRoot(t)

	if providerExists("nope") {
		t.Error("should not exist yet")
	}

	p := &Provider{
		ProviderID:         "exists",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://exists.test.com",
		APIKey:             "sk-exists",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
	}
	if err := writeProvider(p); err != nil {
		t.Fatal(err)
	}

	if !providerExists("exists") {
		t.Error("should exist after write")
	}
}

// ═══════════════════════════════════════════════════════════════════════
// Claude Provider CRUD
// ═══════════════════════════════════════════════════════════════════════

func TestWriteAndReadClaudeProvider(t *testing.T) {
	newTestRoot(t)

	cp := &ClaudeProvider{
		ProviderID: "test-claude",
		Env: map[string]string{
			"ANTHROPIC_BASE_URL":  "https://api.claude.test.com",
			"ANTHROPIC_AUTH_TOKEN": "sk-claude-123",
			"ANTHROPIC_MODEL":     "claude-opus-4",
		},
	}

	if err := writeClaudeProvider(cp); err != nil {
		t.Fatal(err)
	}

	got, err := readClaudeProvider("test-claude")
	if err != nil {
		t.Fatal(err)
	}

	if got.ProviderID != "test-claude" {
		t.Errorf("ProviderID = %q", got.ProviderID)
	}
	if got.Env["ANTHROPIC_BASE_URL"] != "https://api.claude.test.com" {
		t.Errorf("BaseURL = %q", got.Env["ANTHROPIC_BASE_URL"])
	}
	if got.Env["ANTHROPIC_AUTH_TOKEN"] != "sk-claude-123" {
		t.Errorf("Token = %q", got.Env["ANTHROPIC_AUTH_TOKEN"])
	}
	if got.Env["ANTHROPIC_MODEL"] != "claude-opus-4" {
		t.Errorf("Model = %q", got.Env["ANTHROPIC_MODEL"])
	}
}

func TestClaudeProviderNotFound(t *testing.T) {
	newTestRoot(t)
	_, err := readClaudeProvider("nonexistent")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestListClaudeProviders(t *testing.T) {
	newTestRoot(t)

	names, err := listClaudeProviders()
	if err != nil {
		t.Fatal(err)
	}
	if len(names) != 0 {
		t.Errorf("expected 0, got %d", len(names))
	}

	for _, name := range []string{"a", "b"} {
		cp := &ClaudeProvider{ProviderID: name, Env: map[string]string{"MODEL": name}}
		if err := writeClaudeProvider(cp); err != nil {
			t.Fatal(err)
		}
	}

	names, err = listClaudeProviders()
	if err != nil {
		t.Fatal(err)
	}
	if len(names) != 2 {
		t.Errorf("expected 2, got %d: %v", len(names), names)
	}
}

// ═══════════════════════════════════════════════════════════════════════
// JSON / Auth operations
// ═══════════════════════════════════════════════════════════════════════

func TestReadJSONFileNotExist(t *testing.T) {
	dir := t.TempDir()
	data, err := readJSONFile(filepath.Join(dir, "nope.json"))
	if err != nil {
		t.Fatal(err)
	}
	if len(data) != 0 {
		t.Errorf("expected empty map, got %v", data)
	}
}

func TestReadJSONFileCorrupted(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bad.json")
	writeFile(t, path, "{this is not json")

	data, err := readJSONFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(data) != 0 {
		t.Errorf("expected empty map for corrupted json, got %v", data)
	}
}

func TestWriteAndReadJSONFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.json")

	input := map[string]interface{}{
		"key1": "value1",
		"key2": float64(42),
	}
	if err := writeJSONFile(path, input); err != nil {
		t.Fatal(err)
	}

	got, err := readJSONFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if got["key1"] != "value1" {
		t.Errorf("key1 = %v", got["key1"])
	}
}

func TestWriteAuthMerge(t *testing.T) {
	newTestRoot(t)
	os.MkdirAll(filepath.Dir(authPath), 0755)

	// Pre-write with an extra field
	existing := map[string]interface{}{
		"OPENAI_ORG_ID": "org-xyz",
	}
	writeJSONFile(authPath, existing)

	// Write auth — should merge, not replace
	if err := writeAuth("sk-new-key"); err != nil {
		t.Fatal(err)
	}

	data, err := readAuth()
	if err != nil {
		t.Fatal(err)
	}
	if data["OPENAI_API_KEY"] != "sk-new-key" {
		t.Errorf("API key = %v", data["OPENAI_API_KEY"])
	}
	if data["OPENAI_ORG_ID"] != "org-xyz" {
		t.Errorf("ORG_ID lost: %v", data["OPENAI_ORG_ID"])
	}
	if data["OPENAI_API_KEY"] == nil {
		t.Error("API key missing after write")
	}
}

func TestWriteAuthNoopIfSameKey(t *testing.T) {
	newTestRoot(t)
	os.MkdirAll(filepath.Dir(authPath), 0755)
	writeFile(t, authPath, `{"OPENAI_API_KEY": "sk-same", "source": "cxf"}`)

	if err := writeAuth("sk-same"); err != nil {
		t.Fatal(err)
	}

	data, err := readAuth()
	if err != nil {
		t.Fatal(err)
	}
	if data["OPENAI_API_KEY"] != "sk-same" {
		t.Errorf("API key changed: %v", data["OPENAI_API_KEY"])
	}
}

// ═══════════════════════════════════════════════════════════════════════
// Base config
// ═══════════════════════════════════════════════════════════════════════

func TestDefaultBaseConfig(t *testing.T) {
	newTestRoot(t)
	cfg := defaultBaseConfig()
	if cfg.Model != "gpt-5.5" {
		t.Errorf("Model = %q", cfg.Model)
	}
	if cfg.ModelContextWindow != 272000 {
		t.Errorf("ContextWindow = %d", cfg.ModelContextWindow)
	}
}

func TestWriteAndLoadBase(t *testing.T) {
	newTestRoot(t)

	cfg := &BaseConfig{
		Model:                 "gpt-4",
		ReviewModel:           "gpt-4-mini",
		ModelReasoningEffort:  "low",
		ModelContextWindow:    128000,
		ModelAutoCompactLimit: 100000,
	}
	if err := writeBase(cfg); err != nil {
		t.Fatal(err)
	}

	got, err := loadBase()
	if err != nil {
		t.Fatal(err)
	}

	if got.Model != "gpt-4" {
		t.Errorf("Model = %q", got.Model)
	}
	if got.ModelContextWindow != 128000 {
		t.Errorf("ContextWindow = %d", got.ModelContextWindow)
	}
}

func TestWriteDefaultBase(t *testing.T) {
	newTestRoot(t)
	if err := writeDefaultBase(); err != nil {
		t.Fatal(err)
	}

	if _, err := os.Stat(basePath); err != nil {
		t.Errorf("base.toml not created: %v", err)
	}

	// Second call should be no-op (file exists)
	if err := writeDefaultBase(); err != nil {
		t.Fatal(err)
	}
}

// ═══════════════════════════════════════════════════════════════════════
// Probe operations
// ═══════════════════════════════════════════════════════════════════════

func TestExtractProbe(t *testing.T) {
	lines := []string{
		"#:schema https://example.com/schema",
		`# cxf: provider = my-provider`,
		`model = "gpt-4"`,
	}
	got := extractProbe(lines)
	if got != "my-provider" {
		t.Errorf("probe = %q", got)
	}
}

func TestExtractProbeNotFound(t *testing.T) {
	lines := []string{
		`model = "gpt-4"`,
		`model_provider = "OpenAI"`,
	}
	got := extractProbe(lines)
	if got != "" {
		t.Errorf("expected empty, got %q", got)
	}
}

func TestRemoveProbeLines(t *testing.T) {
	lines := []string{
		"#:schema https://example.com",
		`# cxf: provider = old-provider`,
		`model = "gpt-4"`,
		`model_provider = "OpenAI"`,
	}
	got := removeProbeLines(lines)
	if len(got) != 3 {
		t.Errorf("expected 3 lines, got %d: %v", len(got), got)
	}
	for _, line := range got {
		if strings.Contains(line, "cxf: provider") {
			t.Errorf("probe line not removed: %q", line)
		}
	}
}

func TestInjectProbeAfterSchema(t *testing.T) {
	content := "#:schema https://example.com\nmodel = \"gpt-4\"\n"
	got := injectProbe(content, "my-provider")
	expected := "#:schema https://example.com\n# cxf: provider = my-provider\nmodel = \"gpt-4\"\n"
	if got != expected {
		t.Errorf("got:\n%s\nwant:\n%s", got, expected)
	}
}

func TestInjectProbeNoSchema(t *testing.T) {
	content := "model = \"gpt-4\"\n"
	got := injectProbe(content, "my-provider")
	expected := "# cxf: provider = my-provider\nmodel = \"gpt-4\"\n"
	if got != expected {
		t.Errorf("got:\n%s\nwant:\n%s", got, expected)
	}
}

func TestInjectProbeEmptyContent(t *testing.T) {
	got := injectProbe("", "my-provider")
	expected := "# cxf: provider = my-provider\n"
	if got != expected {
		t.Errorf("got:\n%s\nwant:\n%s", got, expected)
	}
}

// ═══════════════════════════════════════════════════════════════════════
// applyProvider
// ═══════════════════════════════════════════════════════════════════════

func TestApplyProviderNewConfig(t *testing.T) {
	newTestRoot(t)

	cw := 200000
	ac := 180000
	p := &Provider{
		ProviderID:         "test",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://api.test.com/v1",
		APIKey:             "sk-test",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
		ContextWindow:      &cw,
		AutoCompactTokenLimit: &ac,
	}

	// Write base config first (applyProvider depends on it)
	writeDefaultBase()

	if err := applyProvider(p); err != nil {
		t.Fatal(err)
	}

	// Verify the config file was created
	data, err := os.ReadFile(codexConfigPath)
	if err != nil {
		t.Fatal(err)
	}
	content := string(data)

	// Check probe
	if !strings.Contains(content, "# cxf: provider = test") {
		t.Errorf("missing probe in:\n%s", content)
	}

	// Check key values
	if !strings.Contains(content, `model = "gpt-5.5"`) {
		t.Errorf("missing model in:\n%s", content)
	}
	if !strings.Contains(content, `model_provider = "OpenAI"`) {
		t.Errorf("missing model_provider in:\n%s", content)
	}
	if !strings.Contains(content, "model_context_window = 200000") {
		t.Errorf("missing context_window override in:\n%s", content)
	}

	// Check model_providers section
	if !strings.Contains(content, `supports_websockets = true`) {
		t.Errorf("missing websocket in:\n%s", content)
	}

	// Check auth was written
	authData, err := readAuth()
	if err != nil {
		t.Fatal(err)
	}
	if authData["OPENAI_API_KEY"] != "sk-test" {
		t.Errorf("auth key = %v", authData["OPENAI_API_KEY"])
	}
}

func TestApplyProviderWithExistingConfig(t *testing.T) {
	newTestRoot(t)

	// Create an existing config with an extra field that should be preserved
	existingConfig := "#:schema https://example.com\n" +
		`# cxf: provider = old` + "\n" +
		`model = "gpt-3.5"` + "\n" +
		`model_provider = "OpenAI"` + "\n" +
		`review_model = "gpt-3.5"` + "\n" +
		`model_reasoning_effort = "low"` + "\n" +
		`model_context_window = 100000` + "\n" +
		`model_auto_compact_token_limit = 90000` + "\n" +
		"\n" +
		"[model_providers.OpenAI]\n" +
		`name = "OpenAI"` + "\n" +
		`base_url = "https://old.test.com"` + "\n" +
		`wire_api = "chat"` + "\n" +
		`supports_websockets = false` + "\n" +
		`requires_openai_auth = true` + "\n" +
		"\n" +
		"[features]\n" +
		"responses_websockets_v2 = false\n"

	writeFile(t, codexConfigPath, existingConfig)
	writeDefaultBase()

	p := &Provider{
		ProviderID:         "new",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://new.test.com/v1",
		APIKey:             "sk-new",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
	}

	if err := applyProvider(p); err != nil {
		t.Fatal(err)
	}

	content := readFile(t, codexConfigPath)

	// Check probe was updated
	if !strings.Contains(content, "# cxf: provider = new") {
		t.Errorf("probe not updated:\n%s", content)
	}
	if strings.Contains(content, "# cxf: provider = old") {
		t.Errorf("old probe still present:\n%s", content)
	}

	// Check values updated
	if !strings.Contains(content, `model = "gpt-5.5"`) {
		t.Errorf("model not updated:\n%s", content)
	}

	// Check schema preserved
	if !strings.HasPrefix(strings.TrimSpace(content), "#:schema") {
		t.Errorf("#:schema not preserved:\n%s", content)
	}
}

func TestApplyProviderCleansStaleProviders(t *testing.T) {
	newTestRoot(t)

	// Config has an extra model_providers table not managed by cxf
	existingConfig := `model = "gpt-4"` + "\n" +
		`model_provider = "OpenAI"` + "\n" +
		"\n" +
		"[model_providers.OpenAI]\n" +
		`name = "OpenAI"` + "\n" +
		`base_url = "https://api.openai.com"` + "\n" +
		`wire_api = "responses"` + "\n" +
		"\n" +
		"[model_providers.CustomProvider]\n" +
		`name = "CustomProvider"` + "\n" +
		`base_url = "https://custom.com"` + "\n"

	writeFile(t, codexConfigPath, existingConfig)
	writeDefaultBase()

	p := &Provider{
		ProviderID:         "test",
		ModelProviders:     "MyProvider",
		BaseURL:            "https://my.test.com",
		APIKey:             "sk-my",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
	}
	writeProvider(p)

	if err := applyProvider(p); err != nil {
		t.Fatal(err)
	}

	content := readFile(t, codexConfigPath)

	// MyProvider should be in the config
	if !strings.Contains(content, "[model_providers.MyProvider]") {
		t.Errorf("MyProvider table not found:\n%s", content)
	}

	// CustomProvider is not cxf-managed, should be preserved
	if !strings.Contains(content, "[model_providers.CustomProvider]") {
		t.Errorf("CustomProvider (non-cxf) was removed:\n%s", content)
	}

	// OpenAI table was managed by cxf via the test provider, should now reference MyProvider
	if strings.Contains(content, `model_provider = "OpenAI"`) && !strings.Contains(content, `model_provider = "MyProvider"`) {
		t.Errorf("model_provider not updated")
	}
}

// ═══════════════════════════════════════════════════════════════════════
// detectCodexDrift
// ═══════════════════════════════════════════════════════════════════════

func TestDetectCodexDriftNoDrift(t *testing.T) {
	newTestRoot(t)

	// Create a config that matches what applyProvider would write
	config := `# cxf: provider = stable
model = "gpt-5.5"
model_provider = "OpenAI"
review_model = "gpt-5.5"
model_reasoning_effort = "high"
model_context_window = 272000
model_auto_compact_token_limit = 240000

[features]
responses_websockets_v2 = true

[model_providers.OpenAI]
name = "OpenAI"
base_url = "https://stable.com"
wire_api = "responses"
supports_websockets = true
requires_openai_auth = true
`
	writeFile(t, codexConfigPath, config)
	writeDefaultBase()

	p := &Provider{
		ProviderID:         "stable",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://stable.com",
		APIKey:             "sk-stable",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
	}

	drifted, err := detectCodexDrift(p)
	if err != nil {
		t.Fatal(err)
	}
	if len(drifted) != 0 {
		t.Errorf("expected no drift, got: %v", drifted)
	}
}

func TestDetectCodexDriftWithDrift(t *testing.T) {
	newTestRoot(t)

	// Config has a different model
	config := `# cxf: provider = stable
model = "gpt-3.5"
model_provider = "OpenAI"
review_model = "gpt-5.5"
model_reasoning_effort = "high"
model_context_window = 272000
model_auto_compact_token_limit = 240000

[features]
responses_websockets_v2 = true

[model_providers.OpenAI]
name = "OpenAI"
base_url = "https://stable.com"
wire_api = "responses"
`
	writeFile(t, codexConfigPath, config)
	writeDefaultBase()

	p := &Provider{
		ProviderID:         "stable",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://stable.com",
		APIKey:             "sk-stable",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
	}

	drifted, err := detectCodexDrift(p)
	if err != nil {
		t.Fatal(err)
	}
	if len(drifted) == 0 {
		t.Fatal("expected drift but none detected")
	}
	foundModel := false
	for _, f := range drifted {
		if f == "model" {
			foundModel = true
		}
	}
	if !foundModel {
		t.Errorf("expected 'model' in drifted fields, got: %v", drifted)
	}
}

// ═══════════════════════════════════════════════════════════════════════
// extractAllProviders
// ═══════════════════════════════════════════════════════════════════════

func TestExtractAllProviders(t *testing.T) {
	newTestRoot(t)

	config := `model = "gpt-5.5"
model_provider = "OpenAI"

[model_providers.OpenAI]
name = "OpenAI"
base_url = "https://api.openai.com"
wire_api = "responses"
supports_websockets = true
requires_openai_auth = true

[model_providers.DeepSeek]
name = "DeepSeek"
base_url = "https://api.deepseek.com"
wire_api = "chat"
supports_websockets = false
requires_openai_auth = false
`
	writeFile(t, codexConfigPath, config)

	providers, err := extractAllProviders()
	if err != nil {
		t.Fatal(err)
	}
	if len(providers) != 2 {
		t.Fatalf("expected 2 providers, got %d", len(providers))
	}

	// Find by provider_id
	var openAIProvider, deepSeekProvider *Provider
	for _, p := range providers {
		switch p.ProviderID {
		case "OpenAI":
			openAIProvider = p
		case "DeepSeek":
			deepSeekProvider = p
		}
	}

	if openAIProvider == nil {
		t.Fatal("OpenAI provider not extracted")
	}
	if openAIProvider.BaseURL != "https://api.openai.com" {
		t.Errorf("OpenAI BaseURL = %q", openAIProvider.BaseURL)
	}
	if !openAIProvider.Websocket {
		t.Error("OpenAI should have websocket=true")
	}

	if deepSeekProvider == nil {
		t.Fatal("DeepSeek provider not extracted")
	}
	if deepSeekProvider.BaseURL != "https://api.deepseek.com" {
		t.Errorf("DeepSeek BaseURL = %q", deepSeekProvider.BaseURL)
	}
	if deepSeekProvider.RequiresOpenAIAuth {
		t.Error("DeepSeek should not require OpenAI auth")
	}
}

func TestExtractAllProvidersEmptyConfig(t *testing.T) {
	newTestRoot(t)
	// No config file exists
	providers, err := extractAllProviders()
	if err != nil {
		t.Fatal(err)
	}
	if len(providers) != 0 {
		t.Errorf("expected 0 providers, got %d", len(providers))
	}
}

// ═══════════════════════════════════════════════════════════════════════
// Claude settings operations
// ═══════════════════════════════════════════════════════════════════════

func TestReadClaudeSettingsNotExist(t *testing.T) {
	newTestRoot(t)
	settings, err := readClaudeSettings()
	if err != nil {
		t.Fatal(err)
	}
	if settings == nil {
		t.Fatal("expected non-nil settings")
	}
	if settings.Model != "" {
		t.Errorf("Model = %q", settings.Model)
	}
	if len(settings.Env) != 0 {
		t.Errorf("expected empty env, got %v", settings.Env)
	}
}

func TestReadClaudeSettingsCorrupted(t *testing.T) {
	newTestRoot(t)
	writeFile(t, claudeSettingsPath, "{bad json")
	settings, err := readClaudeSettings()
	if err != nil {
		t.Fatal(err)
	}
	if settings == nil {
		t.Fatal("expected non-nil settings")
	}
}

func TestApplyClaudeProvider(t *testing.T) {
	newTestRoot(t)

	cp := &ClaudeProvider{
		ProviderID: "test-claude",
		Env: map[string]string{
			"ANTHROPIC_BASE_URL":       "https://api.claude.test.com",
			"ANTHROPIC_AUTH_TOKEN":     "sk-claude-key",
			"ANTHROPIC_MODEL":          "claude-opus-4",
			"CLAUDE_CODE_EFFORT_LEVEL": "max",
		},
	}

	if err := applyClaudeProvider(cp); err != nil {
		t.Fatal(err)
	}

	// Read back
	settings, err := readClaudeSettings()
	if err != nil {
		t.Fatal(err)
	}

	if settings.Model != "claude-opus-4" {
		t.Errorf("Model = %q", settings.Model)
	}
	if settings.Env["ANTHROPIC_BASE_URL"] != "https://api.claude.test.com" {
		t.Errorf("BaseURL = %q", settings.Env["ANTHROPIC_BASE_URL"])
	}
	if settings.Env[claudeProbeEnvKey] != "test-claude" {
		t.Errorf("probe = %q", settings.Env[claudeProbeEnvKey])
	}
}

func TestApplyClaudeProviderClearsOldKeys(t *testing.T) {
	newTestRoot(t)

	// Pre-write settings with old managed keys
	existing := &ClaudeSettings{
		Model: "old-model",
		Env: map[string]string{
			"ANTHROPIC_BASE_URL":       "https://old.com",
			"ANTHROPIC_AUTH_TOKEN":     "sk-old",
			"CXF_CLAUDE_PROVIDER":      "old-provider",
			"ANTHROPIC_MODEL":          "old-model",
			"UNRELATED_VAR":            "should-remain",
		},
	}
	if err := writeClaudeSettings(existing); err != nil {
		t.Fatal(err)
	}

	cp := &ClaudeProvider{
		ProviderID: "new-provider",
		Env: map[string]string{
			"ANTHROPIC_BASE_URL":   "https://new.com",
			"ANTHROPIC_AUTH_TOKEN": "sk-new",
			"ANTHROPIC_MODEL":      "new-model",
		},
	}

	if err := applyClaudeProvider(cp); err != nil {
		t.Fatal(err)
	}

	settings, err := readClaudeSettings()
	if err != nil {
		t.Fatal(err)
	}

	// New values set
	if settings.Env["ANTHROPIC_BASE_URL"] != "https://new.com" {
		t.Errorf("BaseURL = %q", settings.Env["ANTHROPIC_BASE_URL"])
	}

	// Old managed keys cleared
	if _, ok := settings.Env["CLAUDE_CODE_EFFORT_LEVEL"]; ok {
		t.Error("CLAUDE_CODE_EFFORT_LEVEL should have been cleared")
	}

	// Unrelated var preserved
	if settings.Env["UNRELATED_VAR"] != "should-remain" {
		t.Errorf("UNRELATED_VAR lost: %q", settings.Env["UNRELATED_VAR"])
	}

	// Model updated
	if settings.Model != "new-model" {
		t.Errorf("Model = %q", settings.Model)
	}

	// Probe set
	if settings.Env[claudeProbeEnvKey] != "new-provider" {
		t.Errorf("probe = %q", settings.Env[claudeProbeEnvKey])
	}
}

func TestDetectClaudeDrift(t *testing.T) {
	newTestRoot(t)

	// Apply a provider first
	cp := &ClaudeProvider{
		ProviderID: "test",
		Env: map[string]string{
			"ANTHROPIC_BASE_URL":   "https://test.com",
			"ANTHROPIC_AUTH_TOKEN": "sk-test",
		},
	}
	if err := applyClaudeProvider(cp); err != nil {
		t.Fatal(err)
	}

	// No drift expected
	drifted, err := detectClaudeDrift(cp)
	if err != nil {
		t.Fatal(err)
	}
	if len(drifted) != 0 {
		t.Errorf("expected no drift, got: %v", drifted)
	}

	// Manually modify settings
	settings, _ := readClaudeSettings()
	settings.Env["ANTHROPIC_BASE_URL"] = "https://hacked.com"
	writeClaudeSettings(settings)

	drifted, err = detectClaudeDrift(cp)
	if err != nil {
		t.Fatal(err)
	}
	if len(drifted) == 0 {
		t.Fatal("expected drift after manual edit")
	}
}

// ═══════════════════════════════════════════════════════════════════════
// Snapshot (basic coverage)
// ═══════════════════════════════════════════════════════════════════════

func TestTakeSnapshot(t *testing.T) {
	newTestRoot(t)

	// Create a config with a probe
	config := `# cxf: provider = test-provider
model = "gpt-5.5"
`
	writeFile(t, codexConfigPath, config)

	if err := takeSnapshot(); err != nil {
		t.Fatal(err)
	}

	// Check snapshot was created
	entries, err := os.ReadDir(snapshotsDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) == 0 {
		t.Fatal("expected snapshot file")
	}

	// Verify content
	data, err := os.ReadFile(filepath.Join(snapshotsDir, entries[0].Name()))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), "test-provider") {
		t.Errorf("snapshot missing probe reference:\n%s", string(data))
	}
}

func TestTakeClaudeSnapshot(t *testing.T) {
	newTestRoot(t)

	settings := &ClaudeSettings{
		Env: map[string]string{
			claudeProbeEnvKey: "test-claude",
			"ANTHROPIC_MODEL": "opus-4",
		},
	}
	if err := writeClaudeSettings(settings); err != nil {
		t.Fatal(err)
	}

	if err := takeClaudeSnapshot(); err != nil {
		t.Fatal(err)
	}

	entries, err := os.ReadDir(snapshotsDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) == 0 {
		t.Fatal("expected claude snapshot file")
	}
}

// ═══════════════════════════════════════════════════════════════════════
// renderProviderConfig
// ═══════════════════════════════════════════════════════════════════════

func TestRenderProviderConfig(t *testing.T) {
	newTestRoot(t)
	writeDefaultBase()

	p := &Provider{
		ProviderID:         "test",
		ModelProviders:     "TestProvider",
		BaseURL:            "https://test.com",
		APIKey:             "sk-test",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
	}

	output := renderProviderConfig(p)
	if !strings.Contains(output, "model =") {
		t.Errorf("missing model in output:\n%s", output)
	}
	if !strings.Contains(output, "[model_providers.TestProvider]") {
		t.Errorf("missing model_providers table:\n%s", output)
	}
	if !strings.Contains(output, "[features]") {
		t.Errorf("missing features section:\n%s", output)
	}
}

func TestRenderClaudeProviderConfig(t *testing.T) {
	cp := &ClaudeProvider{
		ProviderID: "test",
		Env: map[string]string{
			"ANTHROPIC_BASE_URL":   "https://test.com",
			"ANTHROPIC_AUTH_TOKEN": "sk-very-secret-key-12345",
		},
	}
	output := renderClaudeProviderConfig(cp)
	if !strings.Contains(output, "probe: test") {
		t.Errorf("missing probe in:\n%s", output)
	}
	if !strings.Contains(output, "ANTHROPIC_BASE_URL") {
		t.Errorf("missing BaseURL in:\n%s", output)
	}
}

// ═══════════════════════════════════════════════════════════════════════
// toInt helper
// ═══════════════════════════════════════════════════════════════════════

func TestToInt(t *testing.T) {
	tests := []struct {
		input    interface{}
		expected int
		ok       bool
	}{
		{int64(42), 42, true},
		{float64(3.14), 3, true},
		{42, 42, true},
		{"128000", 128000, true},
		{"abc", 0, false},
		{nil, 0, false},
		{true, 0, false},
	}

	for _, tt := range tests {
		got, ok := toInt(tt.input)
		if ok != tt.ok {
			t.Errorf("toInt(%v) ok = %v, want %v", tt.input, ok, tt.ok)
		}
		if ok && got != tt.expected {
			t.Errorf("toInt(%v) = %d, want %d", tt.input, got, tt.expected)
		}
	}
}

// ═══════════════════════════════════════════════════════════════════════
// providerTableMapping
// ═══════════════════════════════════════════════════════════════════════

func TestProviderTableMapping(t *testing.T) {
	p := &Provider{
		ModelProviders:     "OpenAI",
		BaseURL:            "https://api.openai.com",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          true,
	}

	m := providerTableMapping(p)
	if m["name"] != "OpenAI" {
		t.Errorf("name = %v", m["name"])
	}
	if m["base_url"] != "https://api.openai.com" {
		t.Errorf("base_url = %v", m["base_url"])
	}
	if m["supports_websockets"] != true {
		t.Errorf("supports_websockets = %v", m["supports_websockets"])
	}
}

// ═══════════════════════════════════════════════════════════════════════
// getCurrentCodexProvider / getCurrentClaudeProvider
// ═══════════════════════════════════════════════════════════════════════

func TestGetCurrentCodexProvider(t *testing.T) {
	newTestRoot(t)

	// No config yet
	probe, err := getCurrentCodexProvider()
	if err != nil {
		t.Fatal(err)
	}
	if probe != "" {
		t.Errorf("expected empty, got %q", probe)
	}

	// Write config with probe
	config := `# cxf: provider = my-provider
model = "gpt-5.5"
`
	writeFile(t, codexConfigPath, config)

	probe, err = getCurrentCodexProvider()
	if err != nil {
		t.Fatal(err)
	}
	if probe != "my-provider" {
		t.Errorf("probe = %q", probe)
	}
}

func TestGetCurrentClaudeProvider(t *testing.T) {
	newTestRoot(t)

	// No settings yet
	probe, err := getCurrentClaudeProvider()
	if err != nil {
		t.Fatal(err)
	}
	if probe != "" {
		t.Errorf("expected empty, got %q", probe)
	}

	// Write settings with probe
	settings := &ClaudeSettings{
		Env: map[string]string{
			claudeProbeEnvKey: "my-claude",
		},
	}
	writeClaudeSettings(settings)

	probe, err = getCurrentClaudeProvider()
	if err != nil {
		t.Fatal(err)
	}
	if probe != "my-claude" {
		t.Errorf("probe = %q", probe)
	}
}

// ═══════════════════════════════════════════════════════════════════════
// Permission check: files with secrets are 0600
// ═══════════════════════════════════════════════════════════════════════

func TestProviderFilePermission(t *testing.T) {
	newTestRoot(t)

	p := &Provider{
		ProviderID:         "perm-test",
		ModelProviders:     "OpenAI",
		BaseURL:            "https://test.com",
		APIKey:             "sk-secret",
		WireAPI:            "responses",
		RequiresOpenAIAuth: true,
		Websocket:          false,
	}
	if err := writeProvider(p); err != nil {
		t.Fatal(err)
	}

	fi, err := os.Stat(filepath.Join(providersDir, "perm-test.toml"))
	if err != nil {
		t.Fatal(err)
	}
	perm := fi.Mode().Perm()
	if perm != 0600 {
		t.Errorf("expected 0600, got %#o", perm)
	}
}

func TestAuthFilePermission(t *testing.T) {
	newTestRoot(t)

	if err := writeAuth("sk-secret"); err != nil {
		t.Fatal(err)
	}

	fi, err := os.Stat(authPath)
	if err != nil {
		t.Fatal(err)
	}
	perm := fi.Mode().Perm()
	if perm != 0600 {
		t.Errorf("expected 0600, got %#o", perm)
	}
}
