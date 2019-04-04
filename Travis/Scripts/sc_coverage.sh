#!/usr/bin/env bash
#
#echo 'Running kcov expect for missing API key' &&
#expect Travis/Scripts/Expects/kcov_sc_api_key_expect.exp &&
echo 'Running kcov for bad StatusCake option' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -s &&
echo 'Running kcov for no monitors within account' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -l &&
echo 'Creating Travis test monitors' &&
kcov coverage Travis/Scripts/sc_prep.sh &&
echo 'Sleeping to allow tests to be checked' &&
kcov coverage Travis/Scripts/sleep.sh &&
echo 'Running kcov for travis_tronitor.sh' &&
kcov coverage Travis/Scripts/travis_tronitor.sh &&
echo 'Running kcov for travis_tronitor.sh -h' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -h &&
echo 'Running kcov for travis_tronitor.sh --help' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --help &&
echo 'Running kcov for no argument for option that requires one' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -c &&
echo 'Running kcov for non-existent option' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -x &&
echo 'Running kcov for unavailable reset option' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -r &&
echo 'Running kcov for unavailable reset option' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --reset &&
echo 'Running kcov for travis_tronitor.sh -n' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -n &&
echo 'Running kcov for travis_tronitor.sh --no-prompt' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --no-prompt &&
echo 'Running kcov for travis_tronitor.sh -c http' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -c http &&
echo 'Running kcov for travis_tronitor.sh --create ping' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --create ping &&
echo 'Running kcov for travis_tronitor.sh -c port' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -c port &&
echo 'Testing create with bad monitor type' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -c foobar &&
echo 'Running kcov for travis_tronitor.sh -a' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -a &&
echo 'Running kcov for travis_tronitor.sh --alerts' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --alerts &&
echo 'Running kcov for travis_tronitor.sh -i travisone' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -i travisone &&
echo 'Running kcov for travis_tronitor.sh --info travistwo' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --info travistwo &&
echo 'Running kcov for info option with invalid monitor friendly name' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -i foobar &&
echo 'Running kcov for info option with invalid monitor ID' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -i 123456789 &&
echo 'Running kcov for info option with valid monitor ID' &&
travisThreeId=$(
    curl -s -H "API: ${travisSCApiKeyapiKey}" -H "Username: ${travisSCUsername}" -X GET https://app.statuscake.com/API/Tests/ > foo
    grep TravisThree foo | grep -Po '"TestID":[!0-9]*' foo | awk -F: '{print $2}'
)
kcov coverage Travis/Scripts/travis_tronitor.sh -i "${travisThreeId}" &&
echo 'Running kcov for travis_tronitor.sh -n' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -n &&
echo 'Running kcov for travis_tronitor.sh -p all' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -p all &&
echo 'Running kcov for travis_tronitor.sh --find' &&
expect Travis/Scripts/Expects/kcov_find_expect_long.exp &&
echo 'Running kcov for travis_tronitor.sh -f' &&
expect Travis/Scripts/Expects/kcov_find_expect_long.exp &&
echo 'Running kcov for travis_tronitor.sh -w' &&
#expect Travis/Scripts/Expects/kcov_webhook_empty_expect_short.exp &&
kcov coverage Travis/Scripts/travis_tronitor.sh -w &&
echo 'Running kcov for travis_tronitor.sh --webhook' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --webhook &&
echo 'Running kcov for travis_tronitor.sh --pause travisthree' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --pause travisthree &&
echo 'Running kcov for travis_tronitor.sh -n' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -n &&
echo 'Running kcov for travis_tronitor.sh -u travisone' &&
kcov coverage Travis/Scripts/travis_tronitor.sh -u travisone &&
echo 'Running kcov for travis_tronitor.sh --unpause all' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --unpause all &&
#echo 'Running kcov expect for pause invalid test' &&
#expect Travis/Scripts/Expects/kcov_pause_invalid_expect.exp &&
echo 'Running kcov for travis_tronitor.sh --list' &&
kcov coverage Travis/Scripts/travis_tronitor.sh --list &&
echo 'Running kcov for travis_tronitor.sh -d TravisOne' &&
#kcov coverage Travis/Scripts/travis_tronitor.sh -d TravisOne &&
#expect Travis/Scripts/Expects/kcov_delete_expect_short.exp &&
echo 'Running kcov for travis_tronitor.sh --delete TravisTwo' &&
#kcov coverage Travis/Scripts/travis_tronitor.sh --delete TravisTwo &&
#expect Travis/Scripts/Expects/kcov_delete_expect_long.exp &&
bash <(curl -s https://codecov.io/bash -s coverage/kcov-merged)
