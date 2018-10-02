#!/usr/bin/env bash
#
# Script to utilize the UptimeRobot API to retrieve and work with monitors.
# Tronyx
set -eo pipefail
IFS=$'\n\t'

# Specify UptimeRobot API key
apiKey=''
webhookUrl=''
# Set notifyAll to true for notification to apply for all running state as well
notifyAll='false'

# Declare some variables
# Temp dir and filenames
tempDir='/tmp/uptimerobot_monitor_utility/'
apiTestFullFile="${tempDir}api_test_full.txt"
badMonitorsFile="${tempDir}bad_monitors.txt"
convertedMonitorsFile="${tempDir}converted_monitors.txt"
friendlyListFile="${tempDir}friendly_list.txt"
pausedMonitorsFile="${tempDir}paused_monitors.txt"
specifiedMonitorsFile="${tempDir}specified_monitors.txt"
urMonitorsFile="${tempDir}ur_monitors.txt"
urMonitorsFullFile="${tempDir}ur_monitors_full.txt"
validMonitorsFile="${tempDir}valid_monitors.txt"
validMonitorsTempFile="${tempDir}valid_monitors_temp.txt"
# Set initial API key status
apiKeyStatus='invalid'
#logFile="${tempDir}uptimerobot_monitor_utility.log"
# Arguments
readonly args=("$@")
# UptimeRobot API URL
readonly apiUrl='https://api.uptimerobot.com/v2/'
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
# Log functions
info()    { echo -e "$(date +"%F %T") ${blu}[INFO]${endColor}       $*" | tee -a "${LOG_FILE}" >&2 ; }
warning() { echo -e "$(date +"%F %T") ${ylw}[WARNING]${endColor}    $*" | tee -a "${LOG_FILE}" >&2 ; }
error()   { echo -e "$(date +"%F %T") ${org}[ERROR]${endColor}      $*" | tee -a "${LOG_FILE}" >&2 ; }
fatal()   { echo -e "$(date +"%F %T") ${red}[FATAL]${endColor}      $*" | tee -a "${LOG_FILE}" >&2 ; exit 1 ; }

# Define usage and script options
usage() {
  cat <<- EOF

  Usage: $(echo -e "${lorg}$0${endColor}") $(echo -e "${grn}"-[OPTION]"${endColor}") $(echo -e "${ylw}"\(ARGUMENT\)"${endColor}"...)

  $(echo -e "${grn}"-l/--list"${endColor}")             List all UptimeRobot monitors.
  $(echo -e "${grn}"-f/--find"${endColor}")             Find all paused UptimeRobot monitors.
  $(echo -e "${grn}"-n/--no-prompt"${endColor}")        Find all paused UptimeRobot monitors without an unpause prompt.
  $(echo -e "${grn}"-a/--alert"${endColor}")            Find all paused UptimeRobot monitors without an unpause prompt and
                        send an alert to the Discord webhook specified in the script.
  $(echo -e "${grn}"-p/--pause"${endColor}" "${ylw}"VALUE"${endColor}")      Pause specified UptimeRobot monitors.
                        Option accepts arguments in the form of "$(echo -e "${ylw}"all"${endColor}")" or a comma-separated list
                        of monitors by ID or Friendly Name. Friendly Name should be wrapped in
                        a set of single or double quotes, IE:
                          A) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-p"${endColor}" "${ylw}"all"${endColor}")"
                          B) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"--pause"${endColor}" "${ylw}"18095687,18095688,18095689"${endColor}")"
                          C) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-p"${endColor}" "${ylw}"\'Plex\',\"Tautulli\",18095689"${endColor}")"
  $(echo -e "${grn}"-u/--unpause"${endColor}" "${ylw}"VALUE"${endColor}")    Unpause specified UptimeRobot monitors.
                        Option accepts arguments in the form of "$(echo -e "${ylw}"all"${endColor}")" or a comma-separated list
                        of monitors by ID or Friendly Name. Friendly Name should be wrapped in
                        a set of single or double quotes, IE:
                          A) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-u"${endColor}" "${ylw}"all"${endColor}")"
                          B) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"--unpause"${endColor}" "${ylw}"18095687,18095688,18095689"${endColor}")"
                          C) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-u"${endColor}" "${ylw}"\'Plex\',\"Tautulli\",18095689"${endColor}")"
  $(echo -e "${grn}"-c/--create"${endColor}" "${ylw}"VALUE"${endColor}")     Create a new monitor using the specified config file, IE:
                          A) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-c"${endColor}" "${ylw}"new-monitor.txt"${endColor}")"
                          B) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"--create"${endColor}" "${ylw}"new-monitor.txt"${endColor}")"
  $(echo -e "${grn}"-d/--delete"${endColor}" "${ylw}"VALUE"${endColor}")     Delete the specified monitor, IE:
                          A) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-d"${endColor}" "${ylw}"\'Plex\'"${endColor}")"
                          B) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"--delete"${endColor}" "${ylw}"\"Tautulli\""${endColor}")"
                          C) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-d"${endColor}" "${ylw}"18095688"${endColor}")"
  $(echo -e "${grn}"-r/--reset"${endColor}" "${ylw}"VALUE"${endColor}")      Reset the specified monitor, IE:
                          A) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-r"${endColor}" "${ylw}"\'Plex\'"${endColor}")"
                          B) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"--reset"${endColor}" "${ylw}"\"Tautulli\""${endColor}")"
                          C) "$(echo -e "${lorg}"./uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-r"${endColor}" "${ylw}"18095688"${endColor}")"
  $(echo -e "${grn}"-h/--help"${endColor}")             Display this usage dialog.

EOF

}

# Define script options
cmdline() {
  local arg=
  local local_args
  local OPTERR=0
  for arg
  do
    local delim=""
    case "${arg}" in
      # Translate --gnu-long-options to -g (short options)
      --list)       local_args="${local_args}-l " ;;
      --find)       local_args="${local_args}-f " ;;
      --no-prompt)  local_args="${local_args}-n " ;;
      --alert)      local_args="${local_args}-a " ;;
      --pause)      local_args="${local_args}-p " ;;
      --unpause)    local_args="${local_args}-u " ;;
      --reset)      local_args="${local_args}-r " ;;
      --delete)      local_args="${local_args}-d " ;;
      --help)       local_args="${local_args}-h " ;;
      # Pass through anything else
      *) [[ "${arg:0:1}" == "-" ]] || delim="\""
        local_args="${local_args:-}${delim}${arg}${delim} " ;;
    esac
  done

  # Reset the positional parameters to the short options
  eval set -- "${local_args:-}"

  while getopts "hlfnar:d:p:u:" OPTION
    do
    case "$OPTION" in
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
      a)
        find=true
        prompt=false
        alert=true
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
        if [[ "${arg}" == "-p" || "${arg}" == "-u" || "${arg}" == "-r" || "${arg}" == "-d" ]] && [[ -z "${OPTARG}" ]]; then
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

# Some basic checks
checks() {
# An option is provided
for arg in "${args[@]:-}"
do
  if [ -z "${arg}" ]; then
    usage
    exit
  fi
done
# Alert set to true, but webhook not defined
if [ "${webhookUrl}" = "" ] && [ "${alert}" = "true" ]; then
  echo -e "${red}You didn't define your Discord webhook URL!${endColor}"
  read -rp 'Enter your webhook URL: ' webhook
  sed -i "10 s/webhookUrl='[^']*'/webhookUrl='${API}'/" "$0"
  webhookUrl="${webhook}"
else
  :
fi
}

# Create directory to neatly store temp files
create_dir() {
  mkdir -p "${tempDir}"
  chmod 777 "${tempDir}"
}

# Cleanup temp files
cleanup() {
  rm -rf "${tempDir}"*.txt
}
trap 'cleanup' 0 1 2 3 6 14 15

# Check that provided API Key is valid
check_api_key() {
while [ "${apiKeyStatus}" = 'invalid' ]; do
  if [[ -z "${apiKey}" ]]; then
    echo -e "${red}You didn't define your API key in the script!${endColor}"
    read -rp 'Enter your API key: ' API
    sed -i "9 s/apiKey='[^']*'/apiKey='${API}'/" "$0"
    apiKey="${API}"
  else
    curl -s -X POST "${apiUrl}"getAccountDetails -d "api_key=${apiKey}" -d "format=json" > "${apiTestFullFile}"
    status=$(grep -Po '"stat":"[a-z]*"' "${apiTestFullFile}" |awk -F':' '{print $2}' |tr -d '"')
    if [ "${status}" = "fail" ]; then
      echo -e "${red}The API Key that you provided is not valid!${endColor}"
      sed -i "9 s/apiKey='[^']*'/apiKey=''/" "$0"
      apiKey=""
    elif [ "${status}" = "ok" ]; then
      sed -i "9 s/apiKeyStatus='[^']*'/apiKeyStatus='${status}'/" "$0"
      apiKeyStatus="${status}"
    fi
  fi
done
}

# Grab data for all monitors
get_data() {
  curl -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "format=json" > "${urMonitorsFullFile}"
}

# Create list of monitor IDs
get_monitors() {
  grep -Po '"id":[!0-9]*' "${urMonitorsFullFile}" |tr -d '"id:' > "${urMonitorsFile}"
}

# Create individual monitor files
create_monitor_files() {
  while IFS= read -r monitor; do
    curl -s -X POST "${apiUrl}"getMonitors -d "api_key=${apiKey}" -d "monitors=${monitor}" -d "format=json" > "${tempDir}${monitor}".txt
  done < <(cat "${urMonitorsFile}")
}

# Create friendly output of all monitors
create_friendly_list() {
  true > "${friendlyListFile}"
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    status=$(grep status "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    if [ "${status}" = 0 ]; then
      friendlyStatus="${ylw}Paused${endColor}"
    elif [ "${status}" = 1 ]; then
      friendlyStatus="${mgt}Not checked yet${endColor}"
    elif [ "${status}" = 2 ]; then
      friendlyStatus="${grn}Up${endColor}"
    elif [ "${status}" = 8 ]; then
      friendlyStatus="${org}Seems down${endColor}"
    elif [ "${status}" = 9 ]; then
      friendlyStatus="${red}Down${endColor}"
    fi
    echo -e "${lorg}${friendlyName}${endColor} - ID: ${lblu}${monitor}${endColor} - Status: ${friendlyStatus}" >> "${friendlyListFile}"
  done < <(cat "${urMonitorsFile}")
}

# Display friendly list of all monitors
display_all_monitors() {
  if [ -s "${friendlyListFile}" ]; then
    echo 'The following UptimeRobot monitors were found in your UptimeRobot account:'
    echo ''
    column -ts- "${friendlyListFile}"
  else
    echo 'There are currently no monitors associated with your UptimeRobot account.'
  fi
}

# Find all paused monitors
get_paused_monitors() {
  true > "${pausedMonitorsFile}"
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    status=$(grep status "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    if [ "${status}" = '0' ]; then
      echo -e "${lorg}${friendlyName}${endColor} - ID: ${lblu}${monitor}${endColor}" >> "${pausedMonitorsFile}"
    else
      :
    fi
  done < <(cat "${urMonitorsFile}")
}

# Display list of all paused monitors
display_paused_monitors() {
  if [ -s "${pausedMonitorsFile}" ]; then
    echo 'The following UptimeRobot monitors are currently paused:'
    echo ''
    column -ts- "${pausedMonitorsFile}"
  else
    echo 'There are currently no paused UptimeRobot monitors.'
    echo ''
  fi
}

# Prompt user to unpause monitors after finding paused monitors
unpause_prompt() {
  echo ''
  echo -e "Would you like to unpause the paused monitors? (${grn}[Y]${endColor}es or ${red}[N]${endColor}o): "
  read -r unpausePrompt
  if ! [[ "$unpausePrompt" =~ ^(yes|y|no|n)$  ]]; then
    echo -e "${red}Please specify yes, y, no, or n.${endColor}"
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
  if ! [[ "$invalidPrompt" =~ ^(yes|y|no|n)$  ]]; then
    echo -e "${red}Please specify yes, y, no, or n.${endColor}"
  else
    :
  fi
}

# Check for bad monitors
check_bad_monitors() {
  true > "${badMonitorsFile}"
  while IFS= read -r monitor; do
    if [[ $(grep -ic "${monitor}" "${friendlyListFile}") != "1" ]]; then
      if [[ "${monitor}" =~ ^[A-Za-z]+$ ]]; then
        echo -e "${lorg}${monitor}${endColor}" >> "${badMonitorsFile}"
      elif [[ "${monitor}" != ^[A-Za-z]+$ ]]; then
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
      set -e
      while IFS= read -r monitor; do
        echo -e "${grn}${monitor}${endColor}" >> "${validMonitorsFile}"
      done < <(cat "${validMonitorsTempFile}")
      echo ''
      invalid_prompt
    elif [ ! -s "${validMonitorsTempFile}" ]; then
      echo ''
      echo "Please make sure you're specifying a valid monitor ane try again."
      exit
    fi
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
  while IFS= read -r monitor; do
    if [[ $(echo "${monitor}" |tr -d ' ') =~ [A-Za-z] ]]; then
      grep -Pi "${monitor}" "${friendlyListFile}" |awk -F ':' '{print $2}' |awk -F ' ' '{print $1}' >> "${convertedMonitorsFile}"
    else
      echo "${monitor}" >> "${convertedMonitorsFile}"
    fi
  done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${specifiedMonitorsFile}")
}

# Pause all monitors
pause_all_monitors() {
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Pausing ${friendlyName}:"
    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" |jq
    echo ''
  done < <(cat "${urMonitorsFile}")
}

# Pause specified monitors
pause_specified_monitors() {
  echo "${pauseType}" |tr , '\n' |tr -d '"' > "${specifiedMonitorsFile}"
  check_bad_monitors
  if [[ "${invalidPrompt}" = @(n|no) ]]; then
    exit
  else
    convert_friendly_monitors
  fi
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Pausing ${friendlyName}:"
    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" |jq
    echo ''
  done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Unpause all monitors
unpause_all_monitors() {
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Unpausing ${friendlyName}:"
    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
    echo ''
  done < <(cat "${urMonitorsFile}")
}

# Unpause specified monitors
unpause_specified_monitors() {
  echo "${unpauseType}" |tr , '\n' |tr -d '"' > "${specifiedMonitorsFile}"
  check_bad_monitors
  if [[ "${invalidPrompt}" = @(n|no) ]]; then
    exit
  else
    convert_friendly_monitors
  fi
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Unpausing ${friendlyName}:"
    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
    echo ''
  done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Send Discord notification
send_notification() {
  if [ "${webhookUrl}" = "" ]; then
    echo -e "${org}You didn't define your Discord webhook, skipping notification.${endColor}"
  else
    if [ -s "${pausedMonitorsFile}" ]; then
      pausedTests=$(paste -s -d, "${pausedMonitorsFile}")
      curl -s -H "Content-Type: application/json" -X POST -d '{"content": "There are currently paused UptimeRobot monitors:\n\n'"${pausedTests}"'"}' ${webhookUrl}
    elif [ "${notifyAll}" = "true" ]; then
      curl -s -H "Content-Type: application/json" -X POST -d '{"content": "All UptimeRobot monitors are currently running."}' ${webhookUrl}
    fi
  fi
}

# Reset monitors prompt
reset_prompt() {
  echo ''
  echo -e "${red}***WARNING*** This will reset ALL data for the specified monitors!!!${endColor}"
  echo -e "Are you sure you wish to continue? (${grn}[Y]${endColor}es or ${red}[N]${endColor}o): "
  read -r resetPrompt
  if ! [[ "$resetPrompt" =~ ^(yes|y|no|n)$  ]]; then
    echo -e "${red}Please specify yes, y, no, or n.${endColor}"
  else
    :
  fi
}

# Reset all monitors
reset_all_monitors() {
  reset_prompt
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Resetting ${friendlyName}:"
    curl -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}" |jq
    echo ''
  done < <(cat "${urMonitorsFile}")
}

# Reset specified monitors
reset_specified_monitors() {
  echo "${resetType}" |tr , '\n' |tr -d '"' > "${specifiedMonitorsFile}"
  check_bad_monitors
  if [[ "${invalidPrompt}" = @(n|no) ]]; then
    exit
  else
    convert_friendly_monitors
  fi
  reset_prompt
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Resetting ${friendlyName}:"
    curl -s -X POST "${apiUrl}"resetMonitor -d "api_key=${apiKey}" -d "id=${monitor}" |jq
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
  if ! [[ "$deletePrompt" =~ ^(yes|y|no|n)$  ]]; then
    echo -e "${red}Please specify yes, y, no, or n.${endColor}"
  else
    :
  fi
}

# Delete all monitors
delete_all_monitors() {
  delete_prompt
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Deleting ${friendlyName}:"
    curl -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}" |jq
    echo ''
  done < <(cat "${urMonitorsFile}")
}

# Delete specified monitors
delete_specified_monitors() {
  echo "${deleteType}" |tr , '\n' |tr -d '"' > "${specifiedMonitorsFile}"
  check_bad_monitors
  if [[ "${invalidPrompt}" = @(n|no) ]]; then
    exit
  else
    convert_friendly_monitors
  fi
  delete_prompt
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Deleting ${friendlyName}:"
    curl -s -X POST "${apiUrl}"deleteMonitor -d "api_key=${apiKey}" -d "id=${monitor}" |jq
    echo ''
  done < <(sed 's/\x1B\[[0-9;]*[JKmsu]//g' "${convertedMonitorsFile}")
}

# Run functions
main() {
  cmdline "${args[@]:-}"
  checks
  check_api_key
  create_dir
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
          if [[ "$unpausePrompt" =~ ^(yes|y)$ ]]; then
            while IFS= read -r monitor; do
              friendlyName=$(grep "${monitor}" "${pausedMonitorsFile}" |awk '{print $1}')
              echo "Unpausing ${friendlyName}:"
              curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
              echo ''
            done < <(awk -F: '{print $2}' "${pausedMonitorsFile}" |sed 's/\x1B\[[0-9;]*[JKmsu]//g' |tr -d ' ')
          elif [[ "$unpausePrompt" =~ ^(no|n)$ ]]; then
            exit 1
          fi
      fi
    else
      :
    fi
    if [ "${alert}" = 'true' ]; then
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
  fi
}

main
