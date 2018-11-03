#!/usr/bin/env bash
#
sed -i "10 s/providerName='[^']*'/providerName=''/" Travis/travis_usmu.sh
sed -i "14 s/apiKey='[^']*'/apiKey=''/" Travis/travis_usmu.sh
sed -i "16 s|webhookUrl='[^']*'|webhookUrl=''|" Travis/travis_usmu.sh
sed -i "46 s/apiKeyStatus='[^']*'/apiKeyStatus='invalid'/" Travis/travis_usmu.sh
sed -i "48 s/providerStatus='[^']*'/providerStatus='invalid'/" Travis/travis_usmu.sh
