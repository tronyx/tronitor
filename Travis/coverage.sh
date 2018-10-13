#!/usr/bin/env bash
#
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
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -l &&
echo 'Creating Travis test monitors' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/prep.sh &&
echo 'Sleeping to allow tests to be checked' &&
kcov coverage Travis/sleep.sh &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -h' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -h &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --help' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --help &&
echo 'Running kcov for no argument for option that requires one' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -c &&
echo 'Running kcov for non-existent option' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -x &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -n' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -n &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --no-prompt' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --no-prompt &&
#echo 'Running kcov for empty short webhook' &&
#kcov coverage Travis/expect_wrapper.sh Travis/webhook_empty_expect_short.exp &&
#echo 'Running kcov for empty long webhook' &&
#kcov coverage Travis/expect_wrapper.sh Travis/webhook_empty_expect_long.exp &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -c http' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -c http &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --create ping' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --create ping &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -c port' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -c port &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --create keyword' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --create keyword &&
echo 'Testing create with bad monitor type' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -c foobar &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -a' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -a &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --alerts' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --alerts &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -s' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -s &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --stats' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --stats &&
#echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -d all' &&
#kcov coverage Travis/expect_wrapper.sh Travis/delete_expect_short.exp &&
#echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --delete all' &&
#kcov coverage Travis/expect_wrapper.sh Travis/delete_expect_long.exp &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -i travisone' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -i travisone &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --info travistwo' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --info travistwo &&
echo 'Running kcov for info option with invalid monitor' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -i foobar &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -n' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -n &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -p all' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -p all &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --pause GoogleKeyword' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --pause GoogleKeyword &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -n' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -n &&
#echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -f' &&
#kcov coverage Travis/expect_wrapper.sh Travis/travis_uptimerobot_monitor_utility.sh -f &&
#echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --find' &&
#kcov coverage Travis/expect_wrapper.sh Travis/travis_uptimerobot_monitor_utility.sh --find &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -u GooglePing' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -u GooglePing &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --unpause all' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --unpause all &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --list' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --list &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -d TravisOne' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh -d TravisOne &&
echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --delete TravisTwo' &&
kcov --exclude-line=14,21,32,87,89,95,96,117,118,141,142,145,146,252,285,287,354,355,360,391,399,401,412,420,449,459,638,657 --exclude-region=125:127,186:190,210:226,268:271,309:311,320:327,333:344,370:375464:471,526:617,641:650,686:696,699:709 coverage Travis/travis_uptimerobot_monitor_utility.sh --delete TravisTwo &&
#echo 'Running kcov for travis_uptimerobot_monitor_utility.sh -r all' &&
#kcov coverage Travis/expect_wrapper.sh Travis/reset_expect_short.exp &&
#echo 'Running kcov for travis_uptimerobot_monitor_utility.sh --reset all' &&
#kcov coverage Travis/expect_wrapper.sh Travis/reset_expect_long.exp &&
bash <(curl -s https://codecov.io/bash)
