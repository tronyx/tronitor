#!/usr/bin/env bash
#
# Script to utilize the UptimeRobot API to retrieve and work with monitors.
# Tronyx

# Specify UptimeRobot API key
apiKey=''
webhookUrl=''
# Set notifyAll to true for notification to apply for all running state as well
notifyAll='false'

# Define usage and script options
usage() {
  cat <<EOM

  Usage: $(echo -e "${lorg}$0${endColor}") $(echo -e "${grn}"-[OPTION]"${endColor}") $(echo -e "${ylw}"\(ARGUMENT\)"${endColor}"...)

  $(echo -e "${grn}"-l"${endColor}")          List all UptimeRobot monitors.
  $(echo -e "${grn}"-f"${endColor}")          Find all paused UptimeRobot monitors.
  $(echo -e "${grn}"-n"${endColor}")          Find all paused UptimeRobot monitors without an unpause prompt.
  $(echo -e "${grn}"-a"${endColor}")          Find all paused UptimeRobot monitors without an unpause prompt
              and send an alert via Discord webhook.
  $(echo -e "${grn}"-p"${endColor}" "${ylw}"VALUE"${endColor}")    Pause specified UptimeRobot monitors.
              Option accepts arguments in the form of "$(echo -e "${ylw}"all"${endColor}")" or a comma-separated
              list of monitors by ID or Friendly Name. Friendly Name should be
              wrapped in single or double quotes, IE:
                A) "$(echo -e "${lorg}"uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-p"${endColor}" "${ylw}"all"${endColor}")"
                B) "$(echo -e "${lorg}"uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-p"${endColor}" "${ylw}"18095687,18095688,18095689"${endColor}")"
                C) "$(echo -e "${lorg}"uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-p"${endColor}" "${ylw}"'Plex',"Tautulli",18095689"${endColor}")"
  $(echo -e "${grn}"-u"${endColor}" "${ylw}"VALUE"${endColor}")    Unpause specified UptimeRobot monitors.
              Option accepts arguments in the form of "$(echo -e "${ylw}"all"${endColor}")" or a comma-separated
              list of monitors by ID or Friendly Name. Friendly Name should be
              wrapped in single or double quotes, IE:
                A) "$(echo -e "${lorg}"uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-u"${endColor}" "${ylw}"all"${endColor}")"
                B) "$(echo -e "${lorg}"uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-u"${endColor}" "${ylw}"18095687,18095688,18095689"${endColor}")"
                C) "$(echo -e "${lorg}"uptimerobot_monitor_utility.sh"${endColor}" "${grn}"-u"${endColor}" "${ylw}"'Plex',"Tautulli",18095689"${endColor}")"
  $(echo -e "${grn}"-h"${endColor}")          Display this usage dialog.

EOM

exit 2
}

# Define script options
while getopts "hlfnap:u:" OPTION
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
    p)
      pause=true
      pauseType="${OPTARG}"
      ;;
    u)
      unpause=true
      unpauseType="${OPTARG}"
      ;;
    :)
      echo "Option -${OPTARG} requires an argument."
      exit 1
      ;;
    h|*)
      usage
      ;;
  esac
done

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
logFile="${tempDir}uptimerobot_monitor_utility.log"
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

# Some basic checks
# An option is provided
if [ -z "${1}" ]; then
  usage
  exit 1
# No more than one option is provided
elif [ "${#1}" -ge "3" ]; then
  echo -e "${red}You can only use one option at a time!${endColor}"
  echo ''
  usage
  exit 1
# API key exists and, if not, user is prompted to enter one
elif [ "${apiKey}" = "" ]; then
  echo -e "${red}You didn't define your API key in the script!${endColor}"
  read -rp 'Enter your API key: ' API
  sed -i "7 s/apiKey='[^']*'/apiKey='${API}'/" "$0"
  apiKey="${API}"
# Alert set to true, but webhook not defined
elif [ "${webhookUrl}" = "" ] && [ "${alert}" = "true" ]; then
  echo -e "${red}You didn't define your Discord webhook URL!${endColor}"
  read -rp 'Enter your webhook URL: ' webhook
  sed -i "8 s/webhookUrl='[^']*'/webhookUrl='${API}'/" "$0"
  webhookUrl="${webhook}"
else
  :
fi

# Create directory to neatly store temp files
create_dir() {
  mkdir -m 777 "${tempDir}"
}

# Cleanup temp files
cleanup() {
  rm -rf "${tempDir}"*.txt
}
trap 'cleanup' 0 1 2 3 6 14 15

# Check that provided API Key is valid
check_api_key() {
  curl -s -X POST "${apiUrl}"getAccountDetails -d "api_key=${apiKey}" -d "format=json" > "${apiTestFullFile}"
  status=$(grep -Po '"stat":"[a-z]*"' "${apiTestFullFile}" |awk -F':' '{print $2}' |tr -d '"')
  if [ "${status}" = "fail" ]; then
    echo -e "${red}The API Key that you provided is not valid!${endColor}"
    exit 1
  elif [ "${status}" = "ok" ]; then
    :
  fi
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
    cat "${friendlyListFile}" |column -ts-
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
    cat "${pausedMonitorsFile}" |column -ts-
  else
    echo 'There are currently no paused UptimeRobot monitors.'
  fi
}

# Prompt user to unpause monitors after finding paused monitors
unpause_prompt() {
  echo ''
  echo -e "Would you like to unpause the paused monitors? (${grn}[y]${endColor}es or ${red}[n]${endColor}o): "
  read -r unpausePrompt
  if ! [[ "$unpausePrompt" =~ ^(yes|y|no|n)$  ]]; then
    echo -e "${red}Please specify yes, y, no, or n.${endColor}"
  else
    :
  fi
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
  true > "${convertedMonitorsFile}"
  true > "${badMonitorsFile}"
  echo "${pauseType}" |tr , '\n' |tr -d '"' > "${specifiedMonitorsFile}"
  while IFS= read -r monitor; do
    if [[ $(grep -ic "${monitor}" "${urMonitorsFullFile}") != "1" ]]; then
      if [[ "${monitor}" =~ ^[A-Za-z_]+$ ]]; then
        echo -e "${lorg}${monitor}${endColor}" >> "${badMonitorsFile}"
      elif [[ "${monitor}" != ^[A-Za-z_]+$ ]]; then
        echo -e "${lblu}${monitor}${endColor}" >> "${badMonitorsFile}"
      fi
    else
      :
    fi
  done < <(cat "${specifiedMonitorsFile}" |sed 's/\x1B\[[0-9;]*[JKmsu]//g')
  if [ -s "${badMonitorsFile}" ]; then
    echo -e "${red}The following specified monitors are not valid:${endColor}"
    echo ''
    cat "${badMonitorsFile}"
    echo ''
    echo 'Please correct these and try again.'
    exit 1
  else
    :
  fi
  while IFS= read -r monitor; do
    if [[ "${monitor}" =~ ^[A-Za-z_]+$ ]]; then
      grep -Pi ""${monitor}"" "${friendlyListFile}" |awk -F ':' '{print $2}' |awk -F ' ' '{print $1}' >> "${convertedMonitorsFile}"
    else
      echo "${monitor}" >> "${convertedMonitorsFile}"
    fi
  done < <(cat "${specifiedMonitorsFile}" |sed 's/\x1B\[[0-9;]*[JKmsu]//g')
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Pausing ${friendlyName}:"
    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" |jq
    echo ''
  done < <(cat "${convertedMonitorsFile}" |sed 's/\x1B\[[0-9;]*[JKmsu]//g')
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
  true > "${convertedMonitorsFile}"
  true > "${badMonitorsFile}"
  echo "${unpauseType}" |tr , '\n' |tr -d '"' > "${specifiedMonitorsFile}"
  while IFS= read -r monitor; do
    if [[ $(grep -ic "${monitor}" "${urMonitorsFullFile}") != "1" ]]; then
      if [[ "${monitor}" =~ ^[A-Za-z_]+$ ]]; then
        echo -e "${lorg}${monitor}${endColor}" >> "${badMonitorsFile}"
      elif [[ "${monitor}" != ^[A-Za-z_]+$ ]]; then
        echo -e "${lblu}${monitor}${endColor}" >> "${badMonitorsFile}"
      fi
    else
      :
    fi
  done < <(cat "${specifiedMonitorsFile}" |sed 's/\x1B\[[0-9;]*[JKmsu]//g')
  if [ -s "${badMonitorsFile}" ]; then
    echo -e "${red}The following specified monitors are not valid:${endColor}"
    echo ''
    cat "${badMonitorsFile}"
    echo ''
    echo 'Please correct these and try again.'
    exit 1
  else
    :
  fi
  while IFS= read -r monitor; do
    if [[ "${monitor}" =~ ^[A-Za-z_]+$ ]]; then
      grep -Pi ""${monitor}"" "${friendlyListFile}" |awk -F ':' '{print $2}' |awk -F ' ' '{print $1}' |tr -d ')' >> "${convertedMonitorsFile}"
    else
      echo "${monitor}" >> "${convertedMonitorsFile}"
    fi
  done < <(cat "${specifiedMonitorsFile}" |sed 's/\x1B\[[0-9;]*[JKmsu]//g')
  while IFS= read -r monitor; do
    grep -Po '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' "${tempDir}${monitor}".txt > "${tempDir}${monitor}"_short.txt
    friendlyName=$(grep friend "${tempDir}${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Unpausing ${friendlyName}:"
    curl -s -X POST "${apiUrl}"editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
    echo ''
  done < <(cat "${convertedMonitorsFile}" |sed 's/\x1B\[[0-9;]*[JKmsu]//g')
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

# Run functions
main() {
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
  fi
}

main
