# ik - Infomaniak CLI

AWS CLI style command-line tool for Infomaniak Cloud Services.

## Installation

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