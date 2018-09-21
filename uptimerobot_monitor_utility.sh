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
function usage {
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

while getopts "hlfnap:u:" OPTION
  do
  case "$OPTION" in
    l)
      list=true
      ;;
    f)
      find=true
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

if [[ $1 == "" ]]; then
  usage
  exit 1
elif [ "${apiKey}" = "" ]; then
  echo "You didn't define your API key!"
  exit 1
elif [ "${webhookUrl}" = "" ] && [ "${alert}" = "true" ]; then
  echo "You didn't define your Discord webhook URL!"
  exit 1
else
  :
fi

# Check that provided API Key is valid
function check_api_key {
  curl -s -X POST https://api.uptimerobot.com/v2/getAccountDetails -d "api_key=${apiKey}" -d "format=json" > /tmp/api_test_full.txt
  status=$(egrep -oi '"stat":"[a-z]*"' /tmp/api_test_full.txt |awk -F':' '{print $2}' |tr -d '"')
  if [ "${status}" = "fail" ]; then
    echo "The API Key that you provided is not valid!"
    exit 1
  elif [ "${status}" = "ok" ]; then
    :
  fi
}

# Grab data for all monitors
function get_data {
  curl -s -X POST https://api.uptimerobot.com/v2/getMonitors -d "api_key=${apiKey}" -d "format=json" > /tmp/ur_monitors_full.txt
}

# Create list of monitor IDs
function get_monitors {
  egrep -oi '"id":[!0-9]*' /tmp/ur_monitors_full.txt |tr -d '"id:' > /tmp/ur_monitors.txt
}

# Create individual monitor files
function create_monitor_files {
  for monitor in $(cat /tmp/ur_monitors.txt); do curl -s -X POST https://api.uptimerobot.com/v2/getMonitors -d "api_key=${apiKey}" -d "monitors=${monitor}" -d "format=json" > /tmp/"${monitor}".txt; done
}

# Create friendly output of all monitors
function create_friendly_list {
  > /tmp/friendly_list.txt
  for monitor in $(cat /tmp/ur_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"' /tmp/"${monitor}".txt > /tmp/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "${friendlyName} (ID: ${monitor})" >> /tmp/friendly_list.txt
  done
}

# Display friendly list of all monitors
function display_all_monitors {
  if [ -s /tmp/friendly_list.txt ]; then
    echo "The following UptimeRobot monitors were found in your UptimeRobot account:"
    cat /tmp/friendly_list.txt
  else
    echo "There are currently no monitors associated with your UptimeRobot account."
  fi
}

# Find all paused monitors
function get_paused_monitors {
  > /tmp/paused_monitors.txt
  for monitor in $(cat /tmp/ur_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/"${monitor}".txt > /tmp/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    status=$(grep status /tmp/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    if [ "${status}" = '0' ]; then
      echo "${friendlyName} (ID: ${monitor})" >> /tmp/paused_monitors.txt
    else
      :
    fi
  done
}

# Display list of all paused monitors
function display_paused_monitors {
  if [ -s /tmp/paused_monitors.txt ]; then
    echo "The following UptimeRobot monitors are currently paused:"
    cat /tmp/paused_monitors.txt
  else
    echo "There are currently no paused UptimeRobot monitors."
  fi
}

# Prompt user to unpause monitors after finding paused monitors
function unpause_prompt {
  read -p 'Would you like to unpause the paused monitors? ([y]es or [n]o): ' unpausePrompt
  if ! [[ "$unpausePrompt" =~ ^(yes|y|no|n)$  ]]; then
    echo "Please specify yes, y, no, or n."
  else
    :
  fi
}

# Pause all monitors
function pause_all_monitors {
  for monitor in $(cat /tmp/ur_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/"${monitor}".txt > /tmp/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Pausing ${friendlyName}:"
    curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" |jq
    echo ""
  done
}

# Pause specified monitors
function pause_specified_monitors {
  echo "${pauseType}" |tr , '\n' > /tmp/specified_monitors.txt
  for monitor in $(cat /tmp/specified_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/"${monitor}".txt > /tmp/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Pausing ${friendlyName}:"
    curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=0" |jq
    echo ""
  done
}

# Unpause all monitors
function unpause_all_monitors {
  for monitor in $(cat /tmp/ur_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/"${monitor}".txt > /tmp/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Unpausing ${friendlyName}:"
    curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
    echo ""
  done
}

# Unpause specified monitors
function unpause_specified_monitors {
  echo "${unpauseType}" |tr , '\n' > /tmp/specified_monitors.txt
  for monitor in $(cat /tmp/specified_monitors.txt); do
    egrep -oi '"id":[!0-9]*|"friendly_name":["^][^"]*"|"status":[!0-9]*' /tmp/"${monitor}".txt > /tmp/"${monitor}"_short.txt
    friendlyName=$(grep friend /tmp/"${monitor}"_short.txt |awk -F':' '{print $2}' |tr -d '"')
    echo "Unpausing ${friendlyName}:"
    curl -s -X POST https://api.uptimerobot.com/v2/editMonitor -d "api_key=${apiKey}" -d "id=${monitor}" -d "status=1" |jq
    echo ""
  done
}

# Send Discord notification
function send_notification {
  if [ "${webhookUrl}" = "" ]; then
    echo "You didn't define your Discord webhook, skipping notification."
  else
    if [ -s /tmp/paused_monitors.txt ]; then
      curl -s -H "Content-Type: application/json" -X POST -d '{"content": "There are currently paused UptimeRobot monitors."}' ${webhookUrl}
    elif [ "${notifyAll}" = "true" ]; then
      curl -s -H "Content-Type: application/json" -X POST -d '{"content": "All UptimeRobot monitors are currently running."}' ${webhookUrl}
    fi
  fi
}

# Run functions
check_api_key
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
  if [ -s /tmp/paused_monitors.txt ]; then
    if [ "${prompt}" = "false" ]; then
      :
    else
      unpause_prompt
        if [[ "$unpausePrompt" =~ ^(yes|y)$ ]]; then
          for monitor in $(cat /tmp/paused_monitors.txt |awk -F: '{print $2}' |tr -d ')' |tr -d ' '); do
            friendlyName=$(cat /tmp/paused_monitors.txt |awk '{print $1}')
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
    unpause_specified_monitors
  fi
fi
