#!/usr/bin/env bash
#
# Script to utilize the UptimeRobot, StatusCake, and HealthChecks.io APIs to
# retrieve information on and work with checks you've created.
# Tronyx
set -eo pipefail
IFS=$'\n\t'

# Edit these with your corresponding information to finish setting up the script
# or just run it and it will prompt you for it.
# If your provider is StatusCake, specify your username.
scUsername=''
# If your provider is Upptime, specify the following
gitHubUsername=''
upptimeRepo='upptime'
# Specify API key(s).
urApiKey=''
scApiKey=''
hcApiKey=''
ghToken=''
# Specify the domain to use for Healthchecks as they allow you to self-host the
# application. If you're self-hosting it, replace the default domain with the
# domain you're hosting it on.
healthchecksDomain='healthchecks.io'
# Specify the Discord/Slack webhook URL to send notifications to.
webhookUrl=''
# Set notifyAll to true for notification to apply for all running state as well.
notifyAll='false'
# Set JQ to false to disable the use of the JQ command. This works better for
# using the script with cronjobs, etc.
jq='true'

# Declare some variables.
# Temp dir and filenames.
# Make sure you set this to something your user has write access to.
tempDir="$HOME/tronitor/"
apiTestFullFile="${tempDir}api_test_full.txt"
badMonitorsFile="${tempDir}bad_monitors.txt"
convertedMonitorsFile="${tempDir}converted_monitors.txt"
friendlyListFile="${tempDir}friendly_list.txt"
pausedMonitorsFile="${tempDir}paused_monitors.txt"
specifiedMonitorsFile="${tempDir}specified_monitors.txt"
monitorsFile="${tempDir}monitors.txt"
monitorsFullFile="${tempDir}monitors_full.txt"
hcPingURLsFile="${tempDir}hc_ping_urls.txt"
validMonitorsFile="${tempDir}valid_monitors.txt"
validMonitorsTempFile="${tempDir}valid_monitors_temp.txt"
healthchecksLockFile="${tempDir}healthchecks.lock"
# UUID regex pattern.
uuidPattern='^\{?[A-Z0-9a-z]{8}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{12}\}?$'
# Set initial API key(s) status.
urApiKeyStatus='invalid'
scApiKeyStatus='invalid'
hcApiKeyStatus='invalid'
ghTokenStatus='invalid'
# Set initial provider status.
urProviderStatus='invalid'
scProviderStatus='invalid'
hcProviderStatus='invalid'
upProviderStatus='invalid'
# Set initial SC username status.
scUsernameStatus='invalid'
# Set initial GH username status.
ghUsernameStatus='invalid'
# Set initial Upptime repo status.
upRepoStatus='invalid'
# Arguments.
readonly args=("$@")
# Text colors.
#readonly blu='\e[34m'
readonly lblu='\e[94m'
readonly grn='\e[32m'
readonly red='\e[31m'
readonly ylw='\e[33m'
readonly org='\e[38;5;202m'
readonly lorg='\e[38;5;130m'
readonly mgt='\e[35m'
#readonly bold='\e[1m'
readonly endColor='\e[0m'

# Function to define usage and script options.
usage() {
    cat <<- EOF

  Usage: $(echo -e "${lorg}$0${endColor}") $(echo -e "${grn}"-m"${endColor}" "${ylw}"\{MONITOR\}"${endColor}") $(echo -e "${grn}"-[OPTION]"${endColor}") $(echo -e "${ylw}"\{ARGUMENT\}"${endColor}"...)

  $(echo -e "${grn}"-m/--monitor"${endColor}" "${ylw}"VALUE"${endColor}")      Specify the monitoring provider you would like to work with.
                             A) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-m"${endColor}" "${ylw}"UptimeRobot"${endColor}" "${grn}"-\[OPTION\]"${endColor}" "${ylw}"\{ARGUMENT\}"${endColor}")"
                             B) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"--monitor"${endColor}" "${ylw}"\'sc\'"${endColor}" "${grn}"-l"${endColor}")"
                             C) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-m"${endColor}" "${ylw}"\"healthchecks\""${endColor}" "${grn}"-p"${endColor}" "${ylw}"all"${endColor}")"

  $(echo -e "${grn}"-s/--stats"${endColor}""${red}"*+"${endColor}")            List account statistics.

  $(echo -e "${grn}"-l/--list"${endColor}""${red}"+"${endColor}")              List all monitors.

  $(echo -e "${grn}"-f/--find"${endColor}")               Find all paused monitors.

  $(echo -e "${grn}"-n/--no-prompt"${endColor}")          Find all paused monitors without an unpause prompt.

  $(echo -e "${grn}"-w/--webhook"${endColor}""${red}"+"${endColor}")           Find all paused monitors without an unpause prompt and
                          send an alert to the Discord webhook specified in the script.

  $(echo -e "${grn}"-i/--info"${endColor}""${red}"+"${endColor}" "${ylw}"VALUE"${endColor}")        List all information for the specified monitor.
                             A) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-i"${endColor}" "${ylw}"18095689"${endColor}")"
                             B) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"--info"${endColor}" "${ylw}"\'Plex\'"${endColor}")"
                             C) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-i"${endColor}" "${ylw}"\"Tautulli\""${endColor}")"

  $(echo -e "${grn}"-a/--alerts"${endColor}""${red}"+"${endColor}")            List all alert contacts.

  $(echo -e "${grn}"-p/--pause"${endColor}" "${ylw}"VALUE"${endColor}")        Pause specified monitors.
                          Option accepts arguments in the form of "$(echo -e "${ylw}"all"${endColor}")" or a comma-separated list
                          of monitors by ID or Friendly Name. Friendly Name should be wrapped in
                          a set of single or double quotes, IE:
                             A) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-p"${endColor}" "${ylw}"all"${endColor}")"
                             B) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"--pause"${endColor}" "${ylw}"18095687,18095688,18095689"${endColor}")"
                             C) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-p"${endColor}" "${ylw}"\'Plex\',\"Tautulli\",18095689"${endColor}")"
                          $(echo -e "${ylw}"NOTE:"${endColor}" For Upptime, the only possible option is "${ylw}"all"${endColor}".)

  $(echo -e "${grn}"-u/--unpause"${endColor}" "${ylw}"VALUE"${endColor}")      Unpause specified monitors.
                          Option accepts arguments in the form of "$(echo -e "${ylw}"all"${endColor}")" or a comma-separated list
                          of monitors by ID or Friendly Name. Friendly Name should be wrapped in
                          a set of single or double quotes, IE:
                             A) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-u"${endColor}" "${ylw}"all"${endColor}")"
                             B) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"--unpause"${endColor}" "${ylw}"18095687,18095688,18095689"${endColor}")"
                             C) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-u"${endColor}" "${ylw}"\'Plex\',\"Tautulli\",18095689"${endColor}")"
                          $(echo -e "${ylw}"NOTE:"${endColor}" For Upptime, the only possible option is "${ylw}"all"${endColor}".)

  $(echo -e "${grn}"-c/--create"${endColor}""${red}"+"${endColor}" "${ylw}"VALUE"${endColor}")      Create a new monitor using the corresponding template file. Each type of test
                          (HTTP, Ping, Port, & Keyword) has a template file in the Templates directory.
                          Just edit the template file for the monitor type you wish to create and then run
                          the script with the corresponding monitor type, IE:
                             A) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-c"${endColor}" "${ylw}"http"${endColor}")"
                             B) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"--create"${endColor}" "${ylw}"port"${endColor}")"
                             C) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-c"${endColor}" "${ylw}"keyword"${endColor}")"

  $(echo -e "${grn}"-d/--delete"${endColor}""${red}"+"${endColor}" "${ylw}"VALUE"${endColor}")      Delete the specified monitor, IE:
                             A) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-d"${endColor}" "${ylw}"\'Plex\'"${endColor}")"
                             B) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"--delete"${endColor}" "${ylw}"\"Tautulli\""${endColor}")"
                             C) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-d"${endColor}" "${ylw}"18095688"${endColor}")"

  $(echo -e "${grn}"-r/--reset"${endColor}""${red}"*+"${endColor}" "${ylw}"VALUE"${endColor}")      Reset the specified monitor, IE:
                             A) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-r"${endColor}" "${ylw}"\'Plex\'"${endColor}")"
                             B) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"--reset"${endColor}" "${ylw}"\"Tautulli\""${endColor}")"
                             C) "$(echo -e "${lorg}"./tronitor.sh"${endColor}" "${grn}"-r"${endColor}" "${ylw}"18095688"${endColor}")"

  $(echo -e "${grn}"-h/--help"${endColor}")               Display this usage dialog.


  $(echo -e "${red}"\*"${endColor}""${ylw}" - Option is not compatible with StatusCake or HealthChecks.io."${endColor}")
  $(echo -e "${red}"\+"${endColor}""${ylw}" - Option is not compatible with Upptime."${endColor}")

EOF

}

# Function to define script options.
cmdline() {
    local arg=
    local local_args
    local OPTERR=0
    for arg; do
        local delim=""
        case "${arg}" in
            # Translate --gnu-long-options to -g (short options).
            --monitor) local_args="${local_args}-m " ;;
            --stats) local_args="${local_args}-s " ;;
            --list) local_args="${local_args}-l " ;;
            --find) local_args="${local_args}-f " ;;
            --no-prompt) local_args="${local_args}-n " ;;
            --webhook) local_args="${local_args}-w " ;;
            --info) local_args="${local_args:-}-i " ;;
            --alerts) local_args="${local_args}-a " ;;
            --create) local_args="${local_args:-}-c " ;;
            --pause) local_args="${local_args:-}-p " ;;
            --unpause) local_args="${local_args:-}-u " ;;
            --reset) local_args="${local_args:-}-r " ;;
            --delete) local_args="${local_args:-}-d " ;;
            --help) local_args="${local_args}-h " ;;
            # Pass through anything else.
            *)
                [[ ${arg:0:1} == '-' ]] || delim='"'
                local_args="${local_args:-}${delim}${arg}${delim} "
                ;;
        esac
    done

    # Reset the positional parameters to the short options.
    eval set -- "${local_args:-}"

    while getopts "hm:slfnwai:c:r:d:p:u:" OPTION; do
        case "$OPTION" in
            m)
                providerName="${OPTARG}"
                monitorFlag=true
                ;;
            s)
                stats=true
                ;;
            l)
                list=true
                ;;
            f)
                find=true
                prompt=true
                ;;
            n)
                find=true
                prompt=false
                ;;
            w)
                find=true
                prompt=false
                webhook=true
                ;;
            a)
                alerts=true
                ;;
            i)
                info=true
                infoType="${OPTARG}"
                ;;
            c)
                create=true
                createType="${OPTARG}"
                ;;
            r)
                reset=true
                resetType="${OPTARG}"
                ;;
            d)
                delete=true
                deleteType="${OPTARG}"
                ;;
            p)
                pause=true
                pauseType="${OPTARG}"
                ;;
            u)
                unpause=true
                unpauseType="${OPTARG}"
                ;;
            h)
                usage
                exit
                ;;
            *)
                if [[ ${arg} == '-m' || ${arg} == '-p' || ${arg} == '-u' || ${arg} == '-r' || ${arg} == '-d' || ${arg} == '-i' || ${arg} == '-c' ]] && [[ -z ${OPTARG} ]]; then
                    echo -e "${red}Option ${arg} requires an argument!${endColor}"
                else
                    echo -e "${red}You are specifying a non-existent option!${endColor}"
                fi
                usage
                exit
                ;;
        esac
    done
    shift $((OPTIND - 1))
    return 0
}

# Function to gather script information.
get_scriptname() {
    local source
    local dir
    source="${BASH_SOURCE[0]}"

    while [[ -L ${source} ]]; do
        dir="$(cd -P "$(dirname "${source}")" > /dev/null && pwd)"
        source="$(readlink "${source}")"
        [[ ${source} != /* ]] && source="${dir}/${source}"
    done

    echo "${source}"
}

readonly scriptname="$(get_scriptname)"

# Function to create the directory to neatly store temp files, if it does
# not exist.
create_dir() {
    mkdir -p "${tempDir}"
    chmod 777 "${tempDir}"
}

# Function to cleanup temp files.
cleanup() {
    rm -rf "${tempDir}"*.txt || true
}
trap 'cleanup' 0 1 3 6 14 15

# Function to exit the script if the user hits CTRL+C.
function control_c() {
    cleanup
    exit 0
}
trap 'control_c' 2

# Function to check that the monitor option has been provided.
check_monitor_opt() {
    if [[ ${monitorFlag} != 'true' ]]; then
        echo -e "${red}You must specify the monitor you wish to work with!${endColor}"
        usage
        exit
    fi
}

# Function to check that two options were provided.
check_opt_num() {
    if [[ ${OPTIND} -lt '4' || ${OPTIND} -gt '5' ]]; then
        echo -e "${red}You specified an invalid number of options!${endColor}"
        usage
        exit
    fi
}

# Function to check for an empty arg.
check_empty_arg() {
    for arg in "${args[@]:-}"; do
        if [[ -z ${arg} ]]; then
            usage
            exit
        fi
    done
}

# Function to check that only all is used for pause and unpause if the provide
# is Upptime
check_pauseType_upptime() {
    if [[ ${providerName} == 'upptime' ]] && [[ ${pause} == 'true' || ${unpause} == 'true' ]] && [[ ${pauseType} != 'all' && ${unpauseType} != 'all' ]]; then
        echo -e "${red}You can only specify all for Upptime!${endColor}"
        usage
        exit
    fi
}

# Function to check if cURL is installed and, if not, inform the user and exit.
check_curl() {
    whichCURL=$(which curl)
    if [[ -z ${whichCURL} ]]; then
        echo -e "${red}cURL is not currently installed on this system!${endColor}"
        echo -e "${ylw}The script with NOT function without it. Install cURL and run the script again.${endColor}"
        exit
    fi
}

# Function to grab line numbers of the user-defined and status variables.
get_line_numbers() {
    # Line numbers for user-defined variables.
    scUsernameLineNum=$(head -66 "${scriptname}" | grep -En -A1 'specify your username' | tail -1 | awk -F- '{print $1}')
    ghUsernameLineNum=$(head -66 "${scriptname}" | grep -En 'gitHubUser' | awk -F: '{print $1}')
    upRepoLineNum=$(head -66 "${scriptname}" | grep -En 'upptimeRepo' | awk -F: '{print $1}')
    urApiKeyLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Specify API key' | grep 'ur' | awk -F- '{print $1}')
    scApiKeyLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Specify API key' | grep 'sc' | awk -F- '{print $1}')
    hcApiKeyLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Specify API key' | grep 'hc' | awk -F- '{print $1}')
    ghTokenLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Specify API key' | grep 'gh' | awk -F- '{print $1}')
    webhookUrlLineNum=$(head -66 "${scriptname}" | grep -En -A1 'Discord/Slack' | tail -1 | awk -F- '{print $1}')
    # Line numbers for status variables.
    urApiStatusLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Set initial API key' | grep 'ur' | awk -F- '{print $1}')
    scApiStatusLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Set initial API key' | grep 'sc' | awk -F- '{print $1}')
    hcApiStatusLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Set initial API key' | grep 'hc' | awk -F- '{print $1}')
    ghTokenStatusLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Set initial API key' | grep 'gh' | awk -F- '{print $1}')
    urProviderStatusLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Set initial provider status' | grep 'ur' | awk -F- '{print $1}')
    scProviderStatusLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Set initial provider status' | grep 'sc' | awk -F- '{print $1}')
    hcProviderStatusLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Set initial provider status' | grep 'hc' | awk -F- '{print $1}')
    upProviderStatusLineNum=$(head -66 "${scriptname}" | grep -En -A4 'Set initial provider status' | grep 'up' | awk -F- '{print $1}')
    scUserStatusLineNum=$(head -66 "${scriptname}" | grep -En -A1 'Set initial SC username status' | tail -1 | awk -F- '{print $1}')
    ghUserStatusLineNum=$(head -66 "${scriptname}" | grep -En -A1 'Set initial GH username status' | tail -1 | awk -F- '{print $1}')
    upRepoStatusLineNum=$(head -66 "${scriptname}" | grep -En -A1 'Set initial Upptime repo status' | tail -1 | awk -F- '{print $1}')
}

# Function for catching when a curl or jq command fails to display a message and
# exit the script.
fatal() {
    echo -e "${red}There seems to be an issue connecting to ${providerName^}. Please try again in a few minutes.${endColor}"
    exit
}

# Function to convert shorthand provider names to their full names and to make
# sure the provider name is lowercase and, if not, convert it.
convert_provider_name() {
    if [[ ${providerName} == 'ur' ]]; then
        providerName='uptimerobot'
    elif [[ ${providerName} == 'sc' ]]; then
        providerName='statuscake'
    elif [[ ${providerName} == 'hc' ]]; then
        providerName='healthchecks'
    elif [[ ${providerName} == 'up' ]]; then
        providerName='upptime'
    fi

    if [[ ${providerName} =~ [[:upper:]] ]]; then
        providerName=$(echo "${providerName}" | awk '{print tolower($0)}')
    fi
}

# Function to check that provider is not empty and valid.
check_provider() {
    if [[ ${providerName} == 'uptimerobot' ]]; then
        providerStatus="${urProviderStatus}"
    elif [[ ${providerName} == 'statuscake' ]]; then
        providerStatus="${scProviderStatus}"
    elif [[ ${providerName} == 'healthchecks' ]]; then
        providerStatus="${hcProviderStatus}"
    elif [[ ${providerName} == 'upptime' ]]; then
        providerStatus="${upProviderStatus}"
    else
        providerStatus='invalid'
    fi

    while [[ ${providerStatus} == 'invalid' ]]; do
        if [[ ${providerName} != 'uptimerobot' ]] && [[ ${providerName} != 'statuscake' ]] && [[ ${providerName} != 'healthchecks' ]] && [[ ${providerName} != 'upptime' ]]; then
            echo -e "${red}You didn't specify a valid monitoring provider with the -m flag!${endColor}"
            echo -e "${ylw}Please specify either uptimerobot, statuscake, healthchecks, or upptime.${endColor}"
            exit
        else
            if [[ ${providerName} == 'uptimerobot' ]]; then
                sed -i "${urProviderStatusLineNum} s|urProviderStatus='[^']*'|urProviderStatus='ok'|" "${scriptname}"
            elif [[ ${providerName} == 'statuscake' ]]; then
                sed -i "${scProviderStatusLineNum} s|scProviderStatus='[^']*'|scProviderStatus='ok'|" "${scriptname}"
            elif [[ ${providerName} == 'healthchecks' ]]; then
                sed -i "${hcProviderStatusLineNum} s|hcProviderStatus='[^']*'|hcProviderStatus='ok'|" "${scriptname}"
            elif [[ ${providerName} == 'upptime' ]]; then
                sed -i "${upProviderStatusLineNum} s|upProviderStatus='[^']*'|upProviderStatus='ok'|" "${scriptname}"
            fi

            convert_provider_name

            if [[ ${providerName} == 'uptimerobot' ]]; then
                urProviderStatus='ok'
            elif [[ ${providerName} == 'statuscake' ]]; then
                scProviderStatus='ok'
            elif [[ ${providerName} == 'healthchecks' ]]; then
                hcProviderStatus='ok'
            elif [[ ${providerName} == 'upptime' ]]; then
                upProviderStatus='ok'
            fi

            providerStatus='ok'

        fi
    done

    if [[ ${providerName} == 'uptimerobot' ]]; then
        readonly apiUrl='https://api.uptimerobot.com/v2/'
    elif [[ ${providerName} == 'statuscake' ]]; then
        readonly apiUrl='https://app.statuscake.com/API/'
    elif [[ ${providerName} == 'healthchecks' ]]; then
        readonly apiUrl="https://${healthchecksDomain}/api/v1/"
    elif [[ ${providerName} == 'upptime' ]]; then
        readonly apiUrl='https://api.github.com/'
        upRawURL="https://raw.githubusercontent.com/${gitHubUsername}/${upptimeRepo}/"
    fi
}

# Function to specifically check that the provided StatusCake username and API
# key are valid.
check_sc_creds() {
    while [[ ${scUsernameStatus} == 'invalid' ]] || [[ ${scApiKeyStatus} == 'invalid' ]]; do
        if [[ -z ${scApiKey} ]]; then
            echo -e "${red}You didn't define your ${providerName^} API key in the script!${endColor}"
            echo ''
            echo "Enter your ${providerName^} API key:"
            read -rs API
            echo ''
            echo ''
            sed -i "${scApiKeyLineNum} s/scApiKey='[^']*'/scApiKey='${API}'/" "${scriptname}"
            scApiKey="${API}"
        elif [[ -z ${scUsername} ]]; then
            echo -e "${red}You didn't specify your ${providerName^} username in the script!${endColor}"
            echo ''
            echo "Enter your ${providerName^} username:"
            read -r username
            echo ''
            echo ''
            sed -i "${scUsernameLineNum} s/scUsername='[^']*'/scUsername='${username}'/" "${scriptname}"
            scUsername="${username}"
        else
            scStatus=$(curl -s -H "API: ${scApiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}"Tests/ | jq .ErrNo 2> /dev/null || echo '1')

            if [[ ${scStatus} == '0' ]]; then
                clear >&2
                echo -e "${red}The API Key and/or username that you provided for ${providerName^} are not valid!${endColor}"
                sed -i "${scApiKeyLineNum} s/scApiKey='[^']*'/scApiKey=''/" "${scriptname}"
                scApiKey=''
                sed -i "${scUsernameLineNum} s/scUsername='[^']*'/scUsername=''/" "${scriptname}"
                scUsername=''
                echo ''
                echo "Enter your ${providerName^} username:"
                read -r username
                echo ''
                echo ''
                sed -i "${scUsernameLineNum} s/scUsername='[^']*'/scUsername='${username}'/" "${scriptname}"
                scUsername="${username}"
            elif [[ ${scStatus} == '1' ]]; then
            echo "Validating that the provided ${providerName^} username and API key are functional..."
                sed -i "${scApiStatusLineNum} s/scApiKeyStatus='[^']*'/scApiKeyStatus='ok'/" "${scriptname}"
                scApiKeyStatus='ok'
                sed -i "${scUserStatusLineNum} s/scUsernameStatus='[^']*'/scUsernameStatus='ok'/" "${scriptname}"
                scUsernameStatus='ok'
                echo -e "${grn}Success!${endColor}"
                echo ''
            fi
        fi
    done
}

# Function to check that the provided GitHub username and PAT are valid
check_gh_creds() {
    while [[ ${ghUsernameStatus} == 'invalid' ]] || [[ ${ghTokenStatus} == 'invalid' ]]; do
        if [[ -z ${ghToken} ]]; then
            echo -e "${red}You didn't define your ${providerName^} PAT in the script!${endColor}"
            echo ''
            echo "Enter your ${providerName^} PAT:"
            read -rs API
            echo ''
            echo ''
            sed -i "${ghTokenLineNum} s/ghToken='[^']*'/ghToken='${API}'/" "${scriptname}"
            ghToken="${API}"
        elif [[ -z ${gitHubUsername} ]]; then
            echo -e "${red}You didn't specify your GitHub username in the script!${endColor}"
            echo ''
            echo "Enter your GitHub username:"
            read -r username
            echo ''
            echo ''
            sed -i "${ghUsernameLineNum} s/gitHubUsername='[^']*'/gitHubUsername='${username}'/" "${scriptname}"
            gitHubUsername="${username}"
            upRawURL="https://raw.githubusercontent.com/${gitHubUsername}/${upptimeRepo}/"
        else
            ghStatus=$(curl -s -XGET -H "Authorization: bearer ${ghToken}" "${apiUrl}"user | jq -r .login)
            ghStatus=$(echo "${ghStatus}" | awk '{print tolower($0)}')

            if [[ ${ghStatus} != "${gitHubUsername}" ]]; then
                clear >&2
                echo -e "${red}The PAT and/or username that you provided for GitHub are not valid!${endColor}"
                sed -i "${ghTokenLineNum} s/ghToken='[^']*'/ghToken=''/" "${scriptname}"
                ghToken=''
                sed -i "${ghUsernameLineNum} s/gitHubUsername='[^']*'/gitHubUsername=''/" "${scriptname}"
                gitHubUsername=''
                echo ''
                echo "Enter your GitHub username:"
                read -r username
                echo ''
                echo ''
                sed -i "${ghUsernameLineNum} s/gitHubUsername='[^']*'/gitHubUsername='${username}'/" "${scriptname}"
                gitHubUsername="${username}"
                upRawURL="https://raw.githubusercontent.com/${gitHubUsername}/${upptimeRepo}/"
            elif [[ ${ghStatus} == "${gitHubUsername}" ]]; then
                echo 'Validating that the provided GitHub username and PAT are functional...'
                sed -i "${ghTokenStatusLineNum} s/ghTokenStatus='[^']*'/ghTokenStatus='ok'/" "${scriptname}"
                ghTokenStatus='ok'
                sed -i "${ghUserStatusLineNum} s/ghUsernameStatus='[^']*'/ghUsernameStatus='ok'/" "${scriptname}"
                ghUsernameStatus='ok'
                echo -e "${grn}Success!${endColor}"
                echo ''
            fi
        fi
    done
}

# Function to check that the provided Upptime repository is valid
check_up_repo() {
    while [[ ${upRepoStatus} == 'invalid' ]]; do
        if [[ -z ${upptimeRepo} ]]; then
            echo -e "${red}You didn't define your ${providerName^} repository in the script!${endColor}"
            echo ''
            echo "Enter your ${providerName^} repository name:"
            read -r repo
            echo ''
            echo ''
            sed -i "${upRepoLineNum} s/upptimeRepo='[^']*'/upptimeRepo='${repo}'/" "${scriptname}"
            upptimeRepo="${repo}"
            upRawURL="https://raw.githubusercontent.com/${gitHubUsername}/${upptimeRepo}/"
        else
            echo 'Validating that the provided Upptime repository is functional...'
            status=$(curl -w "%{http_code}\n" -sI -o /dev/null https://github.com/"${gitHubUsername}"/"${upptimeRepo}"/) || fatal

            if [[ ${status} != '200' ]]; then
                echo -e "${red}The Upptime repository that you provided does not appear to be valid!${endColor}"
                sed -i "${upRepoLineNum} s/upptimeRepo='[^']*'/upptimeRepo=''/" "${scriptname}"
                upptimeRepo=''
            elif [[ ${status} == '200' ]]; then
                sed -i "${upRepoStatusLineNum} s/upRepoStatus='[^']*'/upRepoStatus='ok'/" "${scriptname}"
                upRepoStatus='ok'
                upRawURL="https://raw.githubusercontent.com/${gitHubUsername}/${upptimeRepo}/"
                echo -e "${grn}Success!${endColor}"
                echo ''
            fi
        fi
    done
}

# Function to check that the provided UptimeRobot or Healthchecks.io API Key
# is valid.
check_api_key() {
    if [[ ${providerName} == 'uptimerobot' ]]; then
        while [[ ${urApiKeyStatus} == 'invalid' ]]; do
            if [[ -z ${urApiKey} ]]; then
                echo -e "${red}You didn't define your ${providerName^} API key in the script!${endColor}"
                echo ''
                echo "Enter your ${providerName^} API key:"
                read -rs API
                echo ''
                echo ''
                sed -i "${urApiKeyLineNum} s/urApiKey='[^']*'/urApiKey='${API}'/" "${scriptname}"
                urApiKey="${API}"
            else
                curl --fail -s -X POST "${apiUrl}"getAccountDetails -d "api_key=${urApiKey}" -d "format=json" > "${apiTestFullFile}" || fatal
                status=$(jq -r .stat "${apiTestFullFile}" 2> /dev/null) || fatal

                if [[ ${status} == 'fail' ]]; then
                    echo -e "${red}The API Key that you provided for ${providerName^} is not valid!${endColor}"
                    sed -i "${urApiKeyLineNum} s/urApiKey='[^']*'/urApiKey=''/" "${scriptname}"
                    urApiKey=''
                elif [[ ${status} == 'ok' ]]; then
                echo "Validating that the provided ${providerName^} API key is functional..."
                    sed -i "${urApiStatusLineNum} s/urApiKeyStatus='[^']*'/urApiKeyStatus='${status}'/" "${scriptname}"
                    urApiKeyStatus="${status}"
                    echo -e "${grn}Success!${endColor}"
                    echo ''
                fi
            fi
        done
    elif [[ ${providerName} == 'healthchecks' ]]; then
        while [[ ${hcApiKeyStatus} == 'invalid' ]]; do
            if [[ -z ${hcApiKey} ]]; then
                echo -e "${red}You didn't define your ${providerName^} API key in the script!${endColor}"
                echo ''
                echo "Enter your ${providerName^} API key:"
                read -rs API
                echo ''
                echo ''
                sed -i "${hcApiKeyLineNum} s/hcApiKey='[^']*'/hcApiKey='${API}'/" "${scriptname}"
                hcApiKey="${API}"
            else
                curl --fail -s -H "X-Api-Key: ${hcApiKey}" -X GET "${apiUrl}"checks/ > "${apiTestFullFile}"
                status=$(jq -r .error "${apiTestFullFile}" 2> /dev/null) || fatal

                if [[ ${status} != 'null' ]]; then
                    echo -e "${red}The API Key that you provided for ${providerName^} is not valid!${endColor}"
                    sed -i "${hcApiKeyLineNum} s/hcApiKey='[^']*'/hcApiKey=''/" "${scriptname}"
                    hcApiKey=''
                elif [[ ${status} == 'null' ]]; then
                    echo "Validating that the provided ${providerName^} API key is functional..."
                    sed -i "${hcApiStatusLineNum} s/hcApiKeyStatus='[^']*'/hcApiKeyStatus='ok'/" "${scriptname}"
                    hcApiKeyStatus='ok'
                    echo -e "${grn}Success!${endColor}"
                    echo ''
                fi
            fi
        done
    fi
}

# Function to check that the webhook URL is defined if alert is set to true.
check_webhook_url() {
    if [[ ${webhookUrl} == '' ]] && [[ ${webhook} == 'true' ]]; then
        echo -e "${red}You didn't define your Discord webhook URL!${endColor}"
        echo ''
        echo 'Enter your webhook URL:'
        read -r url
        echo ''
        echo ''
        sed -i "${webhookUrlLineNum} s|webhookUrl='[^']*'|webhookUrl='${url}'|" "${scriptname}"
        webhookUrl="${url}"
    fi
}

# Function to wrap all other checks into one function.
checks() {
    get_line_numbers
    check_monitor_opt
    check_opt_num
    check_empty_arg
    check_pauseType_upptime
    check_curl
    check_provider

    if [[ ${providerName} == 'statuscake' ]]; then
        check_sc_creds
    elif [[ ${providerName} == 'upptime' ]]; then
        check_gh_creds
        check_up_repo
    else
        check_api_key
    fi

    check_webhook_url
}

# Function to set the API key variable to the API key for the specified monitor.
set_api_key() {
    if [[ ${providerName} == 'uptimerobot' ]]; then
        apiKey="${urApiKey}"
    elif [[ ${providerName} == 'statuscake' ]]; then
        apiKey="${scApiKey}"
    elif [[ ${providerName} == 'healthchecks' ]]; then
        apiKey="${hcApiKey}"
    elif [[ ${providerName} == 'upptime' ]]; then
        apiKey="${ghToken}"
    fi
}

# Function to grab data for all monitors.
get_data() {
    if [[ ${providerName} == 'uptimerobot' ]]; then
        curl --fail -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "format=json" > "${monitorsFullFile}" || fatal
    elif [[ ${providerName} == 'statuscake' ]]; then
        curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}"Tests/ > "${monitorsFullFile}" || fatal
    elif [[ ${providerName} == 'healthchecks' ]]; then
        curl --fail -s -H "X-Api-Key: ${apiKey}" -X GET "${apiUrl}"checks/ > "${monitorsFullFile}" || fatal
    elif [[ ${providerName} == 'upptime' ]]; then
        curl --fail -s -H "Authorization: bearer ${ghToken}" "${apiUrl}repos/${gitHubUsername}/${upptimeRepo}/git/trees/master?recursive=1" | grep -e 'api\/' | awk -F'/' 'NF==2' | awk -F'/' '{print $2}' | tr -d '",' > "${monitorsFullFile}" || fatal
    fi
}

# Function to create a list of monitor IDs.
get_monitors() {
    if [[ ${providerName} == 'uptimerobot' ]]; then
        totalMonitors=$(jq -r .pagination.total "${monitorsFullFile}" 2> /dev/null) || fatal
    elif [[ ${providerName} == 'statuscake' ]]; then
        totalMonitors=$(jq -r .[].TestID "${monitorsFullFile}" | wc -l 2> /dev/null) || fatal
    elif [[ ${providerName} == 'healthchecks' ]]; then
        totalMonitors=$(jq -r .checks[].name "${monitorsFullFile}" | wc -l 2> /dev/null) || fatal
    elif [[ ${providerName} == 'upptime' ]]; then
        totalMonitors=$(wc -l "${monitorsFullFile}" | awk '{print $1}' 2> /dev/null) || fatal
    fi

    if [[ ${totalMonitors} == '0' ]]; then
        echo "There are currently no monitors associated with your ${providerName^} account."
        exit 0
    else
        if [[ ${providerName} == 'uptimerobot' ]]; then
            jq -r .monitors[].id "${monitorsFullFile}" > "${monitorsFile}" 2> /dev/null || fatal
        elif [[ ${providerName} == 'statuscake' ]]; then
            jq -r .[].TestID "${monitorsFullFile}" > "${monitorsFile}" 2> /dev/null || fatal
        elif [[ ${providerName} == 'healthchecks' ]]; then
            jq -r .checks[].ping_url "${monitorsFullFile}" 2> /dev/null > "${hcPingURLsFile}" || fatal
            rev "${hcPingURLsFile}" | cut -c1-36 | rev > "${monitorsFile}"
        elif [[ ${providerName} == 'upptime' ]]; then
            cat "${monitorsFullFile}" > "${monitorsFile}" 2> /dev/null || fatal
        fi
    fi
}

# Function to create individual monitor files.
create_monitor_files() {
    while IFS= read -r monitor; do
        if [[ ${providerName} == 'uptimerobot' ]]; then
            curl --fail -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "monitors=${monitor}" -d "format=json" > "${tempDir}${monitor}".txt || fatal
        elif [[ ${providerName} == 'statuscake' ]]; then
            curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}Tests/Details/?TestID=${monitor}" > "${tempDir}${monitor}".txt || fatal
        elif [[ ${providerName} == 'healthchecks' ]]; then
            curl --fail -s -H "X-Api-Key: ${apiKey}" -X GET ${apiUrl}checks/ | jq --arg monitor $monitor '.checks[] | select(.ping_url | contains($monitor))' 2> /dev/null > "${tempDir}${monitor}".txt || fatal
        elif [[ ${providerName} == 'upptime' ]]; then
            curl --fail -s -H "Authorization: bearer ${ghToken}" "${upRawURL}master/history/${monitor}.yml" 2> /dev/null > "${tempDir}${monitor}".txt || fatal
        fi
    done < <(cat "${monitorsFile}")
}

# Function to create friendly output of all monitors.
create_friendly_list() {
    true > "${friendlyListFile}"

    while IFS= read -r monitor; do
        if [[ ${providerName} == 'uptimerobot' ]]; then
            friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            status=$(jq .monitors[].status "${tempDir}${monitor}".txt 2> /dev/null) || fatal

            if [[ ${status} == '0' ]]; then
                friendlyStatus="${ylw}Paused${endColor}"
            elif [[ ${status} == '1' ]]; then
                friendlyStatus="${mgt}Not checked yet${endColor}"
            elif [[ ${status} == '2' ]]; then
                friendlyStatus="${grn}Up${endColor}"
            elif [[ ${status} == '8' ]]; then
                friendlyStatus="${org}Seems down${endColor}"
            elif [[ ${status} == '9' ]]; then
                friendlyStatus="${red}Down${endColor}"
            fi
        elif [[ ${providerName} == 'statuscake' ]]; then
            friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            status=$(jq -r .Status "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            paused=$(jq -r .Paused "${tempDir}${monitor}".txt 2> /dev/null) || fatal

            if [[ ${status} == 'Up' ]] && [[ ${paused} == 'true' ]]; then
                friendlyStatus="${ylw}Paused (Up)${endColor}"
            elif [[ ${status} == 'Down' ]] && [[ ${paused} == 'true' ]]; then
                friendlyStatus="${ylw}Paused (Down)${endColor}"
            elif [[ ${status} == 'Up' ]] && [[ ${paused} == 'false' ]]; then
                friendlyStatus="${grn}Up${endColor}"
            elif [[ ${status} == 'Down' ]] && [[ ${paused} == 'false' ]]; then
                friendlyStatus="${red}Down${endColor}"
            fi
        elif [[ ${providerName} == 'healthchecks' ]]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
            status=$(jq -r .status "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal

            if [[ ${status} == 'up' ]]; then
                friendlyStatus="${grn}Up${endColor}"
            elif [[ ${status} == 'down' ]]; then
                friendlyStatus="${red}Down${endColor}"
            elif [[ ${status} == 'paused' ]]; then
                friendlyStatus="${ylw}Paused${endColor}"
            elif [[ ${status} == 'late' ]]; then
                friendlyStatus="${org}Late${endColor}"
            elif [[ ${status} == 'new' ]]; then
                friendlyStatus="${mgt}New${endColor}"
            fi
        elif [[ ${providerName} == 'upptime' ]]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            siteURL=$(grep url "${tempDir}${monitor}"_short.txt | awk '{print $2}')
            friendlyName=$(curl --fail -s "${upRawURL}master/.upptimerc.yml" | grep -v href | grep -B1 "${siteURL}"$ | grep name | awk -F':' '{print $2}' | cut -c2- 2> /dev/null) || fatal
            status=$(grep status "${tempDir}${monitor}"_short.txt | awk '{print $2}' 2> /dev/null) || fatal
            workflowStatus=$(curl -s -H "Authorization: bearer ${ghToken}" -H "Accept: application/vnd.github.v3+json" "${apiUrl}repos/${gitHubUsername}/${upptimeRepo}/actions/workflows/uptime.yml" | jq -r .state)

            if [[ ${workflowStatus} == 'disabled_manually' ]]; then
                status='paused'
            fi

            if [[ ${status} == 'up' ]]; then
                friendlyStatus="${grn}Up${endColor}"
            elif [[ ${status} == 'down' ]]; then
                friendlyStatus="${red}Down${endColor}"
            elif [[ ${status} == 'paused' ]]; then
                friendlyStatus="${ylw}Paused${endColor}"
            fi
        fi

        if [[ ${providerName} == 'upptime' ]]; then
            echo -e "${lorg}${friendlyName}${endColor} | URL: ${lblu}${siteURL}${endColor} | Status: ${friendlyStatus}" >> "${friendlyListFile}"
        else
            echo -e "${lorg}${friendlyName}${endColor} | ID: ${lblu}${monitor}${endColor} | Status: ${friendlyStatus}" >> "${friendlyListFile}"
        fi

    done < <(cat "${monitorsFile}")
}

# Function to display a friendly list of all monitors.
display_all_monitors() {
    if [[ -s ${friendlyListFile} ]]; then
        if [[ ${providerName} == 'upptime' ]]; then
            echo "The following monitors were found in your ${providerName^} repository:"
            echo ''
            column -ts "|" "${friendlyListFile}"
            echo ''
        else
            echo "The following monitors were found in your ${providerName^} account:"
            echo ''
            column -ts "|" "${friendlyListFile}"
            echo ''
        fi
    fi
}

# Function to find all currently paused monitors.
get_paused_monitors() {
    true > "${pausedMonitorsFile}"

    if [[ ${providerName} == 'upptime' ]]; then
        workflowStatus=$(curl -s -H "Authorization: bearer ${ghToken}" -H "Accept: application/vnd.github.v3+json" "${apiUrl}repos/${gitHubUsername}/${upptimeRepo}/actions/workflows/uptime.yml" | jq -r .state)
        if [[ ${workflowStatus} == 'disabled_manually' ]]; then
            while IFS= read -r monitor; do
                cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
                siteURL=$(grep url "${tempDir}${monitor}"_short.txt | awk '{print $2}')
                friendlyName=$(curl --fail -s "${upRawURL}master/.upptimerc.yml" | grep -v href | grep -B1 "${siteURL}"$ | grep name | awk -F':' '{print $2}' | cut -c2- 2> /dev/null) || fatal
                echo -e "${lorg}${friendlyName}${endColor} | URL: ${lblu}${siteURL}${endColor}" >> "${pausedMonitorsFile}"
            done < <(cat "${monitorsFile}")
        fi
    else
        while IFS= read -r monitor; do
            if [[ ${providerName} == 'uptimerobot' ]]; then
                friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                status=$(jq -r .monitors[].status "${tempDir}${monitor}".txt 2> /dev/null) || fatal

                if [[ ${status} == '0' ]]; then
                    echo -e "${lorg}${friendlyName}${endColor} | ID: ${lblu}${monitor}${endColor}" >> "${pausedMonitorsFile}"
                fi
            elif [[ ${providerName} == 'statuscake' ]]; then
                friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                status=$(jq -r .Status "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                paused=$(jq -r .Paused "${tempDir}${monitor}".txt 2> /dev/null) || fatal

                if [[ ${status} == 'Up' ]] && [[ ${paused} == 'true' ]]; then
                    echo -e "${lorg}${friendlyName}${endColor} | ID: ${lblu}${monitor}${endColor}" >> "${pausedMonitorsFile}"
                fi
            elif [[ ${providerName} == 'healthchecks' ]]; then
                cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
                friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
                status=$(jq -r .status "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal

                if [[ ${status} == 'paused' ]]; then
                    echo -e "${lorg}${friendlyName}${endColor} | ID: ${lblu}${monitor}${endColor}" >> "${pausedMonitorsFile}"
                fi
            fi
        done < <(cat "${monitorsFile}")
    fi
}

# Function to display a list of all paused monitors.
display_paused_monitors() {
    if [[ -s ${pausedMonitorsFile} ]]; then
        echo "The following ${providerName^} monitors are currently paused:"
        echo ''
        column -ts "|" "${pausedMonitorsFile}"
        echo ''
    else
        echo "There are currently no paused ${providerName^} monitors."
        echo ''
    fi
}

# Function to prompt the user to unpause monitors after finding paused monitors.
unpause_prompt() {
    echo ''
    echo -e "Would you like to unpause the currently paused monitors? (${grn}[Y]${endColor}es or ${red}[N]${endColor}o): "
    read -r unpausePrompt
    echo ''

    if ! [[ ${unpausePrompt} =~ ^(Yes|yes|Y|y|No|no|N|n)$ ]]; then
        echo -e "${red}Please specify yes, y, no, or n.${endColor}"
        read -r unpausePrompt
    fi
}

# Function to prompt the user to continue actioning valid monitors after
# finding invalid ones.
invalid_prompt() {
    echo 'Would you like to continue actioning the following valid monitors?'
    echo ''
    cat "${validMonitorsFile}"
    echo ''
    echo -e "${grn}[Y]${endColor}es or ${red}[N]${endColor}o):"
    read -r invalidPrompt
    echo ''

    if ! [[ ${invalidPrompt} =~ ^(Yes|yes|Y|y|No|no|N|n)$ ]]; then
        echo -e "${red}Please specify yes, y, no, or n.${endColor}"
        read -r invalidPrompt
    fi
}

# Function to check if any bad, IE: non-existent, monitors were provided.
check_bad_monitors() {
    true > "${badMonitorsFile}"

    while IFS= read -r monitor; do
        if [[ $(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${friendlyListFile}" | grep -ic "${monitor} |") != "1" ]]; then
            if [[ ${monitor} =~ ^[A-Za-z]+$ ]]; then
                echo -e "${lorg}${monitor}${endColor}" >> "${badMonitorsFile}"
            elif [[ ${monitor} != ^[A-Za-z]+$ ]]; then
                echo -e "${lblu}${monitor}${endColor}" >> "${badMonitorsFile}"
            fi
        fi
    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${specifiedMonitorsFile}")

    if [[ -s ${badMonitorsFile} ]]; then
        echo -e "${red}The following monitors you specified are not valid:${endColor}"
        echo ''
        cat "${badMonitorsFile}"
        sed -i 's/\x1B\[[0-9;]*[JKmsu]//g' "${badMonitorsFile}"
        set +e
        grep -vxf "${badMonitorsFile}" "${specifiedMonitorsFile}" > "${validMonitorsTempFile}"
        true > "${validMonitorsFile}"

        if [[ -s ${validMonitorsTempFile} ]]; then
            while IFS= read -r monitor; do
                echo -e "${grn}${monitor}${endColor}" >> "${validMonitorsFile}"
            done < <(cat "${validMonitorsTempFile}")
            echo ''
            invalid_prompt
        elif [[ ! -s ${validMonitorsTempFile} ]]; then
            echo ''
            echo 'Please make sure you are specifying a valid monitor and try again.'
            echo ''
            exit
        fi
        set -e
    fi
}

# Function to convert friendly names to IDs.
convert_friendly_monitors() {
    true > "${convertedMonitorsFile}"

    if [[ -s ${validMonitorsFile} ]]; then
        cat "${validMonitorsFile}" > "${specifiedMonitorsFile}"
    fi

    if [[ ${providerName} == 'healthchecks' ]]; then
        while IFS= read -r monitor; do
            if [[ $(echo "${monitor}" | tr -d ' ') =~ ${uuidPattern} ]]; then
                echo "${monitor}" >> "${convertedMonitorsFile}"
            else
                tempCurl=$(curl --fail -s -H "X-Api-Key: ${apiKey}" -X GET ${apiUrl}checks/) || fatal
                tempJQ=$(echo "${tempCurl}" | jq -r --arg monitor $monitor '.checks[] | select(.name | match($monitor;"i"))'.ping_url 2> /dev/null) || fatal
                echo "${tempJQ}" | rev | cut -c1-36 | rev >> "${convertedMonitorsFile}"
            fi
        done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${specifiedMonitorsFile}")
    else
        while IFS= read -r monitor; do
            if [[ $(echo "${monitor}" | tr -d ' ') =~ [A-Za-z] ]]; then
                sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${friendlyListFile}" | grep -i "${monitor} |" | awk -F ':' '{print $2}' | awk -F ' ' '{print $1}' >> "${convertedMonitorsFile}"
            else
                echo "${monitor}" >> "${convertedMonitorsFile}"
            fi
        done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${specifiedMonitorsFile}")
    fi
}

# Function to pause all monitors.
pause_all_monitors() {
    if [[ ${providerName} == 'upptime' ]]; then
        echo 'Pausing the Uptime CI workflow for your Upptime repository...'
        curl --fail -X PUT -H "Authorization: bearer ${ghToken}" -H "Accept: application/vnd.github.v3+json" "${apiUrl}repos/${gitHubUsername}/${upptimeRepo}/actions/workflows/uptime.yml/disable" 2> /dev/null || fatal
        echo -e "${grn}Success!${endColor}"
        echo ''
    else
        while IFS= read -r monitor; do
            if [[ ${providerName} == 'uptimerobot' ]]; then
                friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                echo "Pausing ${friendlyName}:"

                if [[ ${jq} == 'true' ]]; then
                    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" | jq 2> /dev/null || fatal
                elif [[ ${jq} == 'false' ]]; then
                    curl --fail -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" || fatal
                fi
            elif [[ ${providerName} == 'statuscake' ]]; then
                friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                echo "Pausing ${friendlyName}:"

                if [[ ${jq} == 'true' ]]; then
                    curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=1" -X PUT "${apiUrl}Tests/Update" | jq 2> /dev/null || fatal
                elif [[ ${jq} == 'false' ]]; then
                    curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=1" -X PUT "${apiUrl}Tests/Update" || fatal
                fi
            elif [[ ${providerName} == 'healthchecks' ]]; then
                cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
                friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
                true > "${healthchecksLockFile}"
                echo "Pausing ${friendlyName}:"

                if [[ ${jq} == 'true' ]]; then
                    curl -s "${apiUrl}checks/${monitor}"/pause -X POST -H "X-Api-Key: ${apiKey}" --data "" | jq 2> /dev/null || fatal
                elif [[ ${jq} == 'false' ]]; then
                    curl --fail -s "${apiUrl}checks/${monitor}"/pause -X POST -H "X-Api-Key: ${apiKey}" --data "" || fatal
                fi
            fi

            echo ''

        done < <(cat "${monitorsFile}")
    fi
    if [[ ${providerName} == 'healthchecks' ]]; then
        echo ''
        echo -e "${ylw}**NOTE:** Healthchecks.io works with cronjobs so, unless you disable your cronjobs for${endColor}"
        echo -e "${ylw}the HC.io monitors, or work with the created lock file, all paused monitors will become${endColor}"
        echo -e "${ylw}active again the next time they receive a ping.${endColor}"
        echo ''
    else
        :
    fi
}

# Function to pause specified monitors.
pause_specified_monitors() {
    echo "${pauseType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors

    if [[ ${invalidPrompt} == @(No|no|N|n) ]]; then
        exit 0
    else
        convert_friendly_monitors
    fi

    while IFS= read -r monitor; do
        if [[ ${providerName} == 'uptimerobot' ]]; then
            friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            echo "Pausing ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" || fatal
            fi
        elif [[ ${providerName} == 'statuscake' ]]; then
            friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            echo "Pausing ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=1" -X PUT "${apiUrl}Tests/Update" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=1" -X PUT "${apiUrl}Tests/Update" || fatal
            fi
        elif [[ ${providerName} == 'healthchecks' ]]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
            true > "${tempDir}${monitor}".lock
            echo "Pausing ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s "${apiUrl}checks/${monitor}"/pause -X POST -H "X-Api-Key: ${apiKey}" --data "" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s "${apiUrl}checks/${monitor}"/pause -X POST -H "X-Api-Key: ${apiKey}" --data "" || fatal
            fi
        fi

        echo ''

    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")

    if [[ ${providerName} == 'healthchecks' ]]; then
        echo ''
        echo -e "${ylw}**NOTE:** Healthchecks.io works with cronjobs so, unless you disable your cronjobs for${endColor}"
        echo -e "${ylw}the HC.io monitors, all paused monitors will become active again the next time they receive a ping.${endColor}"
        echo ''
    fi
}

# Function to unpause all monitors.
unpause_all_monitors() {
    if [[ ${providerName} == 'upptime' ]]; then
        echo 'Unpausing the Uptime CI workflow for your Upptime repository...'
        curl --fail -X PUT -H "Authorization: bearer ${ghToken}" -H "Accept: application/vnd.github.v3+json" "${apiUrl}repos/${gitHubUsername}/${upptimeRepo}/actions/workflows/uptime.yml/enable" 2> /dev/null || fatal
        echo -e "${grn}Success!${endColor}"
        echo ''
    else
        while IFS= read -r monitor; do
            if [[ ${providerName} == 'uptimerobot' ]]; then
                friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                echo "Unpausing ${friendlyName}:"

                if [[ ${jq} == 'true' ]]; then
                    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" | jq 2> /dev/null || fatal
                elif [[ ${jq} == 'false' ]]; then
                    curl --fail -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" || fatal
                fi
            elif [[ ${providerName} == 'statuscake' ]]; then
                friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                echo "Unpausing ${friendlyName}:"

                if [[ ${jq} == 'true' ]]; then
                    curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" | jq 2> /dev/null || fatal
                elif [[ ${jq} == 'false' ]]; then
                    curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" || fatal
                fi
            elif [[ ${providerName} == 'healthchecks' ]]; then
                cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
                friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
                pingURL=$(jq -r .ping_url "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
                rm -f "${healthchecksLockFile}"
                rm -f "${tempDir}"*.lock
                echo "Unpausing ${friendlyName} by sending a ping:"
                pingResponse=$(curl -fsS --retry 3 "${pingURL}")

                if [[ ${pingResponse} == 'OK' ]]; then
                    echo -e "${grn}Success!${endColor}"
                else
                    echo -e "${red}Unable to unpause ${friendlyName}!${endColor}"
                fi
            fi

            echo ''

        done < <(cat "${monitorsFile}")
    fi
}

# Function to unpause specified monitors.
unpause_specified_monitors() {
    echo "${unpauseType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors

    if [[ ${invalidPrompt} == @(No|no|N|n) ]]; then
        exit 0
    else
        convert_friendly_monitors
    fi

    while IFS= read -r monitor; do
        if [[ ${providerName} == 'uptimerobot' ]]; then
            friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            echo "Unpausing ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" || fatal
            fi
        elif [[ ${providerName} == 'statuscake' ]]; then
            friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            echo "Unpausing ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" || fatal
            fi
        elif [[ ${providerName} == 'healthchecks' ]]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
            pingURL=$(jq -r .ping_url "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
            rm -f "${tempDir}${monitor}".lock
            echo "Unpausing ${friendlyName} by sending a ping:"
            pingResponse=$(curl -fsS --retry 3 "${pingURL}")

            if [[ ${pingResponse} == 'OK' ]]; then
                echo -e "${grn}Success!${endColor}"
            else
                echo -e "${red}Unable to unpause ${friendlyName}!${endColor}"
            fi
        fi

        echo ''

    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Function to send Discord notifications.
send_notification() {
    if [[ -s ${pausedMonitorsFile} ]]; then
        pausedTests='"fields": ['
        lineCount=$(wc -l < "${pausedMonitorsFile}")
        count=0

        while IFS= read -r line; do
            ((++count))
            pausedTests="${pausedTests}{\"name\": \"$(echo ${line} | sed 's/\x1B\[[0-9;]*[JKmsu]//g' | cut -d '|' -f 1)\",
              \"value\": \"$(echo ${line} | sed 's/\x1B\[[0-9;]*[JKmsu]//g' | cut -d '|' -f 2)\"}"

            if [[ ${count} -ne ${lineCount} ]]; then
                pausedTests="${pausedTests},"
            fi

        done < "${pausedMonitorsFile}"

        pausedTests="${pausedTests}]"

        if [[ ${providerName} == 'uptimerobot' ]]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"embeds": [{ "title": "There are currently paused UptimeRobot monitors:","color": 3381759,'"${pausedTests}"'}]}' "${webhookUrl}"
        elif [[ ${providerName} == 'statuscake' ]]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"embeds": [{ "title": "There are currently paused StatusCake monitors:","color": 3381759,'"${pausedTests}"'}]}' "${webhookUrl}"
        elif [[ ${providerName} == 'healthchecks' ]]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"embeds": [{ "title": "There are currently paused HealthChecks.io monitors:","color": 3381759,'"${pausedTests}"'}]}' "${webhookUrl}"
        fi
    elif [[ ${notifyAll} == 'true' ]]; then
        if [[ ${providerName} == 'uptimerobot' ]]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"embeds": [{ "title": "All UptimeRobot monitors are currently running.","color": 10092339}]}' "${webhookUrl}"
        elif [[ ${providerName} == 'statuscake' ]]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"embeds": [{ "title": "All StatusCake monitors are currently running.","color": 10092339}]}' "${webhookUrl}"
        elif [[ ${providerName} == 'healthchecks' ]]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"embeds": [{ "title": "All HealthChecks.io monitors are currently running.","color": 10092339}]}' "${webhookUrl}"
        fi
    fi
}

# Function to create a new monitor.
create_monitor() {
    if [[ ${providerName} == 'uptimerobot' ]]; then
        newHttpMonitorConfigFile='Templates/UptimeRobot/new-http-monitor.json'
        newPortMonitorConfigFile='Templates/UptimeRobot/new-port-monitor.json'
        newKeywordMonitorConfigFile='Templates/UptimeRobot/new-keyword-monitor.json'
        newPingMonitorConfigFile='Templates/UptimeRobot/new-ping-monitor.json'
    elif [[ ${providerName} == 'statuscake' ]]; then
        newHttpMonitorConfigFile='Templates/StatusCake/new-http-monitor.txt'
        newPortMonitorConfigFile='Templates/StatusCake/new-port-monitor.txt'
        newPingMonitorConfigFile='Templates/StatusCake/new-ping-monitor.txt'
    elif [[ ${providerName} == 'healthchecks' ]]; then
        newPingMonitorConfigFile='Templates/HealthChecks/new-monitor.json'
    fi

    if [[ ${providerName} == 'uptimerobot' ]]; then
        if [[ ${createType} != 'http' && ${createType} != 'ping' && ${createType} != 'port' && ${createType} != 'keyword' ]]; then
            echo -e "${red}You did not specify a valid monitor type!${endColor}"
            echo -e "${red}Your choices are http, ping, port, or keyword.${endColor}"
            echo ''
            exit 0
        fi
    elif [[ ${providerName} == 'statuscake' ]]; then
        if [[ ${createType} != 'http' && ${createType} != 'ping' && ${createType} != 'port' ]]; then
            echo -e "${red}You did not specify a valid monitor type!${endColor}"
            echo -e "${red}Your choices are http, ping, or port.${endColor}"
            echo ''
            exit 0
        fi
    elif [[ ${providerName} == 'healthchecks' ]]; then
        if [[ ${createType} != 'ping' ]]; then
            echo -e "${red}You did not specify a valid monitor type!${endColor}"
            echo -e "${red}Your only choice is ping.${endColor}"
            echo ''
            exit 0
        fi
    fi

    if [[ ${createType} == 'http' ]]; then
        newMonitorConfigFile="${newHttpMonitorConfigFile}"
    elif [[ ${createType} == 'ping' ]]; then
        newMonitorConfigFile="${newPingMonitorConfigFile}"
    elif [[ ${createType} == 'port' ]]; then
        newMonitorConfigFile="${newPortMonitorConfigFile}"
    elif [[ ${createType} == 'keyword' ]]; then
        newMonitorConfigFile="${newKeywordMonitorConfigFile}"
    fi

    sed -i "s|\"api_key\": \"[^']*\"|\"api_key\": \"${apiKey}\"|" "${newMonitorConfigFile}"

    if [[ ${providerName} == 'uptimerobot' ]]; then
        if [[ ${jq} == 'true' ]]; then
            curl -s -X POST "${apiUrl}"newMonitor -d @"${newMonitorConfigFile}" --header "Content-Type: application/json" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -X POST "${apiUrl}"newMonitor -d @"${newMonitorConfigFile}" --header "Content-Type: application/json" || fatal
        fi
    elif [[ ${providerName} == 'statuscake' ]]; then
        if [[ ${jq} == 'true' ]]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "$(cat ${newMonitorConfigFile})" --header "Content-Type: application/json" -X PUT "${apiUrl}Tests/Update" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "$(cat ${newMonitorConfigFile})" --header "Content-Type: application/json" -X PUT "${apiUrl}Tests/Update" || fatal
        fi
    elif [[ ${providerName} == 'healthchecks' ]]; then
        if [[ ${jq} == 'true' ]]; then
            curl -s -X POST "${apiUrl}"checks/ -d "$(cat ${newMonitorConfigFile})" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -X POST "${apiUrl}"checks/ -d "$(cat ${newMonitorConfigFile})" || fatal
        fi
    fi

    echo ''
}

# Function to display account statistics.
get_stats() {
    echo 'Here are the basic statistics for your UptimeRobot account:'
    echo ''

    if [[ ${jq} == 'true' ]]; then
        curl -s -X POST "${apiUrl}"getAccountDetails -d "api_key=${apiKey}" -d "format=json" | jq 2> /dev/null || fatal
    elif [[ ${jq} == 'false' ]]; then
        curl --fail -s -X POST "${apiUrl}"getAccountDetails -d "api_key=${apiKey}" -d "format=json" || fatal
    fi

    echo ''
}

# Function to display all stats for single specified monitor.
get_info() {
    echo "${infoType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors
    convert_friendly_monitors
    monitor=$(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")

    if [[ ${providerName} == 'uptimerobot' ]]; then
        if [[ ${jq} == 'true' ]]; then
            curl -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "monitors=${monitor}" -d "format=json" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "monitors=${monitor}" -d "format=json" || fatal
        fi
    elif [[ ${providerName} == 'statuscake' ]]; then
        if [[ ${jq} == 'true' ]]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}Tests/Details/?TestID=${monitor}" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}Tests/Details/?TestID=${monitor}" || fatal
        fi
    elif [[ ${providerName} == 'healthchecks' ]]; then
        if [[ ${jq} == 'true' ]]; then
            curl -s "${apiUrl}"checks/ -X GET -H "X-Api-Key: ${apiKey}" | jq --arg monitor ${monitor} '.checks[] | select(.ping_url | contains($monitor))' 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s "${apiUrl}checks/${monitor}" -X POST -H "X-Api-Key: ${apiKey}" || fatal
        fi
    fi

    echo ''
}

# Function to display all alert contacts.
get_alert_contacts() {
    if [[ ${providerName} == 'uptimerobot' ]]; then
        echo "The following alert contacts have been found for your ${providerName^} account:"
        echo ''

        if [[ ${jq} == 'true' ]]; then
            curl -s -X POST "${apiUrl}"getAlertContacts -d "api_key=${apiKey}" -d "format=json" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -X POST "${apiUrl}"getAlertContacts -d "api_key=${apiKey}" -d "format=json" || fatal
        fi
    elif [[ ${providerName} == 'statuscake' ]]; then
        echo "The following alert contacts have been found for your ${providerName^} account:"
        echo ''

        if [[ ${jq} == 'true' ]]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}ContactGroups" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}ContactGroups" || fatal
        fi
    elif [[ ${providerName} == 'healthchecks' ]]; then
        if [[ ${jq} == 'true' ]]; then
            curl -s -X GET "${apiUrl}"channels/ -H "X-Api-Key: ${apiKey}" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -X GET "${apiUrl}"channels/ -H "X-Api-Key: ${apiKey}" || fatal
        fi
    fi

    echo ''
}

# Function to display reset monitors prompt.
reset_prompt() {
    echo ''
    echo -e "${red}***WARNING*** This will reset ALL data for the specified monitors!!!${endColor}"
    echo -e "Are you sure you wish to continue? (${grn}[Y]${endColor}es or ${red}[N]${endColor}o): "
    read -r resetPrompt
    echo ''

    if ! [[ ${resetPrompt} =~ ^(Yes|yes|Y|y|No|no|N|n)$ ]]; then
        echo -e "${red}Please specify yes, y, no, or n.${endColor}"
    elif [[ ${resetPrompt} =~ ^(No|no|N|n)$ ]]; then
        exit 0
    elif [[ ${resetPrompt} =~ ^(Yes|yes|Y|y)$ ]]; then
        :
    fi
}

# Function to reset all monitors.
reset_all_monitors() {
    reset_prompt

    while IFS= read -r monitor; do
        friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
        echo "Resetting ${friendlyName}:"

        if [[ ${jq} == 'true' ]]; then
            curl -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}" || fatal
        fi

        echo ''

    done < <(cat "${monitorsFile}")
}

# Function to reset specified monitors.
reset_specified_monitors() {
    echo "${resetType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors

    if [[ ${invalidPrompt} == @(No|no|N|n) ]]; then
        exit 0
    else
        convert_friendly_monitors
    fi

    reset_prompt

    while IFS= read -r monitor; do
        friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
        echo "Resetting ${friendlyName}:"

        if [[ ${jq} == 'true' ]]; then
            curl -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}" | jq 2> /dev/null || fatal
        elif [[ ${jq} == 'false' ]]; then
            curl --fail -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}" || fatal
        fi
        echo ''

    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Function to display delete monitors prompt.
delete_prompt() {
    echo ''

    if [[ ${deleteType} == 'all' ]]; then
        echo -e "${red}***WARNING*** This will delete ALL monitors in your account!!!${endColor}"
    elif [[ ${deleteType} != 'all' ]]; then
        echo -e "${red}***WARNING*** This will delete the specified monitor from your account!!!${endColor}"
    fi

    echo -e "Are you sure you wish to continue? (${grn}[Y]${endColor}es or ${red}[N]${endColor}o): "
    read -r deletePrompt
    echo ''

    if ! [[ ${deletePrompt} =~ ^(Yes|yes|Y|y|No|no|N|n)$ ]]; then
        echo -e "${red}Please specify yes, y, no, or n.${endColor}"
    elif [[ ${deletePrompt} =~ ^(No|no|N|n)$ ]]; then
        exit 0
    elif [[ ${deletePrompt} =~ ^(Yes|yes|Y|y)$ ]]; then
        :
    fi
}

# Function to delete all monitors.
delete_all_monitors() {
    delete_prompt

    while IFS= read -r monitor; do
        if [[ ${providerName} == 'uptimerobot' ]]; then
            friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            echo "Deleting ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}" || fatal
            fi
        elif [[ ${providerName} == 'statuscake' ]]; then
            friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            echo "Deleting ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -X DELETE "${apiUrl}Tests/Details/?TestID=${monitor}" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -X DELETE "${apiUrl}Tests/Details/?TestID=${monitor}" || fatal
            fi
        elif [[ ${providerName} == 'healthchecks' ]]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
            echo "Deleting ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s "${apiUrl}checks/${monitor}" -X DELETE -H "X-Api-Key: ${apiKey}" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s "${apiUrl}checks/${monitor}" -X DELETE -H "X-Api-Key: ${apiKey}" || fatal
            fi
        fi

        echo ''

    done < <(cat "${monitorsFile}")
}

# Function to delete specified monitors.
delete_specified_monitors() {
    echo "${deleteType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors

    if [[ ${invalidPrompt} == @(No|no|N|n) ]]; then
        exit 0
    else
        convert_friendly_monitors
    fi

    delete_prompt

    while IFS= read -r monitor; do
        if [[ ${providerName} == 'uptimerobot' ]]; then
            friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            echo "Deleting ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}" || fatal
            fi
        elif [[ ${providerName} == 'statuscake' ]]; then
            friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
            echo "Deleting ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -X DELETE "${apiUrl}Tests/Details/?TestID=${monitor}" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -X DELETE "${apiUrl}Tests/Details/?TestID=${monitor}" || fatal
            fi
        elif [[ ${providerName} == 'healthchecks' ]]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
            echo "Deleting ${friendlyName}:"

            if [[ ${jq} == 'true' ]]; then
                curl -s "${apiUrl}checks/${monitor}" -X DELETE -H "X-Api-Key: ${apiKey}" | jq 2> /dev/null || fatal
            elif [[ ${jq} == 'false' ]]; then
                curl --fail -s "${apiUrl}checks/${monitor}" -X DELETE -H "X-Api-Key: ${apiKey}" || fatal
            fi
        fi

        echo ''

    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Main function to run all other functions.
main() {
    cmdline "${args[@]:-}"
    create_dir
    convert_provider_name
    checks
    set_api_key

    if [[ ${list} == 'true' ]]; then
        get_data
        get_monitors
        create_monitor_files
        create_friendly_list
        display_all_monitors
    elif [[ ${find} == 'true' ]]; then
        get_data
        get_monitors
        create_monitor_files
        get_paused_monitors
        display_paused_monitors

        if [[ -s ${pausedMonitorsFile} ]]; then
            if [[ ${prompt} == 'false' ]]; then
                :
            else
                unpause_prompt

                if [[ ${unpausePrompt} =~ ^(Yes|yes|Y|y)$ ]]; then
                    if [[ ${providerName} == 'upptime' ]]; then
                        echo 'Unpausing the Uptime CI workflow for your Upptime repository...'
                        curl --fail -s -X PUT -H "Authorization: bearer ${ghToken}" -H "Accept: application/vnd.github.v3+json" "${apiUrl}repos/${gitHubUsername}/${upptimeRepo}/actions/workflows/uptime.yml/enable" || fatal
                        echo -e "${grn}Success!${endColor}"
                        echo ''
                    else
                        while IFS= read -r monitor; do
                            if [[ ${providerName} == 'uptimerobot' ]]; then
                                friendlyName=$(jq -r .monitors[].friendly_name "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                                echo "Unpausing ${friendlyName}:"

                                if [[ ${jq} == 'true' ]]; then
                                    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" | jq 2> /dev/null || fatal
                                elif [[ ${jq} == 'false' ]]; then
                                    curl --fail -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" || fatal
                                fi
                            elif [[ ${providerName} == 'statuscake' ]]; then
                                friendlyName=$(jq -r .WebsiteName "${tempDir}${monitor}".txt 2> /dev/null) || fatal
                                echo "Unpausing ${friendlyName}:"

                                if [[ ${jq} == 'true' ]]; then
                                    curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" | jq 2> /dev/null || fatal
                                elif [[ ${jq} == 'false' ]]; then
                                    curl --fail -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" || fatal
                                fi
                            elif [[ ${providerName} == 'healthchecks' ]]; then
                                cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
                                friendlyName=$(jq -r .name "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
                                pingURL=$(jq -r .ping_url "${tempDir}${monitor}"_short.txt 2> /dev/null) || fatal
                                echo "Unpausing ${friendlyName} by sending a ping:"
                                pingResponse=$(curl -fsS --retry 3 "${pingURL}")

                                if [[ ${pingResponse} == 'OK' ]]; then
                                    echo -e "${grn}Success!${endColor}"
                                else
                                    echo -e "${red}Unable to unpause ${friendlyName}!${endColor}"
                                fi
                            fi

                            echo ''

                        done < <(awk -F: '{print $2}' "${pausedMonitorsFile}" | sed 's/\x1B\[[0-9;]*[JKmsu]//g' | tr -d ' ')
                    fi
                elif [[ ${unpausePrompt} =~ ^(No|no|N|n)$ ]]; then
                    exit 0
                fi
            fi
        fi

        if [[ ${webhook} == 'true' ]]; then
            send_notification
        fi
    elif [[ ${pause} == 'true' ]]; then
        if [[ ${pauseType} == 'all' ]]; then
            get_data
            get_monitors
            create_monitor_files
            pause_all_monitors
        elif [[ ${pauseType} != 'all' ]]; then
            get_data
            get_monitors
            create_monitor_files
            create_friendly_list
            pause_specified_monitors
        fi
    elif [[ ${unpause} == 'true' ]]; then
        if [[ ${unpauseType} == 'all' ]]; then
            get_data
            get_monitors
            create_monitor_files
            unpause_all_monitors
        elif [[ ${unpauseType} != 'all' ]]; then
            get_data
            get_monitors
            create_monitor_files
            create_friendly_list
            unpause_specified_monitors
        fi
    elif [[ ${reset} == 'true' ]]; then
        if [[ ${providerName} == 'statuscake' ]] || [[ ${providerName} == 'healthchecks' ]]; then
            echo -e "${red}Sorry, but that option is not currently possible with you ${providerName^} account!${endColor}"
            exit 0
        fi

        if [[ ${resetType} == 'all' ]]; then
            get_data
            get_monitors
            create_monitor_files
            reset_all_monitors
        elif [[ ${resetType} != 'all' ]]; then
            get_data
            get_monitors
            create_monitor_files
            create_friendly_list
            reset_specified_monitors
        fi
    elif [[ ${delete} == 'true' ]]; then
        if [[ ${deleteType} == 'all' ]]; then
            get_data
            get_monitors
            create_monitor_files
            delete_all_monitors
        elif [[ ${deleteType} != 'all' ]]; then
            get_data
            get_monitors
            create_monitor_files
            create_friendly_list
            delete_specified_monitors
        fi
    elif [[ ${stats} == 'true' ]]; then
        if [[ ${providerName} == 'statuscake' ]] || [[ ${providerName} == 'healthchecks' ]]; then
            echo -e "${red}Sorry, but that option is not valid for ${providerName^}.${endColor}"
            exit 0
        else
            get_stats
        fi
    elif [[ ${create} == 'true' ]]; then
        create_monitor
    elif [[ ${alerts} == 'true' ]]; then
        get_alert_contacts
    elif [[ ${info} == 'true' ]]; then
        get_data
        get_monitors
        create_monitor_files
        create_friendly_list
        get_info
    fi
}

main
