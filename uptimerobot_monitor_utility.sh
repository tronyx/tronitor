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
    Usage: $(basename "$0") -[OPTION] (ARGUMENT)...

    -l          List all UptimeRobot monitors.
    -f          Find all paused UptimeRobot monitors.
    -n          Find all paused UptimeRobot monitors
                without an unpause prompt.
    -a          Find all paused UptimeRobot monitors
                without an unpause prompt and send
                an alert via Discord webhook.
    -p VALUE    Pause specified UptimeRobot monitors.
                Option accepts arguments in the form of "all"
                or a comma-separated list of monitors, IE:
                "$(basename "$0") -p all"
                "$(basename "$0") -p 18095687,18095688,18095689"
    -u VALUE    Unpause specified UptimeRobot monitors.
                Option accepts arguments in the form of "all"
                or a comma-separated list of monitors, IE:
                "$(basename "$0") -u all"
                "$(basename "$0") -u 18095687,18095688,18095689"
    -h          Display this usage dialog.

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

# Some basic checks
# An option is provided
if [ -z "${1}" ]; then
  usage
  exit 1
# No more than one option is provided
elif [ "${#1}" -ge "3" ]; then
  echo "You can only use one option at a time!"
  echo ""
  usage
  exit 1
# API key exists and, if not, user is prompted to enter one
elif [ "${apiKey}" = "" ]; then
  echo "You didn't define your API key in the script!"
  read -rp "Enter your API key: " API
  sed -i "7 s/apiKey='[^']*'/apiKey='${API}'/" $0
  apiKey=${API}
# Alert set to true, but webhook not defined
elif [ "${webhookUrl}" = "" ] && [ "${alert}" = "true" ]; then
  echo "You didn't define your Discord webhook URL!"
  exit 1
else
  :
fi

# Create directory to neatly store temp files
create_dir() {
  mkdir -p /tmp/uptimerobot_monitor_utility
}

# Cleanup temp files
cleanup() {
  rm -rf /tmp/uptimerobot_monitor_utility/*.txt
}
trap cleanup ERR EXIT INT QUIT TERM

# Check that provided API Key is valid
check_api_key() {
  curl -s -X POST https://api.uptimerobot.com/v2/getAccountDetails -d "api_key=${apiKey}" -d "format=json" > /tmp/uptimerobot_monitor_utility/api_test_full.txt
  status=$(egrep -oi '"stat":"[a-z]*"' /tmp/uptimerobot_monitor_utility/api_test_full.txt |awk -F':' '{print $2}' |tr -d '"')
  if [ "${status}" = "fail" ]; then
    echo "The API Key that you provided is not valid!"
    exit 1
  elif [ "${status}" = "ok" ]; then
    :
  fi
}

# Grab data for all monitors
get_data() {
  curl -s -X POST https://api.uptimerobot.com/v2/getMonitors -d "api_key=${apiKey}" -d "format=json" > /tmp/uptimerobot_monitor_utility/ur_monitors_full.txt
}

# Create list of monitor IDs
get_monitors() {
  egrep -oi '"id":[!0-9]*' /tmp/uptimerobot_monitor_utility/ur_monitors_full.txt |tr -d '"id:' > /tmp/uptimerobot_monitor_utility/ur_monitors.txt
}

# Create individual monitor files
create_monitor_files() {
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/ur_monitors.txt); do curl -s -X POST https://api.uptimerobot.com/v2/getMonitors -d "api_key=${apiKey}" -d "monitors=${monitor}" -d "format=json" > /tmp/uptimerobot_monitor_utility/"${monitor}".txt; done
}

# Create friendly output of all monitors
create_friendly_list() {
  > /tmp/uptimerobot_monitor_utility/friendly_list.txt
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/ur_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/uptimerobot_monitor_utility/"${monitor}".txt > /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    status=$(grep status /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    if [ "${status}" = 0 ]; then
      friendlyStatus="Paused"
    elif [ "${status}" = 1 ]; then
      friendlyStatus="Not checked yet"
    elif [ "${status}" = 2 ]; then
      friendlyStatus="Up"
    elif [ "${status}" = 8 ]; then
      friendlyStatus="Seems down"
    elif [ "${status}" = 9 ]; then
      friendlyStatus="Down"
    fi
    echo "${friendlyName} (ID: ${monitor}) - Status: ${friendlyStatus}" >> /tmp/uptimerobot_monitor_utility/friendly_list.txt
  done
}

# Display friendly list of all monitors
display_all_monitors() {
  if [ -s /tmp/uptimerobot_monitor_utility/friendly_list.txt ]; then
    echo "The following UptimeRobot monitors were found in your UptimeRobot account:"
    cat /tmp/uptimerobot_monitor_utility/friendly_list.txt
  else
    echo "There are currently no monitors associated with your UptimeRobot account."
  fi
}

# Find all paused monitors
get_paused_monitors() {
  > /tmp/uptimerobot_monitor_utility/paused_monitors.txt
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/ur_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/uptimerobot_monitor_utility/"${monitor}".txt > /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    status=$(grep status /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    if [ "${status}" = '0' ]; then
      echo "${friendlyName} (ID: ${monitor})" >> /tmp/uptimerobot_monitor_utility/paused_monitors.txt
    else
      :
    fi
  done
}

# Display list of all paused monitors
display_paused_monitors() {
  if [ -s /tmp/uptimerobot_monitor_utility/paused_monitors.txt ]; then
    echo "The following UptimeRobot monitors are currently paused:"
    cat /tmp/uptimerobot_monitor_utility/paused_monitors.txt
  else
    echo "There are currently no paused UptimeRobot monitors."
  fi
}

# Prompt user to unpause monitors after finding paused monitors
unpause_prompt() {
  read -p 'Would you like to unpause the paused monitors? ([y]es or [n]o): ' unpausePrompt
  if ! [[ "$unpausePrompt" =~ ^(yes|y|no|n)$  ]]; then
    echo "Please specify yes, y, no, or n."
  else
    :
  fi
}

# Pause all monitors
pause_all_monitors() {
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/ur_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/uptimerobot_monitor_utility/"${monitor}".txt > /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Pausing ${friendlyName}:"
    curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" |jq
    echo ""
  done
}

# Pause specified monitors
pause_specified_monitors() {
  > /tmp/uptimerobot_monitor_utility/converted_monitors.txt
  echo "${pauseType}" |tr , '\n' |tr -d '"' > /tmp/uptimerobot_monitor_utility/specified_monitors.txt
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/specified_monitors.txt); do
    if [[ "${monitor}" =~ ^[A-Za-z_]+$ ]]; then
      echo $(egrep -i "${monitor}" /tmp/uptimerobot_monitor_utility/friendly_list.txt |awk -F ':' '{print $2}' |awk -F ' ' '{print $1}' |tr -d ')') >> /tmp/uptimerobot_monitor_utility/converted_monitors.txt
    else
      echo "${monitor}" >> /tmp/uptimerobot_monitor_utility/converted_monitors.txt
    fi
  done
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/converted_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/uptimerobot_monitor_utility/"${monitor}".txt > /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Pausing ${friendlyName}:"
    curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" |jq
    echo ""
  done
}

# Unpause all monitors
unpause_all_monitors() {
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/ur_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/uptimerobot_monitor_utility/"${monitor}".txt > /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Unpausing ${friendlyName}:"
    curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
    echo ""
  done
}

# Unpause specified monitors
unpause_specified_monitors() {
  > /tmp/uptimerobot_monitor_utility/converted_monitors.txt
  echo "${unpauseType}" |tr , '\n' |tr -d '"' > /tmp/uptimerobot_monitor_utility/specified_monitors.txt
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/specified_monitors.txt); do
    if [[ "${monitor}" =~ ^[A-Za-z_]+$ ]]; then
      echo $(egrep -i "${monitor}" /tmp/uptimerobot_monitor_utility/friendly_list.txt |awk -F ':' '{print $2}' |awk -F ' ' '{print $1}' |tr -d ')') >> /tmp/uptimerobot_monitor_utility/converted_monitors.txt
    else
      echo "${monitor}" >> /tmp/uptimerobot_monitor_utility/converted_monitors.txt
    fi
  done
  for monitor in $(cat /tmp/uptimerobot_monitor_utility/converted_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/uptimerobot_monitor_utility/"${monitor}".txt > /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/uptimerobot_monitor_utility/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Unpausing ${friendlyName}:"
    curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
    echo ""
  done
}

# Send Discord notification
send_notification() {
  if [ "${webhookUrl}" = "" ]; then
    echo "You didn't define your Discord webhook, skipping notification."
  else
    if [ -s /tmp/uptimerobot_monitor_utility/paused_monitors.txt ]; then
      pausedTests=$(paste -s -d, /tmp/uptimerobot_monitor_utility/paused_monitors.txt)
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
  if [ "${list}" = "true" ]; then
    get_data
    get_monitors
    create_monitor_files
    create_friendly_list
    display_all_monitors
  elif [ "${find}" = "true" ]; then
    get_data
    get_monitors
    create_monitor_files
    get_paused_monitors
    display_paused_monitors
    if [ -s /tmp/uptimerobot_monitor_utility/paused_monitors.txt ]; then
      if [ "${prompt}" = "false" ]; then
        :
      else
        unpause_prompt
          if [[ "$unpausePrompt" =~ ^(yes|y)$ ]]; then
            for monitor in $(cat /tmp/uptimerobot_monitor_utility/paused_monitors.txt |awk -F: '{print $2}' |tr -d ')' |tr -d ' '); do
              friendlyName=$(grep "${monitor}" /tmp/uptimerobot_monitor_utility/paused_monitors.txt |awk '{print $1}')
              echo "Unpausing ${friendlyName}:"
              curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
              echo ""
            done
          elif [[ "$unpausePrompt" =~ ^(no|n)$ ]]; then
            exit 1
          fi
      fi
    else
      :
    fi
    if [ "${alert}" = "true" ]; then
      send_notification
    fi
  elif [ "${pause}" = "true" ]; then
    if [ "${pauseType}" = "all" ]; then
      get_data
      get_monitors
      create_monitor_files
      pause_all_monitors
    elif [ "${pauseType}" != "all" ]; then
      get_data
      get_monitors
      create_monitor_files
      create_friendly_list
      pause_specified_monitors
    fi
  elif [ "${unpause}" = "true" ]; then
    if [ "${unpauseType}" = "all" ]; then
      get_data
      get_monitors
      create_monitor_files
      unpause_all_monitors
    elif [ "${unpauseType}" != "all" ]; then
      get_data
      get_monitors
      create_monitor_files
      create_friendly_list
      unpause_specified_monitors
    fi
  fi
}

main
