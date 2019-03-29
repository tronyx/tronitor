#!/usr/bin/env bash

curl -s -H "Cache-Control: no-cache" -H "Content-Type: application/x-www-form-urlencoded" -H "API: ${travisSCApiKey}" -H "Username: ${travisSCUsername}" -d "WebsiteName=TravisOne&WebsiteURL=https://google.co.uk&CheckRate=300&TestType=HTTP" -X PUT https://app.statuscake.com/API/Tests/Update

curl -s -H "Cache-Control: no-cache" -H "Content-Type: application/x-www-form-urlencoded" -H "API: ${travisSCApiKey}" -H "Username: ${travisSCUsername}" -d "WebsiteName=TravisTwo&WebsiteURL=http://chrisyocumissuperawesome.com&CheckRate=300&TestType=HTTP" -X PUT https://app.statuscake.com/API/Tests/Update

curl -s -H "Cache-Control: no-cache" -H "Content-Type: application/x-www-form-urlencoded" -H "API: ${travisSCApiKey}" -H "Username: ${travisSCUsername}" -d "WebsiteName=TravisThree&WebsiteURL=https://ebay.com&CheckRate=300&TestType=HTTP" -X PUT https://app.statuscake.com/API/Tests/Update
