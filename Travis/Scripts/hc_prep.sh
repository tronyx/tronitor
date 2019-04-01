#!/usr/bin/env bash

curl -s -X POST https://healthchecks.io/api/v1/checks/ -H "X-Api-Key: ${travisHCApiKey}" \
    --data '{"name": "TravisOne", "tags": "prod www", "timeout": 3600, "grace": 60}'

curl -s -X POST https://healthchecks.io/api/v1/checks/ -H "X-Api-Key: ${travisHCApiKey}" \
    --data '{"name": "TravisTwo", "tags": "prod www", "timeout": 3600, "grace": 60}'

curl -s -X POST https://healthchecks.io/api/v1/checks/ -H "X-Api-Key: ${travisHCApiKey}" \
    --data '{"name": "TravisThree", "tags": "prod www", "timeout": 3600, "grace": 60}'

curl -s -X POST https://healthchecks.io/api/v1/checks/ -H "X-Api-Key: ${travisHCApiKey}" \
    --data '{"name": "GooglePing", "tags": "prod www", "timeout": 3600, "grace": 60}'