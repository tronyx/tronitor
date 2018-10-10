#!/usr/bin/env bash
#
curl -X POST -H "Cache-Control: no-cache" -H "Content-Type: application/x-www-form-urlencoded" -d "api_key=${travisApiKey}&format=json&type=1&url=https://google.co.uk&friendly_name=TravisOne" "https://api.uptimerobot.com/v2/newMonitor"

curl -X POST -H "Cache-Control: no-cache" -H "Content-Type: application/x-www-form-urlencoded" -d "api_key=${travisApiKey}&format=json&type=1&url=https://amazon.co.uk&friendly_name=TravisTwo" "https://api.uptimerobot.com/v2/newMonitor" 
