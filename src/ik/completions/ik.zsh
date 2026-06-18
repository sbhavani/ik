#compdef ik
# ik zsh completion — install: ik completion zsh > "${fpath[1]}/_ik"
# (or eval "$(ik completion zsh)" for a one-off session)

_ik_profiles() {
    ik configure --list --output json 2>/dev/null | \
        python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    print("\n".join(d.get("profiles", {}).keys()))
except Exception:
    pass' 2>/dev/null
}

_ik() {
    local -a subcommands
    subcommands=(
        'configure:Configure credentials'
        'whoami:Show current user'
        'drives:List all kDrives'
        'drive:kDrive commands'
        'vps:VPS Cloud commands'
        'mail:Mail (kSuite) commands'
        'completion:Print shell completion script'
    )

    local -a drive_subcommands
    drive_subcommands=(
        'ls:List directory contents'
        'tree:Print a directory tree'
        'mkdir:Create a directory'
        'upload:Upload a file'
        'download:Download a file'
        'search:Search for files'
        'rm:Move file to trash'
        'info:Get file details'
        'mv:Move or rename'
        'cp:Copy'
        'share:Manage share links'
        'trash:Manage trash'
        'activity:List activity log'
    )

    local -a vps_subcommands
    vps_subcommands=(
        'ls:List VPS services'
        'info:Show VPS details'
    )

    local -a mail_subcommands
    mail_subcommands=(
        'ls:List current kSuite'
        'info:Show kSuite details'
        'mailboxes:List mailbox folders'
        'messages:List messages in a mailbox'
        'message:Read one message'
    )

    local -a shells
    shells=('bash' 'zsh' 'fish')

    _arguments -C \
        '--profile[Configuration profile to use]:profile:_ik_profiles' \
        '--token[API token override]' \
        '--output[Output format]:format:(text json)' \
        '--quiet[Suppress non-essential output]' \
        '--yes[Skip confirmation prompts]' \
        '1: :->cmd' \
        '*::arg:->args'

    case $state in
        cmd)
            _describe 'command' subcommands
            ;;
        args)
            case ${words[1]} in
                drive)      _describe 'drive command' drive_subcommands ;;
                vps)        _describe 'vps command' vps_subcommands ;;
                mail)       _describe 'mail command' mail_subcommands ;;
                completion) _describe 'shell' shells ;;
            esac
            ;;
    esac
}

_ik "$@"
