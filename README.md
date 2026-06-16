# ik - Infomaniak CLI

AWS CLI style command-line tool for Infomaniak Cloud Services.

## Installation

```bash
# Recommended
uv tool install ik

# Or, run without installing
uvx ik
```

Or with pip:

```bash
pip install ik
```

## Configuration

```bash
ik configure
```

Or set token via environment:
```bash
export INFOMANIAK_TOKEN="your-token-here"
```

### Profiles

For multiple Infomaniak accounts, store each in a named profile:

```bash
ik configure --profile work        # Save a token under "work"
ik --profile work drives           # Use it for one command
ik configure --profile personal    # Add a second profile
ik configure --list                # See all profiles
```

The first `ik configure` becomes the default. Use `--profile NAME` to switch.

## Commands

### Drive Operations

```bash
ik drives                     # List all kDrives
ik drive ls                  # List root directory
ik drive ls Documents        # List subdirectory
ik drive tree               # Show directory tree
ik drive mkdir Projects/new  # Create directory
ik drive upload file.pdf     # Upload file
ik drive download 123       # Download file by ID
ik drive search "invoice"   # Search files
ik drive info 123           # Get file details
ik drive rm 123             # Move to trash
ik drive mv 123 Archive/    # Move to directory
ik drive cp 123 Archive/    # Copy to directory
ik drive mv 123 Archive/ --name new.pdf   # Move and rename
```

### Account

```bash
ik whoami                    # Show account info
```

## Examples

```bash
# List files in Documents folder
ik drive ls Documents

# Upload file to specific directory
ik drive upload report.pdf --dir 5

# Download file to current directory
ik drive download 123 --local ./

# Search for files containing "budget"
ik drive search "budget"
```

## Development

```bash
git clone https://github.com/sbhavani/ik.git
cd ik
uv sync --group dev
uv run pytest         # run tests
uv run ruff check .   # lint
uv run ruff format .  # format
```