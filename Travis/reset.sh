#!/usr/bin/env bash
#
sed -i "10 s/providerName='[^']*'/providerName=''/" Travis/travis_usmu.sh
sed -i "14 s/apiKey='[^']*'/apiKey=''/" Travis/travis_usmu.sh
