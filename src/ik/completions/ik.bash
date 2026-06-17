# ik bash completion — install: source <(ik completion bash)
# Completes top-level subcommands, drive/vps subcommands, and dynamic
# profile names from the config.

_ik_profiles() {
    # Read profile names from the config; ignore errors (no config yet).
    ik configure --list --output json 2>/dev/null | \
        python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    print("\n".join(d.get("profiles", {}).keys()))
except Exception:
    pass' 2>/dev/null
}

_ik_drive_subcmds="ls tree mkdir upload download search rm info mv cp share trash activity"
_ik_vps_subcmds="ls info"
_ik_mail_subcmds="ls info"
_ik_top_subcmds="configure whoami drives drive vps mail completion"
_ik_shells="bash zsh fish"

_ik() {
    local cur prev words cword
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    words=("${COMP_WORDS[@]}")
    cword=$COMP_CWORD

    # Dynamic completions for value-taking flags.
    case "$prev" in
        --profile)   COMPREPLY=($(compgen -W "$(_ik_profiles)" -- "$cur")); return ;;
        --output)    COMPREPLY=($(compgen -W "text json" -- "$cur")); return ;;
        completion)  COMPREPLY=($(compgen -W "$_ik_shells" -- "$cur")); return ;;
    esac

    # Walk the subcommand path: ik <word1> <word2> ...
    local i subcmd=""
    for ((i = 1; i < cword; i++)); do
        case "${words[i]}" in
            -*) ;;
            *)
                if [[ -z "$subcmd" ]]; then
                    subcmd="${words[i]}"
                elif [[ "$subcmd" == "drive" ]]; then
                    subcmd="drive:${words[i]}"
                fi
                ;;
        esac
    done

    case "$subcmd" in
        drive)         COMPREPLY=($(compgen -W "$_ik_drive_subcmds" -- "$cur")) ;;
        drive:*)       COMPREPLY=() ;;
        vps)           COMPREPLY=($(compgen -W "$_ik_vps_subcmds" -- "$cur")) ;;
        mail)          COMPREPLY=($(compgen -W "$_ik_mail_subcmds" -- "$cur")) ;;
        "")            COMPREPLY=($(compgen -W "$_ik_top_subcmds" -- "$cur")) ;;
        *)             COMPREPLY=() ;;
    esac
}

complete -F _ik ik
