# Support & Issue Triage Guidelines

Guidelines for troubleshooting issues, getting assistance, and filing actionable bug reports for Rush CLI.

---

## 1. Before Requesting Support

Before opening an issue or asking for support, check the following resources:
1. **Troubleshooting Guides**: Read [Troubleshooting Guide](user-guide/troubleshooting.md) and the [Troubleshooting Matrix](TROUBLESHOOTING_MATRIX.md).
2. **Frequently Asked Questions**: Check [FAQ](FAQ.md) and [User Guide FAQ](user-guide/faq.md).
3. **Verify Tool Availability**: Run `rush capabilities . --json` to verify whether Rush discovers the engine on your `PATH`.
4. **Inspect Raw Output**: Run your command with `--json` or `--verbose` to inspect the raw subprocess exit codes and stderr messages.

---

## 2. Information to Include in Bug Reports

When reporting an issue, provide:
- **Rush Version**: Output of `rush --version`.
- **Operating System**: Windows, macOS, or Linux (and architecture).
- **Exact Command Executed**: Including target path and flags (e.g. `rush security . --json`).
- **Engine Version**: Version of the external engine if applicable (e.g. `semgrep --version`).
- **Sanitized Output**: The JSON result or terminal output with any proprietary code or secrets redacted.

See [Support Runbook](maintainers/support-runbook.md).
