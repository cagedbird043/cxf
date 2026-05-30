package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/sergi/go-diff/diffmatchpatch"
)

// ── ANSI colors (zero-dependency, matches skills) ──────────────────────

var useColor = os.Getenv("NO_COLOR") == "" && isTerminal()

func isTerminal() bool {
	fi, err := os.Stdout.Stat()
	return err == nil && (fi.Mode()&os.ModeCharDevice) != 0
}

func green(s string) string {
	if !useColor {
		return s
	}
	return "\033[32m" + s + "\033[0m"
}

func red(s string) string {
	if !useColor {
		return s
	}
	return "\033[31m" + s + "\033[0m"
}

func yellow(s string) string {
	if !useColor {
		return s
	}
	return "\033[33m" + s + "\033[0m"
}

func dim(s string) string {
	if !useColor {
		return s
	}
	return "\033[2m" + s + "\033[0m"
}

func bold(s string) string {
	if !useColor {
		return s
	}
	return "\033[1m" + s + "\033[0m"
}

// ── Output helpers ─────────────────────────────────────────────────────

var quiet bool

func ok(msg string, args ...interface{}) {
	if quiet {
		return
	}
	fmt.Printf("  "+green("✓")+" %s\n", fmt.Sprintf(msg, args...))
}

func fail(msg string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, "  "+red("✗")+" %s\n", fmt.Sprintf(msg, args...))
}

func warn(msg string, args ...interface{}) {
	if quiet {
		return
	}
	fmt.Fprintf(os.Stderr, "  "+yellow("⚠")+" %s\n", fmt.Sprintf(msg, args...))
}

func info(msg string, args ...interface{}) {
	if quiet {
		return
	}
	fmt.Printf("  %s\n", fmt.Sprintf(msg, args...))
}

// ── Diff rendering ─────────────────────────────────────────────────────

func renderDiff(expected, actual string) string {
	dmp := diffmatchpatch.New()
	diffs := dmp.DiffMain(expected, actual, true)
	diffs = dmp.DiffCleanupSemantic(diffs)

	var buf strings.Builder
	for _, d := range diffs {
		switch d.Type {
		case diffmatchpatch.DiffEqual:
			buf.WriteString(dim(d.Text))
		case diffmatchpatch.DiffDelete:
			buf.WriteString(red("-" + d.Text))
		case diffmatchpatch.DiffInsert:
			buf.WriteString(green("+" + d.Text))
		}
	}
	return buf.String()
}

func renderUnifiedDiff(expected, actual string) string {
	dmp := diffmatchpatch.New()

	// Use DiffLinesToChars for line-level diffs
	text1, text2, lineArray := dmp.DiffLinesToChars(expected, actual)
	diffs := dmp.DiffMain(text1, text2, false)
	diffs = dmp.DiffCharsToLines(diffs, lineArray)
	diffs = dmp.DiffCleanupSemantic(diffs)

	var buf strings.Builder
	for _, d := range diffs {
		switch d.Type {
		case diffmatchpatch.DiffEqual:
			continue // skip equal lines for clean diff
		case diffmatchpatch.DiffDelete:
			for _, line := range strings.Split(d.Text, "\n") {
				if line != "" {
					buf.WriteString(red("- " + line + "\n"))
				}
			}
		case diffmatchpatch.DiffInsert:
			for _, line := range strings.Split(d.Text, "\n") {
				if line != "" {
					buf.WriteString(green("+ " + line + "\n"))
				}
			}
		}
	}
	return buf.String()
}

// ── Provider table ─────────────────────────────────────────────────────

func printProviderTable(providers []*Provider, active string) {
	if len(providers) == 0 {
		info("no codex providers configured")
		return
	}
	fmt.Printf("  %-20s %-40s %s\n", bold("PROVIDER"), bold("BASE URL"), bold("STATUS"))
	fmt.Println("  " + dim(strings.Repeat("─", 75)))
	for _, p := range providers {
		status := dim("inactive")
		if p.ProviderID == active {
			status = green("active")
		}
		fmt.Printf("  %-20s %-40s %s\n", p.ProviderID, p.BaseURL, status)
	}
}

func printClaudeProviderTable(providers []*ClaudeProvider, active string) {
	if len(providers) == 0 {
		info("no claude providers configured")
		return
	}
	fmt.Printf("  %-20s %-40s %s\n", bold("PROVIDER"), bold("MODEL"), bold("STATUS"))
	fmt.Println("  " + dim(strings.Repeat("─", 75)))
	for _, cp := range providers {
		model := cp.Env["ANTHROPIC_MODEL"]
		if model == "" {
			model = dim("(default)")
		}
		status := dim("inactive")
		if cp.ProviderID == active {
			status = green("active")
		}
		fmt.Printf("  %-20s %-40s %s\n", cp.ProviderID, model, status)
	}
}

// ── Current panel ──────────────────────────────────────────────────────

func printCodexCurrent(providerID string, p *Provider) {
	fmt.Printf("  %s: %s\n", bold("provider"), providerID)
	if p != nil {
		fmt.Printf("  %s: %s\n", bold("base_url"), p.BaseURL)
		fmt.Printf("  %s: %s\n", bold("wire_api"), p.WireAPI)
		fmt.Printf("  %s: %v\n", bold("websocket"), p.Websocket)
		if p.ContextWindow != nil {
			fmt.Printf("  %s: %d\n", bold("context_window"), *p.ContextWindow)
		}
		if p.AutoCompactTokenLimit != nil {
			fmt.Printf("  %s: %d\n", bold("auto_compact"), *p.AutoCompactTokenLimit)
		}
	}
}

func printClaudeCurrent(providerID string, cp *ClaudeProvider) {
	fmt.Printf("  %s: %s\n", bold("provider"), providerID)
	if cp != nil {
		for k, v := range cp.Env {
			redacted := v
			if strings.Contains(strings.ToLower(k), "token") || strings.Contains(strings.ToLower(k), "key") {
				if len(v) > 8 {
					redacted = v[:8] + "..."
				}
			}
			fmt.Printf("  %s: %s\n", bold(k), redacted)
		}
	}
}

// ── Drift display ──────────────────────────────────────────────────────

func printDrift(fields []string, diffText string) {
	if len(fields) == 0 {
		return
	}
	warn("configuration drift detected in fields: %s", strings.Join(fields, ", "))
	if diffText != "" {
		fmt.Println()
		fmt.Println(diffText)
	}
}

func promptContinue() bool {
	fmt.Print("  continue? [y/N] ")
	var resp string
	fmt.Scanln(&resp)
	return resp == "y" || resp == "Y"
}
