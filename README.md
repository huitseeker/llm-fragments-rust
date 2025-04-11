# llm-fragments-rust

LLM plugin for pulling Rust crate documentation using `cargo doc` and other tools. This plugin allows you to directly feed Rust crate docs into your LLM queries using fragments.

For background on llm fragments see [Simon Willison's blog](https://simonwillison.net/2025/Apr/7/long-context-llm/).

## Installation

Install this plugin in the same environment as [LLM](https://llm.datasette.io/).

```bash
llm install llm-fragments-rust
```

For development installation:

```bash
git clone https://github.com/huitseeker/llm-fragments-rust.git
cd llm-fragments-rust
llm install -e .
```

## Usage

You can feed the docs of a Rust crate into LLM using the `rust:` [fragment](https://llm.datasette.io/en/stable/fragments.html) with the crate name, optionally followed by a version suffix.

```bash
# Using a specific version
llm -f rust:serde@1.0.188 "Explain how to deserialize a custom data type in Rust"

# Using latest version
llm -f rust:tokio "How do I spawn a new task?"

# Asking about multiple crates
llm -f rust:rand@0.8.5 -f rust:tokio "How do I generate random numbers asynchronously?"
```

### How It Works

When you use the `rust:` fragment:

1. The plugin creates a minimal Rust project in a temporary directory
2. It adds the requested crate as a dependency with the specified version
3. It generates documentation using `cargo doc`
4. It extracts and processes the documentation into a readable format
5. The extracted documentation is fed into the LLM context for your query

If the standard documentation methods fail, the plugin will attempt to fall back to simpler approaches:
- First extracting data from the HTML docs
- Using `cargo tree` and `cargo metadata` to get dependency information
- Finally, trying to pull basic information from crates.io API

## Requirements

- Rust and Cargo installed and available in PATH
- LLM 0.24 or higher
- Required standard Rust tools:
  - `cargo` (for building and managing dependencies)
  - `rustdoc` (for documentation generation)

## Examples

### Basic Usage

```bash
llm -f rust:serde_json "How do I parse JSON with unknown structure?"
```

### Compare Different Versions

```bash
llm -f rust:tokio@1.0.0 -f rust:tokio@1.36.0 "What are the key differences between these versions?"
```

### Learning About a Crate

```bash
llm -f rust:axum "Explain how to build a basic web server"
```

## Troubleshooting

If you encounter issues:

1. Make sure Rust and Cargo are properly installed and in your PATH
2. Check that you're using a recent version of the LLM CLI (0.24+)
3. For development, try reinstalling with `llm install -e .`
4. If a crate fails to load, try a simpler or more popular crate to verify the plugin works
