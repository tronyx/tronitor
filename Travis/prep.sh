#!/usr/bin/env bash
#
apiUrl='https://api.uptimerobot.com/v2/'
curl -s -X POST "${apiUrl}"newMonitor -d @travisone.json --header "Content-Type: application/json"
curl -s -X POST "${apiUrl}"newMonitor -d @travistwo.json --header "Content-Type: application/json"
