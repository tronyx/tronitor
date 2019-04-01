#!/usr/bin/env bash
#
# Script to utilize the UptimeRobot, StatusCake, and HealthChecks.io APIs to retrieve and work with monitors.
# Tronyx
set -eo pipefail
IFS=$'\n\t'

# Edit these to finish setting up the script
# Monitor provider name, IE: UptimeRobot, StatusCake, or HealthChecks
providerName=''
# If your provider is StatusCake, specify your username
scUsername=''
# Specify API key
apiKey=''
# Specify the Discord/Slack webhook URL to send notifications to
webhookUrl=''
# Set notifyAll to true for notification to apply for all running state as well
notifyAll='false'
# Set JQ to false to disable the use of the JQ command.
# This works better for using the script with cronjobs, etc.
jq='false'

# Declare some variables
# Temp dir and filenames
tempDir='/tmp/tronitor/'
usernameTestFile="${tempDir}sc_username_temp.txt"
apiTestFullFile="${tempDir}api_test_full.txt"
badMonitorsFile="${tempDir}bad_monitors.txt"
convertedMonitorsFile="${tempDir}converted_monitors.txt"
friendlyListFile="${tempDir}friendly_list.txt"
pausedMonitorsFile="${tempDir}paused_monitors.txt"
specifiedMonitorsFile="${tempDir}specified_monitors.txt"
monitorsFile="${tempDir}monitors.txt"
monitorsFullFile="${tempDir}monitors_full.txt"
validMonitorsFile="${tempDir}valid_monitors.txt"
validMonitorsTempFile="${tempDir}valid_monitors_temp.txt"
# UUID regex pattern
uuidPattern='^\{?[A-Z0-9a-z]{8}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{4}-[A-Z0-9a-z]{12}\}?$'
# Set initial API key status
apiKeyStatus='invalid'
# Set initial provider status
providerStatus='invalid'
# Set initial SC username status
scUsernameStatus='invalid'
# Arguments
readonly args=("$@")
# Colors
readonly blu='\e[34m'
readonly lblu='\e[94m'
readonly grn='\e[32m'
readonly red='\e[31m'
readonly ylw='\e[33m'
readonly org='\e[38;5;202m'
readonly lorg='\e[38;5;130m'
readonly mgt='\e[35m'
readonly endColor='\e[0m'

# Source usage function
. Travis/Config/usage.cfg

# Define script options
cmdline() {
    local arg=
    local local_args
    local OPTERR=0
    for arg; do
        local delim=""
        case "${arg}" in
            # Translate --gnu-long-options to -g (short options)
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
            # Pass through anything else
            *)
                [[ ${arg:0:1} == "-" ]] || delim='"'
                local_args="${local_args:-}${delim}${arg}${delim} "
                ;;
        esac
    done

    # Reset the positional parameters to the short options
    eval set -- "${local_args:-}"

    while getopts "hslfnwai:c:r:d:p:u:" OPTION; do
        case "$OPTION" in
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
                if [[ ${arg} == '-p' || ${arg} == '-u' || ${arg} == '-r' || ${arg} == '-d' || ${arg} == '-i' || ${arg} == '-c' ]] && [[ -z ${OPTARG} ]]; then
                    echo -e "${red}Option ${arg} requires an argument!${endColor}"
                else
                    echo -e "${red}You are specifying a non-existent option!${endColor}"
                fi
                usage
                exit
                ;;
        esac
    done
    return 0
}

# Script Information
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
readonly scriptpath="$(cd -P "$(dirname "${scriptname}")" > /dev/null && pwd)"

# Create directory to neatly store temp files
create_dir() {
    mkdir -p "${tempDir}"
    chmod 777 "${tempDir}"
}

# Cleanup temp files
cleanup() {
    rm -rf "${tempDir}"*.txt || true
}
trap 'cleanup' 0 1 3 6 14 15

# Exit the script if the user hits CTRL+C
function control_c() {
    cleanup
    exit
}
trap 'control_c' 2

# Check for empty arg
check_empty_arg() {
    for arg in "${args[@]:-}"; do
        if [ -z "${arg}" ]; then
            usage
            exit
        fi
    done
}

# Grab status variable line numbers
get_line_numbers() {
    # Line numbers for user-defined vars
    providerNameLineNum=$(head -50 "${scriptname}" | grep -En -A1 'UptimeRobot, StatusCake, or HealthChecks' | tail -1 | awk -F- '{print $1}')
    scUsernameLineNum=$(head -50 "${scriptname}" | grep -En -A1 'specify your username' | tail -1 | awk -F- '{print $1}')
    apiKeyLineNum=$(head -50 "${scriptname}" | grep -En -A1 'Specify API key' | tail -1 | awk -F- '{print $1}')
    webhookUrlLineNum=$(head -50 "${scriptname}" | grep -En -A1 'Discord/Slack' | tail -1 | awk -F- '{print $1}')
    # Line numbers for status vars
    apiStatusLineNum=$(head -50 "${scriptname}" | grep -En -A1 'Set initial API key status' | tail -1 | awk -F- '{print $1}')
    providerStatusLineNum=$(head -50 "${scriptname}" | grep -En -A1 'Set initial provider status' | tail -1 | awk -F- '{print $1}')
    scUserStatusLineNum=$(head -50 "${scriptname}" | grep -En -A1 'Set initial SC username status' | tail -1 | awk -F- '{print $1}')
}

# Make sure provider name is lowercase and, if not, convert it
convert_provider_name() {
    if [[ ${providerName} =~ [[:upper:]] ]]; then
        providerName=$(echo "${providerName}" | awk '{print tolower($0)}')
    else
        :
    fi
}

# Check that provider is valid and not empty
check_provider() {
    while [ "${providerStatus}" = 'invalid' ]; do
        if [ -z "${providerName}" ]; then
            echo -e "${red}You didn't specify your monitoring provider!${endColor}"
            echo ''
            read -rp 'Enter your provider: ' provider
            echo ''
            sed -i "${providerNameLineNum} s|providerName='[^']*'|providerName='${provider}'|" "${scriptname}"
            providerName="${provider}"
            convert_provider_name
        else
            if [[ ${providerName} != 'uptimerobot' ]] && [[ ${providerName} != 'statuscake' ]] && [[ ${providerName} != 'healthchecks' ]]; then
                echo -e "${red}You didn't specify a valid monitoring provider!${endColor}"
                echo -e "${red}Please specify either uptimerobot, statuscake, or healthchecks.${endColor}"
                echo ''
                read -rp 'Enter your provider: ' provider
                echo ''
                sed -i "${providerNameLineNum} s|providerName='[^']*'|providerName='${provider}'|" "${scriptname}"
                providerName="${provider}"
                convert_provider_name
            else
                sed -i "${providerStatusLineNum} s|providerStatus='[^']*'|providerStatus='ok'|" "${scriptname}"
                providerName="${provider}"
                convert_provider_name
                providerStatus="ok"
            fi
        fi
    done
    if [ "${providerName}" = 'uptimerobot' ]; then
        readonly apiUrl='https://api.uptimerobot.com/v2/'
    elif [ "${providerName}" = 'statuscake' ]; then
        readonly apiUrl='https://app.statuscake.com/API/'
    elif [ "${providerName}" = 'healthchecks' ]; then
        readonly apiUrl='https://healthchecks.io/api/v1/'
    fi
}

# Check that StatusCake credentials are valid
check_sc_creds() {
    while [ "${scUsernameStatus}" = 'invalid' ] || [ "${apiKeyStatus}" = 'invalid' ]; do
        if [ -z "${apiKey}" ]; then
            echo -e "${red}You didn't define your API key in the script!${endColor}"
            echo ''
            read -rp 'Enter your API key: ' API
            echo ''
            sed -i "${apiKeyLineNum} s/apiKey='[^']*'/apiKey='${API}'/" "${scriptname}"
            apiKey="${API}"
        else
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}"Tests/ > "${apiTestFullFile}"
            set +e
            scStatus=$(grep -Poc '"ErrNo":[0-9]' "${apiTestFullFile}")
            set -e
            if [ "${scStatus}" = "1" ]; then
                echo -e "${red}The API Key and/or username that you provided are not valid!${endColor}"
                sed -i "${apiKeyLineNum} s/apiKey='[^']*'/apiKey=''/" "${scriptname}"
                apiKey=""
            elif [ "${scStatus}" = "0" ]; then
                sed -i "${apiStatusLineNum} s/apiKeyStatus='[^']*'/apiKeyStatus='ok'/" "${scriptname}"
                apiKeyStatus="ok"
            fi
        fi
        if [ -z "${scUsername}" ]; then
            echo -e "${red}You didn't specify your StatusCake username in the script!${endColor}"
            echo ''
            read -rp 'Enter your username: ' username
            echo ''
            sed -i "${scUsernameLineNum} s/scUsername='[^']*'/scUsername='${username}'/" "${scriptname}"
            scUsername="${username}"
        else
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}"Tests/ > "${usernameTestFile}"
            set +e
            scStatus=$(grep -Poc '"ErrNo":[0-9]' "${usernameTestFile}")
            set -e
            if [ "${scStatus}" = "1" ]; then
                echo -e "${red}The API Key and/or username that you provided are not valid!${endColor}"
                sed -i "${scUsernameLineNum} s/scUsername='[^']*'/scUsername=''/" "${scriptname}"
                scUsername=""
                echo ''
                read -rp 'Enter your username: ' username
                echo ''
                sed -i "${scUsernameLineNum} s/scUsername='[^']*'/scUsername='${username}'/" "${scriptname}"
                scUsername="${username}"
            elif [ "${scStatus}" = "0" ]; then
                sed -i "${scUserStatusLineNum} s/scUsernameStatus='[^']*'/scUsernameStatus='ok'/" "${scriptname}"
                scUsernameStatus="ok"
            fi
        fi
    done
}

# Check that provided API Key is valid
check_api_key() {
    if [[ ${providerName} == 'uptimerobot' ]] || [[ ${providerName} == 'healthchecks' ]]; then
        while [ "${apiKeyStatus}" = 'invalid' ]; do
            if [[ -z ${apiKey} ]]; then
                echo -e "${red}You didn't define your API key in the script!${endColor}"
                echo ''
                read -rp 'Enter your API key: ' API
                echo ''
                sed -i "${apiKeyLineNum} s/apiKey='[^']*'/apiKey='${API}'/" "${scriptname}"
                apiKey="${API}"
            else
                if [ "${providerName}" = 'uptimerobot' ]; then
                    curl -s -X POST "${apiUrl}"getAccountDetails -d "api_key=${apiKey}" -d "format=json" > "${apiTestFullFile}"
                    status=$(grep -Po '"stat":"[a-z]*"' "${apiTestFullFile}" | awk -F':' '{print $2}' | tr -d '"')
                    if [ "${status}" = "fail" ]; then
                        echo -e "${red}The API Key that you provided is not valid!${endColor}"
                        sed -i "${apiKeyLineNum} s/apiKey='[^']*'/apiKey=''/" "${scriptname}"
                        apiKey=""
                    elif [ "${status}" = "ok" ]; then
                        sed -i "${apiStatusLineNum} s/apiKeyStatus='[^']*'/apiKeyStatus='${status}'/" "${scriptname}"
                        apiKeyStatus="${status}"
                    fi
                elif [ "${providerName}" = 'healthchecks' ]; then
                    curl -s -H "X-Api-Key: ${apiKey}" -X GET "${apiUrl}"checks/ | jq .error > "${apiTestFullFile}"
                    status=$(cat "${apiTestFullFile}")
                    if [ "${status}" != 'null' ]; then
                        echo -e "${red}The API Key that you provided is not valid!${endColor}"
                        sed -i "${apiKeyLineNum} s/apiKey='[^']*'/apiKey=''/" "${scriptname}"
                        apiKey=""
                    elif [ "${status}" = "null" ]; then
                        sed -i "${apiStatusLineNum} s/apiKeyStatus='[^']*'/apiKeyStatus='${status}'/" "${scriptname}"
                        apiKeyStatus="${status}"
                    fi
                fi
            fi
        done
    fi
}

# Check that webhok URL is defined if Alert is set to true
check_webhook_url() {
    if [ "${webhookUrl}" = "" ] && [ "${webhook}" = "true" ]; then
        echo -e "${red}You didn't define your Discord webhook URL!${endColor}"
        echo ''
        read -rp 'Enter your webhook URL: ' url
        echo ''
        sed -i "${webhookUrlLineNum} s|webhookUrl='[^']*'|webhookUrl='${url}'|" "${scriptname}"
        webhookUrl="${url}"
    else
        :
    fi
}

# Function to wrap all other checks into one
checks() {
    get_line_numbers
    check_empty_arg
    check_provider
    if [ "${providerName}" = 'statuscake' ]; then
        check_sc_creds
    else
        check_api_key
    fi
    check_webhook_url
}

# Grab data for all monitors
get_data() {
    if [ "${providerName}" = 'uptimerobot' ]; then
        curl -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "format=json" > "${monitorsFullFile}"
    elif [ "${providerName}" = 'statuscake' ]; then
        curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}"Tests/ > "${monitorsFullFile}"
    elif [ "${providerName}" = 'healthchecks' ]; then
        curl -s -H "X-Api-Key: ${apiKey}" -X GET "${apiUrl}"checks/ > "${monitorsFullFile}"
    fi
}

# Create list of monitor IDs
get_monitors() {
    if [ "${providerName}" = 'uptimerobot' ]; then
        totalMonitors=$(grep -Po '"total":[!0-9]*' "${monitorsFullFile}" | awk -F: '{print $2}')
    elif [ "${providerName}" = 'statuscake' ]; then
        totalMonitors=$(grep -Po '"TestID":[!0-9]*' "${monitorsFullFile}" | wc -l)
    elif [ "${providerName}" = 'healthchecks' ]; then
        totalMonitors=$(jq .checks[].name "${monitorsFullFile}" | wc -l)
    fi
    if [ "${totalMonitors}" = '0' ]; then
        echo 'There are currently no monitors associated with your UptimeRobot account.'
        exit
    else
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*' "${monitorsFullFile}" | tr -d '"id:' > "${monitorsFile}"
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*' "${monitorsFullFile}" | tr -d '"TestID:' > "${monitorsFile}"
        elif [ "${providerName}" = 'healthchecks' ]; then
            jq .checks[].ping_url "${monitorsFullFile}" | tr -d '"' | cut -c21- > "${monitorsFile}"
        fi
    fi
}

# Create individual monitor files
create_monitor_files() {
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            curl -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "monitors=${monitor}" -d "format=json" > "${tempDir}${monitor}".txt
        elif [ "${providerName}" = 'statuscake' ]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}Tests/Details/?TestID=${monitor}" > "${tempDir}${monitor}".txt
        elif [ "${providerName}" = 'healthchecks' ]; then
            curl -s -H "X-Api-Key: ${apiKey}" -X GET ${apiUrl}checks/ | jq --arg monitor $monitor '.checks[] | select(.ping_url | contains($monitor))' > "${tempDir}${monitor}".txt
        fi
    done < <(cat "${monitorsFile}")
}

# Create friendly output of all monitors
create_friendly_list() {
    true > "${friendlyListFile}"
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            status=$(grep status "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            if [ "${status}" = '0' ]; then
                friendlyStatus="${ylw}Paused${endColor}"
            elif [ "${status}" = '1' ]; then
                friendlyStatus="${mgt}Not checked yet${endColor}"
            elif [ "${status}" = '2' ]; then
                friendlyStatus="${grn}Up${endColor}"
            elif [ "${status}" = '8' ]; then
                friendlyStatus="${org}Seems down${endColor}"
            elif [ "${status}" = '9' ]; then
                friendlyStatus="${red}Down${endColor}"
            fi
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep WebsiteName "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            status=$(grep Status "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            paused=$(grep Paused "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            if [ "${status}" = 'Up' ] && [ "${paused}" = 'true' ]; then
                friendlyStatus="${ylw}Paused${endColor}"
                #elif [ "${status}" = '1' ]; then
                #friendlyStatus="${mgt}Not checked yet${endColor}"
            elif [ "${status}" = 'Up' ] && [ "${paused}" = 'false' ]; then
                friendlyStatus="${grn}Up${endColor}"
                #elif [ "${status}" = '8' ]; then
                #friendlyStatus="${org}Seems down${endColor}"
            elif [ "${status}" = 'Down' ] && [ "${paused}" = 'false' ]; then
                friendlyStatus="${red}Down${endColor}"
            fi
        elif [ "${providerName}" = 'healthchecks' ]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
            status=$(jq .status "${tempDir}${monitor}"_short.txt | tr -d '"')
            if [ "${status}" = 'up' ]; then
                friendlyStatus="${grn}Up${endColor}"
            elif [ "${status}" = 'down' ]; then
                friendlyStatus="${red}Down${endColor}"
            elif [ "${status}" = 'paused' ]; then
                friendlyStatus="${ylw}Paused${endColor}"
            elif [ "${status}" = 'late' ]; then
                friendlyStatus="${org}Late${endColor}"
            elif [ "${status}" = 'new' ]; then
                friendlyStatus="${mgt}New${endColor}"
            fi
        fi
        echo -e "${lorg}${friendlyName}${endColor} | ID: ${lblu}${monitor}${endColor} | Status: ${friendlyStatus}" >> "${friendlyListFile}"
    done < <(cat "${monitorsFile}")
}

# Display friendly list of all monitors
display_all_monitors() {
    if [ -s "${friendlyListFile}" ]; then
        if [ "${providerName}" = 'uptimerobot' ]; then
            echo 'The following monitors were found in your UptimeRobot account:'
        elif [ "${providerName}" = 'statuscake' ]; then
            echo 'The following monitors were found in your StatusCake account:'
        elif [ "${providerName}" = 'healthchecks' ]; then
            echo 'The following monitors were found in your HealthChecks.io account:'
        fi
        echo ''
        column -ts "|" "${friendlyListFile}"
        echo ''
    else
        :
    fi
}

# Find all paused monitors
get_paused_monitors() {
    true > "${pausedMonitorsFile}"
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            status=$(grep status "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            if [ "${status}" = '0' ]; then
                echo -e "${lorg}${friendlyName}${endColor} - ID: ${lblu}${monitor}${endColor}" >> "${pausedMonitorsFile}"
            else
                :
            fi
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep Website "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            status=$(grep Status "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            paused=$(grep Paused "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            if [ "${status}" = 'Up' ] && [ "${paused}" = 'true' ]; then
                echo -e "${lorg}${friendlyName}${endColor} - ID: ${lblu}${monitor}${endColor}" >> "${pausedMonitorsFile}"
            else
                :
            fi
        elif [ "${providerName}" = 'healthchecks' ]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
            status=$(jq .status "${tempDir}${monitor}"_short.txt | tr -d '"')
            if [ "${status}" = 'paused' ]; then
                echo -e "${lorg}${friendlyName}${endColor} | ID: ${lblu}${monitor}${endColor}" >> "${pausedMonitorsFile}"
            else
                :
            fi
        fi
    done < <(cat "${monitorsFile}")
}

# Display list of all paused monitors
display_paused_monitors() {
    if [ -s "${pausedMonitorsFile}" ]; then
        if [ "${providerName}" = 'uptimerobot' ]; then
            echo 'The following UptimeRobot monitors are currently paused:'
        elif [ "${providerName}" = 'statuscake' ]; then
            echo 'The following StatusCake monitors are currently paused:'
        elif [ "${providerName}" = 'healthchecks' ]; then
            echo 'The following HealthChecks.io monitors are currently paused:'
        fi
        echo ''
        column -ts "|" "${pausedMonitorsFile}"
    else
        if [ "${providerName}" = 'uptimerobot' ]; then
            echo 'There are currently no paused UptimeRobot monitors.'
        elif [ "${providerName}" = 'statuscake' ]; then
            echo 'There are currently no paused StatusCake monitors.'
        elif [ "${providerName}" = 'healthchecks' ]; then
            echo 'There are currently no paused HealthChecks.io monitors.'
        fi
        echo ''
    fi
}

# Prompt user to unpause monitors after finding paused monitors
unpause_prompt() {
    echo ''
    echo -e "Would you like to unpause the paused monitors? (${grn}[Y]${endColor}es or ${red}[N]${endColor}o): "
    read -r unpausePrompt
    echo ''
    if ! [[ $unpausePrompt =~ ^(Yes|yes|Y|y|No|no|N|n)$ ]]; then
        echo -e "${red}Please specify yes, y, no, or n.${endColor}"
        read -r unpausePrompt
    else
        :
    fi
}

# Prompt user to continue actioning valid monitors after finding invalid ones
invalid_prompt() {
    echo "Would you like to continue actioning the valid monitors below?"
    echo ''
    cat "${validMonitorsFile}"
    echo ''
    echo -e "${grn}[Y]${endColor}es or ${red}[N]${endColor}o):"
    read -r invalidPrompt
    echo ''
    if ! [[ $invalidPrompt =~ ^(Yes|yes|Y|y|No|no|N|n)$ ]]; then
        echo -e "${red}Please specify yes, y, no, or n.${endColor}"
        read -r invalidPrompt
    else
        :
    fi
}

# Check for bad monitors
check_bad_monitors() {
    true > "${badMonitorsFile}"
    while IFS= read -r monitor; do
        if [[ $(grep -ic "${monitor}" "${friendlyListFile}") != "1" ]]; then
            if [[ ${monitor} =~ ^[A-Za-z]+$ ]]; then
                echo -e "${lorg}${monitor}${endColor}" >> "${badMonitorsFile}"
            elif [[ ${monitor} != ^[A-Za-z]+$ ]]; then
                echo -e "${lblu}${monitor}${endColor}" >> "${badMonitorsFile}"
            fi
        else
            :
        fi
    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${specifiedMonitorsFile}")
    if [ -s "${badMonitorsFile}" ]; then
        echo -e "${red}The following specified monitors are not valid:${endColor}"
        echo ''
        cat "${badMonitorsFile}"
        sed -i 's/\x1B\[[0-9;]*[JKmsu]//g' "${badMonitorsFile}"
        set +e
        grep -vxf "${badMonitorsFile}" "${specifiedMonitorsFile}" > "${validMonitorsTempFile}"
        true > "${validMonitorsFile}"
        if [ -s "${validMonitorsTempFile}" ]; then
            while IFS= read -r monitor; do
                echo -e "${grn}${monitor}${endColor}" >> "${validMonitorsFile}"
            done < <(cat "${validMonitorsTempFile}")
            echo ''
            invalid_prompt
        elif [ ! -s "${validMonitorsTempFile}" ]; then
            echo ''
            echo "Please make sure you're specifying a valid monitor and try again."
            echo ''
            exit
        fi
        set -e
    else
        :
    fi
}

# Convert friendly names to IDs
convert_friendly_monitors() {
    true > "${convertedMonitorsFile}"
    if [ -s "${validMonitorsFile}" ]; then
        cat "${validMonitorsFile}" > "${specifiedMonitorsFile}"
    else
        :
    fi
    if [ "${providerName}" = 'healthchecks' ]; then
        while IFS= read -r monitor; do
            if [[ $(echo "${monitor}" | tr -d ' ') =~ $uuidPattern ]]; then
                echo "${monitor}" >> "${convertedMonitorsFile}"
                #curl -s -H "X-Api-Key: ${apiKey}" -X GET ${apiUrl}checks/ | jq --arg monitor $monitor '.checks[] | select(.name | match($monitor;"i"))'.ping_url | tr -d '"' | cut -c21- >> "${convertedMonitorsFile}"
            else
                curl -s -H "X-Api-Key: ${apiKey}" -X GET ${apiUrl}checks/ | jq --arg monitor $monitor '.checks[] | select(.name | match($monitor;"i"))'.ping_url | tr -d '"' | cut -c21- >> "${convertedMonitorsFile}"
                #echo "${monitor}" >> "${convertedMonitorsFile}"
            fi
        done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${specifiedMonitorsFile}")
    else
        while IFS= read -r monitor; do
            if [[ $(echo "${monitor}" | tr -d ' ') =~ [A-Za-z] ]]; then
                grep -Pi "${monitor}" "${friendlyListFile}" | awk -F ':' '{print $2}' | awk -F ' ' '{print $1}' >> "${convertedMonitorsFile}"
            else
                echo "${monitor}" >> "${convertedMonitorsFile}"
            fi
        done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${specifiedMonitorsFile}")
    fi
}

# Pause all monitors
pause_all_monitors() {
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Pausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0"
            fi
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep Website "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Pausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=1" -X PUT "${apiUrl}Tests/Update" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=1" -X PUT "${apiUrl}Tests/Update"
            fi
        elif [ "${providerName}" = 'healthchecks' ]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
            echo "Pausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s "${apiUrl}checks/${monitor}"/pause -X POST -H "X-Api-Key: ${apiKey}" --data "" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s "${apiUrl}checks/${monitor}"/pause -X POST -H "X-Api-Key: ${apiKey}" --data ""
            fi
        fi
        echo ''
    done < <(cat "${monitorsFile}")
    if [ "${providerName}" = 'healthchecks' ]; then
        echo -e "${ylw}**NOTE:** Healthchecks.io works with cronjobs so, unless you disable your cronjobs for${endColor}"
        echo -e "${ylw}the HC.io monitors, all paused monitors will become active again the next time they receive a ping.${endColor}"
    else
        :
    fi
}

# Pause specified monitors
pause_specified_monitors() {
    echo "${pauseType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors
    if [[ ${invalidPrompt} == @(N|No|n|no) ]]; then
        exit 0
    else
        convert_friendly_monitors
    fi
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Pausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0"
            fi
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep Website "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Pausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=1" -X PUT "${apiUrl}Tests/Update" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=1" -X PUT "${apiUrl}Tests/Update"
            fi
        elif [ "${providerName}" = 'healthchecks' ]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
            echo "Pausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s "${apiUrl}checks/${monitor}"/pause -X POST -H "X-Api-Key: ${apiKey}" --data "" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s "${apiUrl}checks/${monitor}"/pause -X POST -H "X-Api-Key: ${apiKey}" --data ""
            fi
        fi
        echo ''
    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
    if [ "${providerName}" = 'healthchecks' ]; then
        echo -e "${ylw}**NOTE:** Healthchecks.io works with cronjobs so, unless you disable your cronjobs for${endColor}"
        echo -e "${ylw}the HC.io monitors, all paused monitors will become active again the next time they receive a ping.${endColor}"
    else
        :
    fi
}

# Unpause all monitors
unpause_all_monitors() {
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Unpausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1"
            fi
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep Website "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Unpausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update"
            fi
        elif [ "${providerName}" = 'healthchecks' ]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
            pingURL=$(jq .ping_url "${tempDir}${monitor}"_short.txt | tr -d '"')
            echo "Unpausing ${friendlyName} by sending a ping:"
            pingResponse=$(curl -fsS --retry 3 "${pingURL}")
            if [ "${pingResponse}" = 'OK' ]; then
                echo -e "${grn}Success!${endColor}"
            else
                echo -e "${red}Unable to unpause ${friendlyName}!${endColor}"
            fi
        fi
        echo ''
    done < <(cat "${monitorsFile}")
}

# Unpause specified monitors
unpause_specified_monitors() {
    echo "${unpauseType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors
    if [[ ${invalidPrompt} == @(No|no|N|n) ]]; then
        exit 0
    else
        convert_friendly_monitors
    fi
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Unpausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1"
            fi
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep Website "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Unpausing ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update"
            fi
        elif [ "${providerName}" = 'healthchecks' ]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
            pingURL=$(jq .ping_url "${tempDir}${monitor}"_short.txt | tr -d '"')
            echo "Unpausing ${friendlyName} by sending a ping:"
            pingResponse=$(curl -fsS --retry 3 "${pingURL}")
            if [ "${pingResponse}" = 'OK' ]; then
                echo -e "${grn}Success!${endColor}"
            else
                echo -e "${red}Unable to unpause ${friendlyName}!${endColor}"
            fi
        fi
        echo ''
    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Send Discord notification
send_notification() {
    if [ -s "${pausedMonitorsFile}" ]; then
        pausedTests=$(paste -s -d, "${pausedMonitorsFile}" | sed 's/\x1B\[[0-9;]*[JKmsu]//g')
        if [ "${providerName}" = 'uptimerobot' ]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"content": "There are currently paused UptimeRobot monitors:\n\n'"${pausedTests}"'"}' ${webhookUrl}
        elif [ "${providerName}" = 'statuscake' ]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"content": "There are currently paused StatusCake monitors:\n\n'"${pausedTests}"'"}' ${webhookUrl}
        elif [ "${providerName}" = 'healthchecks' ]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"content": "There are currently paused HealthChecks.io monitors:\n\n'"${pausedTests}"'"}' ${webhookUrl}
        fi
    elif [ "${notifyAll}" = "true" ]; then
        curl -s -H "Content-Type: application/json" -X POST -d '{"content": ""}' ${webhookUrl}
        if [ "${providerName}" = 'uptimerobot' ]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"content": "All UptimeRobot monitors are currently running."}' ${webhookUrl}
        elif [ "${providerName}" = 'statuscake' ]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"content": "All StatusCake monitors are currently running."}' ${webhookUrl}
        elif [ "${providerName}" = 'healthchecks' ]; then
            curl -s -H "Content-Type: application/json" -X POST -d '{"content": "All HealthChecks.io monitors are currently running."}' ${webhookUrl}
        fi
    fi
}

# Create a new monitor
create_monitor() {
    if [ "${providerName}" = 'uptimerobot' ]; then
        newHttpMonitorConfigFile='Templates/UptimeRobot/new-http-monitor.json'
        newPortMonitorConfigFile='Templates/UptimeRobot/new-port-monitor.json'
        newKeywordMonitorConfigFile='Templates/UptimeRobot/new-keyword-monitor.json'
        newPingMonitorConfigFile='Templates/UptimeRobot/new-ping-monitor.json'
    elif [ "${providerName}" = 'statuscake' ]; then
        newHttpMonitorConfigFile='Templates/StatusCake/new-http-monitor.txt'
        newPortMonitorConfigFile='Templates/StatusCake/new-port-monitor.txt'
        newPingMonitorConfigFile='Templates/StatusCake/new-ping-monitor.txt'
    elif [ "${providerName}" = 'healthchecks' ]; then
        newPingMonitorConfigFile='Templates/HealthChecks/new-monitor.json'
    fi
    if [ "${providerName}" = 'uptimerobot' ]; then
        if [[ ${createType} != 'http' && ${createType} != 'ping' && ${createType} != 'port' && ${createType} != 'keyword' ]]; then
            echo -e "${red}You did not specify a valid monitor type!${endColor}"
            echo -e "${red}Your choices are http, ping, port, or keyword.${endColor}"
            echo ''
            exit 0
        else
            :
        fi
    elif [ "${providerName}" = 'statuscake' ]; then
        if [[ ${createType} != 'http' && ${createType} != 'ping' && ${createType} != 'port' ]]; then
            echo -e "${red}You did not specify a valid monitor type!${endColor}"
            echo -e "${red}Your choices are http, ping, or port.${endColor}"
            echo ''
            exit 0
        else
            :
        fi
    elif [ "${providerName}" = 'healthchecks' ]; then
        if [[ ${createType} != 'ping' ]]; then
            echo -e "${red}You did not specify a valid monitor type!${endColor}"
            echo -e "${red}Your only choice is ping.${endColor}"
            echo ''
            exit 0
        else
            :
        fi
    fi
    if [ "${createType}" = 'http' ]; then
        newMonitorConfigFile="${newHttpMonitorConfigFile}"
    elif [ "${createType}" = 'ping' ]; then
        newMonitorConfigFile="${newPingMonitorConfigFile}"
    elif [ "${createType}" = 'port' ]; then
        newMonitorConfigFile="${newPortMonitorConfigFile}"
    elif [ "${createType}" = 'keyword' ]; then
        newMonitorConfigFile="${newKeywordMonitorConfigFile}"
    fi
    sed -i "s|\"api_key\": \"[^']*\"|\"api_key\": \"${apiKey}\"|" "${newMonitorConfigFile}"
    if [ "${providerName}" = 'uptimerobot' ]; then
        if [ "${jq}" = 'true' ]; then
            curl -s -X POST "${apiUrl}"newMonitor -d @"${newMonitorConfigFile}" --header "Content-Type: application/json" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -X POST "${apiUrl}"newMonitor -d @"${newMonitorConfigFile}" --header "Content-Type: application/json"
        fi
    elif [ "${providerName}" = 'statuscake' ]; then
        if [ "${jq}" = 'true' ]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "$(cat ${newMonitorConfigFile})" --header "Content-Type: application/json" -X PUT "${apiUrl}Tests/Update" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "$(cat ${newMonitorConfigFile})" --header "Content-Type: application/json" -X PUT "${apiUrl}Tests/Update"
        fi
    elif [ "${providerName}" = 'healthchecks' ]; then
        if [ "${jq}" = 'true' ]; then
            curl -s -X POST "${apiUrl}"checks/ -d "$(cat ${newMonitorConfigFile})" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -X POST "${apiUrl}"checks/ -d "$(cat ${newMonitorConfigFile})"
        fi
    fi
    echo ''
}

# Display account statistics
get_stats() {
    echo 'Here are the basic statistics for your UptimeRobot account:'
    echo ''
    if [ "${jq}" = 'true' ]; then
        curl -s -X POST "${apiUrl}"getAccountDetails -d "api_key=${apiKey}" -d "format=json" | jq
    elif [ "${jq}" = 'false' ]; then
        curl -s -X POST "${apiUrl}"getAccountDetails -d "api_key=${apiKey}" -d "format=json"
    fi
    echo ''
}

# Display all stats for single specified monitor
get_info() {
    echo "${infoType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors
    convert_friendly_monitors
    if [ "${providerName}" = 'uptimerobot' ]; then
        if [ "${jq}" = 'true' ]; then
            curl -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "monitors=$(sed 's/\x1B\[[0-9;]*[JKmsu]//g' ${convertedMonitorsFile})" -d "format=json" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "monitors=$(sed 's/\x1B\[[0-9;]*[JKmsu]//g' ${convertedMonitorsFile})" -d "format=json"
        fi
    elif [ "${providerName}" = 'statuscake' ]; then
        if [ "${jq}" = 'true' ]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}Tests/Details/?TestID=${monitor}" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}Tests/Details/?TestID=${monitor}"
        fi
    elif [ "${providerName}" = 'healthchecks' ]; then
        if [ "${jq}" = 'true' ]; then
            curl -s "${apiUrl}"checks/ -X GET -H "X-Api-Key: ${apiKey}" | jq --arg monitor $monitor '.checks[] | select(.ping_url | contains($monitor))'
        elif [ "${jq}" = 'false' ]; then
            curl -s "${apiUrl}checks/${monitor}" -X POST -H "X-Api-Key: ${apiKey}"
        fi
    fi
    echo ''
}

# Display all alert contacts
get_alert_contacts() {
    if [ "${providerName}" = 'uptimerobot' ]; then
        echo 'The following alert contacts have been found for your UptimeRobot account:'
        echo ''
        if [ "${jq}" = 'true' ]; then
            curl -s -X POST "${apiUrl}"getAlertContacts -d "api_key=${apiKey}" -d "format=json" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -X POST "${apiUrl}"getAlertContacts -d "api_key=${apiKey}" -d "format=json"
        fi
    elif [ "${providerName}" = 'statuscake' ]; then
        echo 'The following alert contacts have been found for your StatusCake account:'
        echo ''
        if [ "${jq}" = 'true' ]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}ContactGroups" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -X GET "${apiUrl}ContactGroups"
        fi
    elif [ "${providerName}" = 'healthchecks' ]; then
        if [ "${jq}" = 'true' ]; then
            curl -s -X GET "${apiUrl}"channels/ -H "X-Api-Key: ${apiKey}" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -X GET "${apiUrl}"channels/ -H "X-Api-Key: ${apiKey}"
        fi
    fi
    echo ''
}

# Reset monitors prompt
reset_prompt() {
    echo ''
    echo -e "${red}***WARNING*** This will reset ALL data for the specified monitors!!!${endColor}"
    echo -e "Are you sure you wish to continue? (${grn}[Y]${endColor}es or ${red}[N]${endColor}o): "
    read -r resetPrompt
    echo ''
    if ! [[ $resetPrompt =~ ^(yes|y|no|n)$ ]]; then
        echo -e "${red}Please specify yes, y, no, or n.${endColor}"
        read -r resetPrompt
    else
        :
    fi
}

# Reset all monitors
reset_all_monitors() {
    reset_prompt
    while IFS= read -r monitor; do
        grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
        friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
        echo "Resetting ${friendlyName}:"
        if [ "${jq}" = 'true' ]; then
            curl -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}"
        fi
        echo ''
    done < <(cat "${monitorsFile}")
}

# Reset specified monitors
reset_specified_monitors() {
    echo "${resetType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors
    if [[ ${invalidPrompt} == @(No|no|N|n) ]]; then
        exit 0
    else
        convert_friendly_monitors
    fi
    #reset_prompt
    while IFS= read -r monitor; do
        grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
        friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
        echo "Resetting ${friendlyName}:"
        if [ "${jq}" = 'true' ]; then
            curl -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}" | jq
        elif [ "${jq}" = 'false' ]; then
            curl -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}"
        fi
        echo ''
    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Delete monitors prompt
delete_prompt() {
    echo ''
    if [ "${deleteType}" = 'all' ]; then
        echo -e "${red}***WARNING*** This will delete ALL monitors in your account!!!${endColor}"
    elif [ "${deleteType}" != 'all' ]; then
        echo -e "${red}***WARNING*** This will delete the specified monitor from your account!!!${endColor}"
    fi
    echo -e "Are you sure you wish to continue? (${grn}[Y]${endColor}es or ${red}[N]${endColor}o): "
    read -r deletePrompt
    echo ''
    if ! [[ $deletePrompt =~ ^(Yes|yes|Y|y|No|no|N|n)$ ]]; then
        echo -e "${red}Please specify yes, y, no, or n.${endColor}"
    else
        :
    fi
}

# Delete all monitors
delete_all_monitors() {
    delete_prompt
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Deleting ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}"
            fi
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep Website "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Deleting ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -X DELETE "${apiUrl}Tests/Details/?TestID=${monitor}" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -X DELETE "${apiUrl}Tests/Details/?TestID=${monitor}"
            fi
        elif [ "${providerName}" = 'healthchecks' ]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
            echo "Deleting ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s "${apiUrl}checks/${monitor}" -X DELETE -H "X-Api-Key: ${apiKey}" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s "${apiUrl}checks/${monitor}" -X DELETE -H "X-Api-Key: ${apiKey}"
            fi
        fi
        echo ''
    done < <(cat "${monitorsFile}")
}

# Delete specified monitors
delete_specified_monitors() {
    echo "${deleteType}" | tr , '\n' | tr -d '"' > "${specifiedMonitorsFile}"
    check_bad_monitors
    if [[ ${invalidPrompt} == @(No|no|N|n) ]]; then
        exit 0
    else
        convert_friendly_monitors
    fi
    #delete_prompt
    while IFS= read -r monitor; do
        if [ "${providerName}" = 'uptimerobot' ]; then
            grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Deleting ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}"
            fi
        elif [ "${providerName}" = 'statuscake' ]; then
            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
            friendlyName=$(grep Website "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
            echo "Deleting ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -X DELETE "${apiUrl}Tests/Details/?TestID=${monitor}" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -X DELETE "${apiUrl}Tests/Details/?TestID=${monitor}"
            fi
        elif [ "${providerName}" = 'healthchecks' ]; then
            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
            echo "Deleting ${friendlyName}:"
            if [ "${jq}" = 'true' ]; then
                curl -s "${apiUrl}checks/${monitor}" -X DELETE -H "X-Api-Key: ${apiKey}" | jq
            elif [ "${jq}" = 'false' ]; then
                curl -s "${apiUrl}checks/${monitor}" -X DELETE -H "X-Api-Key: ${apiKey}"
            fi
        fi
        echo ''
    done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Run functions
main() {
    cmdline "${args[@]:-}"
    create_dir
    convert_provider_name
    checks
    if [ "${list}" = 'true' ]; then
        get_data
        get_monitors
        create_monitor_files
        create_friendly_list
        display_all_monitors
    elif [ "${find}" = 'true' ]; then
        get_data
        get_monitors
        create_monitor_files
        get_paused_monitors
        display_paused_monitors
        if [ -s "${pausedMonitorsFile}" ]; then
            if [ "${prompt}" = 'false' ]; then
                :
            else
                unpause_prompt
                if [[ $unpausePrompt =~ ^(Yes|yes|Y|y)$ ]]; then
                    while IFS= read -r monitor; do
                        if [ "${providerName}" = 'uptimerobot' ]; then
                            friendlyName=$(grep "${monitor}" "${pausedMonitorsFile}" | awk '{print $1}')
                            echo "Unpausing ${friendlyName}:"
                            if [ "${jq}" = 'true' ]; then
                                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" | jq
                            elif [ "${jq}" = 'false' ]; then
                                curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1"
                            fi
                        elif [ "${providerName}" = 'statuscake' ]; then
                            grep -Po '"TestID":[!0-9]*|"WebsiteName":["^][^"]*"|"Status":["^][^"]*"|"Paused":[!a-z]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
                            friendlyName=$(grep Website "${tempDir}${monitor}"_short.txt | awk -F':' '{print $2}' | tr -d '"')
                            echo "Pausing ${friendlyName}:"
                            if [ "${jq}" = 'true' ]; then
                                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update" | jq
                            elif [ "${jq}" = 'false' ]; then
                                curl -s -H "API: ${apiKey}" -H "Username: ${scUsername}" -d "TestID=${monitor}" -d "Paused=0" -X PUT "${apiUrl}Tests/Update"
                            fi
                        elif [ "${providerName}" = 'healthchecks' ]; then
                            cp "${tempDir}${monitor}".txt "${tempDir}${monitor}"_short.txt
                            friendlyName=$(jq .name "${tempDir}${monitor}"_short.txt | tr -d '"')
                            pingURL=$(jq .ping_url "${tempDir}${monitor}"_short.txt | tr -d '"')
                            echo "Unpausing ${friendlyName} by sending a ping:"
                            pingResponse=$(curl -fsS --retry 3 "${pingURL}")
                            if [ "${pingResponse}" = 'OK' ]; then
                                echo -e "${grn}Success!${endColor}"
                            else
                                echo -e "${red}Unable to unpause ${friendlyName}!${endColor}"
                            fi
                        fi
                        echo ''
                    done < <(awk -F: '{print $2}' "${pausedMonitorsFile}" | sed 's/\x1B\[[0-9;]*[JKmsu]//g' | tr -d ' ')
                elif [[ $unpausePrompt =~ ^(No|no|N|n)$ ]]; then
                    exit 0
                fi
            fi
        else
            :
        fi
        if [ "${webhook}" = 'true' ]; then
            send_notification
        fi
    elif [ "${pause}" = 'true' ]; then
        if [ "${pauseType}" = 'all' ]; then
            get_data
            get_monitors
            create_monitor_files
            pause_all_monitors
        elif [ "${pauseType}" != 'all' ]; then
            get_data
            get_monitors
            create_monitor_files
            create_friendly_list
            pause_specified_monitors
        fi
    elif [ "${unpause}" = 'true' ]; then
        if [ "${unpauseType}" = 'all' ]; then
            get_data
            get_monitors
            create_monitor_files
            unpause_all_monitors
        elif [ "${unpauseType}" != 'all' ]; then
            get_data
            get_monitors
            create_monitor_files
            create_friendly_list
            unpause_specified_monitors
        fi
    elif [ "${reset}" = 'true' ]; then
        if [[ ${providerName} == 'statuscake' ]] || [[ ${providerName} == 'healthchecks' ]]; then
            echo -e "${red}Sorry, but that option is not valid for your specified provider!${endColor}"
            exit 0
        else
            :
        fi
        if [ "${resetType}" = 'all' ]; then
            get_data
            get_monitors
            create_monitor_files
            reset_all_monitors
        elif [ "${resetType}" != 'all' ]; then
            get_data
            get_monitors
            create_monitor_files
            create_friendly_list
            reset_specified_monitors
        fi
    elif [ "${delete}" = 'true' ]; then
        if [ "${deleteType}" = 'all' ]; then
            get_data
            get_monitors
            create_monitor_files
            delete_all_monitors
        elif [ "${deleteType}" != 'all' ]; then
            get_data
            get_monitors
            create_monitor_files
            create_friendly_list
            delete_specified_monitors
        fi
    elif [ "${stats}" = 'true' ]; then
        if [[ ${providerName} == 'statuscake' ]] || [[ ${providerName} == 'healthchecks' ]]; then
            echo -e "${red}Sorry, but that option is not valid for your specified provider!${endColor}"
            exit 0
        else
            get_stats
        fi
    elif [ "${create}" = 'true' ]; then
        create_monitor
    elif [ "${alerts}" = 'true' ]; then
        get_alert_contacts
    elif [ "${info}" = 'true' ]; then
        get_data
        get_monitors
        create_monitor_files
        create_friendly_list
        get_info
    fi
}

main
