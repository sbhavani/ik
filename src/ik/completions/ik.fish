# ik fish completion — install: ik completion fish | source
# Completes top-level subcommands, drive/vps subcommands, and dynamic
# profile names from the config.

function __ik_profiles
    ik configure --list --output json 2>/dev/null | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    print("\n".join(d.get("profiles", {}).keys()))
except Exception:
    pass' 2>/dev/null
end

# Top-level subcommands.
complete -c ik -n "__fish_use_subcommand" -a "configure"   -d "Configure credentials"
complete -c ik -n "__fish_use_subcommand" -a "whoami"      -d "Show current user"
complete -c ik -n "__fish_use_subcommand" -a "drives"      -d "List all kDrives"
complete -c ik -n "__fish_use_subcommand" -a "drive"       -d "kDrive commands"
complete -c ik -n "__fish_use_subcommand" -a "vps"         -d "VPS Cloud commands"
complete -c ik -n "__fish_use_subcommand" -a "mail"        -d "Mail (kSuite) commands"
complete -c ik -n "__fish_use_subcommand" -a "completion"  -d "Print shell completion script"

# Drive subcommands.
complete -c ik -n "__fish_seen_subcommand_from drive" -a "ls tree mkdir upload download search rm info mv cp share trash activity"

# VPS subcommands.
complete -c ik -n "__fish_seen_subcommand_from vps" -a "ls info"

# Mail subcommands.
complete -c ik -n "__fish_seen_subcommand_from mail" -a "ls info"

# `ik completion` shells.
complete -c ik -n "__fish_seen_subcommand_from completion" -a "bash zsh fish"

# Global flags.
complete -c ik -l profile -f -a "(__ik_profiles)"
complete -c ik -l token   -f
complete -c ik -l output  -f -a "text json"
complete -c ik -l quiet   -f
complete -c ik -l yes     -f
