#!/usr/bin/env bash
#
wget https://github.com/SimonKagstrom/kcov/archive/master.tar.gz &&
  tar xzf master.tar.gz &&
  cd kcov-master &&
  mkdir build &&
  cd build &&
  cmake .. &&
  make &&
  sudo make install &&
  cd ../.. &&
  rm -rf kcov-master &&
  mkdir -p coverage &&
  echo 'Running kcov for no monitors within account' &&
  kcov coverage Travis/travis_usmu.sh -l &&
  echo 'Creating Travis test monitors' &&
  kcov coverage Travis/ur_prep.sh &&
  echo 'Sleeping to allow tests to be checked' &&
  kcov coverage Travis/sleep.sh &&
  echo 'Running kcov for travis_usmu.sh' &&
  kcov coverage Travis/travis_usmu.sh &&
  echo 'Running kcov for travis_usmu.sh -h' &&
  kcov coverage Travis/travis_usmu.sh -h &&
  echo 'Running kcov for travis_usmu.sh --help' &&
  kcov coverage Travis/travis_usmu.sh --help &&
  echo 'Running kcov for no argument for option that requires one' &&
  kcov coverage Travis/travis_usmu.sh -c &&
  echo 'Running kcov for non-existent option' &&
  kcov coverage Travis/travis_usmu.sh -x &&
  echo 'Running kcov for travis_usmu.sh -n' &&
  kcov coverage Travis/travis_usmu.sh -n &&
  echo 'Running kcov for travis_usmu.sh --no-prompt' &&
  kcov coverage Travis/travis_usmu.sh --no-prompt &&
  echo 'Running kcov for travis_usmu.sh -c http' &&
  kcov coverage Travis/travis_usmu.sh -c http &&
  echo 'Running kcov for travis_usmu.sh --create ping' &&
  kcov coverage Travis/travis_usmu.sh --create ping &&
  echo 'Running kcov for travis_usmu.sh -c port' &&
  kcov coverage Travis/travis_usmu.sh -c port &&
  echo 'Running kcov for travis_usmu.sh --create keyword' &&
  kcov coverage Travis/travis_usmu.sh --create keyword &&
  echo 'Testing create with bad monitor type' &&
  kcov coverage Travis/travis_usmu.sh -c foobar &&
  echo 'Running kcov for travis_usmu.sh -a' &&
  kcov coverage Travis/travis_usmu.sh -a &&
  echo 'Running kcov for travis_usmu.sh --alerts' &&
  kcov coverage Travis/travis_usmu.sh --alerts &&
  echo 'Running kcov for travis_usmu.sh -s' &&
  kcov coverage Travis/travis_usmu.sh -s &&
  echo 'Running kcov for travis_usmu.sh --stats' &&
  kcov coverage Travis/travis_usmu.sh --stats &&
  echo 'Running kcov for travis_usmu.sh -i travisone' &&
  kcov coverage Travis/travis_usmu.sh -i travisone &&
  echo 'Running kcov for travis_usmu.sh --info travistwo' &&
  kcov coverage Travis/travis_usmu.sh --info travistwo &&
  echo 'Running kcov for info option with invalid monitor friendly name' &&
  kcov coverage Travis/travis_usmu.sh -i foobar &&
  echo 'Running kcov for info option with invalid monitor ID' &&
  kcov coverage Travis/travis_usmu.sh -i 123456789 &&
  echo 'Running kcov for info option with valid monitor ID' &&
  travisThreeId=$(
    curl -s -X POST getMonitors -d "api_key=${travisApiKey}" -d "format=json" > foo
    grep TravisThree foo | grep -Po '"id":[!0-9]*' foo | awk -F: '{print $2}'
  )
kcov coverage Travis/travis_usmu.sh -i "${travisThreeId}" &&
  echo 'Running kcov for travis_usmu.sh -n' &&
  kcov coverage Travis/travis_usmu.sh -n &&
  echo 'Running kcov for travis_usmu.sh -p all' &&
  kcov coverage Travis/travis_usmu.sh -p all &&
  echo 'Running kcov for travis_usmu.sh -w' &&
  kcov coverage Travis/travis_usmu.sh -w &&
  echo 'Running kcov for travis_usmu.sh --webhook' &&
  kcov coverage Travis/travis_usmu.sh --webhook &&
  echo 'Running kcov for travis_usmu.sh --pause GoogleKeyword' &&
  kcov coverage Travis/travis_usmu.sh --pause GoogleKeyword &&
  echo 'Running kcov for travis_usmu.sh -n' &&
  kcov coverage Travis/travis_usmu.sh -n &&
  echo 'Running kcov for travis_usmu.sh -r TravisOne' &&
  kcov coverage Travis/travis_usmu.sh -r TravisOne &&
  echo 'Running kcov for travis_usmu.sh --reset TravisTwo' &&
  kcov coverage Travis/travis_usmu.sh --reset TravisTwo &&
  echo 'Running kcov for travis_usmu.sh -u GooglePing' &&
  kcov coverage Travis/travis_usmu.sh -u GooglePing &&
  echo 'Running kcov for travis_usmu.sh --unpause all' &&
  kcov coverage Travis/travis_usmu.sh --unpause all &&
  echo 'Running kcov for travis_usmu.sh --list' &&
  kcov coverage Travis/travis_usmu.sh --list &&
  echo 'Running kcov for travis_usmu.sh -d TravisOne' &&
  kcov coverage Travis/travis_usmu.sh -d TravisOne &&
  echo 'Running kcov for travis_usmu.sh --delete TravisTwo' &&
  kcov coverage Travis/travis_usmu.sh --delete TravisTwo &&
  bash <(curl -s https://codecov.io/bash -s coverage/kcov-merged)
