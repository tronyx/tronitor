#!/usr/bin/env bash
#

curl -s -X POST "${apiUrl}"newMonitor -d @travisone.json --header "Content-Type: application/json"
curl -s -X POST "${apiUrl}"newMonitor -d @travistwo.json --header "Content-Type: application/json"
