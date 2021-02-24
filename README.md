# Tronitor

[![CodeFactor](https://www.codefactor.io/repository/github/tronyx/tronitor/badge)](https://www.codefactor.io/repository/github/tronyx/tronitor) [![Travis (.org) branch](https://img.shields.io/travis/rust-lang/rust/master.svg?logo=travis)](https://travis-ci.org/tronyx/tronitor) [![made-with-bash](https://img.shields.io/badge/Made%20with-Bash-1f425f.svg)](https://www.gnu.org/software/bash/) [![GitHub](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/tronyx/tronitor/blob/develop/LICENSE.md) [![Average time to resolve an issue](http://isitmaintained.com/badge/resolution/tronyx/tronitor.svg)](http://isitmaintained.com/project/tronyx/tronitor "Average time to resolve an issue") [![Percentage of issues still open](http://isitmaintained.com/badge/open/tronyx/tronitor.svg)](http://isitmaintained.com/project/tronyx/tronitor "Percentage of issues still open")

A bash script to work with [UptimeRobot](https://uptimerobot.com), [StatusCake](https://www.statuscake.com), [HealthChecks.io](https://healthchecks.io), and [Upptime](https://upptime.js.org/) monitors via their respective APIs. It checks to make sure that the API key/token, username for StatusCake, and your GitHub username and the name of your Upptime repository on GitHub, that you provided are valid before performing any requested operations.

## Contributors

[![GitHub contributors](https://img.shields.io/github/contributors/tronyx/tronitor.svg)](https://github.com/tronyx/tronitor/graphs/contributors/)

Big thanks to [nemchik](https://github.com/GhostWriters/DockSTARTer/commits?author=nemchik) for all the ideas and help with getting some things to work, and to [1activegeek](https://github.com/1activegeek) for asking me to create this for him in the first place, albeit MUCH less complicated than what it's become.

Feel free to check out their work and buy them a beer too!

## Application Healthchecks

This script partners up with my [Application Healthchecks](https://github.com/tronyx/HealthChecks-Linux) script that provides checks for a lot of popular HTPC applications, IE: Plex, Sonarr, Radarr, etc. that work with HealthChecks.io. Tronitor would allow you to pause and unpause the checks manually or on a schedule, via a cronjob, for planned maintenance, etc. This essentially allows you to create your own maintenance windows without having to pay for a premium account with either of the providers.

## Package Requirements/Recommendations

### cURL

The `cURL` command is required for the script to function as it's used to submit API calls to the providers. If it is not installed before you execute the script most, if not all, operations will fail. Because of this, the script does check whether or not `cURL` is installed and, if not, it will inform you as such and then exit.

### JQ

It is recommended that you also install the `JQ` package as the script uses it to automatically format the JSON output into a human-readable and colorized output. There is a variable at the beginning of the script to set the use of the `JQ` command to true or false. I've personally encountered some issues with it when using the script within a cronjob and not using `JQ` to format the output resolves them. It is set to `true` by default.

```bash
# Set JQ to false to disable the use of the JQ command.
# This works better for using the script with cronjobs, etc.
jq='true'
```

#### Installing JQ on Ubuntu Server 18.04:

```bash
tronyx@suladan:~$ sudo apt install jq
Reading package lists... Done
Building dependency tree
Reading state information... Done
The following NEW packages will be installed:
  jq
0 upgraded, 1 newly installed, 0 to remove and 7 not upgraded.
Need to get 45.6 kB of archives.
After this operation, 90.1 kB of additional disk space will be used.
Get:1 http://archive.ubuntu.com/ubuntu bionic/universe amd64 jq amd64 1.5+dfsg-2 [45.6 kB]
Fetched 45.6 kB in 0s (123 kB/s)
Selecting previously unselected package jq.
(Reading database ... 107503 files and directories currently installed.)
Preparing to unpack .../jq_1.5+dfsg-2_amd64.deb ...
Unpacking jq (1.5+dfsg-2) ...
Setting up jq (1.5+dfsg-2) ...
Processing triggers for man-db (2.8.3-2) ...
```

#### Sample output using JQ:

![JQ True](/Images/jq_sample.png)

#### Sample output without JQ:

![JQ False](/Images/no_jq_sample.png)

## Setting it up

The best method to get the script working is to use `git` to clone the repository onto your preferred machine:

```bash
tronyx@suladan:~$ git clone https://github.com/tronyx/tronitor.git
Cloning into 'tronitor'...
remote: Enumerating objects: 108, done.
remote: Counting objects: 100% (108/108), done.
remote: Compressing objects: 100% (75/75), done.
remote: Total 262 (delta 60), reused 76 (delta 32), pack-reused 154
Receiving objects: 100% (262/262), 161.85 KiB | 6.74 MiB/s, done.
Resolving deltas: 100% (143/143), done.
```

:warning: **NOTE:** You CAN get away with just grabbing a copy of the `tronitor.sh` script itself, but the monitor creation functionality will not work as it depends on the included template files in the repository.

The script stores the API keys/token, username for StatusCake, and, for Upptime, your GitHub username, PAT (Personal Access Token), and the name of your Upptime reposistory, for up to all four providers so that you do not need multiple copies of the script to work with each of the different providers.

If you do not know how to create a PAT for your GitHub account, you can checkout their documentation on it [HERE](https://docs.github.com/en/free-pro-team@latest/github/authenticating-to-github/creating-a-personal-access-token).

The first time that you run the script for a specific monitor it will alert you that the API key/token, etc. are missing and prompt you to input them:

### UptimeRobot
![UptimeRobot User Data Prompt](/Images/ur_user_data.png)

### StatusCake
![StatusCake User Data Prompt](/Images/sc_user_data.png)

### Healthchecks.io
![Healthchecks User Data Prompt](/Images/hc_user_data.png)

:warning: **NOTE:** If you are running your own, self-hosted version of the Healthchecks.io application, you will need to modify the `healthchecksDomain` variable on `line 24` of the  `tronitor.sh` script with the domain name that you're hosting the application with.

### Upptime
![Upptime/GitHub User Data Prompt](/Images/up_user_data.png)

You can also simply open the script with your favorite text editor and add your provider's API key, if you're using StatusCake, your account username, and, if you're using Upptime, the repository owner (organization or user), your GitHub username, PAT (Personal Access Token), and the name of your Upptime reposistory.

After entering the information, the script will check whether or not it is valid and then add it to the script for you.

If you use the alert option, be sure to also enter in your Discord/Slack webhook URL. If you forget this as well, the script will also prompt you to enter it:

![Webhook URL Prompt](/Images/webhook_url.png)

## Usage

![Script Usage](/Images/usage.png)

The `-m/--monitor` option accepts both full and shorthand versions of the provider's name:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m uptimerobot -l
tronyx@suladan:~/tronitor$ ./tronitor.sh -m ur -l
tronyx@suladan:~/tronitor$ ./tronitor.sh -m statuscake -l
tronyx@suladan:~/tronitor$ ./tronitor.sh -m sc -l
tronyx@suladan:~/tronitor$ ./tronitor.sh -m healthchecks -l
tronyx@suladan:~/tronitor$ ./tronitor.sh -m hc -l
tronyx@suladan:~/tronitor$ ./tronitor.sh -m upptime -l
tronyx@suladan:~/tronitor$ ./tronitor.sh -m up -l
```

## Examples
### Get account statistics

Display basic statistics for your account:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m uptimerobot -s
Here are the basic statistics for your UptimeRobot account:

{
 "stat": "ok",
 "account": {
   "email": "me@domain.com",
   "monitor_limit": 50,
   "monitor_interval": 5,
   "up_monitors": 14,
   "down_monitors": 0,
   "paused_monitors": 0
 }
}
```

### List all monitors

Display all monitors associated with your account and their current statuses:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh --monitor ur -l
The following UptimeRobot monitors were found in your UptimeRobot account:

Plex (ID: 779783111) - Status: Up
Radarr (ID: 780859973) - Status: Down
Sonarr (ID: 780859962) - Status: Paused
Tautulli (ID: 780859975) - Status: Seems down
```

### Find currently paused monitors

Find and display all monitors in your account that are currently paused and then prompt you as to whether or not you would like to unpause them:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m ur -f
The following StatusCake monitors are currently paused:

Plex (ID: 779783111)
Radarr (ID: 780859973)
Sonarr (ID: 780859962)
Tautulli (ID: 780859975)

Would you like to unpause the paused monitors? ([Y]es or [N]o):
```

You can also use the `-n` option to display the same list, but not display a prompt to unpause the paused monitors.

### Discord alert for paused monitors

Using the `-w` option will check for any paused monitors and, if there are any, send an alert to the specified Discord/Slack webhook like below:

![Discord/Slack Notification](/Images/webhook_paused.png)

If you set the `notifyAll` option to `true`, Tronitor will send a notification even if there are no paused monitors:

![Discord/Slack Notification](/Images/webhook_notifyAll.png)

### Info

Display all information for a single monitor:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m uptimerobot -i 'plex'
{
  "stat": "ok",
  "pagination": {
    "offset": 0,
    "limit": 50,
    "total": 1
  },
  "monitors": [
    {
      "id": 779783111,
      "friendly_name": "Plex",
      "url": "https://plex.tv",
      "type": 1,
      "sub_type": "",
      "keyword_type": null,
      "keyword_value": "",
      "http_username": "",
      "http_password": "",
      "port": "",
      "interval": 300,
      "status": 2,
      "create_datetime": 1513815865
    }
  ]
}
```

### Get alert contacts

Displays a list of all of the alert contacts configured for the account:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m ur -a
The following alert contacts have been found for your UptimeRobot account:

{
  "stat": "ok",
  "offset": 0,
  "limit": 50,
  "total": 2,
  "alert_contacts": [
    {
      "id": "0526944",
      "friendly_name": "E-Mail",
      "type": 2,
      "status": 2,
      "value": "me@domain.com"
    },
    {
      "id": "2611518",
      "friendly_name": "Discord",
      "type": 11,
      "status": 2,
      "value": "https://discordapp.com/api/webhooks/123456789/qwerty-qwerty-qwerty/slack"
    }
  ]
}
```

This can be helpful when creating a new monitor as you can use the `id` field of the alert contact to specify the alert contact that you want to be notified when an event occurs with the new monitor that you're creating.

### Pause all monitors

Pause all monitors in your account:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m uptimerobot -p all
Pausing Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 779783111
  }
}

Pausing Radarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859973
  }
}

Pausing Sonarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859962
  }
}

Pausing Tautulli:
{
  "stat": "ok",
  "monitor": {
    "id": 780859975
  }
}
```

:warning: **NOTE:** Healthchecks.io works with cronjobs so, unless you disable your cronjobs for the HC.io monitors, or work with the created lock file, all paused monitors will become active again the next time they receive a ping. Tronitor creates a lock file, `/tmp/tronitor/healthchecks.lock`, so that you can modify your existing HC.io script to check for the lock file and not send pings if it is present.


### Pause specific monitors

Pause specific monitors in your account:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh --monitor ur -p 'Plex',780859973
Pausing Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 779783111
  }
}

Pausing Radarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859973
  }
}
```

:warning: **NOTE:** Healthchecks.io works with cronjobs so, unless you disable your cronjobs for the HC.io monitors, or work with the created lock file, all paused monitors will become active again the next time they receive a ping. Tronitor creates a lock file, `/tmp/tronitor/MONITOR-UUID.lock`, so that you can modify your existing HC.io script to check for the lock file and not send pings if it is present.

### Unpause all currently paused monitors

Unpause all monitors in your account:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m ur -u all
Unpausing Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 779783111
  }
}

Unpausing Radarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859973
  }
}

Unpausing Sonarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859962
  }
}

Unpausing Tautulli:
{
  "stat": "ok",
  "monitor": {
    "id": 780859975
  }
}
```

### Unpause specific monitors

Unpause specific monitors that are currently paused in your account:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m ur -u 'Plex',780859973
Unpausing Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 779783111
  }
}

Unpausing Radarr:
{
  "stat": "ok",
  "monitor": {
    "id": 780859973
  }
}
```

### Create a new monitor

Monitors can be created using this option.

:warning: **NOTE:** StatusCake's API is dumb and WILL let you create more tests than you're supposed to have with the limit for your account and it can cause some very odd behavior with the monitors.

Modify the settings of the corresponding monitor type template file in the corresponding `Templates` directory for your provider, IE: creating a new HTTP(s) monitor for UptimeRobot would require you to modify the `Templates/UptimeRobot/new-http-monitor.json` file. The full API documentation for the two providers can be found [HERE (UR)](https://uptimerobot.com/api), [HERE (SC)](https://www.statuscake.com/api/index.md), and [HERE (HC)](https://healthchecks.io/docs/api/) for information on monitor types and any required values and what they're for.

The following example is for creating a new HTTP(s) monitor for Google:

```json
tronyx@suladan:~/tronitor$ cat Templates/UptimeRobot/new-http-monitor.json
{
      "api_key": "",
      "friendly_name": "Google",
      "url": "https://google.com",
      "type": 1,
      "http_username": "",
      "http_password": "",
      "interval": 300,
      "alert_contacts": "",
      "ignore_ssl_errors": "false",
      "format": "json"
}
```

The `api_key` field is filled in automatically by the script, but you can still add it yourself if you'd like to. The `alert_contacts` field can be filled in with the `id` field from your preferred alert contact which you can retrieve using the `-a/--alerts` option with the script.

Then just execute the script to create the monitor:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh --monitor uptimerobot -c http
{
  "stat": "ok",
  "monitor": {
    "id": 781067574,
    "status": 1
  }
}
```

### Resetting monitors

Reset (deleting all stats and response time data) all or specific monitors in your account:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m ur -r google

***WARNING*** This will reset ALL data for the specified monitors!!!
Are you sure you wish to continue? ([Y]es or [N]o):
y

Resetting Google:
{
  "stat": "ok",
  "monitor": {
    "id": 781067574
  }
}
```

### Deleting monitors

Delete all, or a specific, monitor from your account:

```json
tronyx@suladan:~/tronitor$ ./tronitor.sh -m ur -d plex

***WARNING*** This will delete the specified monitor from your account!!!
Are you sure you wish to continue? ([Y]es or [N]o):
y

Deleting Plex:
{
  "stat": "ok",
  "monitor": {
    "id": 781067560
  }
}
```
